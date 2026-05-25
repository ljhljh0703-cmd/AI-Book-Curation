#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

import joblib
import numpy as np
from lightfm import LightFM
from lightfm.data import Dataset
from lightfm.evaluation import auc_score
from scipy import sparse

DEFAULT_EXCLUDED_EVENT_TYPES = {
    "DISLIKE_ADD",
    "DISLIKE_REMOVE",
    "DISLIKED",
    "NOT_INTERESTED",
    "UNLIKE",
    "BLOCK",
    "NEGATIVE",
}
DEFAULT_DISLIKE_EVENT_TYPES = {"DISLIKE_ADD", "DISLIKED", "NOT_INTERESTED", "NEGATIVE"}
DEFAULT_EVENT_WEIGHTS = {
    "READ": 1.0,
    "READING": 3.0,
    "PREFERRED": 3.0,
    "FAVORITE": 3.0,
    "INTERESTED": 2.5,
    # 수정 포인트: 현재 synthetic event generator와 backend enum에서 사용하는 이벤트명을 그대로 받습니다.
    "FAVORITE_ADD": 3.0,
    "READING_ADD": 3.0,
    "READ_ADD": 1.0,
    "RATING_ADD": 4.0,
    "REVIEW_ADD": 4.0,
    "RATING_HIGH": 4.0,
    "REVIEW_POSITIVE": 4.0,
}

DEFAULT_USER_CATEGORICAL_FIELDS = (
    "user_age_group",
    "age_group_source",
    "profile_strategy",
    "profile_schema_version",
    "rule_mode",
)
DEFAULT_USER_TEXT_FIELDS = (
    "profile_query_text",
    "reading_purpose_summary",
    "reading_purpose",
    "interest_profile_text",
    "preference_summary",
    "reading_now_profile_text",
    "read_completed_profile_text",
    "dislike_profile_text",
)
DEFAULT_ITEM_CATEGORICAL_FIELDS = (
    "category",
    "categories",
    "author",
    "publisher",
)
DEFAULT_ITEM_TEXT_FIELDS = (
    "title",
    "category",
    "categories",
    "description",
)


@dataclass(frozen=True)
class ParsedEvent:
    user_id: str
    item_id: str
    event_type: str
    weight: float
    row: dict[str, Any]


@dataclass(frozen=True)
class SplitEvents:
    train: list[ParsedEvent]
    validation: list[ParsedEvent]
    test: list[ParsedEvent]
    dislikes: list[ParsedEvent]


@dataclass(frozen=True)
class FeatureBundle:
    user_features_by_id: dict[str, list[str]]
    item_features_by_id: dict[str, list[str]]
    user_feature_names: list[str]
    item_feature_names: list[str]
    user_feature_matrix: sparse.csr_matrix | None
    item_feature_matrix: sparse.csr_matrix | None


