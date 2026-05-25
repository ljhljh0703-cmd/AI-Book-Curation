#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Sequence

DEFAULT_EVENT_COUNTS = {
    "READ": 20,
    "READING": 3,
    "PREFERRED": 20,
    "DISLIKED": 20,
}
DEFAULT_EVENT_WEIGHTS = {
    "READ": 1.0,
    "READING": 3.0,
    "PREFERRED": 3.0,
    "DISLIKED": 0.0,
}


@dataclass(frozen=True)
class CandidateRow:
    user_key: str
    item_key: str
    event_type: str
    source_path: str
    raw: Dict[str, Any]


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build LightFM-ready synthetic event JSONL from persona/book candidate files. "
            "This script never invents books; it only samples rows that already exist in the input files."
        )
    )
    parser.add_argument(
        "--input-path",
        action="append",
        default=[],
        help="JSONL/JSON/CSV file or directory containing persona-book candidates. Can be repeated.",
    )
    parser.add_argument(
        "--output-path",
        required=True,
        help="Output JSONL path for normalized synthetic events.",
    )
    parser.add_argument("--user-field", default="user_key,user_id,persona_id")
    parser.add_argument("--item-field", default="isbn13,isbn,book_key,book_id,item_id")
    parser.add_argument("--event-type-field", default="event_type,behavior_type,target_event_type,intent,bucket")
    parser.add_argument("--qdrant-score-field", default="qdrant_score,score,similarity")
    parser.add_argument(
        "--event-counts",
        default=",".join(f"{key}:{value}" for key, value in DEFAULT_EVENT_COUNTS.items()),
        help="Comma-separated target counts, e.g. READ:20,READING:3,PREFERRED:20,DISLIKED:20",
    )
    parser.add_argument(
        "--event-weights",
        default=",".join(f"{key}:{value}" for key, value in DEFAULT_EVENT_WEIGHTS.items()),
        help="Comma-separated base weights, e.g. READ:1.0,READING:3.0,PREFERRED:3.0,DISLIKED:0.0",
    )
    parser.add_argument("--source-weight", type=float, default=0.4)
    parser.add_argument("--user-source", default="SYNTHETIC_PERSONA")
    parser.add_argument("--profile-version", default="persona_profile_v1")
    parser.add_argument("--generation-version", default="synthetic_event_v1")
    parser.add_argument("--qdrant-collection", default="books_kure")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--strict-counts", action="store_true", help="Fail when any persona lacks enough candidates for a target event type.")
    args = parser.parse_args()

    input_paths = resolve_input_paths(args.input_path)
    if not input_paths:
        raise SystemExit("No input paths were provided. Pass --input-path at least once.")

    event_counts = parse_count_map(args.event_counts)
    event_weights = parse_weight_map(args.event_weights)
    user_fields = split_field_names(args.user_field)
    item_fields = split_field_names(args.item_field)
    event_type_fields = split_field_names(args.event_type_field)
    qdrant_score_fields = split_field_names(args.qdrant_score_field)

    candidates = list(load_candidate_rows(input_paths, user_fields, item_fields, event_type_fields))
    if not candidates:
        raise SystemExit("No valid candidate rows were found. Check user/item/event field names.")

    events = build_events(
        candidates=candidates,
        event_counts=event_counts,
        event_weights=event_weights,
        qdrant_score_fields=qdrant_score_fields,
        source_weight=args.source_weight,
        user_source=args.user_source,
        profile_version=args.profile_version,
        generation_version=args.generation_version,
        qdrant_collection=args.qdrant_collection,
        seed=args.seed,
        strict_counts=args.strict_counts,
    )
    if not events:
        raise SystemExit("No synthetic events were generated. Check input event_type values and event-counts.")

    output_path = Path(args.output_path).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        for event in events:
            file.write(json.dumps(event, ensure_ascii=False) + "\n")

    summary = summarize_events(events)
    print(
        "[SYNTHETIC EVENTS DONE] "
        f"output_path={output_path} personas={summary['persona_count']} events={summary['event_count']} "
        f"counts={summary['event_type_counts']}"
    )


def resolve_input_paths(raw_paths: Sequence[str]) -> List[Path]:
    paths: List[Path] = []
    for value in raw_paths or []:
        path = Path(str(value or "").strip()).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Synthetic candidate path does not exist: {path}")
        if path.is_dir():
            for suffix in ("*.jsonl", "*.json", "*.csv"):
                paths.extend(sorted(path.glob(suffix)))
        else:
            paths.append(path)
    return dedupe_paths(paths)


def dedupe_paths(paths: Iterable[Path]) -> List[Path]:
    seen: set[str] = set()
    result: List[Path] = []
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def load_candidate_rows(
    paths: Sequence[Path],
    user_fields: Sequence[str],
    item_fields: Sequence[str],
    event_type_fields: Sequence[str],
) -> Iterator[CandidateRow]:
    for path in paths:
        for row in read_rows(path):
            user_key = first_value(row, user_fields)
            item_key = first_value(row, item_fields)
            event_type = first_value(row, event_type_fields).upper()
            if not user_key or not item_key or not event_type:
                continue
            yield CandidateRow(
                user_key=user_key,
                item_key=item_key,
                event_type=event_type,
                source_path=str(path),
                raw=row,
            )


