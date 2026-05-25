#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from common_env import load_ai_server_env

# 수정 포인트: .env.local 로딩은 기존 synthetic generator와 동일하게 수행합니다.
AI_SERVER_ROOT = load_ai_server_env(Path(__file__))

from generate_nemotron_persona_synthetic_events import (  # noqa: E402
    ACTION_TYPE_BY_EVENT_TYPE,
    BOOK_ID_FIELDS,
    BOOK_TEXT_FIELDS,
    CURRENT_PROJECT_EVENT_TYPES,
    DEFAULT_EVENT_COUNTS,
    DEFAULT_EVENT_WEIGHTS,
    DEFAULT_RATED_READ_COUNT,
    DEFAULT_RATING_WEIGHT_BONUS,
    DEFAULT_REVIEW_WEIGHT_BONUS,
    DEFAULT_REVIEWED_READ_COUNT,
    GenerationConfig,
    KureEmbeddingClient,
    QdrantBookReader,
    SyntheticDataError,
    append_jsonl,
    build_event_row,
    dedupe_book_candidates,
    now_iso_from_base,
    parse_datetime_utc,
    parse_map,
    read_existing_event_state,
    stable_hash,
    truncate_jsonl_if_needed,
)

DEFAULT_ACTION_SEARCH_FIELDS: dict[str, tuple[str, ...]] = {
    "FAVORITE_ADD": ("interest_profile_text", "search_profile_text", "preference_summary"),
    "READING_ADD": ("reading_now_profile_text", "search_profile_text", "preference_summary"),
    "READ_ADD": ("read_completed_profile_text", "search_profile_text", "preference_summary"),
    "DISLIKE_ADD": ("dislike_profile_text", "dispreference_summary", "search_profile_text"),
}


class ProfileSyntheticEventError(RuntimeError):
    pass


class QdrantActionSearchError(ProfileSyntheticEventError):
    pass


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def clamp01(value: Any, default: float) -> float:
    try:
        number = float(value)
    except Exception:
        number = default
    return clamp(number, 0.0, 1.0)