@dataclass(frozen=True)
class TrainedModel:
    model: LightFM
    dataset: Dataset
    user_id_to_index: dict[str, int]
    item_id_to_index: dict[str, int]
    item_index_to_id: dict[int, str]
    user_feature_id_to_index: dict[str, int]
    item_feature_id_to_index: dict[str, int]
    user_features: sparse.csr_matrix | None
    item_features: sparse.csr_matrix | None
    feature_mode: str


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Train/evaluate LightFM with a 7:2:1 split. Supports identity-only and hybrid modes. "
            "DISLIKE events are never used as positive training interactions; they are used only for avoidance metrics."
        )
    )
    parser.add_argument("--events-path", action="append", required=True, help="JSONL/JSON/CSV event file. Can be repeated.")
    parser.add_argument("--user-features-path", action="append", default=[], help="Optional real/synthetic user feature JSONL/JSON/CSV file. Can be repeated.")
    parser.add_argument("--item-features-path", action="append", default=[], help="Optional real/synthetic item feature JSONL/JSON/CSV file. Can be repeated.")
    parser.add_argument("--user-feature-id-field", default="user_key,user_id,synthetic_user_id,persona_id,real_user_id")
    parser.add_argument("--item-feature-id-field", default="isbn13,isbn,book_key,book_id,item_id")
    parser.add_argument("--external-feature-field", default="features,feature_names,lightfm_features")
    parser.add_argument("--output-dir", required=True, help="Directory for final model artifact and metrics.json.")
    parser.add_argument("--user-field", default="user_key,user_id,persona_id,synthetic_user_id")
    parser.add_argument("--item-field", default="isbn13,isbn,book_key,book_id,item_id")
    parser.add_argument("--event-type-field", default="event_type,type,action")
    parser.add_argument("--weight-field", default="final_weight,weight,base_weight,score")
    parser.add_argument(
        "--excluded-event-types",
        default=",".join(sorted(DEFAULT_EXCLUDED_EVENT_TYPES)),
        help="Events excluded from positive LightFM training. Dislikes should remain here.",
    )
    parser.add_argument(
        "--dislike-event-types",
        default=",".join(sorted(DEFAULT_DISLIKE_EVENT_TYPES)),
        help="Events used only as negative evaluation labels.",
    )
    parser.add_argument("--train-ratio", type=float, default=0.7)
    parser.add_argument("--validation-ratio", type=float, default=0.2)
    parser.add_argument("--test-ratio", type=float, default=0.1)
    parser.add_argument("--loss", default="warp", choices=["warp", "bpr", "warp-kos"])
    parser.add_argument("--components", type=int, default=64)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--learning-rate", type=float, default=0.05)
    parser.add_argument("--item-alpha", type=float, default=0.0)
    parser.add_argument("--user-alpha", type=float, default=0.0)
    parser.add_argument("--num-threads", type=int, default=2)
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument(
        "--candidate-eval-pool-size",
        type=int,
        default=0,
        help=(
            "When > 0, also evaluate the operational candidate-compression scenario. "
            "Example: 50 candidates -> top 20 by LightFM score."
        ),
    )
    parser.add_argument(
        "--candidate-eval-top-k",
        type=int,
        default=0,
        help="Top-K to keep inside the simulated candidate pool. If omitted, uses --k.",
    )
    parser.add_argument(
        "--candidate-eval-random-state",
        type=int,
        default=42,
        help="Random seed used only for filling neutral items in the simulated candidate pool.",
    )
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument(
        "--feature-mode",
        choices=("identity", "hybrid"),
        default="hybrid",
        help="identity는 user_id/item_id만 사용합니다. hybrid는 user/item feature를 함께 사용합니다.",
    )
    parser.add_argument("--user-categorical-fields", default=",".join(DEFAULT_USER_CATEGORICAL_FIELDS))
    parser.add_argument("--user-text-fields", default=",".join(DEFAULT_USER_TEXT_FIELDS))
    parser.add_argument("--item-categorical-fields", default=",".join(DEFAULT_ITEM_CATEGORICAL_FIELDS))
    parser.add_argument("--item-text-fields", default=",".join(DEFAULT_ITEM_TEXT_FIELDS))
    parser.add_argument("--max-user-text-features", type=int, default=80)
    parser.add_argument("--max-item-text-features", type=int, default=80)
    parser.add_argument("--max-token-chars", type=int, default=40)
    parser.add_argument("--min-token-chars", type=int, default=2)
    parser.add_argument(
        "--normalize-feature-matrices",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="LightFM Dataset.build_user_features/build_item_features normalize 옵션입니다.",
    )
    parser.add_argument(
        "--save-final-model",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="After validation/test evaluation, train a final model on all positive events and save it.",
    )
    args = parser.parse_args()

    validate_ratios(args.train_ratio, args.validation_ratio, args.test_ratio)

    excluded_types = normalize_set(args.excluded_event_types)
    dislike_types = normalize_set(args.dislike_event_types)
    positive_events, dislike_events, raw_counter = load_events(
        event_paths=resolve_event_paths(args.events_path),
        user_fields=split_field_names(args.user_field),
        item_fields=split_field_names(args.item_field),
        event_type_fields=split_field_names(args.event_type_field),
        weight_fields=split_field_names(args.weight_field),
        excluded_event_types=excluded_types,
        dislike_event_types=dislike_types,
    )
    if not positive_events:
        raise SystemExit("No positive events remained after filtering. Check event types and schema.")

    user_feature_rows = load_external_feature_rows(resolve_optional_paths(args.user_features_path))
    item_feature_rows = load_external_feature_rows(resolve_optional_paths(args.item_features_path))

    all_events = [*positive_events, *dislike_events]
    feature_source = build_feature_source(
        all_events=all_events,
        feature_mode=args.feature_mode,
        user_categorical_fields=split_field_names(args.user_categorical_fields),
        user_text_fields=split_field_names(args.user_text_fields),
        item_categorical_fields=split_field_names(args.item_categorical_fields),
        item_text_fields=split_field_names(args.item_text_fields),
        max_user_text_features=args.max_user_text_features,
        max_item_text_features=args.max_item_text_features,
        max_token_chars=args.max_token_chars,
        min_token_chars=args.min_token_chars,
        external_user_feature_rows=user_feature_rows,
        external_item_feature_rows=item_feature_rows,
        user_feature_id_fields=split_field_names(args.user_feature_id_field),
        item_feature_id_fields=split_field_names(args.item_feature_id_field),
        external_feature_fields=split_field_names(args.external_feature_field),
    )

    split = split_positive_events_by_user(
        positive_events=positive_events,
        dislike_events=dislike_events,
        train_ratio=args.train_ratio,
        validation_ratio=args.validation_ratio,
        test_ratio=args.test_ratio,
        random_state=args.random_state,
    )

    print("[LIGHTFM 7:2:1 HYBRID SPLIT]")
    print(f"raw_event_counts={dict(raw_counter)}")
    print(f"positive_events={len(positive_events)}")
    print(f"dislike_events_for_negative_eval={len(dislike_events)}")
    print(f"train_positive={len(split.train)} validation_positive={len(split.validation)} test_positive={len(split.test)}")
    print(f"feature_mode={args.feature_mode}")
    print(f"user_feature_count={len(feature_source.user_feature_names)} item_feature_count={len(feature_source.item_feature_names)}")
    print(f"external_user_feature_rows={len(user_feature_rows)} external_item_feature_rows={len(item_feature_rows)}")
    print(f"excluded_event_types={sorted(excluded_types)}")
    print(f"dislike_event_types={sorted(dislike_types)}")
    print("DISLIKE events are not used in LightFM positive training; they are used only for avoidance metrics.")

    # 수정 포인트: validation은 train 70%로 평가하고, test는 train+validation 90%로 재학습 후 평가합니다.
    # hybrid 모드에서는 user/item feature matrices를 모든 학습·평가 함수에 동일하게 전달합니다.
    val_model = train_model(
        train_events=split.train,
        all_events=all_events,
        feature_source=feature_source,
        args=args,
        label="validation_train70",
    )
    validation_metrics = evaluate_model(
        trained=val_model,
        eval_positive_events=split.validation,
        dislike_events=split.dislikes,
        exclude_positive_events=split.train,
        k=args.k,
        num_threads=args.num_threads,
        label="validation",
        candidate_eval_pool_size=args.candidate_eval_pool_size,
        candidate_eval_top_k=args.candidate_eval_top_k or args.k,
        candidate_eval_random_state=args.candidate_eval_random_state,
    )

    test_train_events = [*split.train, *split.validation]
    test_model = train_model(
        train_events=test_train_events,
        all_events=all_events,
        feature_source=feature_source,
        args=args,
        label="test_train90",
    )
    test_metrics = evaluate_model(
        trained=test_model,
        eval_positive_events=split.test,
        dislike_events=split.dislikes,
        exclude_positive_events=test_train_events,
        k=args.k,
        num_threads=args.num_threads,
        label="test",
        candidate_eval_pool_size=args.candidate_eval_pool_size,
        candidate_eval_top_k=args.candidate_eval_top_k or args.k,
        candidate_eval_random_state=args.candidate_eval_random_state,
    )

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    final_artifact_metadata: dict[str, Any] = {}
    if args.save_final_model:
        final_model = train_model(
            train_events=positive_events,
            all_events=all_events,
            feature_source=feature_source,
            args=args,
            label="final_train100_positive",
        )
        final_artifact_metadata = save_artifact(
            trained=final_model,
            output_dir=output_dir,
            positive_events=positive_events,
            dislike_events=dislike_events,
            feature_source=feature_source,
            args=args,
        )

    metrics = {
        "created_at": utc_now_iso(),
        "training_type": "lightfm_701_hybrid" if args.feature_mode == "hybrid" else "lightfm_701_identity",
        "split": {
            "train_ratio": args.train_ratio,
            "validation_ratio": args.validation_ratio,
            "test_ratio": args.test_ratio,
            "train_positive": len(split.train),
            "validation_positive": len(split.validation),
            "test_positive": len(split.test),
            "dislike_events": len(split.dislikes),
        },
        "raw_event_counts": dict(raw_counter),
        "excluded_event_types": sorted(excluded_types),
        "dislike_event_types": sorted(dislike_types),
        "feature_summary": {
            "feature_mode": args.feature_mode,
            "user_feature_count": len(feature_source.user_feature_names),
            "item_feature_count": len(feature_source.item_feature_names),
            "user_count_with_features": sum(1 for value in feature_source.user_features_by_id.values() if value),
            "item_count_with_features": sum(1 for value in feature_source.item_features_by_id.values() if value),
            "user_categorical_fields": split_field_names(args.user_categorical_fields),
            "user_text_fields": split_field_names(args.user_text_fields),
            "item_categorical_fields": split_field_names(args.item_categorical_fields),
            "item_text_fields": split_field_names(args.item_text_fields),
            "external_user_feature_rows": len(user_feature_rows),
            "external_item_feature_rows": len(item_feature_rows),
            "user_features_path": [str(path) for path in resolve_optional_paths(args.user_features_path)],
            "item_features_path": [str(path) for path in resolve_optional_paths(args.item_features_path)],
        },
        "hyperparameters": {
            "loss": args.loss,
            "components": args.components,
            "epochs": args.epochs,
            "learning_rate": args.learning_rate,
            "item_alpha": args.item_alpha,
            "user_alpha": args.user_alpha,
            "num_threads": args.num_threads,
            "k": args.k,
            "candidate_eval_pool_size": args.candidate_eval_pool_size,
            "candidate_eval_top_k": args.candidate_eval_top_k or args.k,
            "candidate_eval_random_state": args.candidate_eval_random_state,
            "random_state": args.random_state,
            "normalize_feature_matrices": args.normalize_feature_matrices,
        },
        "validation": validation_metrics,
        "test": test_metrics,
        "final_artifact": final_artifact_metadata,
        "metric_notes": {
            "positive_metrics": "Higher is better. Computed from held-out positive events.",
            "dislike_metrics": "Lower is better. DISLIKE events are not used for training; they are used only as negative evaluation labels.",
            "hybrid_note": "Hybrid mode passes user_features and item_features to LightFM training, prediction, and AUC evaluation.",
            "candidate_eval_note": "When candidate_eval_pool_size > 0, the script simulates the 50->20 candidate-compression step by scoring only a per-user candidate pool that contains held-out positives, held-out dislikes, and randomly sampled neutral items. This approximates the operational LightFM reranking stage without calling Qdrant.",
        },
    }
    with (output_dir / "metrics.json").open("w", encoding="utf-8") as file:
        json.dump(metrics, file, ensure_ascii=False, indent=2)

    print_metrics("validation", validation_metrics)
    print_metrics("test", test_metrics)
    print(f"[LIGHTFM 7:2:1 HYBRID DONE] output_dir={output_dir}")
    print(f"metrics_path={output_dir / 'metrics.json'}")


