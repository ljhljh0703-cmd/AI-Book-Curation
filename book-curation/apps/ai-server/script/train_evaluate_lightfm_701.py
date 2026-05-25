#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
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
class TrainedModel:
    model: LightFM
    dataset: Dataset
    user_id_to_index: dict[str, int]
    item_id_to_index: dict[str, int]
    item_index_to_id: dict[int, str]


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Train LightFM with a 7:2:1 user-level positive split and evaluate positive hit/recall "
            "plus dislike avoidance metrics. DISLIKE events are never used as positive training interactions."
        )
    )
    parser.add_argument("--events-path", action="append", required=True, help="JSONL/JSON/CSV event file. Can be repeated.")
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
    parser.add_argument("--random-state", type=int, default=42)
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

    split = split_positive_events_by_user(
        positive_events=positive_events,
        dislike_events=dislike_events,
        train_ratio=args.train_ratio,
        validation_ratio=args.validation_ratio,
        test_ratio=args.test_ratio,
        random_state=args.random_state,
    )

    print("[LIGHTFM 7:2:1 SPLIT]")
    print(f"raw_event_counts={dict(raw_counter)}")
    print(f"positive_events={len(positive_events)}")
    print(f"dislike_events_for_negative_eval={len(dislike_events)}")
    print(f"train_positive={len(split.train)} validation_positive={len(split.validation)} test_positive={len(split.test)}")
    print(f"excluded_event_types={sorted(excluded_types)}")
    print(f"dislike_event_types={sorted(dislike_types)}")
    print("DISLIKE events are not used in LightFM positive training; they are used only for avoidance metrics.")

    # 수정 포인트: validation은 train 70%로 평가하고, test는 train+validation 90%로 재학습 후 평가합니다.
    # 이렇게 해야 validation으로 튜닝하고 test는 최종 확인용으로 분리할 수 있습니다.
    val_model = train_model(
        train_events=split.train,
        all_events=[*positive_events, *dislike_events],
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
    )

    test_train_events = [*split.train, *split.validation]
    test_model = train_model(
        train_events=test_train_events,
        all_events=[*positive_events, *dislike_events],
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
    )

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    final_artifact_metadata: dict[str, Any] = {}
    if args.save_final_model:
        final_model = train_model(
            train_events=positive_events,
            all_events=[*positive_events, *dislike_events],
            args=args,
            label="final_train100_positive",
        )
        final_artifact_metadata = save_artifact(
            trained=final_model,
            output_dir=output_dir,
            positive_events=positive_events,
            dislike_events=dislike_events,
            args=args,
        )

    metrics = {
        "created_at": utc_now_iso(),
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
        "hyperparameters": {
            "loss": args.loss,
            "components": args.components,
            "epochs": args.epochs,
            "learning_rate": args.learning_rate,
            "item_alpha": args.item_alpha,
            "user_alpha": args.user_alpha,
            "num_threads": args.num_threads,
            "k": args.k,
            "random_state": args.random_state,
        },
        "validation": validation_metrics,
        "test": test_metrics,
        "final_artifact": final_artifact_metadata,
        "metric_notes": {
            "positive_metrics": "Higher is better. Computed from held-out positive events.",
            "dislike_metrics": "Lower is better. DISLIKE events are not used for training; they are used only as negative evaluation labels.",
        },
    }
    with (output_dir / "metrics.json").open("w", encoding="utf-8") as file:
        json.dump(metrics, file, ensure_ascii=False, indent=2)

    print_metrics("validation", validation_metrics)
    print_metrics("test", test_metrics)
    print(f"[LIGHTFM 7:2:1 DONE] output_dir={output_dir}")
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


def train_model(*, train_events: Sequence[ParsedEvent], all_events: Sequence[ParsedEvent], args: argparse.Namespace, label: str) -> TrainedModel:
    users = sorted({event.user_id for event in all_events})
    items = sorted({event.item_id for event in all_events})
    dataset = Dataset()
    dataset.fit(users=users, items=items)
    interactions, weights = dataset.build_interactions((event.user_id, event.item_id, event.weight) for event in train_events)
    model = LightFM(
        no_components=args.components,
        loss=args.loss,
        learning_rate=args.learning_rate,
        item_alpha=args.item_alpha,
        user_alpha=args.user_alpha,
        random_state=args.random_state,
    )
    print(f"[LIGHTFM TRAIN] label={label} train_events={len(train_events)} users={len(users)} items={len(items)}")
    model.fit(
        interactions=interactions,
        sample_weight=weights,
        epochs=args.epochs,
        num_threads=max(1, args.num_threads),
        verbose=True,
    )
    user_id_to_index, _, item_id_to_index, _ = dataset.mapping()
    return TrainedModel(
        model=model,
        dataset=dataset,
        user_id_to_index={str(key): int(value) for key, value in user_id_to_index.items()},
        item_id_to_index={str(key): int(value) for key, value in item_id_to_index.items()},
        item_index_to_id={int(value): str(key) for key, value in item_id_to_index.items()},
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
    }
    return metrics


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
        top_items = top_k_items(trained.model, user_idx, all_items, exclude_sets.get(user_idx, set()), k)
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


def top_k_items(model: LightFM, user_idx: int, all_items: np.ndarray, exclude_items: set[int], k: int) -> list[int]:
    if all_items.size <= 0:
        return []
    scores = model.predict(user_idx, all_items)
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
    args: argparse.Namespace,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_version = datetime.now(timezone.utc).strftime("lightfm_701_%Y%m%dT%H%M%SZ")
    joblib.dump(trained.model, output_dir / "model.joblib")
    with (output_dir / "mappings.json").open("w", encoding="utf-8") as file:
        json.dump(
            {
                "user_id_to_index": trained.user_id_to_index,
                "item_id_to_index": trained.item_id_to_index,
            },
            file,
            ensure_ascii=False,
            indent=2,
        )
    metadata = {
        "artifact_version": artifact_version,
        "trained_at": utc_now_iso(),
        "training_strategy": "final model trained on all positive events after 7:2:1 evaluation",
        "positive_event_count": len(positive_events),
        "dislike_event_count_used_only_for_eval": len(dislike_events),
        "user_count": len(trained.user_id_to_index),
        "item_count": len(trained.item_id_to_index),
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


def split_field_names(value: str) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def normalize_set(value: str) -> set[str]:
    return {item.strip().upper() for item in str(value or "").split(",") if item.strip()}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    main()
