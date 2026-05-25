from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field


def load_env_files(*paths: str) -> None:
    for item in paths:
        env_path = Path(item)
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_files(".env", ".env.local")

PROJECT_DIR = Path(os.environ.get("PROJECT_DIR", Path.cwd())).resolve()
AI_SERVER_DIR = Path(os.environ.get("AI_SERVER_DIR", PROJECT_DIR / "apps" / "ai-server")).resolve()
EVAL_SCRIPT = Path(os.environ.get("EVAL_SCRIPT", AI_SERVER_DIR / "script" / "evaluate_query_payload_and_rules.py")).resolve()
EVAL_CASES = Path(os.environ.get("EVAL_CASES", AI_SERVER_DIR / "script" / "evaluation" / "query_payload_eval_cases.example.jsonl")).resolve()
EVAL_OUTPUT_DIR = Path(os.environ.get("EVAL_OUTPUT_DIR", "/mnt/nas-eval/query-payload-rules")).resolve()
LOCAL_LOG_DIR = Path(os.environ.get("LOCAL_LOG_DIR", PROJECT_DIR / ".local" / "query-eval-runner" / "logs")).resolve()
# ai-server pod가 같은 NAS 폴더를 다른 mountPath로 읽는 경우 backend에는 reader용 경로를 돌려줄 수 있습니다.
EVAL_READER_OUTPUT_DIR = os.environ.get("EVAL_READER_OUTPUT_DIR", os.environ.get("QUERY_EVAL_READER_OUTPUT_DIR", "")).strip()
# 평가 스크립트는 ai-server 의존성이 설치된 venv Python으로 실행해야 합니다.
# venv의 python/python3는 symlink일 수 있으므로 resolve()를 사용하지 않습니다.
# resolve()를 호출하면 /usr/bin/python3.x로 풀려 venv site-packages를 우회할 수 있습니다.
PYTHON_BIN = Path(
    os.environ.get("EVAL_PYTHON_BIN")
    or os.environ.get("EVAL_PYTHON")
    or str(AI_SERVER_DIR / ".venv-eval" / "bin" / "python3")
)

RUNNER_API_KEY = os.environ.get("RUNNER_API_KEY", "")
MAX_TOP_K = int(os.environ.get("MAX_TOP_K", "10"))
MAX_CORPUS_DOCS = int(os.environ.get("MAX_CORPUS_DOCS", "20000"))
MAX_CONCURRENT_JOBS = max(1, int(os.environ.get("MAX_CONCURRENT_EVAL_JOBS", "1")))
DEFAULT_TIMEOUT_SECONDS = int(os.environ.get("EVAL_JOB_TIMEOUT_SECONDS", "7200"))

LOCAL_LOG_DIR.mkdir(parents=True, exist_ok=True)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def ensure_output_dir(path: Path) -> None:
    # CIFS/SMB mount에서는 이미 존재하는 디렉터리에 mkdir -p를 호출해도 PermissionError가 날 수 있습니다.
    # runner 시작 시에는 루트 디렉터리를 만들지 않고, probe 파일 write/delete로 mount와 쓰기 권한만 확인합니다.
    probe = path / ".runner-write-check"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except Exception as exc:
        raise RuntimeError(
            f"Evaluation output directory is not writable or not mounted: {path}. "
            "Create the directory on NAS first and check WSL CIFS mount options."
        ) from exc


def ensure_directory_for_job(path: Path) -> None:
    # job별 디렉터리는 평가 실행에 필요한 신규 디렉터리이므로 여기에서만 생성합니다.
    # CIFS 오류가 나면 어느 경로에서 실패했는지 runner log와 API 응답에 명확히 남깁니다.
    try:
        if not path.exists():
            path.mkdir(parents=True, exist_ok=False)
        if not path.is_dir():
            raise RuntimeError(f"path exists but is not a directory: {path}")
    except FileExistsError:
        if not path.is_dir():
            raise RuntimeError(f"path exists but is not a directory: {path}")
    except Exception as exc:
        raise RuntimeError(f"Failed to create evaluation job directory on NAS/CIFS: {path}") from exc


ensure_output_dir(EVAL_OUTPUT_DIR)