def validate_ratios(train_ratio: float, validation_ratio: float, test_ratio: float) -> None:
    total = train_ratio + validation_ratio + test_ratio
    if not math.isclose(total, 1.0, rel_tol=1e-6, abs_tol=1e-6):
        raise SystemExit(f"train/validation/test ratios must sum to 1.0. actual={total}")
    if min(train_ratio, validation_ratio, test_ratio) <= 0:
        raise SystemExit("train/validation/test ratios must all be positive.")


def resolve_event_paths(raw_paths: Sequence[str]) -> list[Path]:
    paths: list[Path] = []
    for value in raw_paths:
        path = Path(str(value)).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Event path does not exist: {path}")
        if path.is_dir():
            for suffix in ("*.jsonl", "*.json", "*.csv"):
                paths.extend(sorted(path.glob(suffix)))
        else:
            paths.append(path)
    return dedupe_paths(paths)


def resolve_optional_paths(raw_paths: Sequence[str]) -> list[Path]:
    paths: list[Path] = []
    for value in raw_paths or []:
        if not str(value or "").strip():
            continue
        path = Path(str(value)).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Feature path does not exist: {path}")
        if path.is_dir():
            for suffix in ("*.jsonl", "*.json", "*.csv"):
                paths.extend(sorted(path.glob(suffix)))
        else:
            paths.append(path)
    return dedupe_paths(paths)


