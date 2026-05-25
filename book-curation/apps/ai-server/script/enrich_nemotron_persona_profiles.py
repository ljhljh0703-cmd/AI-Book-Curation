#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

import requests
from common_env import load_ai_server_env

# 수정 포인트: FastAPI와 동일하게 apps/ai-server/.env.local을 로드해서 CLOVA 키/URL을 코드에 하드코딩하지 않습니다.
AI_SERVER_ROOT = load_ai_server_env(Path(__file__))

try:
    from datasets import load_dataset
except Exception:  # pragma: no cover - 실행 환경 의존 패키지 안내용입니다.
    load_dataset = None  # type: ignore[assignment]

SCALAR_TYPES = (str, int, float, bool)
REQUIRED_PROFILE_TEXT_FIELDS: tuple[str, ...] = (
    "reading_purpose_summary",
    "preference_summary",
    "dispreference_summary",
    "search_profile_text",
    "interest_profile_text",
    "reading_now_profile_text",
    "read_completed_profile_text",
    "dislike_profile_text",
)
NUMERIC_PROFILE_FIELDS: tuple[str, ...] = (
    "rating_bias",
    "review_sentiment_bias",
    "exploration_level",
    "confidence",
)


class ProfileEnrichmentError(RuntimeError):
    pass


@dataclass(frozen=True)
class EnrichmentConfig:
    dataset_name: str
    dataset_split: str
    sample_size: int
    seed: int
    shuffle_buffer_size: int
    hf_token: str
    persona_id_field: str
    persona_fields: list[str]
    max_persona_field_chars: int
    clova_api_key: str
    clova_chat_url: str
    clova_chat_model: str
    clova_timeout_seconds: float
    clova_max_retries: int
    clova_retry_initial_delay_seconds: float
    clova_retry_max_delay_seconds: float
    llm_min_interval_seconds: float
    system_prompt_path: Path
    user_prompt_path: Path
    profile_schema_version: str
    resume: bool
    failure_policy: str
    max_failed_personas: int
    failure_cooldown_seconds: float
    max_source_scan: int
    output_persona_subset_path: Path | None
    output_profile_path: Path
    created_at_start: datetime