ALLOWED_QUERY_VARIANTS = {
    "original",
    "llm_search_query",
    "retrieval_query",
    "retrieval_plus_genre",
    "retrieval_plus_purpose",
    "retrieval_plus_context",
    "retrieval_plus_profile",
}
ALLOWED_RETRIEVAL_VARIANTS = {
    "dense",
    "lookup",
    "bm25",
    "dense_lookup",
    "dense_bm25",
    "dense_bm25_lookup",
}
ALLOWED_RULE_VARIANTS = {
    "current",
    "rule_off",
    "no_genre",
    "no_purpose",
    "no_review",
    "no_bookshelf",
    "no_negative",
    "no_audience",
    "half_personalization",
    "strong_personalization",
}

app = FastAPI(title="Book Curation Local Query Evaluation Runner")

jobs: Dict[str, dict] = {}
processes: Dict[str, subprocess.Popen[str]] = {}
process_lock = threading.Lock()
run_slots = threading.Semaphore(MAX_CONCURRENT_JOBS)


class RunRequest(BaseModel):
    # backend가 snake_case로 전달하고, 필요 시 직접 호출자가 camelCase로 보내도 받을 수 있게 alias를 둡니다.
    cases_path: Optional[str] = Field(default=None, alias="casesPath")
    cases_jsonl: Optional[str] = Field(default=None, alias="casesJsonl")
    top_k: int = Field(default=5, ge=1, alias="topK")
    max_corpus_docs: int = Field(default=3000, ge=1, alias="maxCorpusDocs")
    embedding_model: str = Field(default="KURE", alias="embeddingModel")
    query_variants: List[str] = Field(default_factory=lambda: ["original"], alias="queryVariants")
    retrieval_variants: List[str] = Field(default_factory=lambda: ["dense"], alias="retrievalVariants")
    rule_variants: List[str] = Field(default_factory=lambda: ["current"], alias="ruleVariants")

    class Config:
        allow_population_by_field_name = True
        populate_by_name = True


def request_to_dict(req: RunRequest) -> dict:
    if hasattr(req, "model_dump"):
        return req.model_dump(by_alias=False)
    return req.dict(by_alias=False)


def require_api_key(x_runner_key: Optional[str]) -> None:
    if not RUNNER_API_KEY:
        raise HTTPException(status_code=500, detail="RUNNER_API_KEY is not configured")
    if x_runner_key != RUNNER_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid runner API key")


def validate_request(req: RunRequest) -> None:
    if req.top_k > MAX_TOP_K:
        raise HTTPException(status_code=400, detail=f"top_k exceeds MAX_TOP_K={MAX_TOP_K}")
    if req.max_corpus_docs > MAX_CORPUS_DOCS:
        raise HTTPException(status_code=400, detail=f"max_corpus_docs exceeds MAX_CORPUS_DOCS={MAX_CORPUS_DOCS}")

    invalid_query = sorted(set(req.query_variants) - ALLOWED_QUERY_VARIANTS)
    invalid_retrieval = sorted(set(req.retrieval_variants) - ALLOWED_RETRIEVAL_VARIANTS)
    invalid_rule = sorted(set(req.rule_variants) - ALLOWED_RULE_VARIANTS)
    if invalid_query or invalid_retrieval or invalid_rule:
        raise HTTPException(
            status_code=400,
            detail={
                "invalid_query_variants": invalid_query,
                "invalid_retrieval_variants": invalid_retrieval,
                "invalid_rule_variants": invalid_rule,
            },
        )


def job_output_dir(job_id: str) -> Path:
    return EVAL_OUTPUT_DIR / "jobs" / job_id


def reader_output_dir(job_id: str) -> str:
    if not EVAL_READER_OUTPUT_DIR:
        return str(job_output_dir(job_id))
    return str(Path(EVAL_READER_OUTPUT_DIR) / "jobs" / job_id)


def latest_path() -> Path:
    return EVAL_OUTPUT_DIR / "latest.json"


def metadata_path(job_id: str) -> Path:
    return job_output_dir(job_id) / "run_metadata.json"


def root_log_path(job_id: str) -> Path:
    return EVAL_OUTPUT_DIR / f"runner-{job_id}.log"


