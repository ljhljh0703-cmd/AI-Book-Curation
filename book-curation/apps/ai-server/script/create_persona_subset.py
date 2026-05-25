#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from common_env import load_ai_server_env

# 수정 포인트: CLI 실행 시 apps/ai-server/.env.local을 자동 로드합니다.
AI_SERVER_ROOT = load_ai_server_env(Path(__file__))

try:
    from datasets import load_dataset
except Exception:  # pragma: no cover - 실행 환경에서 명확한 메시지를 내기 위해 지연 처리합니다.
    load_dataset = None  # type: ignore[assignment]

SCALAR_TYPES = (str, int, float, bool)


def stable_hash(value: Any, length: int = 16) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_csv(value: str) -> list[str]:
    return [part.strip() for part in str(value or "").split(",") if part.strip()]


def compact_value(value: Any, max_chars: int = 1200) -> Any:
    """Keep original scalar/list/dict shape where possible while protecting output size."""
    if value is None:
        return None
    if isinstance(value, SCALAR_TYPES):
        text = " ".join(str(value).replace("\n", " ").split())
        return text[:max_chars]
    if isinstance(value, list):
        return [compact_value(item, max_chars=max_chars) for item in value[:50]]
    if isinstance(value, dict):
        return {str(key): compact_value(item, max_chars=max_chars) for key, item in list(value.items())[:50]}
    text = " ".join(json.dumps(value, ensure_ascii=False, default=str).replace("\n", " ").split())
    return text[:max_chars]


def select_fields(row: Mapping[str, Any], fields: Sequence[str], max_field_chars: int) -> dict[str, Any]:
    selected_names = [field for field in fields if field in row] if fields else list(row.keys())
    selected: dict[str, Any] = {}
    for field in selected_names:
        value = compact_value(row.get(field), max_chars=max_field_chars)
        if value in (None, "", [], {}):
            continue
        selected[field] = value
    return selected


def resolve_persona_id(row: Mapping[str, Any], index: int, persona_id_field: str) -> str:
    candidate_fields = [persona_id_field, "persona_id", "id", "user_id", "uuid", "record_id"]
    for field in candidate_fields:
        if not field:
            continue
        value = row.get(field)
        if value not in (None, ""):
            return f"persona:{str(value).strip()}"
    return f"persona:nemotron:{index:06d}:{stable_hash(row)}"


def iter_streaming_rows(args: argparse.Namespace) -> Iterable[tuple[int, dict[str, Any]]]:
    if load_dataset is None:
        raise SystemExit(
            "datasets 패키지가 없습니다. apps/ai-server에서 `py -3.11 -m pip install -r requirements-lightfm-training.txt`를 먼저 실행해주세요."
        )

    dataset_kwargs: dict[str, Any] = {
        "split": args.dataset_split,
        "streaming": True,
    }
    if args.hf_token:
        dataset_kwargs["token"] = args.hf_token

    # 수정 포인트: 로컬 input 경로 없이 Hugging Face streaming으로 직접 읽습니다.
    dataset = load_dataset(args.dataset_name, **dataset_kwargs)
    if args.shuffle_buffer_size > 0:
        dataset = dataset.shuffle(buffer_size=args.shuffle_buffer_size, seed=args.seed)

    for index, row in enumerate(dataset):
        if index >= args.sample_size:
            break
        if isinstance(row, dict):
            yield index, row


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a JSONL subset from nvidia/Nemotron-Personas-Korea using Hugging Face streaming.")
    parser.add_argument("--dataset-name", default="nvidia/Nemotron-Personas-Korea")
    parser.add_argument("--dataset-split", default="train")
    parser.add_argument("--sample-size", type=int, required=True)
    parser.add_argument("--output-path", required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--shuffle-buffer-size", type=int, default=10_000)
    parser.add_argument("--hf-token", default=os.getenv("HF_TOKEN", ""))
    parser.add_argument("--persona-id-field", default="")
    parser.add_argument("--persona-fields", default="", help="Comma-separated fields. Empty means all available non-empty fields.")
    parser.add_argument("--max-field-chars", type=int, default=1200)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = Path(args.output_path).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fields = parse_csv(args.persona_fields)

    count = 0
    with output_path.open("w", encoding="utf-8") as fp:
        for index, row in iter_streaming_rows(args):
            persona_fields = select_fields(row, fields, max_field_chars=args.max_field_chars)
            if not persona_fields:
                continue
            persona_id = resolve_persona_id(row, index=index, persona_id_field=args.persona_id_field)
            record = {
                "persona_id": persona_id,
                "synthetic_user_id": persona_id,
                "dataset_name": args.dataset_name,
                "dataset_split": args.dataset_split,
                "source_index": index,
                "persona_fields": persona_fields,
                "persona_hash": stable_hash(persona_fields),
                "created_at": now_iso(),
            }
            fp.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            fp.write("\n")
            count += 1

    print(f"[PERSONA SUBSET DONE] output_path={output_path} rows={count} ai_server_root={AI_SERVER_ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
