#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from common_env import load_ai_server_env

# 수정 포인트: 학습 스크립트도 app.core.config와 같은 .env/.env.local 값을 사용하게 합니다.
load_ai_server_env(Path(__file__))
from typing import Any, Dict, Iterable, Iterator, List, Sequence


DEFAULT_EXCLUDED_EVENT_TYPES = {"DISLIKED", "DISLIKE_ADD", "DISLIKE_REMOVE", "NOT_INTERESTED", "UNLIKE", "BLOCK", "NEGATIVE"}
DEFAULT_EVENT_WEIGHTS = {
    "READ": 1.0,
    "READING": 3.0,
    "PREFERRED": 3.0,
    "FAVORITE": 3.0,
    "INTERESTED": 2.5,
    # 수정 포인트: backend UserBehaviorEventType enum과 synthetic event 기본값을 그대로 학습 입력으로 받을 수 있게 합니다.
    "FAVORITE_ADD": 3.0,
    "READING_ADD": 3.0,
    "READ_ADD": 1.0,
    "RATING_ADD": 4.0,
    "REVIEW_ADD": 4.0,
    "RATING_HIGH": 4.0,
    "REVIEW_POSITIVE": 4.0,
}


@dataclass(frozen=True)
class TrainingEvent:
    user_id: str
    item_id: str
    event_type: str
    weight: float
    source: str


