from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from app.schemas.query_evaluation import (
    QueryEvaluationCommandResponse,
    QueryEvaluationJobListResponse,
    QueryEvaluationLabelSaveRequest,
    QueryEvaluationRowsResponse,
    QueryEvaluationRunRequest,
    QueryEvaluationSummaryRequest,
)

AI_SERVER_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = AI_SERVER_ROOT / "script" / "evaluate_query_payload_and_rules.py"
DEFAULT_CASES_PATH = AI_SERVER_ROOT / "script" / "evaluation" / "query_payload_eval_cases.example.jsonl"
DEFAULT_OUT_DIR = Path(os.getenv("QUERY_EVAL_OUTPUT_DIR", "/app/evaluation/query-payload-rules"))
QUERY_EVAL_DIRECT_RUN_DISABLED = os.getenv("QUERY_EVAL_DIRECT_RUN_DISABLED", "false").strip().lower() == "true"
QUERY_EVAL_COMMAND_TIMEOUT_SECONDS = int(os.getenv("QUERY_EVAL_COMMAND_TIMEOUT_SECONDS", "7200"))
QUERY_EVAL_CLOVA_TIMEOUT_SECONDS = float(os.getenv("EVAL_CLOVA_TIMEOUT_SECONDS", "8.0"))

# 수정 포인트: Docker 이미지의 .dockerignore에서 jsonl 파일이 제외된 환경에서도
# 관리자 화면에서 질의를 비워 실행하면 기본 평가 케이스를 생성해 사용할 수 있게 합니다.
# 운영 추천 로직과 분리된 평가 전용 기본 질의이며, 사용자가 화면에서 질의를 입력하면 이 값은 사용하지 않습니다.
DEFAULT_EVALUATION_CASES: List[Dict[str, Any]] = [
    {
        "id": "Q001",
        "category": "audiobook_context",
        "query": "운전하면서 듣기 좋은 책 추천해줘",
        "expected": {
            "consumption_context": "driving",
            "audio_evidence_required": True,
            "topic_context_should_be_separated": True,
        },
    },
    {
        "id": "Q002",
        "category": "count_constraint",
        "query": "재밌는 책 한 권만 추천해줘",
        "expected": {
            "recommendation_count": 1,
            "count_should_not_be_in_retrieval_query": True,
        },
    },
    {
        "id": "Q003",
        "category": "child_audience",
        "query": "초등학생 아이가 읽기 좋은 책 추천해줘",
        "expected": {
            "target_reader": "child",
            "adult_guardrail_required": True,
        },
    },
    {
        "id": "Q004",
        "category": "light_reading",
        "query": "무겁지 않고 가볍게 읽을 수 있는 소설 추천해줘",
        "expected": {
            "tone": "light",
            "genre": "novel",
        },
    },
    {
        "id": "Q005",
        "category": "commute_context",
        "query": "출퇴근길에 읽기 좋은 책 추천해줘",
        "expected": {
            "consumption_context": "commute",
            "topic_context_should_be_separated": True,
        },
    },
]