def load_external_feature_rows(paths: Sequence[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        rows.extend(dict(row) for row in read_rows(path))
    return rows


def dedupe_paths(paths: Iterable[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def load_events(
    *,
    event_paths: Sequence[Path],
    user_fields: Sequence[str],
    item_fields: Sequence[str],
    event_type_fields: Sequence[str],
    weight_fields: Sequence[str],
    excluded_event_types: set[str],
    dislike_event_types: set[str],
) -> tuple[list[ParsedEvent], list[ParsedEvent], Counter[str]]:
    positives: list[ParsedEvent] = []
    dislikes: list[ParsedEvent] = []
    raw_counter: Counter[str] = Counter()
    for path in event_paths:
        for row in read_rows(path):
            event_type = first_value(row, event_type_fields, default="POSITIVE").upper()
            raw_counter[event_type] += 1
            user_id = first_value(row, user_fields)
            item_id = first_value(row, item_fields)
            if not user_id or not item_id:
                continue
            event = ParsedEvent(
                user_id=user_id,
                item_id=item_id,
                event_type=event_type,
                weight=parse_weight(first_value(row, weight_fields), event_type),
                row=dict(row),
            )
            if event_type in dislike_event_types:
                dislikes.append(event)
                continue
            if event_type in excluded_event_types:
                continue
            if event.weight <= 0:
                continue
            positives.append(event)
    return positives, dislikes, raw_counter


def read_rows(path: Path) -> Iterator[dict[str, Any]]:
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
            rows = value.get("events") or value.get("data")
            if isinstance(rows, list):
                for item in rows:
                    if isinstance(item, dict):
                        yield item
            else:
                yield value
        return
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            for row in csv.DictReader(file):
                yield dict(row)
        return
    raise ValueError(f"Unsupported event file extension: {path}")


def split_positive_events_by_user(
    *,
    positive_events: Sequence[ParsedEvent],
    dislike_events: Sequence[ParsedEvent],
    train_ratio: float,
    validation_ratio: float,
    test_ratio: float,
    random_state: int,
) -> SplitEvents:
    by_user: dict[str, list[ParsedEvent]] = defaultdict(list)
    for event in positive_events:
        by_user[event.user_id].append(event)

    train: list[ParsedEvent] = []
    validation: list[ParsedEvent] = []
    test: list[ParsedEvent] = []
    rng = random.Random(random_state)

    for user_id in sorted(by_user):
        events = list(by_user[user_id])
        rng.shuffle(events)
        n = len(events)
        if n < 3:
            train.extend(events)
            continue
        train_count = max(1, int(round(n * train_ratio)))
        validation_count = max(1, int(round(n * validation_ratio)))
        if train_count + validation_count >= n:
            overflow = train_count + validation_count - (n - 1)
            if validation_count > 1:
                validation_count = max(1, validation_count - overflow)
            else:
                train_count = max(1, train_count - overflow)
        test_count = n - train_count - validation_count
        if test_count <= 0:
            test_count = 1
            if validation_count > 1:
                validation_count -= 1
            else:
                train_count -= 1
        train.extend(events[:train_count])
        validation.extend(events[train_count : train_count + validation_count])
        test.extend(events[train_count + validation_count :])

    return SplitEvents(train=train, validation=validation, test=test, dislikes=list(dislike_events))


def build_feature_source(
    *,
    all_events: Sequence[ParsedEvent],
    feature_mode: str,
    user_categorical_fields: Sequence[str],
    user_text_fields: Sequence[str],
    item_categorical_fields: Sequence[str],
    item_text_fields: Sequence[str],
    max_user_text_features: int,
    max_item_text_features: int,
    max_token_chars: int,
    min_token_chars: int,
    external_user_feature_rows: Sequence[Mapping[str, Any]] = (),
    external_item_feature_rows: Sequence[Mapping[str, Any]] = (),
    user_feature_id_fields: Sequence[str] = (),
    item_feature_id_fields: Sequence[str] = (),
    external_feature_fields: Sequence[str] = (),
) -> FeatureBundle:
    if feature_mode == "identity":
        return FeatureBundle({}, {}, [], [], None, None)

    rows_by_user: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rows_by_item: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in all_events:
        rows_by_user[event.user_id].append(event.row)
        rows_by_item[event.item_id].append(event.row)

    # 수정 포인트: 실사용자는 행동 이벤트가 sparse할 수 있으므로, 별도 user/item feature 파일만으로도
    # LightFM mapping과 feature matrix에 포함될 수 있게 외부 feature rows를 병합합니다.
    for row in external_user_feature_rows:
        user_id = first_value(row, user_feature_id_fields)
        if user_id:
            rows_by_user[user_id].append(dict(row))
    for row in external_item_feature_rows:
        item_id = first_value(row, item_feature_id_fields)
        if item_id:
            rows_by_item[item_id].append(dict(row))

    user_features_by_id: dict[str, list[str]] = {}
    item_features_by_id: dict[str, list[str]] = {}

    for user_id, rows in rows_by_user.items():
        user_features_by_id[user_id] = build_entity_features(
            rows=rows,
            entity_prefix="user",
            categorical_prefix="u_cat",
            text_prefix="u_text",
            categorical_fields=user_categorical_fields,
            text_fields=user_text_fields,
            max_text_features=max_user_text_features,
            max_token_chars=max_token_chars,
            min_token_chars=min_token_chars,
            external_feature_fields=external_feature_fields,
        )

    for item_id, rows in rows_by_item.items():
        item_features_by_id[item_id] = build_entity_features(
            rows=rows,
            entity_prefix="item",
            categorical_prefix="i_cat",
            text_prefix="i_text",
            categorical_fields=item_categorical_fields,
            text_fields=item_text_fields,
            max_text_features=max_item_text_features,
            max_token_chars=max_token_chars,
            min_token_chars=min_token_chars,
            external_feature_fields=external_feature_fields,
        )

    user_feature_names = sorted({feature for features in user_features_by_id.values() for feature in features})
    item_feature_names = sorted({feature for features in item_features_by_id.values() for feature in features})
    return FeatureBundle(
        user_features_by_id=user_features_by_id,
        item_features_by_id=item_features_by_id,
        user_feature_names=user_feature_names,
        item_feature_names=item_feature_names,
        user_feature_matrix=None,
        item_feature_matrix=None,
    )


def build_entity_features(
    *,
    rows: Sequence[Mapping[str, Any]],
    entity_prefix: str,
    categorical_prefix: str,
    text_prefix: str,
    categorical_fields: Sequence[str],
    text_fields: Sequence[str],
    max_text_features: int,
    max_token_chars: int,
    min_token_chars: int,
    external_feature_fields: Sequence[str] = (),
) -> list[str]:
    features: list[str] = []
    for row in rows:
        for field_name in external_feature_fields:
            for value in flatten_values(row.get(field_name)):
                text = clean_value(value, max_chars=max_token_chars * 4)
                if text:
                    features.append(text)
    for row in rows:
        for field_name in categorical_fields:
            for value in flatten_values(row.get(field_name)):
                text = clean_value(value, max_chars=max_token_chars)
                if text:
                    features.append(f"{categorical_prefix}:{field_name}:{text}")

    text_counter: Counter[str] = Counter()
    for row in rows:
        for field_name in text_fields:
            for value in flatten_values(row.get(field_name)):
                for token in tokenize_feature_text(
                    value,
                    max_token_chars=max_token_chars,
                    min_token_chars=min_token_chars,
                ):
                    text_counter[f"{text_prefix}:{field_name}:{token}"] += 1

    # 수정 포인트: title/description/profile text에서 너무 많은 고유 토큰이 feature로 들어가는 것을 막기 위해
    # 빈도순 상한을 둡니다. 특정 장르/키워드 목록을 하드코딩하지 않고 데이터 자체에서만 feature를 구성합니다.
    features.extend(feature for feature, _count in text_counter.most_common(max(0, max_text_features)))
    return sorted(set(features))


def flatten_values(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        result: list[Any] = []
        for item in value:
            result.extend(flatten_values(item))
        return result
    if isinstance(value, tuple):
        result: list[Any] = []
        for item in value:
            result.extend(flatten_values(item))
        return result
    if isinstance(value, dict):
        result: list[Any] = []
        for key, item in value.items():
            result.append(key)
            result.extend(flatten_values(item))
        return result
    text = str(value).strip()
    if not text:
        return []
    # JSON 문자열이 들어온 경우 파일을 수정하지 않고 런타임에서만 안전하게 풀어냅니다.
    if (text.startswith("{") and text.endswith("}")) or (text.startswith("[") and text.endswith("]")):
        try:
            decoded = json.loads(text)
            if decoded is not value:
                return flatten_values(decoded)
        except Exception:
            pass
    parts = re.split(r"[>/|,;·•]+", text)
    cleaned = [part.strip() for part in parts if part and part.strip()]
    return cleaned if cleaned else [text]


def clean_value(value: Any, *, max_chars: int) -> str:
    text = " ".join(str(value or "").strip().split())
    text = text.replace('\\"', '"').strip().strip('"').strip("'")
    if not text:
        return ""
    return text[:max_chars].rstrip()


def tokenize_feature_text(value: Any, *, max_token_chars: int, min_token_chars: int) -> list[str]:
    tokens: list[str] = []
    for item in flatten_values(value):
        text = clean_value(item, max_chars=2000).lower()
        if not text:
            continue
        for token in re.split(r"[^0-9a-zA-Z가-힣]+", text):
            token = token.strip()
            if len(token) < min_token_chars:
                continue
            if token.isdigit():
                continue
            tokens.append(token[:max_token_chars].rstrip())
    return tokens


def train_model(
    *,
    train_events: Sequence[ParsedEvent],
    all_events: Sequence[ParsedEvent],
    feature_source: FeatureBundle,
    args: argparse.Namespace,
    label: str,
) -> TrainedModel:
    users = sorted({event.user_id for event in all_events} | set(feature_source.user_features_by_id))
    items = sorted({event.item_id for event in all_events} | set(feature_source.item_features_by_id))
    dataset = Dataset()
    dataset.fit(
        users=users,
        items=items,
        user_features=feature_source.user_feature_names if args.feature_mode == "hybrid" else None,
        item_features=feature_source.item_feature_names if args.feature_mode == "hybrid" else None,
    )
    interactions, weights = dataset.build_interactions((event.user_id, event.item_id, event.weight) for event in train_events)

    user_features = None
    item_features = None
    if args.feature_mode == "hybrid":
        user_features = dataset.build_user_features(
            ((user_id, feature_source.user_features_by_id.get(user_id, [])) for user_id in users),
            normalize=bool(args.normalize_feature_matrices),
        )
        item_features = dataset.build_item_features(
            ((item_id, feature_source.item_features_by_id.get(item_id, [])) for item_id in items),
            normalize=bool(args.normalize_feature_matrices),
        )

    model = LightFM(
        no_components=args.components,
        loss=args.loss,
        learning_rate=args.learning_rate,
        item_alpha=args.item_alpha,
        user_alpha=args.user_alpha,
        random_state=args.random_state,
    )
    print(
        f"[LIGHTFM TRAIN] label={label} train_events={len(train_events)} users={len(users)} items={len(items)} "
        f"feature_mode={args.feature_mode} user_features={len(feature_source.user_feature_names)} item_features={len(feature_source.item_feature_names)}"
    )
    model.fit(
        interactions=interactions,
        sample_weight=weights,
        user_features=user_features,
        item_features=item_features,
        epochs=args.epochs,
        num_threads=max(1, args.num_threads),
        verbose=True,
    )
    user_id_to_index, user_feature_id_to_index, item_id_to_index, item_feature_id_to_index = dataset.mapping()
    return TrainedModel(
        model=model,
        dataset=dataset,
        user_id_to_index={str(key): int(value) for key, value in user_id_to_index.items()},
        item_id_to_index={str(key): int(value) for key, value in item_id_to_index.items()},
        item_index_to_id={int(value): str(key) for key, value in item_id_to_index.items()},
        user_feature_id_to_index={str(key): int(value) for key, value in user_feature_id_to_index.items()},
        item_feature_id_to_index={str(key): int(value) for key, value in item_feature_id_to_index.items()},
        user_features=user_features,
        item_features=item_features,
        feature_mode=args.feature_mode,
    )


def evaluate_model(
    *,
    trained: TrainedModel,
    eval_positive_events: Sequence[ParsedEvent],
    dislike_events: Sequence[ParsedEvent],
    exclude_positive_events: Sequence[ParsedEvent],
    k: int,
    num_threads: int,
    label: str,
    candidate_eval_pool_size: int,
    candidate_eval_top_k: int,
    candidate_eval_random_state: int,
) -> dict[str, Any]:
    positive_targets = events_to_user_item_index_sets(eval_positive_events, trained)
    dislike_targets = events_to_user_item_index_sets(dislike_events, trained)
    exclude_sets = events_to_user_item_index_sets(exclude_positive_events, trained)

    positive_ranking_metrics = ranking_metrics(
        trained=trained,
        targets=positive_targets,
        exclude_sets=exclude_sets,
        k=k,
        prefix="positive",
        lower_is_better=False,
    )
    dislike_ranking_metrics = ranking_metrics(
        trained=trained,
        targets=dislike_targets,
        exclude_sets=exclude_sets,
        k=k,
        prefix="dislike",
        lower_is_better=True,
    )
    candidate_metrics: dict[str, Any] = {}
    if candidate_eval_pool_size > 0:
        # 수정 포인트: 실제 운영 목표인 "후보 50개 중 LightFM 점수로 20개를 남기는" 상황을 별도 평가합니다.
        # Qdrant를 다시 호출하지 않고, held-out positive/dislike와 neutral item을 섞어 per-user candidate pool을 구성합니다.
        candidate_metrics = candidate_pool_compression_metrics(
            trained=trained,
            positive_targets=positive_targets,
            dislike_targets=dislike_targets,
            exclude_sets=exclude_sets,
            pool_size=candidate_eval_pool_size,
            top_k=candidate_eval_top_k,
            random_state=candidate_eval_random_state,
        )

    auc = compute_auc(
        trained=trained,
        train_events=exclude_positive_events,
        test_events=eval_positive_events,
        num_threads=num_threads,
    )
    metrics = {
        "label": label,
        "positive_eval_events": len(eval_positive_events),
        "dislike_eval_events": len(dislike_events),
        "evaluated_positive_users": len(positive_targets),
        "evaluated_dislike_users": len(dislike_targets),
        "auc": auc,
        **positive_ranking_metrics,
        **dislike_ranking_metrics,
        **candidate_metrics,
    }
    return metrics


def candidate_pool_compression_metrics(
    *,
    trained: TrainedModel,
    positive_targets: Mapping[int, set[int]],
    dislike_targets: Mapping[int, set[int]],
    exclude_sets: Mapping[int, set[int]],
    pool_size: int,
    top_k: int,
    random_state: int,
) -> dict[str, Any]:
    if pool_size <= 0:
        return {}
    if top_k <= 0:
        raise ValueError("candidate_eval_top_k must be positive when candidate_eval_pool_size is enabled.")
    if top_k > pool_size:
        raise ValueError("candidate_eval_top_k must be less than or equal to candidate_eval_pool_size.")

    item_count = len(trained.item_id_to_index)
    if item_count <= 0:
        return {
            "candidate_eval_pool_size": pool_size,
            "candidate_eval_top_k": top_k,
            "candidate_eval_user_count": 0,
            "candidate_eval_note": "No items available in trained mapping.",
        }

    user_indices = sorted(set(positive_targets) | set(dislike_targets))
    if not user_indices:
        return {
            "candidate_eval_pool_size": pool_size,
            "candidate_eval_top_k": top_k,
            "candidate_eval_user_count": 0,
            "candidate_eval_note": "No held-out positive/dislike users available for candidate compression evaluation.",
        }

    positive_acc = TargetMetricAccumulator(prefix=f"positive_candidate@{top_k}_in_{pool_size}", lower_is_better=False, denominator_k=top_k)
    dislike_acc = TargetMetricAccumulator(prefix=f"dislike_candidate@{top_k}_in_{pool_size}", lower_is_better=True, denominator_k=top_k)

    candidate_sizes: list[int] = []
    mandatory_positive_counts: list[int] = []
    mandatory_dislike_counts: list[int] = []

    for user_idx in user_indices:
        positive_items = set(positive_targets.get(user_idx, set()))
        dislike_items = set(dislike_targets.get(user_idx, set()))
        exclude_items = set(exclude_sets.get(user_idx, set()))

        candidate_items = build_candidate_pool_for_user(
            user_idx=user_idx,
            item_count=item_count,
            positive_items=positive_items,
            dislike_items=dislike_items,
            exclude_items=exclude_items,
            pool_size=pool_size,
            random_state=random_state,
        )
        if not candidate_items:
            continue
        candidate_sizes.append(len(candidate_items))
        mandatory_positive_counts.append(len(positive_items & set(candidate_items)))
        mandatory_dislike_counts.append(len(dislike_items & set(candidate_items)))

        top_items = top_k_items_from_candidates(
            trained=trained,
            user_idx=user_idx,
            candidate_items=np.array(candidate_items, dtype=np.int32),
            k=min(top_k, len(candidate_items)),
        )
        if positive_items:
            positive_acc.add(top_items=top_items, target_items=positive_items)
        if dislike_items:
            dislike_acc.add(top_items=top_items, target_items=dislike_items)

    result: dict[str, Any] = {
        "candidate_eval_pool_size": pool_size,
        "candidate_eval_top_k": top_k,
        "candidate_eval_user_count": len(user_indices),
        "candidate_eval_average_pool_size": float(np.mean(candidate_sizes)) if candidate_sizes else 0.0,
        "candidate_eval_average_positive_targets_in_pool": float(np.mean(mandatory_positive_counts)) if mandatory_positive_counts else 0.0,
        "candidate_eval_average_dislike_targets_in_pool": float(np.mean(mandatory_dislike_counts)) if mandatory_dislike_counts else 0.0,
        "candidate_eval_note": (
            f"Offline approximation of operational candidate compression: score only {pool_size} candidates and keep top {top_k}. "
            "The pool contains held-out positive targets, held-out dislike targets, and randomly sampled neutral items; "
            "it does not call Qdrant or reproduce the exact upstream candidate generator."
        ),
    }
    result.update(positive_acc.to_metrics())
    result.update(dislike_acc.to_metrics())
    return result


@dataclass
class TargetMetricAccumulator:
    prefix: str
    lower_is_better: bool
    denominator_k: int
    evaluated_users: int = 0
    hit_users: int = 0
    total_hits: int = 0
    precision_values: list[float] | None = None
    recall_values: list[float] | None = None
    mrr_values: list[float] | None = None
    ndcg_values: list[float] | None = None

    def __post_init__(self) -> None:
        if self.precision_values is None:
            self.precision_values = []
        if self.recall_values is None:
            self.recall_values = []
        if self.mrr_values is None:
            self.mrr_values = []
        if self.ndcg_values is None:
            self.ndcg_values = []

    def add(self, *, top_items: Sequence[int], target_items: set[int]) -> None:
        if not target_items:
            return
        self.evaluated_users += 1
        hits_at_rank = [1 if item_idx in target_items else 0 for item_idx in top_items]
        hit_count = int(sum(hits_at_rank))
        self.total_hits += hit_count
        if hit_count > 0:
            self.hit_users += 1
        self.precision_values.append(hit_count / max(1, self.denominator_k))
        self.recall_values.append(hit_count / max(1, len(target_items)))
        self.mrr_values.append(reciprocal_rank(hits_at_rank))
        self.ndcg_values.append(ndcg_at_k(hits_at_rank, ideal_count=min(len(target_items), self.denominator_k)))

    def to_metrics(self) -> dict[str, Any]:
        denominator = max(1, self.evaluated_users)
        return {
            f"{self.prefix}_hit_rate": self.hit_users / denominator if self.evaluated_users else None,
            f"{self.prefix}_item_rate": self.total_hits / max(1, self.evaluated_users * self.denominator_k) if self.evaluated_users else None,
            f"{self.prefix}_precision": float(np.mean(self.precision_values)) if self.precision_values else None,
            f"{self.prefix}_recall": float(np.mean(self.recall_values)) if self.recall_values else None,
            f"{self.prefix}_mrr": float(np.mean(self.mrr_values)) if self.mrr_values else None,
            f"{self.prefix}_ndcg": float(np.mean(self.ndcg_values)) if self.ndcg_values else None,
            f"{self.prefix}_evaluated_users": self.evaluated_users,
            f"{self.prefix}_lower_is_better": self.lower_is_better,
        }


def build_candidate_pool_for_user(
    *,
    user_idx: int,
    item_count: int,
    positive_items: set[int],
    dislike_items: set[int],
    exclude_items: set[int],
    pool_size: int,
    random_state: int,
) -> list[int]:
    # 수정 포인트: 운영 후보 50개 안에는 테스트 positive/dislike가 들어있어야 "20개로 줄였을 때 남기는지" 평가할 수 있습니다.
    # 따라서 held-out target을 mandatory candidate로 넣고 나머지는 neutral item으로 채웁니다.
    mandatory_items = [item for item in sorted(positive_items | dislike_items) if 0 <= item < item_count and item not in exclude_items]
    rng = random.Random(random_state + user_idx * 1_000_003)
    if len(mandatory_items) > pool_size:
        # 일반적으로 user당 positive는 적고 dislike는 20개 수준이라 50개를 넘지 않습니다.
        # 그래도 초과하면 positive를 우선 보존하고 남은 칸에 dislike를 deterministic sampling 합니다.
        positive_ordered = [item for item in sorted(positive_items) if 0 <= item < item_count and item not in exclude_items]
        dislike_ordered = [item for item in sorted(dislike_items) if 0 <= item < item_count and item not in exclude_items and item not in set(positive_ordered)]
        rng.shuffle(dislike_ordered)
        mandatory_items = (positive_ordered + dislike_ordered)[:pool_size]

    candidates = list(mandatory_items)
    used = set(candidates) | set(exclude_items)
    attempts = 0
    max_attempts = max(pool_size * 500, item_count * 2)
    while len(candidates) < pool_size and attempts < max_attempts and len(used) < item_count:
        attempts += 1
        item_idx = rng.randrange(item_count)
        if item_idx in used:
            continue
        used.add(item_idx)
        candidates.append(item_idx)

    # Fallback: random sampling attempts can miss items when the candidate space is small.
    if len(candidates) < pool_size:
        for item_idx in range(item_count):
            if len(candidates) >= pool_size:
                break
            if item_idx in used:
                continue
            used.add(item_idx)
            candidates.append(item_idx)

    return candidates


def top_k_items_from_candidates(trained: TrainedModel, user_idx: int, candidate_items: np.ndarray, k: int) -> list[int]:
    if candidate_items.size <= 0:
        return []
    scores = trained.model.predict(
        user_idx,
        candidate_items,
        user_features=trained.user_features,
        item_features=trained.item_features,
    )
    finite_count = int(np.isfinite(scores).sum())
    if finite_count <= 0:
        return []
    actual_k = min(max(1, k), finite_count)
    top_unsorted = np.argpartition(-scores, actual_k - 1)[:actual_k]
    top_sorted = top_unsorted[np.argsort(-scores[top_unsorted])]
    return [int(candidate_items[position]) for position in top_sorted]


def compute_auc(*, trained: TrainedModel, train_events: Sequence[ParsedEvent], test_events: Sequence[ParsedEvent], num_threads: int) -> float | None:
    train_matrix = build_binary_interaction_matrix(events=train_events, trained=trained)
    test_matrix = build_binary_interaction_matrix(events=test_events, trained=trained)
    if test_matrix.nnz <= 0:
        return None
    try:
        values = auc_score(
            trained.model,
            test_interactions=test_matrix,
            train_interactions=train_matrix if train_matrix.nnz > 0 else None,
            user_features=trained.user_features,
            item_features=trained.item_features,
            num_threads=max(1, num_threads),
        )
        if values.size == 0:
            return None
        return float(np.nanmean(values))
    except Exception as exc:
        print(f"[WARN] auc_score failed: {exc}")
        return None


def build_binary_interaction_matrix(*, events: Sequence[ParsedEvent], trained: TrainedModel) -> sparse.coo_matrix:
    rows: list[int] = []
    cols: list[int] = []
    for event in events:
        user_idx = trained.user_id_to_index.get(event.user_id)
        item_idx = trained.item_id_to_index.get(event.item_id)
        if user_idx is None or item_idx is None:
            continue
        rows.append(user_idx)
        cols.append(item_idx)
    data = np.ones(len(rows), dtype=np.float32)
    return sparse.coo_matrix((data, (rows, cols)), shape=(len(trained.user_id_to_index), len(trained.item_id_to_index)))


def events_to_user_item_index_sets(events: Sequence[ParsedEvent], trained: TrainedModel) -> dict[int, set[int]]:
    result: dict[int, set[int]] = defaultdict(set)
    for event in events:
        user_idx = trained.user_id_to_index.get(event.user_id)
        item_idx = trained.item_id_to_index.get(event.item_id)
        if user_idx is None or item_idx is None:
            continue
        result[user_idx].add(item_idx)
    return dict(result)


def ranking_metrics(
    *,
    trained: TrainedModel,
    targets: Mapping[int, set[int]],
    exclude_sets: Mapping[int, set[int]],
    k: int,
    prefix: str,
    lower_is_better: bool,
) -> dict[str, Any]:
    if not targets:
        return {
            f"{prefix}_hit_rate@{k}": None,
            f"{prefix}_item_rate@{k}": None,
            f"{prefix}_precision@{k}": None,
            f"{prefix}_recall@{k}": None,
            f"{prefix}_mrr@{k}": None,
            f"{prefix}_ndcg@{k}": None,
            f"{prefix}_lower_is_better": lower_is_better,
        }

    item_count = len(trained.item_id_to_index)
    all_items = np.arange(item_count, dtype=np.int32)
    hit_users = 0
    total_hits = 0
    precision_values: list[float] = []
    recall_values: list[float] = []
    mrr_values: list[float] = []
    ndcg_values: list[float] = []
    evaluated_users = 0

    for user_idx, target_items in sorted(targets.items()):
        if not target_items:
            continue
        top_items = top_k_items(trained, user_idx, all_items, exclude_sets.get(user_idx, set()), k)
        if not top_items:
            continue
        evaluated_users += 1
        hits_at_rank = [1 if item_idx in target_items else 0 for item_idx in top_items]
        hit_count = int(sum(hits_at_rank))
        total_hits += hit_count
        if hit_count > 0:
            hit_users += 1
        precision_values.append(hit_count / max(1, k))
        recall_values.append(hit_count / max(1, len(target_items)))
        mrr_values.append(reciprocal_rank(hits_at_rank))
        ndcg_values.append(ndcg_at_k(hits_at_rank, ideal_count=min(len(target_items), k)))

    denominator = max(1, evaluated_users)
    return {
        f"{prefix}_hit_rate@{k}": hit_users / denominator,
        f"{prefix}_item_rate@{k}": total_hits / max(1, evaluated_users * k),
        f"{prefix}_precision@{k}": float(np.mean(precision_values)) if precision_values else None,
        f"{prefix}_recall@{k}": float(np.mean(recall_values)) if recall_values else None,
        f"{prefix}_mrr@{k}": float(np.mean(mrr_values)) if mrr_values else None,
        f"{prefix}_ndcg@{k}": float(np.mean(ndcg_values)) if ndcg_values else None,
        f"{prefix}_evaluated_users": evaluated_users,
        f"{prefix}_lower_is_better": lower_is_better,
    }


def top_k_items(trained: TrainedModel, user_idx: int, all_items: np.ndarray, exclude_items: set[int], k: int) -> list[int]:
    if all_items.size <= 0:
        return []
    scores = trained.model.predict(
        user_idx,
        all_items,
        user_features=trained.user_features,
        item_features=trained.item_features,
    )
    if exclude_items:
        valid_excludes = [idx for idx in exclude_items if 0 <= idx < scores.shape[0]]
        if valid_excludes:
            scores[np.array(valid_excludes, dtype=np.int32)] = -np.inf
    finite_count = int(np.isfinite(scores).sum())
    if finite_count <= 0:
        return []
    actual_k = min(max(1, k), finite_count)
    top_unsorted = np.argpartition(-scores, actual_k - 1)[:actual_k]
    top_sorted = top_unsorted[np.argsort(-scores[top_unsorted])]
    return [int(item_idx) for item_idx in top_sorted]


def reciprocal_rank(hits_at_rank: Sequence[int]) -> float:
    for index, hit in enumerate(hits_at_rank, start=1):
        if hit:
            return 1.0 / index
    return 0.0


def ndcg_at_k(hits_at_rank: Sequence[int], *, ideal_count: int) -> float:
    dcg = 0.0
    for index, hit in enumerate(hits_at_rank, start=1):
        if hit:
            dcg += 1.0 / math.log2(index + 1)
    ideal = sum(1.0 / math.log2(index + 1) for index in range(1, ideal_count + 1))
    if ideal <= 0:
        return 0.0
    return dcg / ideal


def save_artifact(
    *,
    trained: TrainedModel,
    output_dir: Path,
    positive_events: Sequence[ParsedEvent],
    dislike_events: Sequence[ParsedEvent],
    feature_source: FeatureBundle,
    args: argparse.Namespace,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_version = datetime.now(timezone.utc).strftime("lightfm_701_hybrid_%Y%m%dT%H%M%SZ")
    joblib.dump(trained.model, output_dir / "model.joblib")
    with (output_dir / "mappings.json").open("w", encoding="utf-8") as file:
        json.dump(
            {
                "user_id_to_index": trained.user_id_to_index,
                "item_id_to_index": trained.item_id_to_index,
                "user_feature_id_to_index": trained.user_feature_id_to_index,
                "item_feature_id_to_index": trained.item_feature_id_to_index,
            },
            file,
            ensure_ascii=False,
            indent=2,
        )
    if trained.user_features is not None:
        sparse.save_npz(output_dir / "user_features.npz", trained.user_features)
    if trained.item_features is not None:
        sparse.save_npz(output_dir / "item_features.npz", trained.item_features)
    if args.feature_mode == "hybrid":
        with (output_dir / "feature_sources.json").open("w", encoding="utf-8") as file:
            json.dump(
                {
                    "user_features_by_id": feature_source.user_features_by_id,
                    "item_features_by_id": feature_source.item_features_by_id,
                    "user_feature_names": feature_source.user_feature_names,
                    "item_feature_names": feature_source.item_feature_names,
                },
                file,
                ensure_ascii=False,
                indent=2,
            )
    metadata = {
        "artifact_version": artifact_version,
        "trained_at": utc_now_iso(),
        "training_strategy": "final model trained on all positive events after 7:2:1 evaluation",
        "feature_mode": args.feature_mode,
        "positive_event_count": len(positive_events),
        "dislike_event_count_used_only_for_eval": len(dislike_events),
        "user_count": len(trained.user_id_to_index),
        "item_count": len(trained.item_id_to_index),
        "user_feature_count": len(trained.user_feature_id_to_index),
        "item_feature_count": len(trained.item_feature_id_to_index),
        "loss": args.loss,
        "no_components": args.components,
        "epochs": args.epochs,
        "learning_rate": args.learning_rate,
        "item_alpha": args.item_alpha,
        "user_alpha": args.user_alpha,
        "random_state": args.random_state,
    }
    with (output_dir / "metadata.json").open("w", encoding="utf-8") as file:
        json.dump(metadata, file, ensure_ascii=False, indent=2)
    return metadata


def print_metrics(label: str, metrics: Mapping[str, Any]) -> None:
    print("")
    print(f"[LIGHTFM {label.upper()} METRICS]")
    for key in sorted(metrics):
        value = metrics[key]
        if isinstance(value, float):
            print(f"{key}={value:.6f}")
        else:
            print(f"{key}={value}")


def first_value(row: Mapping[str, Any], field_names: Sequence[str], default: str = "") -> str:
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


def split_field_names(value: str | Sequence[str]) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in str(value or "").split(",") if item.strip()]
    return [str(item).strip() for item in value if str(item).strip()]


def normalize_set(value: str) -> set[str]:
    return {item.strip().upper() for item in str(value or "").split(",") if item.strip()}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    main()