@dataclass(frozen=True)
class EventCollection:
    events: List[TrainingEvent]
    source_counts: Dict[str, int]
    real_event_count: int
    synthetic_event_count: int


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Train LightFM from synthetic/real interaction files. "
            "Use --events-path repeatedly or set LIGHTFM_TRAIN_EVENTS_PATH with comma-separated paths."
        )
    )
    parser.add_argument(
        "--events-path",
        action="append",
        default=[],
        help="JSONL/JSON/CSV file or directory containing training events. Can be repeated.",
    )
    parser.add_argument(
        "--output-dir",
        default=os.getenv("LIGHTFM_OUTPUT_DIR", "artifacts/lightfm/latest"),
        help="Directory where model.joblib, mappings.json and metadata.json will be written.",
    )
    parser.add_argument("--user-field", default=os.getenv("LIGHTFM_USER_FIELD", "user_key,user_id,persona_id"))
    parser.add_argument("--item-field", default=os.getenv("LIGHTFM_ITEM_FIELD", "isbn13,isbn,book_key,book_id,item_id"))
    parser.add_argument("--event-type-field", default=os.getenv("LIGHTFM_EVENT_TYPE_FIELD", "event_type,type,action"))
    parser.add_argument("--weight-field", default=os.getenv("LIGHTFM_WEIGHT_FIELD", "final_weight,weight,base_weight"))
    parser.add_argument("--source-field", default=os.getenv("LIGHTFM_SOURCE_FIELD", "user_source,event_source,source"))
    parser.add_argument(
        "--excluded-event-types",
        default=os.getenv("LIGHTFM_EXCLUDED_EVENT_TYPES", ",".join(sorted(DEFAULT_EXCLUDED_EVENT_TYPES))),
        help="Comma-separated event types excluded from positive WARP training.",
    )
    parser.add_argument("--loss", default=env_str("LIGHTFM_LOSS", "LIGHTFM_TRAINING_LOSS", default="warp"), choices=["warp", "bpr", "warp-kos"])
    parser.add_argument("--components", type=int, default=env_int("LIGHTFM_NO_COMPONENTS", "LIGHTFM_TRAINING_NO_COMPONENTS", default=32))
    parser.add_argument("--epochs", type=int, default=env_int("LIGHTFM_EPOCHS", "LIGHTFM_TRAINING_EPOCHS", default=10))
    parser.add_argument("--learning-rate", type=float, default=env_float("LIGHTFM_LEARNING_RATE", "LIGHTFM_TRAINING_LEARNING_RATE", default=0.03))
    parser.add_argument("--item-alpha", type=float, default=env_float("LIGHTFM_ITEM_ALPHA", default=0.0))
    parser.add_argument("--user-alpha", type=float, default=env_float("LIGHTFM_USER_ALPHA", default=0.0))
    parser.add_argument("--num-threads", type=int, default=env_int("LIGHTFM_NUM_THREADS", "LIGHTFM_TRAINING_NUM_THREADS", default=1))
    parser.add_argument("--max-sampled", type=int, default=env_int("LIGHTFM_MAX_SAMPLED", "LIGHTFM_TRAINING_MAX_SAMPLED", default=10))
    parser.add_argument("--training-mode", default=env_str("LIGHTFM_TRAINING_MODE", default="HYBRID_LITE"))
    parser.add_argument("--synthetic-max-ratio", type=float, default=env_float("LIGHTFM_SYNTHETIC_MAX_RATIO", "LIGHTFM_TRAINING_SYNTHETIC_MAX_RATIO", default=0.5))
    parser.add_argument("--real-weight-multiplier", type=float, default=env_float("LIGHTFM_REAL_WEIGHT_MULTIPLIER", "LIGHTFM_TRAINING_REAL_WEIGHT_MULTIPLIER", default=2.0))
    parser.add_argument("--max-rows-per-source", type=int, default=env_int("LIGHTFM_MAX_ROWS_PER_SOURCE", "LIGHTFM_TRAINING_MAX_ROWS_PER_SOURCE", default=0))
    parser.add_argument("--random-state", type=int, default=env_int("LIGHTFM_RANDOM_STATE", default=42))
    args = parser.parse_args()

    event_paths = resolve_event_paths(args.events_path)
    if not event_paths:
        raise SystemExit(
            "No training event paths were provided. Pass --events-path or set LIGHTFM_TRAIN_EVENTS_PATH."
        )

    excluded_event_types = normalize_set(args.excluded_event_types)
    user_fields = split_field_names(args.user_field)
    item_fields = split_field_names(args.item_field)
    event_type_fields = split_field_names(args.event_type_field)
    weight_fields = split_field_names(args.weight_field)
    source_fields = split_field_names(args.source_field)

    collection = collect_training_events(
        load_training_events(
            event_paths=event_paths,
            user_fields=user_fields,
            item_fields=item_fields,
            event_type_fields=event_type_fields,
            weight_fields=weight_fields,
            source_fields=source_fields,
            excluded_event_types=excluded_event_types,
        ),
        training_mode=args.training_mode,
        synthetic_max_ratio=args.synthetic_max_ratio,
        real_weight_multiplier=args.real_weight_multiplier,
        max_rows_per_source=args.max_rows_per_source,
    )
    if not collection.events:
        raise SystemExit("No positive events remained after filtering. Check schema and excluded event types.")

    train_lightfm(
        events=collection.events,
        args=args,
        event_paths=event_paths,
        excluded_event_types=excluded_event_types,
        collection=collection,
    )


def resolve_event_paths(raw_paths: Sequence[str]) -> List[Path]:
    values: List[str] = []
    values.extend(raw_paths or [])
    env_value = os.getenv("LIGHTFM_TRAIN_EVENTS_PATH", "")
    if env_value:
        values.extend(env_value.split(","))

    paths: List[Path] = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        path = Path(text).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Training event path does not exist: {path}")
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


def load_training_events(
    *,
    event_paths: Sequence[Path],
    user_fields: Sequence[str],
    item_fields: Sequence[str],
    event_type_fields: Sequence[str],
    weight_fields: Sequence[str],
    source_fields: Sequence[str],
    excluded_event_types: set[str],
) -> Iterator[TrainingEvent]:
    for path in event_paths:
        for row in read_rows(path):
            event_type = first_value(row, event_type_fields, default="POSITIVE").upper()
            if event_type in excluded_event_types:
                continue
            user_id = first_value(row, user_fields)
            item_id = first_value(row, item_fields)
            if not user_id or not item_id:
                continue
            explicit_weight = first_value(row, weight_fields)
            weight = parse_weight(explicit_weight, event_type)
            if weight <= 0:
                continue
            source = first_value(row, source_fields, default="UNKNOWN")
            yield TrainingEvent(
                user_id=user_id,
                item_id=item_id,
                event_type=event_type,
                weight=weight,
                source=source,
            )