class QueryPayloadRuleEvaluationService:
    def run(self, request: QueryEvaluationRunRequest) -> QueryEvaluationCommandResponse:
        out_dir = self._resolve_out_dir(request.out_dir, create_job_if_blank=True)
        out_dir.mkdir(parents=True, exist_ok=True)
        job_id = self._job_id_from_out_dir(out_dir)
        if QUERY_EVAL_DIRECT_RUN_DISABLED:
            # 수정 포인트: NAS ai-server pod에서 무거운 평가가 직접 실행되는 사고를 막고 local runner 사용을 강제할 수 있습니다.
            return QueryEvaluationCommandResponse(
                status="FAILED",
                exit_code=1,
                out_dir=str(out_dir),
                label_csv_path=str(out_dir / "candidate_label_template.csv"),
                auto_summary_path=str(out_dir / "auto_summary.csv"),
                labeled_summary_path=str(out_dir / "labeled_summary.csv"),
                raw_results_path=str(out_dir / "raw_results.jsonl"),
                stdout_tail="",
                stderr_tail="QUERY_EVAL_DIRECT_RUN_DISABLED=true",
                message="ai-server pod 직접 평가는 비활성화되어 있습니다. backend를 local runner 모드로 설정해주세요.",
                job_id=job_id,
                log_path=None,
            )
        cases_path = self._resolve_cases_path(request, out_dir)

        command = [
            sys.executable,
            str(SCRIPT_PATH),
            "run",
            "--cases",
            str(cases_path),
            "--out-dir",
            str(out_dir),
            "--embedding-model",
            request.embedding_model.upper(),
            "--top-k",
            str(request.top_k),
            "--max-corpus-docs",
            str(request.max_corpus_docs),
            "--query-variants",
            self._join(request.query_variants),
            "--retrieval-variants",
            self._join(request.retrieval_variants),
            "--rule-variants",
            self._join(request.rule_variants),
            "--llm-timeout-seconds",
            str(QUERY_EVAL_CLOVA_TIMEOUT_SECONDS),
        ]
        self._write_run_metadata(
            out_dir,
            {
                "job_id": job_id,
                "status": "RUNNING",
                "created_at": self._now(),
                "started_at": self._now(),
                "out_dir": str(out_dir),
                "output_dir": str(out_dir),
                "request": request.model_dump(mode="json") if hasattr(request, "model_dump") else dict(request),
            },
        )
        result = self._run_command(command)
        response = self._response_from_result(result, out_dir, "evaluation run")
        self._write_run_metadata(
            out_dir,
            {
                "job_id": job_id,
                "status": "COMPLETED" if response.status == "SUCCEEDED" else "FAILED",
                "created_at": self._read_existing_metadata(out_dir).get("created_at") or self._now(),
                "started_at": self._read_existing_metadata(out_dir).get("started_at") or self._now(),
                "finished_at": self._now(),
                "out_dir": str(out_dir),
                "output_dir": str(out_dir),
                "exit_code": result.returncode,
                "message": response.message,
            },
        )
        return response

    def summarize(self, request: QueryEvaluationSummaryRequest) -> QueryEvaluationCommandResponse:
        out_dir = self._resolve_out_dir(request.out_dir)
        labels = out_dir / "candidate_label_template.csv"
        if not labels.exists():
            return self._missing_file_response(out_dir, labels, "label CSV가 없습니다. 먼저 평가 실행을 완료해주세요.")
        command = [
            sys.executable,
            str(SCRIPT_PATH),
            "summarize",
            "--labels",
            str(labels),
            "--out-dir",
            str(out_dir),
            "--top-k",
            str(request.top_k),
        ]
        result = self._run_command(command)
        response = self._response_from_result(result, out_dir, "label summarize")
        if response.status == "SUCCEEDED":
            self._write_final_score(out_dir, request.top_k)
        return response

    def list_jobs(self, limit: int = 50) -> QueryEvaluationJobListResponse:
        jobs_dir = DEFAULT_OUT_DIR / "jobs"
        jobs: List[QueryEvaluationCommandResponse] = []
        if jobs_dir.exists():
            for item in jobs_dir.iterdir():
                if not item.is_dir():
                    continue
                metadata = self._read_existing_metadata(item)
                jobs.append(self._response_from_metadata(item, metadata))
        jobs.sort(key=lambda job: str(self._read_existing_metadata(Path(job.out_dir)).get("created_at") or ""), reverse=True)
        return QueryEvaluationJobListResponse(jobs=jobs[: max(1, min(200, limit))])

    def read_labels(self, out_dir: str | None, offset: int, limit: int) -> QueryEvaluationRowsResponse:
        resolved_out_dir = self._resolve_out_dir(out_dir)
        return self._read_csv(resolved_out_dir, "candidate_label_template.csv", offset, limit)

    def read_summary(self, out_dir: str | None, summary_type: str, offset: int, limit: int) -> QueryEvaluationRowsResponse:
        resolved_out_dir = self._resolve_out_dir(out_dir)
        normalized_type = (summary_type or "labeled").strip().lower()
        if normalized_type in {"dimension", "aggregate", "score"}:
            file_name = "dimension_summary.csv"
        else:
            file_name = "labeled_summary.csv" if normalized_type == "labeled" else "auto_summary.csv"
        return self._read_csv(resolved_out_dir, file_name, offset, limit)

    def save_labels(self, request: QueryEvaluationLabelSaveRequest) -> QueryEvaluationCommandResponse:
        out_dir = self._resolve_out_dir(request.out_dir)
        path = out_dir / "candidate_label_template.csv"
        if not path.exists():
            return self._missing_file_response(out_dir, path, "저장할 label CSV가 없습니다. 먼저 평가 실행을 완료해주세요.")

        rows, fieldnames = self._load_csv(path)
        update_map = {item.row_key: item for item in request.rows if item.row_key}
        changed = 0
        for row in rows:
            update = update_map.get(self._row_key(row))
            if not update:
                continue
            if update.human_relevance_0_2 is not None:
                value = str(update.human_relevance_0_2).strip()
                # 수정 포인트: 관리자 화면 저장 시 정성평가 점수는 반드시 0/1/2만 허용합니다.
                # 빈 값까지 허용하면 labeled summary가 왜곡되므로 서버에서도 한 번 더 방어합니다.
                if value not in {"0", "1", "2"}:
                    raise ValueError("human_relevance_0_2는 0, 1, 2 중 하나여야 합니다.")
                row["human_relevance_0_2"] = value
            if update.human_memo is not None:
                row["human_memo"] = str(update.human_memo)
            changed += 1
        self._write_csv(path, rows, fieldnames)
        self._write_qualitative_labels(out_dir, rows)

        # 수정 포인트: 관리자 화면 저장 버튼이 곧바로 labeled_summary/final_score를 갱신하도록 summarize 명령을 재실행합니다.
        response = self.summarize(QueryEvaluationSummaryRequest(out_dir=str(out_dir), top_k=request.top_k))
        response.message = f"{changed}개 label row 저장 후 요약을 갱신했습니다."
        return response

    def _resolve_cases_path(self, request: QueryEvaluationRunRequest, out_dir: Path) -> Path:
        """Return the evaluation case file to use for this run.

        수정 포인트: 관리자 화면에서 질의를 입력하면 job별 폴더 안에 임시 JSONL 파일을 생성해 그 파일로 평가합니다.
        입력이 비어 있으면 기존 기본 평가 파일을 그대로 사용하므로, 화면 입력 없이도 기존 baseline 평가가 가능합니다.
        """
        manual_cases = (request.cases_jsonl or "").strip()
        if not manual_cases:
            # 수정 포인트: 기본 JSONL 파일이 Docker 이미지에 포함되지 않은 경우에도
            # /app/script/evaluation/*.jsonl FileNotFoundError가 나지 않도록 out_dir 아래에 기본 케이스를 생성합니다.
            if request.cases_path and str(request.cases_path).strip():
                return self._resolve_file(request.cases_path, DEFAULT_CASES_PATH)
            return self._resolve_default_cases_path(out_dir)

        manual_path = out_dir / "manual_eval_cases.jsonl"
        rows = self._normalize_manual_cases(manual_cases)
        with manual_path.open("w", encoding="utf-8") as out:
            for row in rows:
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
        return manual_path

    def _resolve_default_cases_path(self, out_dir: Path) -> Path:
        if DEFAULT_CASES_PATH.exists():
            return DEFAULT_CASES_PATH
        generated_path = out_dir / "default_eval_cases.generated.jsonl"
        self._write_jsonl(generated_path, DEFAULT_EVALUATION_CASES)
        return generated_path

    @staticmethod
    def _write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as out:
            for row in rows:
                out.write(json.dumps(row, ensure_ascii=False) + "\n")

    @staticmethod
    def _normalize_manual_cases(value: str) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for index, raw_line in enumerate(value.splitlines(), start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("{"):
                data = json.loads(line)
                query = str(data.get("query") or "").strip()
                if not query:
                    raise ValueError("수동 평가 JSONL row에는 query가 필요합니다.")
                data.setdefault("id", f"MANUAL{index:03d}")
                data.setdefault("category", "manual")
                rows.append(data)
                continue
            # 일반 텍스트 한 줄을 평가 질의 하나로 취급합니다. 운영 로직이 아니라 관리자 평가 입력 전용 변환입니다.
            rows.append({"id": f"MANUAL{index:03d}", "category": "manual", "query": line})
        if not rows:
            raise ValueError("평가 질의 입력이 비어 있습니다.")
        return rows

    def _run_command(self, command: List[str]) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PYTHONPATH"] = f"{AI_SERVER_ROOT}{os.pathsep}{env.get('PYTHONPATH', '')}".rstrip(os.pathsep)
        # 수정 포인트: Qdrant NodePort/http 경고는 평가 실패가 아니므로 subprocess stderr에 쌓이지 않게 합니다.
        env["PYTHONWARNINGS"] = self._merge_python_warning_filter(
            env.get("PYTHONWARNINGS"),
            "ignore:Api key is used with an insecure connection.:UserWarning",
        )
        try:
            return subprocess.run(
                command,
                cwd=str(AI_SERVER_ROOT),
                env=env,
                text=True,
                capture_output=True,
                check=False,
                timeout=QUERY_EVAL_COMMAND_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            # 수정 포인트: 평가 subprocess가 멈춘 것처럼 보이는 상황을 FAILED 응답으로 명확히 반환합니다.
            return subprocess.CompletedProcess(
                command,
                returncode=124,
                stdout=exc.stdout or "",
                stderr=f"query evaluation timed out after {QUERY_EVAL_COMMAND_TIMEOUT_SECONDS}s",
            )

    def _read_csv(self, out_dir: Path, file_name: str, offset: int, limit: int) -> QueryEvaluationRowsResponse:
        path = out_dir / file_name
        if not path.exists():
            return QueryEvaluationRowsResponse(
                out_dir=str(out_dir),
                file_name=file_name,
                columns=[],
                rows=[],
                total_rows=0,
                offset=max(0, offset),
                limit=max(1, limit),
            )
        rows, fieldnames = self._load_csv(path)
        safe_offset = max(0, offset)
        safe_limit = max(1, min(1000, limit))
        sliced = rows[safe_offset : safe_offset + safe_limit]
        return QueryEvaluationRowsResponse(
            out_dir=str(out_dir),
            file_name=file_name,
            columns=["row_key", *fieldnames],
            rows=[{"row_key": self._row_key(row), **row} for row in sliced],
            total_rows=len(rows),
            offset=safe_offset,
            limit=safe_limit,
        )

    @staticmethod
    def _load_csv(path: Path) -> Tuple[List[Dict[str, str]], List[str]]:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            fieldnames = list(reader.fieldnames or [])
            rows = [dict(row) for row in reader]
        return rows, fieldnames

    @staticmethod
    def _write_csv(path: Path, rows: Iterable[Dict[str, str]], fieldnames: List[str]) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as out:
            writer = csv.DictWriter(out, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in fieldnames})

    @staticmethod
    def _row_key(row: Dict[str, Any]) -> str:
        # CSV에는 DB id가 없으므로 run_id/rank/isbn/title 조합을 화면 편집용 안정 key로 사용합니다.
        return "|".join(
            str(row.get(key) or "")
            for key in ["run_id", "rank", "isbn", "title", "author"]
        )

    @staticmethod
    def _join(values: List[str]) -> str:
        return ",".join(str(value).strip() for value in values if str(value or "").strip())

    @staticmethod
    def _merge_python_warning_filter(current: str | None, warning_filter: str) -> str:
        if not current:
            return warning_filter
        if warning_filter in current.split(","):
            return current
        return f"{warning_filter},{current}"

    @staticmethod
    def _tail(value: str, limit: int = 4000) -> str:
        if not value:
            return ""
        sanitized_lines = [
            line
            for line in value.splitlines()
            if "Api key is used with an insecure connection" not in line
        ]
        return "\n".join(sanitized_lines)[-limit:]

    @staticmethod
    def _resolve_file(value: str | None, default_path: Path) -> Path:
        if not value or not str(value).strip():
            return default_path
        path = Path(value)
        if not path.is_absolute():
            path = AI_SERVER_ROOT / path
        return path

    def _resolve_out_dir(self, value: str | None, *, create_job_if_blank: bool = False) -> Path:
        # 수정 포인트: 외부에서 받은 WSL/NAS 경로를 그대로 열지 않고 jobs/<jobId> 부분만 추출해
        # ai-server 컨테이너의 QUERY_EVAL_OUTPUT_DIR mountPath 아래로 매핑합니다.
        if not value or not str(value).strip():
            return DEFAULT_OUT_DIR / "jobs" / self._new_job_id() if create_job_if_blank else DEFAULT_OUT_DIR

        raw = str(value).strip().replace("\\", "/")
        parts = [part for part in raw.split("/") if part]
        if "jobs" in parts:
            index = parts.index("jobs")
            if index + 1 < len(parts):
                job_id = self._safe_job_id(parts[index + 1])
                return DEFAULT_OUT_DIR / "jobs" / job_id

        path = Path(raw)
        if not path.is_absolute():
            path = DEFAULT_OUT_DIR / path
        try:
            path.resolve().relative_to(DEFAULT_OUT_DIR.resolve())
            return path
        except Exception:
            return DEFAULT_OUT_DIR

    @staticmethod
    def _new_job_id() -> str:
        return f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"

    @staticmethod
    def _safe_job_id(value: str) -> str:
        return "".join(ch for ch in str(value) if ch.isalnum() or ch in {"-", "_"})[:80]

    @staticmethod
    def _job_id_from_out_dir(out_dir: Path) -> str | None:
        return out_dir.name if out_dir.parent.name == "jobs" else None

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    def _response_from_result(
        self,
        result: subprocess.CompletedProcess[str],
        out_dir: Path,
        task_name: str,
    ) -> QueryEvaluationCommandResponse:
        status = "SUCCEEDED" if result.returncode == 0 else "FAILED"
        return QueryEvaluationCommandResponse(
            status=status,
            exit_code=result.returncode,
            out_dir=str(out_dir),
            label_csv_path=str(out_dir / "candidate_label_template.csv"),
            auto_summary_path=str(out_dir / "auto_summary.csv"),
            labeled_summary_path=str(out_dir / "labeled_summary.csv"),
            raw_results_path=str(out_dir / "raw_results.jsonl"),
            stdout_tail=self._tail(result.stdout),
            stderr_tail=self._tail(result.stderr),
            message=f"{task_name} {'completed' if status == 'SUCCEEDED' else 'failed'}.",
            job_id=self._job_id_from_out_dir(out_dir),
            log_path=str(out_dir / "run_metadata.json") if self._job_id_from_out_dir(out_dir) else None,
        )

    def _response_from_metadata(self, out_dir: Path, metadata: Dict[str, Any]) -> QueryEvaluationCommandResponse:
        status = str(metadata.get("status") or "SUCCEEDED").upper()
        if status == "COMPLETED":
            status = "SUCCEEDED"
        return QueryEvaluationCommandResponse(
            status=status,
            exit_code=int(metadata.get("exit_code") or (0 if status == "SUCCEEDED" else 1)),
            out_dir=str(out_dir),
            label_csv_path=str(out_dir / "candidate_label_template.csv"),
            auto_summary_path=str(out_dir / "auto_summary.csv"),
            labeled_summary_path=str(out_dir / "labeled_summary.csv"),
            raw_results_path=str(out_dir / "raw_results.jsonl"),
            stdout_tail="",
            stderr_tail=str(metadata.get("error") or ""),
            message=str(metadata.get("message") or ""),
            job_id=str(metadata.get("job_id") or self._job_id_from_out_dir(out_dir) or ""),
            log_path=str(out_dir / "run_metadata.json"),
        )

    def _missing_file_response(self, out_dir: Path, missing_file: Path, message: str) -> QueryEvaluationCommandResponse:
        return QueryEvaluationCommandResponse(
            status="FAILED",
            exit_code=1,
            out_dir=str(out_dir),
            label_csv_path=str(out_dir / "candidate_label_template.csv"),
            auto_summary_path=str(out_dir / "auto_summary.csv"),
            labeled_summary_path=str(out_dir / "labeled_summary.csv"),
            raw_results_path=str(out_dir / "raw_results.jsonl"),
            stdout_tail="",
            stderr_tail=f"missing file: {missing_file}",
            message=message,
            job_id=self._job_id_from_out_dir(out_dir),
            log_path=str(out_dir / "run_metadata.json") if self._job_id_from_out_dir(out_dir) else None,
        )

    def _write_run_metadata(self, out_dir: Path, metadata: Dict[str, Any]) -> None:
        existing = self._read_existing_metadata(out_dir)
        merged = {**existing, **metadata}
        merged.setdefault("job_id", self._job_id_from_out_dir(out_dir))
        merged.setdefault("out_dir", str(out_dir))
        merged.setdefault("output_dir", str(out_dir))
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "run_metadata.json").write_text(json.dumps(merged, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        (DEFAULT_OUT_DIR / "latest.json").write_text(json.dumps(merged, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    @staticmethod
    def _read_existing_metadata(out_dir: Path) -> Dict[str, Any]:
        path = out_dir / "run_metadata.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write_qualitative_labels(self, out_dir: Path, rows: List[Dict[str, str]]) -> None:
        payload = {
            "job_id": self._job_id_from_out_dir(out_dir),
            "generated_at": self._now(),
            "rows": [
                {
                    "row_key": self._row_key(row),
                    "run_id": row.get("run_id"),
                    "rank": row.get("rank"),
                    "isbn": row.get("isbn"),
                    "title": row.get("title"),
                    "human_relevance_0_2": row.get("human_relevance_0_2"),
                    "human_memo": row.get("human_memo"),
                }
                for row in rows
            ],
        }
        (out_dir / "qualitative_labels.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_final_score(self, out_dir: Path, top_k: int) -> None:
        dimension_rows: List[Dict[str, str]] = []
        labeled_rows: List[Dict[str, str]] = []
        if (out_dir / "dimension_summary.csv").exists():
            dimension_rows, _ = self._load_csv(out_dir / "dimension_summary.csv")
        if (out_dir / "labeled_summary.csv").exists():
            labeled_rows, _ = self._load_csv(out_dir / "labeled_summary.csv")
        payload = {
            "job_id": self._job_id_from_out_dir(out_dir),
            "generated_at": self._now(),
            "top_k": top_k,
            "dimension_summary": dimension_rows,
            "labeled_summary": labeled_rows,
        }
        (out_dir / "final_score.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