def append_local_log(job_id: str, message: str) -> None:
    log_file = LOCAL_LOG_DIR / f"runner-{job_id}.debug.log"
    with log_file.open("a", encoding="utf-8") as out:
        out.write(f"{now_iso()} {message}\n")


def persist_job(job_id: str) -> None:
    job = dict(jobs.get(job_id) or {})
    if not job:
        return
    job.setdefault("job_id", job_id)
    job.setdefault("output_dir", str(job_output_dir(job_id)))
    job.setdefault("reader_out_dir", reader_output_dir(job_id))
    job.setdefault("out_dir", reader_output_dir(job_id))
    job.setdefault("log_path", str(root_log_path(job_id)))
    path = metadata_path(job_id)
    try:
        ensure_directory_for_job(path.parent)
        path.write_text(json.dumps(job, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        if str(job.get("status") or "").upper() in {"COMPLETED", "SUCCEEDED", "FAILED", "CANCELED"}:
            latest_path().write_text(json.dumps(job, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    except Exception as exc:
        append_local_log(job_id, f"metadata persist failed: {exc}")


def load_persisted_job(job_id: str) -> Optional[dict]:
    path = metadata_path(job_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data.setdefault("job_id", job_id)
        data.setdefault("output_dir", str(job_output_dir(job_id)))
        data.setdefault("reader_out_dir", reader_output_dir(job_id))
        data.setdefault("out_dir", reader_output_dir(job_id))
        data.setdefault("log_path", str(root_log_path(job_id)))
        return data
    except Exception:
        return None


def list_persisted_jobs(limit: int = 50) -> List[dict]:
    jobs_dir = EVAL_OUTPUT_DIR / "jobs"
    rows: List[dict] = []
    if jobs_dir.exists():
        for item in jobs_dir.iterdir():
            if not item.is_dir():
                continue
            path = item / "run_metadata.json"
            if not path.exists():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                data.setdefault("job_id", item.name)
                data.setdefault("output_dir", str(item))
                data.setdefault("reader_out_dir", reader_output_dir(item.name))
                data.setdefault("out_dir", reader_output_dir(item.name))
                data.setdefault("log_path", str(root_log_path(item.name)))
                rows.append(data)
            except Exception:
                continue
    with process_lock:
        for job_id, job in jobs.items():
            if not any(row.get("job_id") == job_id for row in rows):
                rows.append(dict(job))
    rows.sort(key=lambda row: str(row.get("created_at") or row.get("started_at") or ""), reverse=True)
    return rows[: max(1, min(200, limit))]


def normalize_manual_cases(value: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for index, raw_line in enumerate(value.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("{"):
            data = json.loads(line)
            query = str(data.get("query") or "").strip()
            if not query:
                raise ValueError("manual JSONL row requires query")
            data.setdefault("id", f"MANUAL{index:03d}")
            data.setdefault("category", "manual")
            rows.append(data)
        else:
            rows.append({"id": f"MANUAL{index:03d}", "category": "manual", "query": line})
    if not rows:
        raise ValueError("manual evaluation cases are empty")
    return rows


def resolve_cases_path(job_id: str, req: RunRequest, job_dir: Path) -> Path:
    manual_cases = (req.cases_jsonl or "").strip()
    if manual_cases:
        manual_path = job_dir / "manual_eval_cases.jsonl"
        with manual_path.open("w", encoding="utf-8") as out:
            for row in normalize_manual_cases(manual_cases):
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
        return manual_path

    if req.cases_path:
        candidate = Path(req.cases_path).expanduser()
        return candidate if candidate.is_absolute() else (PROJECT_DIR / candidate).resolve()

    return EVAL_CASES


def run_job(job_id: str, req: RunRequest) -> None:
    job_dir = job_output_dir(job_id)
    log_path = root_log_path(job_id)
    slot_acquired = False
    try:
        run_slots.acquire()
        slot_acquired = True
        ensure_directory_for_job(job_dir)
        jobs[job_id].update({
            "status": "RUNNING",
            "started_at": now_iso(),
            "output_dir": str(job_dir),
            "reader_out_dir": reader_output_dir(job_id),
            "out_dir": reader_output_dir(job_id),
            "log_path": str(log_path),
            "label_csv_path": str(job_dir / "candidate_label_template.csv"),
            "auto_summary_path": str(job_dir / "auto_summary.csv"),
            "labeled_summary_path": str(job_dir / "labeled_summary.csv"),
            "raw_results_path": str(job_dir / "raw_results.jsonl"),
        })
        persist_job(job_id)
        append_local_log(job_id, "thread started")
        print(f"[runner] started job_id={job_id}", flush=True)

        cases_path = resolve_cases_path(job_id, req, job_dir)
        for path, label in [(PYTHON_BIN, "python"), (EVAL_SCRIPT, "evaluation script"), (cases_path, "evaluation cases")]:
            if not path.exists():
                raise FileNotFoundError(f"{label} not found: {path}")

        cmd = [
            str(PYTHON_BIN),
            str(EVAL_SCRIPT),
            "run",
            "--cases",
            str(cases_path),
            "--out-dir",
            str(job_dir),
            "--embedding-model",
            req.embedding_model,
            "--top-k",
            str(req.top_k),
            "--max-corpus-docs",
            str(req.max_corpus_docs),
            "--query-variants",
            ",".join(req.query_variants),
            "--retrieval-variants",
            ",".join(req.retrieval_variants),
            "--rule-variants",
            ",".join(req.rule_variants),
        ]

        env = os.environ.copy()
        env["PYTHONPATH"] = f"{AI_SERVER_DIR}{os.pathsep}{env.get('PYTHONPATH', '')}".rstrip(os.pathsep)
        # 수정 포인트: Qdrant NodePort/http 경고는 평가 실패가 아니어서 runner log와 관리자 stderr에 남기지 않습니다.
        warning_filter = "ignore:Api key is used with an insecure connection.:UserWarning"
        current_warnings = env.get("PYTHONWARNINGS", "")
        env["PYTHONWARNINGS"] = (
            current_warnings
            if warning_filter in current_warnings.split(",")
            else f"{warning_filter},{current_warnings}".rstrip(",")
        )

        with log_path.open("w", encoding="utf-8") as log_file:
            log_file.write(f"[runner] job_id={job_id}\n")
            log_file.write(f"[runner] started_at={jobs[job_id]['started_at']}\n")
            log_file.write(f"[runner] project_dir={PROJECT_DIR}\n")
            log_file.write(f"[runner] output_dir={job_dir}\n")
            log_file.write(f"[runner] reader_out_dir={reader_output_dir(job_id)}\n")
            log_file.write(f"[runner] cases={cases_path}\n")
            log_file.write(f"[runner] command={' '.join(cmd)}\n\n")
            log_file.flush()

            process = subprocess.Popen(
                cmd,
                cwd=str(PROJECT_DIR),
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
            )
            with process_lock:
                processes[job_id] = process
                jobs[job_id]["pid"] = process.pid
                persist_job(job_id)
            append_local_log(job_id, f"process started pid={process.pid}")
            try:
                return_code = process.wait(timeout=DEFAULT_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                process.terminate()
                jobs[job_id]["status"] = "FAILED"
                jobs[job_id]["error"] = f"Process timed out after {DEFAULT_TIMEOUT_SECONDS}s"
                persist_job(job_id)
                return

        append_local_log(job_id, f"process finished code={return_code}")
        print(f"[runner] finished job_id={job_id} code={return_code}", flush=True)
        if return_code == 0:
            jobs[job_id]["status"] = "COMPLETED"
            jobs[job_id]["exit_code"] = 0
            jobs[job_id]["message"] = "evaluation completed"
        else:
            jobs[job_id]["status"] = "FAILED"
            jobs[job_id]["exit_code"] = return_code
            jobs[job_id]["error"] = f"Process exited with code {return_code}"
    except Exception as exc:
        jobs[job_id]["status"] = "FAILED"
        jobs[job_id]["error"] = str(exc)
        jobs[job_id]["traceback"] = traceback.format_exc()
        append_local_log(job_id, "exception=" + str(exc))
        append_local_log(job_id, traceback.format_exc())
    finally:
        jobs[job_id]["finished_at"] = now_iso()
        append_local_log(job_id, f"final_status={jobs[job_id]['status']}")
        with process_lock:
            processes.pop(job_id, None)
        persist_job(job_id)
        if slot_acquired:
            run_slots.release()


@app.get("/health")
def health(x_runner_key: Optional[str] = Header(default=None, alias="X-Runner-Key")):
    require_api_key(x_runner_key)
    active_jobs = [job_id for job_id, job in jobs.items() if str(job.get("status") or "").upper() == "RUNNING"]
    return {
        "status": "UP",
        "runner": "local-query-eval-runner",
        "project_dir": str(PROJECT_DIR),
        "ai_server_dir": str(AI_SERVER_DIR),
        "output_dir": str(EVAL_OUTPUT_DIR),
        "reader_output_dir": EVAL_READER_OUTPUT_DIR,
        "local_log_dir": str(LOCAL_LOG_DIR),
        "active_jobs": active_jobs,
        "job_count": len(list_persisted_jobs(limit=200)),
        "max_concurrent_jobs": MAX_CONCURRENT_JOBS,
    }


@app.post("/evaluation/run")
def run_evaluation(req: RunRequest, x_runner_key: Optional[str] = Header(default=None, alias="X-Runner-Key")):
    require_api_key(x_runner_key)
    validate_request(req)

    job_id = f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    job_dir = job_output_dir(job_id)
    jobs[job_id] = {
        "job_id": job_id,
        "status": "PENDING",
        "created_at": now_iso(),
        "request": request_to_dict(req),
        "output_dir": str(job_dir),
        "reader_out_dir": reader_output_dir(job_id),
        "out_dir": reader_output_dir(job_id),
        "log_path": str(root_log_path(job_id)),
        "label_csv_path": str(job_dir / "candidate_label_template.csv"),
        "auto_summary_path": str(job_dir / "auto_summary.csv"),
        "labeled_summary_path": str(job_dir / "labeled_summary.csv"),
        "raw_results_path": str(job_dir / "raw_results.jsonl"),
        "message": "evaluation job queued",
    }
    append_local_log(job_id, "job accepted")
    # 수정 포인트: 관리자 페이지가 실제 local runner를 호출했는지 콘솔에서 바로 확인할 수 있게 합니다.
    print(f"[runner] accepted job_id={job_id} out_dir={job_dir}", flush=True)
    persist_job(job_id)
    thread = threading.Thread(target=run_job, args=(job_id, req), daemon=False)
    thread.start()
    append_local_log(job_id, "thread.start called")
    return jobs[job_id]


@app.get("/evaluation/jobs")
def list_jobs(
    limit: int = 50,
    x_runner_key: Optional[str] = Header(default=None, alias="X-Runner-Key"),
):
    require_api_key(x_runner_key)
    return {"jobs": list_persisted_jobs(limit=limit)}


@app.get("/evaluation/jobs/latest")
def latest_job(x_runner_key: Optional[str] = Header(default=None, alias="X-Runner-Key")):
    require_api_key(x_runner_key)
    if latest_path().exists():
        try:
            return json.loads(latest_path().read_text(encoding="utf-8"))
        except Exception:
            pass
    rows = list_persisted_jobs(limit=1)
    if not rows:
        raise HTTPException(status_code=404, detail="Job not found")
    return rows[0]


@app.get("/evaluation/jobs/{job_id}")
def get_job(job_id: str, x_runner_key: Optional[str] = Header(default=None, alias="X-Runner-Key")):
    require_api_key(x_runner_key)
    if job_id in jobs:
        return jobs[job_id]
    persisted = load_persisted_job(job_id)
    if persisted:
        return persisted
    raise HTTPException(status_code=404, detail="Job not found")


@app.post("/evaluation/jobs/{job_id}/cancel")
def cancel_job(job_id: str, x_runner_key: Optional[str] = Header(default=None, alias="X-Runner-Key")):
    require_api_key(x_runner_key)
    if job_id not in jobs:
        persisted = load_persisted_job(job_id)
        if not persisted:
            raise HTTPException(status_code=404, detail="Job not found")
        return persisted
    with process_lock:
        process = processes.get(job_id)
        if process is not None:
            process.send_signal(signal.SIGTERM)
            processes.pop(job_id, None)
        jobs[job_id]["status"] = "CANCELED"
        jobs[job_id]["finished_at"] = now_iso()
        jobs[job_id]["message"] = "evaluation job canceled"
        persist_job(job_id)
    return jobs[job_id]