class ClovaProfileClient:
    """CLOVA Studio chat completion을 스크립트에서 직접 호출하는 최소 클라이언트입니다."""

    RETRY_STATUS_CODES = {429, 500, 502, 503, 504}

    def __init__(self, config: EnrichmentConfig) -> None:
        if not config.clova_api_key.strip():
            raise ProfileEnrichmentError("CLOVA_API_KEY가 비어 있습니다. apps/ai-server/.env.local을 확인해주세요.")
        self.config = config
        self.session = requests.Session()
        self.last_request_at = 0.0

    @staticmethod
    def _is_openai_compatible_url(url: str) -> bool:
        return "/v1/openai" in (url or "")

    @classmethod
    def _build_native_model_url(cls, url: str, model: str) -> str:
        # 수정 포인트: 현재 ai-server ClovaClient와 동일하게 네이티브 v3 URL에는 모델명을 경로에 붙입니다.
        base_url = (url or "").strip().rstrip("/")
        model_name = (model or "").strip()
        if not base_url:
            return base_url
        base_url = base_url.replace("/v3/chat/completions", "/v3/chat-completions")
        if model_name and not base_url.endswith(f"/{model_name}"):
            return f"{base_url}/{model_name}"
        return base_url

    def _resolve_chat_request(self) -> tuple[str, bool]:
        if self._is_openai_compatible_url(self.config.clova_chat_url):
            return self.config.clova_chat_url.rstrip("/"), True
        return self._build_native_model_url(self.config.clova_chat_url, self.config.clova_chat_model), False

    @staticmethod
    def _clamp_delay(seconds: float, max_seconds: float) -> float:
        return max(0.0, min(float(seconds), max(0.0, float(max_seconds))))

    @staticmethod
    def _retry_after_seconds(response: requests.Response, fallback: float, max_seconds: float) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            retry_after = retry_after.strip()
            try:
                return ClovaProfileClient._clamp_delay(float(retry_after), max_seconds)
            except ValueError:
                pass
            try:
                retry_datetime = parsedate_to_datetime(retry_after)
                if retry_datetime.tzinfo is None:
                    retry_datetime = retry_datetime.replace(tzinfo=timezone.utc)
                seconds = (retry_datetime - datetime.now(timezone.utc)).total_seconds()
                return ClovaProfileClient._clamp_delay(seconds, max_seconds)
            except Exception:
                pass
        return ClovaProfileClient._clamp_delay(fallback, max_seconds)

    def _wait_for_turn(self) -> None:
        wait_seconds = max(0.0, self.config.llm_min_interval_seconds - (time.time() - self.last_request_at))
        if wait_seconds > 0:
            print(f"[LLM WAIT] sleep={round(wait_seconds, 3)}s")
            time.sleep(wait_seconds)
        self.last_request_at = time.time()

    def chat_completion(self, system_prompt: str, user_prompt: str) -> str:
        chat_url, is_openai_compatible = self._resolve_chat_request()
        if not chat_url:
            raise ProfileEnrichmentError("CLOVA_CHAT_URL이 비어 있습니다. apps/ai-server/.env.local을 확인해주세요.")

        headers = {
            "Authorization": f"Bearer {self.config.clova_api_key}",
            "Content-Type": "application/json; charset=utf-8",
            "X-NCP-CLOVASTUDIO-REQUEST-ID": uuid.uuid4().hex,
        }
        body: dict[str, Any] = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        }
        if is_openai_compatible:
            body["model"] = self.config.clova_chat_model

        delay = max(0.1, float(self.config.clova_retry_initial_delay_seconds))
        for attempt in range(1, self.config.clova_max_retries + 1):
            try:
                self._wait_for_turn()
                response = self.session.post(chat_url, headers=headers, json=body, timeout=self.config.clova_timeout_seconds)
                if response.status_code in self.RETRY_STATUS_CODES:
                    sleep_seconds = self._retry_after_seconds(response, delay, self.config.clova_retry_max_delay_seconds)
                    print(
                        f"[LLM RETRY] status={response.status_code} attempt={attempt}/{self.config.clova_max_retries} "
                        f"sleep={round(sleep_seconds, 3)}s",
                        file=sys.stderr,
                    )
                    if attempt == self.config.clova_max_retries:
                        raise ProfileEnrichmentError(f"CLOVA chat 호출 실패: status={response.status_code}, body={response.text[:500]}")
                    time.sleep(sleep_seconds)
                    delay = min(delay * 2, self.config.clova_retry_max_delay_seconds)
                    continue

                response.raise_for_status()
                data = response.json()
                if "result" in data and "message" in data["result"]:
                    return str(data["result"]["message"].get("content", ""))
                if "choices" in data and data["choices"]:
                    return str(data["choices"][0]["message"].get("content", ""))
                if "message" in data:
                    return str(data["message"].get("content", ""))
                raise ProfileEnrichmentError(f"CLOVA chat 응답에서 content를 찾지 못했습니다. keys={list(data.keys())}")
            except requests.RequestException as exc:
                print(
                    f"[LLM ERROR] attempt={attempt}/{self.config.clova_max_retries} error={exc} sleep={round(delay, 3)}s",
                    file=sys.stderr,
                )
                if attempt == self.config.clova_max_retries:
                    raise ProfileEnrichmentError(f"CLOVA chat 네트워크 호출 실패: {exc}") from exc
                time.sleep(self._clamp_delay(delay, self.config.clova_retry_max_delay_seconds))
                delay = min(delay * 2, self.config.clova_retry_max_delay_seconds)

        raise ProfileEnrichmentError("CLOVA chat 호출 실패")


def stable_hash(value: Any, length: int = 16) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def parse_csv(value: str) -> list[str]:
    return [part.strip() for part in str(value or "").split(",") if part.strip()]