def collect_training_events(
    events: Iterable[TrainingEvent],
    *,
    training_mode: str,
    synthetic_max_ratio: float,
    real_weight_multiplier: float,
    max_rows_per_source: int,
) -> EventCollection:
    """운영 NAS 학습용 입력을 source별로 제한하고 hybrid-lite 비율을 적용합니다."""
    normalized_mode = str(training_mode or "HYBRID_LITE").strip().upper()
    per_source_seen: defaultdict[str, int] = defaultdict(int)
    real_events: List[TrainingEvent] = []
    synthetic_events: List[TrainingEvent] = []

    for event in events:
        source_key = str(event.source or "UNKNOWN").strip() or "UNKNOWN"
        if max_rows_per_source > 0 and per_source_seen[source_key] >= max_rows_per_source:
            continue
        per_source_seen[source_key] += 1

        if is_real_user_event(event):
            adjusted_weight = max(0.0, float(event.weight) * max(0.0, float(real_weight_multiplier)))
            if adjusted_weight > 0:
                real_events.append(TrainingEvent(event.user_id, event.item_id, event.event_type, adjusted_weight, event.source))
        else:
            synthetic_events.append(event)

    if normalized_mode in {"REAL_ONLY", "RECENT_REAL_ONLY"}:
        selected = real_events
    elif normalized_mode in {"SYNTHETIC_ONLY", "PERSONA_ONLY"}:
        selected = synthetic_events
    else:
        selected_synthetic = cap_synthetic_events(
            real_count=len(real_events),
            synthetic_events=synthetic_events,
            synthetic_max_ratio=synthetic_max_ratio,
        )
        selected = [*real_events, *selected_synthetic]

    source_counts = Counter(event.source for event in selected)
    return EventCollection(
        events=selected,
        source_counts=dict(source_counts),
        real_event_count=sum(1 for event in selected if is_real_user_event(event)),
        synthetic_event_count=sum(1 for event in selected if not is_real_user_event(event)),
    )


def cap_synthetic_events(
    *,
    real_count: int,
    synthetic_events: Sequence[TrainingEvent],
    synthetic_max_ratio: float,
) -> List[TrainingEvent]:
    if real_count <= 0:
        # 초기 운영 데이터가 거의 없을 때는 persona synthetic만으로 bootstrap 할 수 있게 둡니다.
        return list(synthetic_events)
    ratio = max(0.0, min(float(synthetic_max_ratio), 1.0))
    if ratio <= 0.0:
        return []
    if ratio >= 1.0:
        return list(synthetic_events)
    max_synthetic = int((real_count * ratio) / max(1e-9, 1.0 - ratio))
    return list(synthetic_events)[:max(0, max_synthetic)]


def is_real_user_event(event: TrainingEvent) -> bool:
    source = str(event.source or "").strip().upper()
    return source.startswith("REAL_USER") or str(event.user_id or "").startswith("real_user:")


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
            rows = value.get("events") or value.get("data") or []
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

    raise ValueError(f"Unsupported event file extension: {path}")