def parse_action_search_fields(value: str) -> dict[str, tuple[str, ...]]:
    result = dict(DEFAULT_ACTION_SEARCH_FIELDS)
    if not value.strip():
        return result
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("--action-search-fields는 JSON object 문자열이어야 합니다.") from exc
    if not isinstance(parsed, dict):
        raise ValueError("--action-search-fields는 JSON object 문자열이어야 합니다.")
    for event_type, fields in parsed.items():
        normalized_event_type = str(event_type).strip().upper()
        if normalized_event_type not in CURRENT_PROJECT_EVENT_TYPES:
            raise ValueError(f"지원하지 않는 event_type입니다: {event_type}")
        if not isinstance(fields, list) or not all(isinstance(field, str) and field.strip() for field in fields):
            raise ValueError(f"{event_type}의 field 목록은 문자열 배열이어야 합니다.")
        result[normalized_event_type] = tuple(field.strip() for field in fields)
    return result


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise ProfileSyntheticEventError(f"persona profile 파일이 없습니다. path={path}")
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fp:
        for line_number, line in enumerate(fp, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ProfileSyntheticEventError(f"JSONL 파싱 실패. path={path}, line={line_number}, error={exc}") from exc
            if isinstance(row, dict):
                rows.append(row)
    return rows


def compact_text(value: Any, max_chars: int = 1600) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    text = " ".join(text.replace("\n", " ").split())
    if len(text) > max_chars:
        return text[:max_chars].rstrip()
    return text


def resolve_profile(profile_record: Mapping[str, Any]) -> dict[str, Any]:
    profile = profile_record.get("llm_profile") or profile_record.get("profile") or {}
    if not isinstance(profile, dict):
        raise ProfileSyntheticEventError(f"llm_profile이 객체가 아닙니다. persona_id={profile_record.get('persona_id')}")
    return dict(profile)


def resolve_profile_text(
    *,
    profile: Mapping[str, Any],
    persona_fields: Mapping[str, Any],
    event_type: str,
    action_search_fields: Mapping[str, Sequence[str]],
) -> tuple[str, str]:
    for field_name in action_search_fields.get(event_type, DEFAULT_ACTION_SEARCH_FIELDS.get(event_type, ("search_profile_text",))):
        text = compact_text(profile.get(field_name), max_chars=1600)
        if text:
            return text, field_name
    fallback = compact_text(profile or persona_fields, max_chars=1600)
    return fallback, "profile_fallback"


def build_reader_config(args: argparse.Namespace, event_counts: Mapping[str, int]) -> GenerationConfig:
    # 수정 포인트: 새 profile 기반 generator도 기존 Qdrant/KURE reader를 재사용하되,
    # action별 검색에서는 최소 후보 수를 1로 두어 기존 candidate_pool_size>=63 강제와 분리합니다.
    return GenerationConfig(
        dataset_name="profile-jsonl",
        dataset_split="profile-jsonl",
        sample_size=max(1, int(args.sample_size)),
        seed=0,
        shuffle_buffer_size=0,
        hf_token="",
        persona_id_field="",
        persona_fields=[],
        max_persona_field_chars=1200,
        qdrant_url=args.qdrant_url,
        qdrant_api_key=args.qdrant_api_key,
        qdrant_collection=args.qdrant_collection,
        kure_base_url=args.kure_base_url,
        kure_internal_api_key=args.kure_internal_api_key,
        kure_internal_header_name=args.kure_internal_header_name,
        embedding_timeout_seconds=float(args.embedding_timeout_seconds),
        qdrant_timeout_seconds=float(args.qdrant_timeout_seconds),
        qdrant_search_retries=max(1, int(args.qdrant_search_retries)),
        qdrant_retry_backoff_seconds=max(0.0, float(args.qdrant_retry_backoff_seconds)),
        qdrant_search_delay_seconds=max(0.0, float(args.qdrant_search_delay_seconds)),
        qdrant_min_candidate_pool_size=max(1, max((int(value) for value in event_counts.values() if int(value) > 0), default=1) * max(1, int(args.patterns))),
        candidate_pool_size=max(1, int(args.action_candidate_limit)),
        event_counts={str(key): int(value) for key, value in event_counts.items()},
        event_weights=parse_map(args.event_weights, DEFAULT_EVENT_WEIGHTS, float),
        source_weight=float(args.source_weight),
        rated_read_count=max(0, int(args.rated_read_count)),
        reviewed_read_count=max(0, int(args.reviewed_read_count)),
        rating_weight_bonus=float(args.rating_weight_bonus),
        review_weight_bonus=float(args.review_weight_bonus),
        patterns=max(1, int(args.patterns)),
        strict_counts=bool(args.strict_counts),
        resume=bool(args.resume),
        failure_policy=str(args.failure_policy),
        max_failed_personas=max(0, int(args.max_failed_personas)),
        failure_cooldown_seconds=max(0.0, float(args.failure_cooldown_seconds)),
        max_source_scan=max(1, int(args.sample_size)),
        output_persona_subset_path=None,
        output_events_path=Path(args.output_events_path),
        output_candidates_path=Path(args.output_candidates_path) if args.output_candidates_path else None,
        created_at_start=parse_datetime_utc(args.created_at_start),
    )


def action_limit(target_count: int, patterns: int, action_candidate_limit: int, action_candidate_multiplier: float, action_candidate_extra: int) -> int:
    needed = max(1, int(target_count) * max(1, int(patterns)))
    dynamic_limit = int(math.ceil(needed * max(1.0, float(action_candidate_multiplier)))) + max(0, int(action_candidate_extra))
    return max(needed, min(max(needed, int(action_candidate_limit)), dynamic_limit))


def rotate_by_exploration(candidates: Sequence[Any], exploration_level: float, pattern_index: int, salt: str) -> list[Any]:
    if not candidates:
        return []
    max_offset = max(0, len(candidates) - 1)
    if max_offset == 0:
        return list(candidates)
    hash_offset = int(stable_hash([salt, pattern_index, exploration_level], length=8), 16) % max(1, max_offset + 1)
    exploration_offset = int(max_offset * clamp01(exploration_level, 0.35) * 0.5)
    offset = min(max_offset, (hash_offset + exploration_offset) % (max_offset + 1))
    return list(candidates[offset:]) + list(candidates[:offset])


def select_action_candidates(
    *,
    candidates: Sequence[Any],
    target_count: int,
    used_item_ids: set[str],
    strict_counts: bool,
    persona_id: str,
    event_type: str,
) -> list[Any]:
    selected: list[Any] = []
    for candidate in candidates:
        if candidate.item_id in used_item_ids:
            continue
        selected.append(candidate)
        used_item_ids.add(candidate.item_id)
        if len(selected) >= target_count:
            break
    if strict_counts and len(selected) < target_count:
        raise ProfileSyntheticEventError(
            f"persona_id={persona_id} event_type={event_type} 후보가 부족합니다. expected={target_count} actual={len(selected)}. "
            "--action-candidate-limit 또는 --action-candidate-extra를 늘려주세요."
        )
    return selected


def profile_rating(profile: Mapping[str, Any], persona_id: str, item_id: str, read_ordinal: int, pattern_index: int) -> float:
    bias = clamp01(profile.get("rating_bias"), 0.65)
    jitter_seed = int(stable_hash([persona_id, item_id, read_ordinal, pattern_index, "rating"], length=8), 16)
    jitter = ((jitter_seed % 1000) / 1000.0 - 0.5) * 0.7
    raw = 2.5 + (bias * 2.2) + jitter
    # 수정 포인트: 사용자별 rating_bias를 반영하되 LightFM 입력이 흔들리지 않도록 0.5점 단위로 결정론적 반올림합니다.
    return round(clamp(round(raw * 2) / 2, 1.0, 5.0), 1)


def profile_review_sentiment(profile: Mapping[str, Any], persona_id: str, item_id: str, read_ordinal: int, pattern_index: int) -> float:
    bias = clamp01(profile.get("review_sentiment_bias"), 0.65)
    jitter_seed = int(stable_hash([persona_id, item_id, read_ordinal, pattern_index, "sentiment"], length=8), 16)
    jitter = ((jitter_seed % 1000) / 1000.0 - 0.5) * 0.2
    return round(clamp(0.25 + (bias * 0.7) + jitter, 0.0, 1.0), 6)


def enrich_event_row_with_profile(
    row: dict[str, Any],
    *,
    profile_record: Mapping[str, Any],
    profile: Mapping[str, Any],
    profile_action: str,
    profile_text_field: str,
    profile_query_text: str,
    read_ordinal: int | None,
) -> dict[str, Any]:
    persona_id = str(row.get("persona_id") or "")
    item_id = str(row.get("item_id") or "")
    pattern_index = int(row.get("pattern_index") or 0)
    if row.get("event_type") == "READ_ADD" and read_ordinal is not None:
        if row.get("has_rating"):
            row["rating"] = profile_rating(profile, persona_id, item_id, read_ordinal, pattern_index)
        if row.get("has_review"):
            row["review_sentiment_score"] = profile_review_sentiment(profile, persona_id, item_id, read_ordinal, pattern_index)
            score = float(row["review_sentiment_score"])
            row["sentiment_label"] = "POSITIVE" if score >= 0.6 else "NEUTRAL" if score >= 0.4 else "NEGATIVE"

    row["user_source"] = "SYNTHETIC_NEMOTRON_LLM_PROFILE_QDRANT"
    row["event_source"] = "SYNTHETIC_NEMOTRON_LLM_PROFILE_QDRANT"
    row["source"] = "SYNTHETIC_NEMOTRON_LLM_PROFILE_QDRANT"
    row["profile_strategy"] = "llm_persona_action_profile_v1"
    row["profile_schema_version"] = profile_record.get("profile_schema_version")
    row["profile_action"] = profile_action
    row["profile_text_field"] = profile_text_field
    row["profile_query_text"] = profile_query_text
    metadata = dict(row.get("metadata") or {})
    metadata.update(
        {
            "persona_profile_source": profile_record.get("profile_source"),
            "profile_action": profile_action,
            "profile_text_field": profile_text_field,
            "profile_confidence": profile.get("confidence"),
            "exploration_level": profile.get("exploration_level"),
            "negative_event_policy": "LLM_DISLIKE_PROFILE_SEARCH" if row.get("event_type") == "DISLIKE_ADD" else None,
        }
    )
    row["metadata"] = metadata
    return row


def build_candidate_row(
    *,
    persona_id: str,
    persona_hash: str,
    candidate: Any,
    event_type: str,
    profile_action: str,
    profile_text_field: str,
) -> dict[str, Any]:
    return {
        "persona_id": persona_id,
        "persona_hash": persona_hash,
        "event_type": event_type,
        "action_type": ACTION_TYPE_BY_EVENT_TYPE.get(event_type, event_type),
        "profile_action": profile_action,
        "profile_text_field": profile_text_field,
        "item_id": candidate.item_id,
        "book_id": candidate.payload.get("book_id"),
        "book_key": candidate.item_id,
        "isbn": candidate.isbn,
        "isbn13": candidate.isbn13,
        "title": candidate.title,
        "author": candidate.author,
        "publisher": candidate.publisher,
        "category": candidate.category,
        "categories": candidate.categories,
        "description": candidate.description,
        "qdrant_point_id": candidate.point_id,
        "qdrant_score": candidate.qdrant_score,
    }


def parse_args() -> tuple[argparse.Namespace, GenerationConfig, dict[str, tuple[str, ...]]]:
    parser = argparse.ArgumentParser(description="Generate LightFM-ready synthetic events from LLM-enriched Nemotron persona profiles.")
    parser.add_argument("--persona-profile-path", required=True)
    parser.add_argument("--sample-size", type=int, default=100)
    parser.add_argument("--patterns", type=int, default=1)
    parser.add_argument("--strict-counts", action="store_true")
    parser.add_argument("--created-at-start", default="2026-01-01T00:00:00Z")

    parser.add_argument("--qdrant-url", default=os.getenv("QDRANT_URL", "http://127.0.0.1:6333"))
    parser.add_argument("--qdrant-api-key", default=os.getenv("QDRANT_API_KEY", ""))
    parser.add_argument("--qdrant-collection", default=os.getenv("QDRANT_KURE_COLLECTION", os.getenv("QDRANT_COLLECTION", "books_kure")))
    parser.add_argument("--qdrant-timeout-seconds", type=float, default=float(os.getenv("QDRANT_TIMEOUT_SECONDS", "45")))
    parser.add_argument("--qdrant-search-retries", type=int, default=int(os.getenv("QDRANT_SEARCH_RETRIES", "5")))
    parser.add_argument("--qdrant-retry-backoff-seconds", type=float, default=float(os.getenv("QDRANT_RETRY_BACKOFF_SECONDS", "1")))
    parser.add_argument("--qdrant-search-delay-seconds", type=float, default=float(os.getenv("QDRANT_SEARCH_DELAY_SECONDS", "0.03")))

    parser.add_argument("--kure-base-url", default=os.getenv("KURE_EMBEDDING_BASE_URL", "http://127.0.0.1:8002"))
    parser.add_argument("--kure-internal-api-key", default=os.getenv("KURE_INTERNAL_API_KEY", ""))
    parser.add_argument("--kure-internal-header-name", default=os.getenv("KURE_INTERNAL_HEADER_NAME", "X-KURE-Internal-Key"))
    parser.add_argument("--embedding-timeout-seconds", type=float, default=float(os.getenv("KURE_REQUEST_TIMEOUT_SECONDS", "30")))

    parser.add_argument("--event-counts", default=",".join(f"{key}:{value}" for key, value in DEFAULT_EVENT_COUNTS.items()))
    parser.add_argument("--event-weights", default=",".join(f"{key}:{value}" for key, value in DEFAULT_EVENT_WEIGHTS.items()))
    parser.add_argument("--source-weight", type=float, default=0.4)
    parser.add_argument("--rated-read-count", type=int, default=DEFAULT_RATED_READ_COUNT)
    parser.add_argument("--reviewed-read-count", type=int, default=DEFAULT_REVIEWED_READ_COUNT)
    parser.add_argument("--rating-weight-bonus", type=float, default=DEFAULT_RATING_WEIGHT_BONUS)
    parser.add_argument("--review-weight-bonus", type=float, default=DEFAULT_REVIEW_WEIGHT_BONUS)

    parser.add_argument("--action-search-fields", default="")
    parser.add_argument("--action-candidate-limit", type=int, default=64)
    parser.add_argument("--action-candidate-multiplier", type=float, default=2.0)
    parser.add_argument("--action-candidate-extra", type=int, default=12)
    parser.add_argument("--fallback-to-general-profile", action=argparse.BooleanOptionalAction, default=True)

    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--failure-policy", choices=("abort", "skip"), default="skip")
    parser.add_argument("--max-failed-personas", type=int, default=100)
    parser.add_argument("--failure-cooldown-seconds", type=float, default=5.0)
    parser.add_argument("--output-events-path", required=True)
    parser.add_argument("--output-candidates-path", default="")
    args = parser.parse_args()

    event_counts = parse_map(args.event_counts, DEFAULT_EVENT_COUNTS, int)
    action_search_fields = parse_action_search_fields(args.action_search_fields)
    reader_config = build_reader_config(args, event_counts=event_counts)
    return args, reader_config, action_search_fields


def main() -> int:
    args, config, action_search_fields = parse_args()
    profiles = read_jsonl(Path(args.persona_profile_path))
    if not profiles:
        raise ProfileSyntheticEventError(f"persona profile 파일에 데이터가 없습니다. path={args.persona_profile_path}")

    embedder = KureEmbeddingClient(
        base_url=config.kure_base_url,
        internal_api_key=config.kure_internal_api_key,
        header_name=config.kure_internal_header_name,
        timeout_seconds=config.embedding_timeout_seconds,
    )
    qdrant_reader = QdrantBookReader(config=config, embedder=embedder)

    if config.resume:
        completed_persona_ids, event_counter, existing_event_count = read_existing_event_state(config.output_events_path)
        print(
            "[RESUME] "
            f"completed_personas={len(completed_persona_ids)} existing_events={existing_event_count} "
            f"target_personas={config.sample_size} output_events={config.output_events_path}"
        )
    else:
        completed_persona_ids = set()
        event_counter = Counter()
        existing_event_count = 0
        truncate_jsonl_if_needed(config.output_events_path, resume=False)
        truncate_jsonl_if_needed(config.output_candidates_path, resume=False)

    generated_personas = len(completed_persona_ids)
    failed_personas = 0
    global_sequence = existing_event_count

    for profile_index, profile_record in enumerate(profiles):
        if generated_personas >= config.sample_size:
            break
        persona_id = str(profile_record.get("persona_id") or profile_record.get("synthetic_user_id") or "").strip()
        if not persona_id:
            print(f"[SKIP PROFILE] index={profile_index} reason=no persona_id", file=sys.stderr)
            continue
        if persona_id in completed_persona_ids:
            print(f"[SKIP DONE] persona_id={persona_id}")
            continue

        persona_fields = profile_record.get("persona_fields") if isinstance(profile_record.get("persona_fields"), dict) else {}
        profile = resolve_profile(profile_record)
        persona_hash = str(profile_record.get("persona_hash") or stable_hash(profile_record))
        exploration_level = clamp01(profile.get("exploration_level"), 0.35)
        print(f"[PROFILE PERSONA] {generated_personas + 1}/{config.sample_size} persona_id={persona_id}")

        try:
            event_type_candidates: dict[str, list[Any]] = {}
            event_type_text_meta: dict[str, tuple[str, str]] = {}
            local_candidate_rows: list[dict[str, Any]] = []

            for event_type in CURRENT_PROJECT_EVENT_TYPES:
                target_per_pattern = max(0, int(config.event_counts.get(event_type, 0)))
                if target_per_pattern <= 0:
                    continue
                profile_query_text, profile_text_field = resolve_profile_text(
                    profile=profile,
                    persona_fields=persona_fields,
                    event_type=event_type,
                    action_search_fields=action_search_fields,
                )
                limit = action_limit(
                    target_count=target_per_pattern,
                    patterns=config.patterns,
                    action_candidate_limit=int(args.action_candidate_limit),
                    action_candidate_multiplier=float(args.action_candidate_multiplier),
                    action_candidate_extra=int(args.action_candidate_extra),
                )
                candidates = qdrant_reader.search_by_persona(profile_query_text, limit=limit)
                if config.strict_counts and len(candidates) < target_per_pattern:
                    raise ProfileSyntheticEventError(
                        f"persona_id={persona_id} event_type={event_type} 후보가 부족합니다. required={target_per_pattern} actual={len(candidates)}"
                    )
                event_type_candidates[event_type] = candidates
                event_type_text_meta[event_type] = (profile_text_field, profile_query_text)
                for candidate in candidates:
                    local_candidate_rows.append(
                        build_candidate_row(
                            persona_id=persona_id,
                            persona_hash=persona_hash,
                            candidate=candidate,
                            event_type=event_type,
                            profile_action=ACTION_TYPE_BY_EVENT_TYPE.get(event_type, event_type),
                            profile_text_field=profile_text_field,
                        )
                    )

            local_event_rows: list[dict[str, Any]] = []
            local_counter: Counter[str] = Counter()
            used_item_ids: set[str] = set()

            for pattern_index in range(config.patterns):
                synthetic_user_id = persona_id if config.patterns == 1 else f"{persona_id}:pattern:{pattern_index:02d}"
                pattern_count = 0
                read_ordinal = 0
                for event_type in CURRENT_PROJECT_EVENT_TYPES:
                    target = max(0, int(config.event_counts.get(event_type, 0)))
                    if target <= 0:
                        continue
                    candidates = event_type_candidates.get(event_type, [])
                    rotated_candidates = rotate_by_exploration(
                        candidates,
                        exploration_level=exploration_level,
                        pattern_index=pattern_index,
                        salt=f"{persona_id}:{event_type}",
                    )
                    selected = select_action_candidates(
                        candidates=rotated_candidates,
                        target_count=target,
                        used_item_ids=used_item_ids,
                        strict_counts=config.strict_counts,
                        persona_id=persona_id,
                        event_type=event_type,
                    )
                    profile_text_field, profile_query_text = event_type_text_meta.get(event_type, ("profile_fallback", ""))
                    for candidate in selected:
                        global_sequence += 1
                        pattern_count += 1
                        current_read_ordinal = None
                        if event_type == "READ_ADD":
                            read_ordinal += 1
                            current_read_ordinal = read_ordinal
                        row = build_event_row(
                            persona_id=persona_id,
                            synthetic_user_id=synthetic_user_id,
                            persona_hash=persona_hash,
                            candidate=candidate,
                            event_type=event_type,
                            event_weight=float(config.event_weights.get(event_type, 1.0)),
                            source_weight=config.source_weight,
                            sequence=pattern_count,
                            pattern_index=pattern_index,
                            created_at=now_iso_from_base(config.created_at_start, global_sequence),
                            qdrant_collection=config.qdrant_collection,
                            read_ordinal=current_read_ordinal,
                            rated_read_count=config.rated_read_count,
                            reviewed_read_count=config.reviewed_read_count,
                            rating_weight_bonus=config.rating_weight_bonus,
                            review_weight_bonus=config.review_weight_bonus,
                        )
                        local_event_rows.append(
                            enrich_event_row_with_profile(
                                row,
                                profile_record=profile_record,
                                profile=profile,
                                profile_action=ACTION_TYPE_BY_EVENT_TYPE.get(event_type, event_type),
                                profile_text_field=profile_text_field,
                                profile_query_text=profile_query_text,
                                read_ordinal=current_read_ordinal,
                            )
                        )
                        local_counter[event_type] += 1

            if config.strict_counts:
                expected = sum(max(0, int(value)) for value in config.event_counts.values()) * config.patterns
                if len(local_event_rows) != expected:
                    raise ProfileSyntheticEventError(
                        f"persona_id={persona_id} 생성 이벤트 수가 맞지 않습니다. expected={expected} actual={len(local_event_rows)}"
                    )

            if config.output_candidates_path:
                append_jsonl(config.output_candidates_path, local_candidate_rows)
            append_jsonl(config.output_events_path, local_event_rows)
            completed_persona_ids.add(persona_id)
            generated_personas += 1
            event_counter.update(local_counter)
            print(
                "[PROFILE PERSONA DONE] "
                f"persona_id={persona_id} events_added={len(local_event_rows)} candidates={len(local_candidate_rows)} "
                f"progress={generated_personas}/{config.sample_size} flushed=true"
            )
        except (SyntheticDataError, ProfileSyntheticEventError) as exc:
            failed_personas += 1
            global_sequence = existing_event_count + sum(event_counter.values())
            print(
                "[PROFILE PERSONA ERROR] "
                f"persona_id={persona_id} failed={failed_personas}/{config.max_failed_personas} "
                f"policy={config.failure_policy} error={exc}",
                file=sys.stderr,
            )
            if config.failure_policy == "abort" or failed_personas > config.max_failed_personas:
                raise
            if config.failure_cooldown_seconds > 0:
                time.sleep(config.failure_cooldown_seconds)
            continue

    if generated_personas < config.sample_size:
        raise ProfileSyntheticEventError(
            f"목표 persona 수를 채우지 못했습니다. generated={generated_personas}, target={config.sample_size}, "
            f"profiles_available={len(profiles)}, failed={failed_personas}. profile 파일을 더 생성하거나 --resume으로 이어서 실행해주세요."
        )

    print(
        "[PROFILE SYNTHETIC DONE] "
        f"personas={generated_personas} patterns={config.patterns} events_total={sum(event_counter.values())} "
        f"failed_personas={failed_personas} event_counts={dict(event_counter)} output_events={config.output_events_path}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SyntheticDataError, ProfileSyntheticEventError) as exc:
        print(f"[PROFILE SYNTHETIC ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