def parse_datetime_utc(value: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        return datetime(2026, 1, 1, tzinfo=timezone.utc)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def now_iso_from_base(base: datetime, offset_seconds: int) -> str:
    return (base + timedelta(seconds=offset_seconds)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def compact_value(value: Any, max_chars: int = 1200) -> str:
    if value is None:
        return ""
    if isinstance(value, SCALAR_TYPES):
        text = str(value)
    else:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    text = " ".join(text.replace("\n", " ").split())
    if len(text) > max_chars:
        return text[:max_chars].rstrip()
    return text


def select_persona_fields(row: Mapping[str, Any], fields: Sequence[str], max_chars: int) -> dict[str, Any]:
    selected_names = [field for field in fields if field in row] if fields else list(row.keys())
    selected: dict[str, Any] = {}
    for field_name in selected_names:
        text = compact_value(row.get(field_name), max_chars=max_chars)
        if text:
            selected[field_name] = text
    return selected


def resolve_persona_id(row: Mapping[str, Any], index: int, persona_id_field: str) -> str:
    for field_name in [persona_id_field, "persona_id", "id", "user_id", "uuid", "record_id"]:
        if not field_name:
            continue
        value = row.get(field_name)
        if value not in (None, ""):
            return f"persona:{str(value).strip()}"
    return f"persona:nemotron:{index:06d}:{stable_hash(row)}"


def stream_personas(config: EnrichmentConfig) -> Iterator[tuple[int, dict[str, Any]]]:
    if load_dataset is None:
        raise ProfileEnrichmentError(
            "datasets 패키지가 없습니다. apps/ai-server에서 `py -3.11 -m pip install -r requirements-synthetic-data.txt`를 실행해주세요."
        )
    dataset_kwargs: dict[str, Any] = {"split": config.dataset_split, "streaming": True}
    if config.hf_token:
        dataset_kwargs["token"] = config.hf_token
    dataset = load_dataset(config.dataset_name, **dataset_kwargs)
    if config.shuffle_buffer_size > 0:
        dataset = dataset.shuffle(buffer_size=config.shuffle_buffer_size, seed=config.seed)
    for index, row in enumerate(dataset):
        if index >= config.max_source_scan:
            break
        if isinstance(row, dict):
            yield index, row


def load_prompt(path: Path) -> str:
    if not path.exists():
        raise ProfileEnrichmentError(f"프롬프트 파일이 없습니다. path={path}")
    return path.read_text(encoding="utf-8").strip()


def extract_json_object(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`").strip()
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < start:
        raise ProfileEnrichmentError(f"LLM 응답에서 JSON 객체를 찾지 못했습니다. response={text[:500]!r}")
    try:
        parsed = json.loads(raw[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ProfileEnrichmentError(f"LLM JSON 파싱 실패: {exc}. response={text[:500]!r}") from exc
    if not isinstance(parsed, dict):
        raise ProfileEnrichmentError("LLM 응답 JSON이 객체가 아닙니다.")
    return parsed


def clamp01(value: Any, default: float) -> float:
    try:
        number = float(value)
    except Exception:
        number = default
    return round(max(0.0, min(1.0, number)), 6)


def normalize_profile(raw_profile: Mapping[str, Any], persona_fields: Mapping[str, Any]) -> dict[str, Any]:
    # 수정 포인트: LLM 출력이 약간 흔들려도 후속 Qdrant 검색 스키마는 고정되도록 정규화합니다.
    fallback_text = compact_value(persona_fields, max_chars=1800)
    profile: dict[str, Any] = {}
    for field_name in REQUIRED_PROFILE_TEXT_FIELDS:
        text = compact_value(raw_profile.get(field_name), max_chars=1200)
        profile[field_name] = text or fallback_text
    profile["rating_bias"] = clamp01(raw_profile.get("rating_bias"), 0.65)
    profile["review_sentiment_bias"] = clamp01(raw_profile.get("review_sentiment_bias"), 0.65)
    profile["exploration_level"] = clamp01(raw_profile.get("exploration_level"), 0.35)
    profile["confidence"] = clamp01(raw_profile.get("confidence"), 0.5)
    return profile


def build_user_prompt(template: str, persona_fields: Mapping[str, Any]) -> str:
    persona_json = json.dumps(persona_fields, ensure_ascii=False, sort_keys=True, indent=2)
    return template.replace("{{PERSONA_JSON}}", persona_json)


def append_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("a", encoding="utf-8") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            fp.write("\n")
            count += 1
    return count


def truncate_if_needed(path: Path | None, *, resume: bool) -> None:
    if path is None or resume:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def read_completed_profile_ids(path: Path) -> set[str]:
    completed: set[str] = set()
    if not path.exists():
        return completed
    with path.open("r", encoding="utf-8") as fp:
        for line_number, line in enumerate(fp, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ProfileEnrichmentError(f"--resume 대상 profile JSONL이 깨져 있습니다. path={path}, line={line_number}, error={exc}") from exc
            persona_id = str(row.get("persona_id") or "").strip()
            if persona_id:
                completed.add(persona_id)
    return completed


def build_persona_record(
    *,
    persona_id: str,
    synthetic_user_id: str,
    index: int,
    config: EnrichmentConfig,
    persona_fields: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "persona_id": persona_id,
        "synthetic_user_id": synthetic_user_id,
        "dataset_name": config.dataset_name,
        "dataset_split": config.dataset_split,
        "source_index": index,
        "persona_fields": dict(persona_fields),
        "persona_hash": stable_hash(persona_fields),
        "created_at": now_iso_from_base(config.created_at_start, index),
    }


def parse_args() -> EnrichmentConfig:
    default_system_prompt = AI_SERVER_ROOT / "script" / "prompts" / "nemotron_persona_reading_profile_system.v1.ko.md"
    default_user_prompt = AI_SERVER_ROOT / "script" / "prompts" / "nemotron_persona_reading_profile_user.v1.ko.md"

    parser = argparse.ArgumentParser(description="Use CLOVA LLM to enrich Nemotron personas into reading profiles for synthetic events.")
    parser.add_argument("--dataset-name", default="nvidia/Nemotron-Personas-Korea")
    parser.add_argument("--dataset-split", default="train")
    parser.add_argument("--sample-size", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--shuffle-buffer-size", type=int, default=10_000)
    parser.add_argument("--hf-token", default=os.getenv("HF_TOKEN", ""))
    parser.add_argument("--persona-id-field", default="")
    parser.add_argument("--persona-fields", default="")
    parser.add_argument("--max-persona-field-chars", type=int, default=1200)

    parser.add_argument("--clova-api-key", default=os.getenv("CLOVA_API_KEY", ""))
    parser.add_argument("--clova-chat-url", default=os.getenv("CLOVA_CHAT_URL", "https://clovastudio.stream.ntruss.com/v3/chat-completions"))
    parser.add_argument("--clova-chat-model", default=os.getenv("CLOVA_CHAT_MODEL", "HCX-007"))
    parser.add_argument("--clova-timeout-seconds", type=float, default=float(os.getenv("CLOVA_CHAT_TIMEOUT_SECONDS", "60")))
    parser.add_argument("--clova-max-retries", type=int, default=int(os.getenv("CLOVA_MAX_RETRIES", "4")))
    parser.add_argument("--clova-retry-initial-delay-seconds", type=float, default=float(os.getenv("CLOVA_RETRY_INITIAL_DELAY_SECONDS", "1")))
    parser.add_argument("--clova-retry-max-delay-seconds", type=float, default=float(os.getenv("CLOVA_RETRY_MAX_DELAY_SECONDS", "30")))
    parser.add_argument("--llm-min-interval-seconds", type=float, default=float(os.getenv("CLOVA_CHAT_MIN_INTERVAL_SECONDS", "1.2")))

    parser.add_argument("--system-prompt-path", default=str(default_system_prompt))
    parser.add_argument("--user-prompt-path", default=str(default_user_prompt))
    parser.add_argument("--profile-schema-version", default="llm_persona_reading_profile_v1")
    parser.add_argument("--created-at-start", default="2026-01-01T00:00:00Z")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--failure-policy", choices=("abort", "skip"), default="skip")
    parser.add_argument("--max-failed-personas", type=int, default=100)
    parser.add_argument("--failure-cooldown-seconds", type=float, default=5.0)
    parser.add_argument("--max-source-scan", type=int, default=0)
    parser.add_argument("--output-persona-subset-path", default="")
    parser.add_argument("--output-profile-path", required=True)
    args = parser.parse_args()

    sample_size = max(1, int(args.sample_size))
    max_source_scan = int(args.max_source_scan) if int(args.max_source_scan) > 0 else sample_size * 5
    return EnrichmentConfig(
        dataset_name=args.dataset_name,
        dataset_split=args.dataset_split,
        sample_size=sample_size,
        seed=int(args.seed),
        shuffle_buffer_size=max(0, int(args.shuffle_buffer_size)),
        hf_token=args.hf_token,
        persona_id_field=args.persona_id_field,
        persona_fields=parse_csv(args.persona_fields),
        max_persona_field_chars=max(200, int(args.max_persona_field_chars)),
        clova_api_key=args.clova_api_key,
        clova_chat_url=args.clova_chat_url,
        clova_chat_model=args.clova_chat_model,
        clova_timeout_seconds=float(args.clova_timeout_seconds),
        clova_max_retries=max(1, int(args.clova_max_retries)),
        clova_retry_initial_delay_seconds=max(0.1, float(args.clova_retry_initial_delay_seconds)),
        clova_retry_max_delay_seconds=max(1.0, float(args.clova_retry_max_delay_seconds)),
        llm_min_interval_seconds=max(0.0, float(args.llm_min_interval_seconds)),
        system_prompt_path=Path(args.system_prompt_path),
        user_prompt_path=Path(args.user_prompt_path),
        profile_schema_version=args.profile_schema_version,
        resume=bool(args.resume),
        failure_policy=str(args.failure_policy),
        max_failed_personas=max(0, int(args.max_failed_personas)),
        failure_cooldown_seconds=max(0.0, float(args.failure_cooldown_seconds)),
        max_source_scan=max(sample_size, max_source_scan),
        output_persona_subset_path=Path(args.output_persona_subset_path) if args.output_persona_subset_path else None,
        output_profile_path=Path(args.output_profile_path),
        created_at_start=parse_datetime_utc(args.created_at_start),
    )


def main() -> int:
    config = parse_args()
    system_prompt = load_prompt(config.system_prompt_path)
    user_prompt_template = load_prompt(config.user_prompt_path)
    client = ClovaProfileClient(config)

    truncate_if_needed(config.output_persona_subset_path, resume=config.resume)
    truncate_if_needed(config.output_profile_path, resume=config.resume)

    completed_ids = read_completed_profile_ids(config.output_profile_path) if config.resume else set()
    generated = len(completed_ids)
    failed = 0
    scanned = 0
    print(
        f"[PROFILE ENRICH START] target={config.sample_size} completed={generated} "
        f"output={config.output_profile_path} ai_server_root={AI_SERVER_ROOT}"
    )

    for index, raw_persona in stream_personas(config):
        scanned += 1
        if generated >= config.sample_size:
            break

        persona_fields = select_persona_fields(raw_persona, fields=config.persona_fields, max_chars=config.max_persona_field_chars)
        if not persona_fields:
            print(f"[SKIP PERSONA] source_index={index} reason=no usable fields", file=sys.stderr)
            continue

        persona_id = resolve_persona_id(raw_persona, index=index, persona_id_field=config.persona_id_field)
        if persona_id in completed_ids:
            print(f"[SKIP DONE] persona_id={persona_id}")
            continue

        synthetic_user_id = persona_id
        persona_record = build_persona_record(
            persona_id=persona_id,
            synthetic_user_id=synthetic_user_id,
            index=index,
            config=config,
            persona_fields=persona_fields,
        )
        print(f"[PROFILE] {generated + 1}/{config.sample_size} persona_id={persona_id}")

        try:
            prompt = build_user_prompt(user_prompt_template, persona_fields)
            content = client.chat_completion(system_prompt=system_prompt, user_prompt=prompt)
            raw_profile = extract_json_object(content)
            normalized_profile = normalize_profile(raw_profile, persona_fields)
            profile_record = {
                **persona_record,
                # 수정 포인트: LLM은 도서명을 생성하지 않고, action별 Qdrant 검색 문장과 사용자 성향 수치만 생성합니다.
                "profile_schema_version": config.profile_schema_version,
                "profile_source": "CLOVA_LLM_PERSONA_READING_PROFILE",
                "llm_profile": normalized_profile,
                "llm_raw_profile_keys": sorted(str(key) for key in raw_profile.keys()),
            }
            if config.output_persona_subset_path:
                append_jsonl(config.output_persona_subset_path, [persona_record])
            append_jsonl(config.output_profile_path, [profile_record])
            completed_ids.add(persona_id)
            generated += 1
            print(f"[PROFILE DONE] persona_id={persona_id} progress={generated}/{config.sample_size} flushed=true")
        except ProfileEnrichmentError as exc:
            failed += 1
            print(
                f"[PROFILE ERROR] persona_id={persona_id} failed={failed}/{config.max_failed_personas} "
                f"policy={config.failure_policy} error={exc}",
                file=sys.stderr,
            )
            if config.failure_policy == "abort" or failed > config.max_failed_personas:
                raise
            if config.failure_cooldown_seconds > 0:
                time.sleep(config.failure_cooldown_seconds)
            continue

    if generated < config.sample_size:
        raise ProfileEnrichmentError(
            "목표 persona profile 수를 채우지 못했습니다. "
            f"generated={generated}, target={config.sample_size}, scanned={scanned}, failed={failed}, "
            f"max_source_scan={config.max_source_scan}. --resume으로 이어서 실행하거나 --max-source-scan을 늘려주세요."
        )

    print(
        f"[PROFILE ENRICH DONE] profiles={generated} scanned={scanned} failed={failed} "
        f"output={config.output_profile_path}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProfileEnrichmentError as exc:
        print(f"[PROFILE ENRICH ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