def train_lightfm(
    *,
    events: Sequence[TrainingEvent],
    args: argparse.Namespace,
    event_paths: Sequence[Path],
    excluded_event_types: set[str],
    collection: EventCollection,
) -> None:
    try:
        import joblib
        from lightfm import LightFM
        from lightfm.data import Dataset
    except ImportError as exc:
        raise SystemExit(
            "LightFM training dependencies are missing. Install requirements.txt first. "
            f"Import error: {exc}"
        ) from exc

    users = sorted({event.user_id for event in events})
    items = sorted({event.item_id for event in events})
    dataset = Dataset()
    dataset.fit(users=users, items=items)
    interactions, weights = dataset.build_interactions(
        (event.user_id, event.item_id, event.weight) for event in events
    )

    model = LightFM(
        no_components=args.components,
        loss=args.loss,
        learning_rate=args.learning_rate,
        item_alpha=args.item_alpha,
        user_alpha=args.user_alpha,
        max_sampled=max(1, int(args.max_sampled)),
        random_state=args.random_state,
    )
    model.fit(
        interactions=interactions,
        sample_weight=weights,
        epochs=args.epochs,
        num_threads=max(1, args.num_threads),
        verbose=True,
    )

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    user_id_map, _, item_id_map, _ = dataset.mapping()
    artifact_version = datetime.now(timezone.utc).strftime("lightfm_%Y%m%dT%H%M%SZ")

    joblib.dump(model, output_dir / "model.joblib")
    weights_dict = {
        "user_embeddings": model.user_embeddings,
        "item_embeddings": model.item_embeddings,
        "user_biases": model.user_biases,
        "item_biases": model.item_biases,
    }
    joblib.dump(weights_dict, output_dir / "weights.joblib")
    with (output_dir / "mappings.json").open("w", encoding="utf-8") as file:
        json.dump(
            {
                "user_id_to_index": {str(user): int(index) for user, index in user_id_map.items()},
                "item_id_to_index": {str(item): int(index) for item, index in item_id_map.items()},
            },
            file,
            ensure_ascii=False,
            indent=2,
        )
    with (output_dir / "metadata.json").open("w", encoding="utf-8") as file:
        json.dump(
            {
                "artifact_version": artifact_version,
                "trained_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "event_count": len(events),
                "positive_event_count": len(events),
                "user_count": len(users),
                "item_count": len(items),
                "real_event_count": collection.real_event_count,
                "synthetic_event_count": collection.synthetic_event_count,
                "source_counts": collection.source_counts,
                "event_paths": [str(path) for path in event_paths],
                "excluded_event_types": sorted(excluded_event_types),
                "training_mode": args.training_mode,
                "loss": args.loss,
                "no_components": args.components,
                "epochs": args.epochs,
                "learning_rate": args.learning_rate,
                "max_sampled": args.max_sampled,
                "num_threads": args.num_threads,
                "synthetic_max_ratio": args.synthetic_max_ratio,
                "real_weight_multiplier": args.real_weight_multiplier,
                "max_rows_per_source": args.max_rows_per_source,
                "item_alpha": args.item_alpha,
                "user_alpha": args.user_alpha,
                "random_state": args.random_state,
            },
            file,
            ensure_ascii=False,
            indent=2,
        )

    print(
        "[LIGHTFM TRAINING DONE] "
        f"output_dir={output_dir} users={len(users)} items={len(items)} events={len(events)} version={artifact_version}"
    )


def env_str(*names: str, default: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return default


def env_int(*names: str, default: int) -> int:
    value = env_str(*names, default=str(default))
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def env_float(*names: str, default: float) -> float:
    value = env_str(*names, default=str(default))
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def first_value(row: Dict[str, Any], field_names: Sequence[str], default: str = "") -> str:
    for field_name in field_names:
        value = row.get(field_name)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return default


def parse_weight(value: str, event_type: str) -> float:
    try:
        if str(value or "").strip():
            return float(value)
    except (TypeError, ValueError):
        pass
    return float(DEFAULT_EVENT_WEIGHTS.get(event_type, 1.0))


def split_field_names(value: str) -> List[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def normalize_set(value: str) -> set[str]:
    return {item.strip().upper() for item in str(value or "").split(",") if item.strip()}


if __name__ == "__main__":
    main()