def read_rows(path: Path) -> Iterator[Dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        with path.open("r", encoding="utf-8") as file:
            for line in file:
                text = line.strip()
                if not text:
                    continue
                value = json.loads(text)
                if isinstance(value, dict):
                    yield value
        return

    if suffix == ".json":
        with path.open("r", encoding="utf-8") as file:
            value = json.load(file)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    yield item
        elif isinstance(value, dict):
            rows = value.get("candidates") or value.get("events") or value.get("data")
            if isinstance(rows, list):
                for item in rows:
                    if isinstance(item, dict):
                        yield item
            else:
                yield value
        return

    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            for row in reader:
                yield dict(row)
        return

    raise ValueError(f"Unsupported input file extension: {path}")


def build_events(
    *,
    candidates: Sequence[CandidateRow],
    event_counts: Dict[str, int],
    event_weights: Dict[str, float],
    qdrant_score_fields: Sequence[str],
    source_weight: float,
    user_source: str,
    profile_version: str,
    generation_version: str,
    qdrant_collection: str,
    seed: int,
    strict_counts: bool,
) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, List[CandidateRow]]] = defaultdict(lambda: defaultdict(list))
    seen_user_items: set[tuple[str, str]] = set()
    for row in candidates:
        key = (row.user_key, row.item_key)
        if key in seen_user_items:
            continue
        seen_user_items.add(key)
        grouped[row.user_key][row.event_type].append(row)

    rng = random.Random(seed)
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    events: List[Dict[str, Any]] = []

    for user_key in sorted(grouped):
        for event_type, target_count in event_counts.items():
            bucket = list(grouped[user_key].get(event_type, []))
            if not bucket:
                if strict_counts and target_count > 0:
                    raise ValueError(f"persona={user_key} has no candidates for event_type={event_type}")
                continue
            rng.shuffle(bucket)
            selected = bucket[:target_count]
            if strict_counts and len(selected) < target_count:
                raise ValueError(
                    f"persona={user_key} event_type={event_type} expected={target_count} actual={len(selected)}"
                )
            for ordinal, row in enumerate(selected, start=1):
                base_weight = float(event_weights.get(event_type, 1.0))
                final_weight = round(max(0.0, base_weight) * max(0.0, source_weight), 6)
                event_id = stable_event_id(user_key=user_key, item_key=row.item_key, event_type=event_type)
                qdrant_score = parse_optional_float(first_value(row.raw, qdrant_score_fields))
                events.append(
                    {
                        "event_id": event_id,
                        "user_key": user_key,
                        "user_source": user_source,
                        "persona_id": user_key,
                        "book_key": row.item_key,
                        "isbn13": row.item_key,
                        "event_type": event_type,
                        "implicit_label": 1 if final_weight > 0 else 0,
                        "base_weight": base_weight,
                        "source_weight": source_weight,
                        "final_weight": final_weight,
                        "event_time": generated_at,
                        "profile_version": profile_version,
                        "generation_version": generation_version,
                        "qdrant_collection": qdrant_collection,
                        "qdrant_score": qdrant_score,
                        "metadata": {
                            "source_path": row.source_path,
                            "source_event_type": row.event_type,
                            "selection_ordinal": ordinal,
                            "training_usage": "positive" if final_weight > 0 else "filter_or_evaluation",
                        },
                    }
                )
    return events


def summarize_events(events: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    personas = {str(event.get("user_key")) for event in events}
    counts: Dict[str, int] = defaultdict(int)
    for event in events:
        counts[str(event.get("event_type"))] += 1
    return {
        "persona_count": len(personas),
        "event_count": len(events),
        "event_type_counts": dict(sorted(counts.items())),
    }


def stable_event_id(*, user_key: str, item_key: str, event_type: str) -> str:
    digest = hashlib.sha1(f"{user_key}|{item_key}|{event_type}".encode("utf-8")).hexdigest()[:16]
    return f"synthetic:{digest}"


def first_value(row: Dict[str, Any], field_names: Sequence[str], default: str = "") -> str:
    for field_name in field_names:
        value = row.get(field_name)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return default


def parse_optional_float(value: str) -> float | None:
    try:
        text = str(value or "").strip()
        return float(text) if text else None
    except (TypeError, ValueError):
        return None


def split_field_names(value: str) -> List[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def parse_count_map(value: str) -> Dict[str, int]:
    result: Dict[str, int] = {}
    for item in split_field_names(value):
        key, raw_count = split_pair(item, default_value="0")
        count = int(raw_count)
        if count < 0:
            raise ValueError(f"event count must be non-negative: {item}")
        result[key.upper()] = count
    return result


def parse_weight_map(value: str) -> Dict[str, float]:
    result: Dict[str, float] = {}
    for item in split_field_names(value):
        key, raw_weight = split_pair(item, default_value="1.0")
        result[key.upper()] = float(raw_weight)
    return result


def split_pair(value: str, default_value: str) -> tuple[str, str]:
    text = str(value or "").strip()
    if not text:
        return "", default_value
    if ":" not in text:
        return text.upper(), default_value
    key, raw_value = text.split(":", 1)
    return key.strip().upper(), raw_value.strip() or default_value


if __name__ == "__main__":
    main()
