#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from common_env import load_ai_server_env

# 수정 포인트: 운영 FastAPI와 같은 .env/.env.local 값을 먼저 로드합니다.
# Qdrant, KURE, CLOVA 같은 비밀값은 CLI나 코드에 하드코딩하지 않습니다.
AI_SERVER_ROOT = load_ai_server_env(Path(__file__))
if str(AI_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_SERVER_ROOT))

from app.services.recommendation.profile_reranker import ProfileReranker  # noqa: E402
from generate_nemotron_persona_synthetic_events import (  # noqa: E402
    ACTION_TYPE_BY_EVENT_TYPE,
    BOOK_ID_FIELDS,
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
    now_iso_from_base,
    parse_datetime_utc,
    parse_map,
    read_existing_event_state,
    stable_hash,
    truncate_jsonl_if_needed,
)
from generate_nemotron_profile_synthetic_events import (  # noqa: E402
    DEFAULT_ACTION_SEARCH_FIELDS,
    ProfileSyntheticEventError,
    action_limit,
    build_candidate_row,
    clamp01,
    compact_text,
    enrich_event_row_with_profile,
    parse_action_search_fields,
    read_jsonl,
    resolve_profile_text,
)

POSITIVE_EVENT_TYPES = {"FAVORITE_ADD", "READING_ADD", "READ_ADD"}
NEGATIVE_EVENT_TYPES = {"DISLIKE_ADD"}
RULE_SOURCE = "SYNTHETIC_NEMOTRON_LLM_PROFILE_RULE_BASED"


@dataclass(frozen=True)
class RuleRankedCandidate:
    candidate: Any
    ranked_payload: dict[str, Any]
    event_type: str
    profile_text_field: str
    profile_query_text: str
    rank_position: int
    selection_direction: str
    candidate_pool_scope: str = "PERSONAL"
    shared_group_key: str = ""
    shared_pool_query_text: str = ""

    @property
    def item_id(self) -> str:
        return str(self.candidate.item_id)

    @property
    def rule_score(self) -> float:
        return safe_float(
            self.ranked_payload.get("rerank_score")
            or self.ranked_payload.get("profileVectorScore")
            or self.ranked_payload.get("ruleScore")
            or self.ranked_payload.get("score")
        )


@dataclass(frozen=True)
class PreparedProfileRecord:
    """LLM profile row를 3단계 합성데이터 생성에서 재사용하기 좋게 정규화한 값입니다.

    수정 포인트: LLM 호출을 다시 하지 않고 기존 persona_profiles_llm_*.jsonl만 읽어서
    group shared pool을 만들 수 있게 profile/profile_record/group_key를 한 번만 정리합니다.
    """

    index: int
    persona_id: str
    profile_record: dict[str, Any]
    profile: dict[str, Any]
    persona_fields: dict[str, Any]
    persona_hash: str
    age_info: dict[str, Any]
    shared_group_key: str


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def compact_terms(values: Iterable[Any], *, max_terms: int, max_chars: int) -> list[str]:
    """LLM 프로필 텍스트를 현재 ProfileReranker가 이해할 수 있는 범용 term 배열로 변환합니다.

    수정 포인트: 특정 장르/키워드 사전을 하드코딩하지 않고, LLM이 생성한 프로필 텍스트를
    문장/구 단위로만 분해합니다. 따라서 페르소나별 취미·관심·독서 목적 차이가 그대로 rule-based
    score에 전달됩니다.
    """
    terms: list[str] = []
    for value in values:
        text = clean_compact_text(value, max_chars=max_chars)
        if not text:
            continue
        terms.append(text)
        parts = re.split(r"[\n,;|/·•]+|(?<=[.!?。！？])\s+", text)
        for part in parts:
            normalized = " ".join(str(part or "").split())
            if normalized:
                terms.append(normalized[:max_chars].rstrip())
    seen: set[str] = set()
    result: list[str] = []
    for term in terms:
        normalized = str(term or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
        if len(result) >= max_terms:
            break
    return result


def list_values(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def try_decode_json_string(value: Any, *, max_depth: int = 3) -> Any:
    """JSONL 내부에 문자열로 한 번 더 저장된 JSON을 안전하게 복원합니다.

    수정 포인트: LLM 프로필 파일에서 `llm_profile` 또는 개별 profile text가
    `\"key\"` 형태로 보일 수 있습니다. 파일 원문을 replace하지 않고,
    읽는 시점에만 중첩 JSON 문자열을 dict/list/str로 복원합니다.
    """
    current = value
    for _ in range(max(1, int(max_depth))):
        if not isinstance(current, str):
            return current
        text = current.strip()
        if not text:
            return text
        try:
            decoded = json.loads(text)
        except Exception:
            return current
        current = decoded
    return current


def flatten_profile_value(value: Any, *, max_parts: int = 80) -> str:
    """dict/list 형태로 복원된 LLM profile 값을 검색용 텍스트로 평탄화합니다.

    수정 포인트: fallback profile text가 `{\"age\": \"55\", ...}` 같은 JSON 문자열인 경우
    키를 잃지 않으면서 Qdrant/KURE 검색에 넣을 수 있는 일반 텍스트로 바꿉니다.
    """
    parts: list[str] = []

    def visit(node: Any, prefix: str = "") -> None:
        if len(parts) >= max_parts:
            return
        if isinstance(node, dict):
            for key, item in node.items():
                key_text = str(key or "").strip()
                next_prefix = f"{prefix}.{key_text}" if prefix and key_text else key_text or prefix
                visit(item, next_prefix)
            return
        if isinstance(node, list):
            for item in node:
                visit(item, prefix)
            return
        text = " ".join(str(node or "").split())
        if not text:
            return
        if prefix:
            parts.append(f"{prefix}: {text}")
        else:
            parts.append(text)

    visit(value)
    return " | ".join(parts)


def clean_profile_text_value(value: Any) -> Any:
    """LLM profile JSONL에 남을 수 있는 이중 인코딩 따옴표를 안전하게 정리합니다.

    수정 포인트: JSONL 원문에서 `\"`를 전역 치환하면 JSON 문법이 깨질 수 있습니다.
    따라서 파일을 직접 replace하지 않고, json.loads 이후 Python 값이 된 뒤에만 후처리합니다.
    """
    decoded = try_decode_json_string(value)
    if isinstance(decoded, (dict, list)):
        return flatten_profile_value(decoded)
    if not isinstance(decoded, str):
        return decoded
    text = " ".join(decoded.strip().split())
    text = text.replace('\\\"', '"').strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        text = text[1:-1].strip()
    return text


def clean_profile_values(value: Any) -> Any:
    decoded = try_decode_json_string(value)
    if isinstance(decoded, dict):
        return {str(key).strip().strip('\"'): clean_profile_values(item) for key, item in decoded.items()}
    if isinstance(decoded, list):
        return [clean_profile_values(item) for item in decoded]
    return clean_profile_text_value(decoded)


def resolve_llm_profile(profile_record: Mapping[str, Any]) -> dict[str, Any]:
    """llm_profile이 객체이든 JSON 문자열이든 같은 dict로 읽습니다.

    수정 포인트: 일부 LLM profile JSONL은 `llm_profile` 전체가 문자열화되어
    내부 키가 `\"age\"`처럼 보일 수 있습니다. 이 경우 기존 resolve_profile은
    객체가 아니라는 이유로 실패하므로, rule-based 생성기에서는 더 견고하게 복원합니다.
    """
    profile = profile_record.get("llm_profile") or profile_record.get("profile") or {}
    profile = try_decode_json_string(profile, max_depth=4)
    if isinstance(profile, dict):
        return dict(profile)
    raise ProfileSyntheticEventError(
        f"llm_profile을 객체로 복원하지 못했습니다. persona_id={profile_record.get('persona_id')} type={type(profile).__name__}"
    )

def clean_compact_text(value: Any, *, max_chars: int) -> str:
    return compact_text(clean_profile_text_value(value), max_chars=max_chars)


def parse_age_number(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        age = int(value)
        return age if 0 < age < 130 else None
    text = str(value or "").strip()
    if not text:
        return None
    match = re.search(r"(?<!\d)(\d{1,3})(?!\d)", text)
    if not match:
        return None
    age = int(match.group(1))
    return age if 0 < age < 130 else None


def normalize_age_group(value: Any) -> str:
    group = str(value or "UNKNOWN").strip().upper()
    return group if group in {"CHILD", "TEEN", "YOUNG_ADULT", "ADULT", "SENIOR", "GENERAL", "ANY", "UNKNOWN"} else "UNKNOWN"


def age_to_group(age: int | None) -> str:
    """현재 ProfileReranker의 audience group enum에 맞춰 나이를 그룹화합니다.

    수정 포인트: 특정 장르나 키워드가 아니라 인구통계 속성(age)을 deterministic하게 변환합니다.
    19~29세는 YOUNG_ADULT, 30~64세는 ADULT로 두어 서비스의 audience 정책과 맞춥니다.
    """
    if age is None:
        return "UNKNOWN"
    if age <= 12:
        return "CHILD"
    if age <= 18:
        return "TEEN"
    if age <= 29:
        return "YOUNG_ADULT"
    if age <= 64:
        return "ADULT"
    return "SENIOR"


def resolve_age_group(profile_record: Mapping[str, Any], profile: Mapping[str, Any]) -> dict[str, Any]:
    persona_fields = profile_record.get("persona_fields") if isinstance(profile_record.get("persona_fields"), dict) else {}
    demographic_profile = profile.get("demographicProfile") or profile.get("demographic_profile") or {}
    if not isinstance(demographic_profile, dict):
        demographic_profile = {}

    for key in ("userAgeGroup", "user_age_group", "ageGroup", "age_group"):
        group = normalize_age_group(demographic_profile.get(key) or profile.get(key))
        if group not in {"UNKNOWN", "ANY"}:
            return {"age": None, "age_group": group, "source": f"LLM_PROFILE.{key}"}

    # 수정 포인트: Nemotron 원본 persona_fields에 있는 age/나이 계열 값을 우선 사용합니다.
    # 필드명이 조금 달라도 동작하도록 일반적인 age 계열 키를 순회합니다.
    candidate_keys = ("age", "Age", "AGE", "나이", "age_years", "ageYears", "years_old", "yearsOld")
    for key in candidate_keys:
        if key in persona_fields:
            age = parse_age_number(persona_fields.get(key))
            if age is not None:
                return {"age": age, "age_group": age_to_group(age), "source": f"PERSONA_FIELDS.{key}"}

    # 일부 row는 전체 문장 안에 `age: 55`처럼 들어올 수 있어 마지막으로 전체 persona_fields에서 추출합니다.
    age = parse_age_number(json.dumps(persona_fields, ensure_ascii=False, sort_keys=True, default=str))
    if age is not None:
        return {"age": age, "age_group": age_to_group(age), "source": "PERSONA_FIELDS.TEXT_SCAN"}
    return {"age": None, "age_group": "UNKNOWN", "source": "UNKNOWN"}


def build_rule_based_profile(profile: Mapping[str, Any], profile_record: Mapping[str, Any], *, max_terms: int, enable_age_group: bool = True) -> dict[str, Any]:
    """LLM 독서 프로필을 현재 ai-server ProfileReranker 입력 형태로 어댑팅합니다."""
    positive_sources = [
        profile.get("reading_purpose_summary"),
        profile.get("preference_summary"),
        profile.get("search_profile_text"),
        profile.get("interest_profile_text"),
        profile.get("reading_now_profile_text"),
        profile.get("read_completed_profile_text"),
        *list_values(profile.get("positive_terms")),
        *list_values(profile.get("preferred_terms")),
        *list_values(profile.get("interests")),
        *list_values(profile.get("hobbies")),
    ]
    negative_sources = [
        profile.get("dispreference_summary"),
        profile.get("dislike_profile_text"),
        *list_values(profile.get("negative_terms")),
        *list_values(profile.get("avoid_terms")),
    ]
    positive_terms = compact_terms(positive_sources, max_terms=max_terms, max_chars=360)
    negative_terms = compact_terms(negative_sources, max_terms=max_terms, max_chars=360)
    age_info = resolve_age_group(profile_record, profile) if enable_age_group else {"age": None, "age_group": "UNKNOWN", "source": "DISABLED"}

    # 수정 포인트: 기존 룰베이스가 읽는 필드명(reading_purpose_profile, preference_profile,
    # reviewPreferenceSignals)에 맞춰 LLM 결과를 복사합니다. 책 제목은 생성하지 않고 Qdrant 실제 후보만 사용합니다.
    # 또한 ProfileReranker의 audience alignment가 동작하도록 Nemotron age를 user age group으로 전달합니다.
    rule_profile: dict[str, Any] = {
        "readingPurpose": clean_compact_text(profile.get("reading_purpose_summary"), max_chars=600),
        "ageGroup": age_info["age_group"],
        "age_group": age_info["age_group"],
        "userAgeGroup": age_info["age_group"],
        "user_age_group": age_info["age_group"],
        "ageGroupSource": age_info["source"],
        "age_group_source": age_info["source"],
        "demographicProfile": {
            "age": age_info["age"],
            "userAgeGroup": age_info["age_group"],
            "ageGroupSource": age_info["source"],
        },
        "reading_purpose_profile": {
            "summary": clean_compact_text(profile.get("reading_purpose_summary"), max_chars=600),
            "positive_terms": positive_terms,
            "negative_terms": negative_terms,
        },
        "preference_profile": {
            "positiveTerms": positive_terms,
            "likedAspects": compact_terms([profile.get("preference_summary")], max_terms=max_terms, max_chars=360),
            "negativeTerms": negative_terms,
            "dislikedAspects": compact_terms([profile.get("dispreference_summary")], max_terms=max_terms, max_chars=360),
        },
        "reviewPreferenceSignals": [
            {
                "overallSentiment": "positive",
                "preferenceTerms": positive_terms,
                "likedAspects": compact_terms([profile.get("preference_summary")], max_terms=max_terms, max_chars=360),
                "rating": 4.5,
            },
            {
                "overallSentiment": "negative",
                "avoidTerms": negative_terms,
                "dislikedAspects": compact_terms([profile.get("dispreference_summary")], max_terms=max_terms, max_chars=360),
                "rating": 2.0,
            },
        ],
        "preferred_genres": list_values(profile.get("preferred_genres") or profile.get("preferredGenres")),
        "persona_id": profile_record.get("persona_id"),
        "synthetic_user_id": profile_record.get("synthetic_user_id"),
    }
    return rule_profile


def candidate_to_rule_dict(candidate: Any) -> dict[str, Any]:
    payload = dict(candidate.payload or {})
    row = dict(payload)
    # 수정 포인트: ProfileReranker가 실제 서비스 후보에서 읽는 대표 필드를 보강합니다.
    row.update(
        {
            "item_id": candidate.item_id,
            "book_id": payload.get("book_id"),
            "book_key": candidate.item_id,
            "isbn": candidate.isbn,
            "isbn13": candidate.isbn13,
            "title": candidate.title,
            "author": candidate.author,
            "publisher": candidate.publisher,
            "category": candidate.category,
            "categories": candidate.categories,
            "description": candidate.description,
            "score": candidate.qdrant_score,
            "qdrantScore": candidate.qdrant_score,
            "qdrant_score": candidate.qdrant_score,
            "_synthetic_item_id": candidate.item_id,
        }
    )
    return row


def rerank_candidates(
    *,
    reranker: ProfileReranker,
    candidates: Sequence[Any],
    rule_profile: Mapping[str, Any],
    event_type: str,
    rule_mode: str,
    profile_text_field: str,
    profile_query_text: str,
    limit: int,
    candidate_pool_scope: str = "PERSONAL",
    shared_group_key: str = "",
    shared_pool_query_text: str = "",
) -> list[RuleRankedCandidate]:
    if not candidates:
        return []
    candidate_by_id = {str(candidate.item_id): candidate for candidate in candidates}
    candidate_rows = [candidate_to_rule_dict(candidate) for candidate in candidates]
    ranked_rows = reranker.rerank(
        candidates=candidate_rows,
        profile=dict(rule_profile),
        personalized=True,
        mode=rule_mode,
    )
    direction = "ASC_RULE_SCORE_FOR_NEGATIVE" if event_type in NEGATIVE_EVENT_TYPES else "DESC_RULE_SCORE_FOR_POSITIVE"
    if event_type in NEGATIVE_EVENT_TYPES:
        ranked_rows = sorted(ranked_rows, key=lambda row: safe_float(row.get("rerank_score", row.get("score", 0.0))))
    else:
        ranked_rows = sorted(ranked_rows, key=lambda row: safe_float(row.get("rerank_score", row.get("score", 0.0))), reverse=True)

    result: list[RuleRankedCandidate] = []
    for index, row in enumerate(ranked_rows[: max(1, limit)], start=1):
        item_id = str(row.get("_synthetic_item_id") or row.get("item_id") or row.get("book_key") or "")
        candidate = candidate_by_id.get(item_id)
        if candidate is None:
            continue
        result.append(
            RuleRankedCandidate(
                candidate=candidate,
                ranked_payload=dict(row),
                event_type=event_type,
                profile_text_field=profile_text_field,
                profile_query_text=profile_query_text,
                rank_position=index,
                selection_direction=direction,
                candidate_pool_scope=candidate_pool_scope,
                shared_group_key=shared_group_key,
                shared_pool_query_text=shared_pool_query_text,
            )
        )
    return result


def merge_ranked_candidates(ranked_groups: Iterable[Sequence[RuleRankedCandidate]], *, negative: bool) -> list[RuleRankedCandidate]:
    by_item: dict[str, RuleRankedCandidate] = {}
    for group in ranked_groups:
        for item in group:
            existing = by_item.get(item.item_id)
            if existing is None:
                by_item[item.item_id] = item
                continue
            if negative:
                if item.rule_score < existing.rule_score:
                    by_item[item.item_id] = item
            else:
                if item.rule_score > existing.rule_score:
                    by_item[item.item_id] = item
    return sorted(by_item.values(), key=lambda item: item.rule_score, reverse=not negative)



def hash_bucket(value: Any, *, buckets: int) -> int:
    if buckets <= 1:
        return 0
    try:
        return int(stable_hash(value, length=8), 16) % buckets
    except Exception:
        return 0


def build_shared_group_key(
    profile_record: Mapping[str, Any],
    profile: Mapping[str, Any],
    *,
    group_buckets: int,
    enable_age_group: bool,
) -> str:
    """비슷한 사용자끼리 일부 도서를 공유하도록 deterministic group key를 만듭니다.

    수정 포인트: 특정 장르/키워드 if/else 없이 age_group과 LLM 독서 프로필 텍스트의 hash bucket만 사용합니다.
    따라서 페르소나 다양성은 유지하면서 LightFM이 학습할 수 있는 item overlap을 만듭니다.
    """
    age_info = resolve_age_group(profile_record, profile) if enable_age_group else {"age_group": "UNKNOWN"}
    age_group = normalize_age_group(age_info.get("age_group"))
    profile_basis = " | ".join(
        clean_compact_text(profile.get(key), max_chars=420)
        for key in (
            "reading_purpose_summary",
            "search_profile_text",
            "interest_profile_text",
            "preference_summary",
            "dispreference_summary",
        )
        if clean_compact_text(profile.get(key), max_chars=420)
    )
    bucket = hash_bucket(profile_basis or profile_record.get("persona_id"), buckets=max(1, int(group_buckets)))
    return f"age={age_group}|bucket={bucket:02d}"


def prepare_profile_records(
    profiles: Sequence[Mapping[str, Any]],
    *,
    group_buckets: int,
    enable_age_group: bool,
) -> list[PreparedProfileRecord]:
    prepared: list[PreparedProfileRecord] = []
    for index, raw_record in enumerate(profiles):
        persona_id = str(raw_record.get("persona_id") or raw_record.get("synthetic_user_id") or "").strip()
        if not persona_id:
            print(f"[SKIP PROFILE] index={index} reason=no persona_id", file=sys.stderr)
            continue
        try:
            profile = clean_profile_values(resolve_llm_profile(raw_record))
            profile_record = clean_profile_values(dict(raw_record))
        except ProfileSyntheticEventError as exc:
            print(f"[SKIP PROFILE] index={index} persona_id={persona_id} reason={exc}", file=sys.stderr)
            continue
        persona_fields = profile_record.get("persona_fields") if isinstance(profile_record.get("persona_fields"), dict) else {}
        persona_hash = str(profile_record.get("persona_hash") or stable_hash(profile_record))
        age_info = resolve_age_group(profile_record, profile)
        shared_group_key = build_shared_group_key(
            profile_record,
            profile,
            group_buckets=max(1, int(group_buckets)),
            enable_age_group=bool(enable_age_group),
        )
        prepared.append(
            PreparedProfileRecord(
                index=index,
                persona_id=persona_id,
                profile_record=dict(profile_record),
                profile=dict(profile),
                persona_fields=dict(persona_fields),
                persona_hash=persona_hash,
                age_info=age_info,
                shared_group_key=shared_group_key,
            )
        )
    return prepared


def build_group_index(prepared_profiles: Sequence[PreparedProfileRecord]) -> dict[str, list[PreparedProfileRecord]]:
    group_index: dict[str, list[PreparedProfileRecord]] = {}
    for prepared in prepared_profiles:
        group_index.setdefault(prepared.shared_group_key, []).append(prepared)
    return group_index


def build_shared_pool_query_text(
    *,
    profiles: Sequence[PreparedProfileRecord],
    event_type: str,
    action_search_fields: Mapping[str, tuple[str, ...]],
    max_profiles: int,
    max_chars: int,
) -> str:
    """그룹/전역 shared pool 조회용 query text를 만듭니다.

    수정 포인트: shared pool은 동일 그룹 사용자의 LLM profile action text를 샘플링해서 만듭니다.
    LLM을 다시 호출하지 않고, 하드코딩된 장르 목록도 사용하지 않습니다.
    """
    terms: list[str] = []
    sorted_profiles = sorted(profiles, key=lambda item: item.persona_id)
    for prepared in sorted_profiles[: max(1, int(max_profiles))]:
        try:
            profile_text, _field = resolve_profile_text(
                profile=prepared.profile,
                persona_fields=prepared.persona_fields,
                event_type=event_type,
                action_search_fields=action_search_fields,
            )
        except Exception:
            profile_text = ""
        for term in compact_terms(
            [
                profile_text,
                prepared.profile.get("reading_purpose_summary"),
                prepared.profile.get("preference_summary"),
                prepared.profile.get("dispreference_summary") if event_type in NEGATIVE_EVENT_TYPES else None,
            ],
            max_terms=8,
            max_chars=180,
        ):
            if term and term not in terms:
                terms.append(term)
    query = " | ".join(terms)
    return query[: max(200, int(max_chars))].rstrip()


def target_source_counts(
    *,
    target_count: int,
    group_ratio: float,
    global_ratio: float,
    shared_enabled: bool,
) -> dict[str, int]:
    if target_count <= 0:
        return {"personal": 0, "group": 0, "global": 0}
    if not shared_enabled:
        return {"personal": target_count, "group": 0, "global": 0}
    global_count = int(round(target_count * max(0.0, float(global_ratio))))
    group_count = int(round(target_count * max(0.0, float(group_ratio))))
    if target_count >= 3 and group_ratio > 0 and group_count == 0:
        group_count = 1
    if target_count < 10:
        global_count = 0
    if group_count + global_count > target_count:
        overflow = group_count + global_count - target_count
        group_count = max(0, group_count - overflow)
    personal_count = max(0, target_count - group_count - global_count)
    return {"personal": personal_count, "group": group_count, "global": global_count}


def take_ranked_candidates(
    source: Sequence[RuleRankedCandidate],
    *,
    count: int,
    used_item_ids: set[str],
) -> list[RuleRankedCandidate]:
    selected: list[RuleRankedCandidate] = []
    if count <= 0:
        return selected
    for ranked in source:
        if ranked.item_id in used_item_ids:
            continue
        selected.append(ranked)
        used_item_ids.add(ranked.item_id)
        if len(selected) >= count:
            return selected
    return selected


def select_mixed_rule_ranked_candidates(
    *,
    personal: Sequence[RuleRankedCandidate],
    group_shared: Sequence[RuleRankedCandidate],
    global_shared: Sequence[RuleRankedCandidate],
    fallback: Sequence[RuleRankedCandidate],
    target_count: int,
    used_item_ids: set[str],
    strict_counts: bool,
    persona_id: str,
    event_type: str,
    shared_enabled: bool,
    group_ratio: float,
    global_ratio: float,
) -> list[RuleRankedCandidate]:
    """개인 후보와 shared 후보를 섞어 최종 이벤트를 선택합니다.

    수정 포인트: 개인화 다양성을 유지하기 위해 personal 후보를 가장 많이 사용하고,
    비슷한 사용자 간 item overlap을 만들기 위해 group/global shared 후보를 일부만 섞습니다.
    """
    quotas = target_source_counts(
        target_count=target_count,
        group_ratio=group_ratio,
        global_ratio=global_ratio,
        shared_enabled=shared_enabled,
    )
    selected: list[RuleRankedCandidate] = []
    selected.extend(take_ranked_candidates(personal, count=quotas["personal"], used_item_ids=used_item_ids))
    selected.extend(take_ranked_candidates(group_shared, count=quotas["group"], used_item_ids=used_item_ids))
    selected.extend(take_ranked_candidates(global_shared, count=quotas["global"], used_item_ids=used_item_ids))

    # 수정 포인트: quota별 후보가 부족할 때는 점수 순 fallback으로 채워 strict count를 유지합니다.
    if len(selected) < target_count:
        fill_sources = [personal, group_shared, global_shared, fallback]
        for source in fill_sources:
            for ranked in source:
                if ranked.item_id in used_item_ids:
                    continue
                selected.append(ranked)
                used_item_ids.add(ranked.item_id)
                if len(selected) >= target_count:
                    return selected
    if strict_counts and len(selected) < target_count:
        raise ProfileSyntheticEventError(
            f"persona_id={persona_id} event_type={event_type} mixed 룰베이스 후보가 부족합니다. "
            f"expected={target_count} actual={len(selected)}. --action-candidate-limit 또는 shared pool limit을 늘려주세요."
        )
    return selected


def select_rule_ranked_candidates(
    *,
    primary: Sequence[RuleRankedCandidate],
    fallback: Sequence[RuleRankedCandidate],
    target_count: int,
    used_item_ids: set[str],
    strict_counts: bool,
    persona_id: str,
    event_type: str,
) -> list[RuleRankedCandidate]:
    selected: list[RuleRankedCandidate] = []
    for source in (primary, fallback):
        for ranked in source:
            if ranked.item_id in used_item_ids:
                continue
            selected.append(ranked)
            used_item_ids.add(ranked.item_id)
            if len(selected) >= target_count:
                return selected
    if strict_counts and len(selected) < target_count:
        raise ProfileSyntheticEventError(
            f"persona_id={persona_id} event_type={event_type} 룰베이스 후보가 부족합니다. "
            f"expected={target_count} actual={len(selected)}. --action-candidate-limit 또는 --action-candidate-extra를 늘려주세요."
        )
    return selected


def build_reader_config(args: argparse.Namespace, event_counts: Mapping[str, int]) -> GenerationConfig:
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


def enrich_rule_event_row(
    row: dict[str, Any],
    *,
    ranked: RuleRankedCandidate,
    profile_record: Mapping[str, Any],
    profile: Mapping[str, Any],
    rule_mode: str,
    read_ordinal: int | None,
) -> dict[str, Any]:
    row = enrich_event_row_with_profile(
        row,
        profile_record=profile_record,
        profile=profile,
        profile_action=ACTION_TYPE_BY_EVENT_TYPE.get(row.get("event_type"), row.get("event_type")),
        profile_text_field=ranked.profile_text_field,
        profile_query_text=ranked.profile_query_text,
        read_ordinal=read_ordinal,
    )
    # 수정 포인트: LightFM 학습 데이터가 기존 룰베이스 추천 결과를 teacher signal로 사용했음을 명시합니다.
    row["event_id"] = f"synthetic:rule:{stable_hash([row.get('synthetic_user_id'), row.get('item_id'), row.get('event_type'), row.get('sequence')], length=24)}"
    row["user_source"] = RULE_SOURCE
    row["event_source"] = RULE_SOURCE
    row["source"] = RULE_SOURCE
    row["profile_strategy"] = "llm_profile_rule_based_teacher_v1"
    age_info = resolve_age_group(profile_record, profile)
    row["user_age"] = age_info["age"]
    row["user_age_group"] = age_info["age_group"]
    row["age_group_source"] = age_info["source"]
    row["teacher_model"] = "RULE_BASED_PROFILE_RERANKER"
    row["rule_mode"] = rule_mode
    row["rule_based_score"] = round(ranked.rule_score, 6)
    row["rule_rank_position"] = ranked.rank_position
    row["rule_selection_direction"] = ranked.selection_direction
    row["candidate_pool_scope"] = ranked.candidate_pool_scope
    row["shared_group_key"] = ranked.shared_group_key or None
    row["shared_pool_query_text"] = ranked.shared_pool_query_text or None
    row["rule_rerank_reason"] = ranked.ranked_payload.get("rerank_reason")
    row["rule_score_detail"] = ranked.ranked_payload.get("score_detail")

    if row.get("event_type") in POSITIVE_EVENT_TYPES:
        multiplier = 0.75 + max(0.0, min(1.0, ranked.rule_score))
        row["weight"] = round(float(row.get("weight") or 0.0) * multiplier, 6)
        row["final_weight"] = row["weight"]
    elif row.get("event_type") in NEGATIVE_EVENT_TYPES:
        row["implicit_label"] = 0

    metadata = dict(row.get("metadata") or {})
    metadata.update(
        {
            "teacher_model": "RULE_BASED_PROFILE_RERANKER",
            "rule_mode": rule_mode,
            "user_age": age_info["age"],
            "user_age_group": age_info["age_group"],
            "age_group_source": age_info["source"],
            "rule_based_score": round(ranked.rule_score, 6),
            "rule_rank_position": ranked.rank_position,
            "rule_selection_direction": ranked.selection_direction,
            "candidate_pool_scope": ranked.candidate_pool_scope,
            "shared_group_key": ranked.shared_group_key or None,
            "shared_pool_query_text": ranked.shared_pool_query_text or None,
            "rule_rerank_reason": ranked.ranked_payload.get("rerank_reason"),
            "candidate_selection_policy": "PERSONAL_PLUS_GROUP_SHARED_PLUS_GLOBAL_SHARED_RULE_SCORE",
        }
    )
    row["metadata"] = metadata
    return row


def build_rule_candidate_row(
    *,
    persona_id: str,
    persona_hash: str,
    ranked: RuleRankedCandidate,
    rule_mode: str,
    profile_record: Mapping[str, Any],
    profile: Mapping[str, Any],
) -> dict[str, Any]:
    row = build_candidate_row(
        persona_id=persona_id,
        persona_hash=persona_hash,
        candidate=ranked.candidate,
        event_type=ranked.event_type,
        profile_action=ACTION_TYPE_BY_EVENT_TYPE.get(ranked.event_type, ranked.event_type),
        profile_text_field=ranked.profile_text_field,
    )
    age_info = resolve_age_group(profile_record, profile)
    row.update(
        {
            "candidate_source": RULE_SOURCE,
            "teacher_model": "RULE_BASED_PROFILE_RERANKER",
            "user_age": age_info["age"],
            "user_age_group": age_info["age_group"],
            "age_group_source": age_info["source"],
            "rule_mode": rule_mode,
            "rule_based_score": round(ranked.rule_score, 6),
            "rule_rank_position": ranked.rank_position,
            "rule_selection_direction": ranked.selection_direction,
            "candidate_pool_scope": ranked.candidate_pool_scope,
            "shared_group_key": ranked.shared_group_key or None,
            "shared_pool_query_text": ranked.shared_pool_query_text or None,
            "rule_rerank_reason": ranked.ranked_payload.get("rerank_reason"),
            "rule_score_detail": ranked.ranked_payload.get("score_detail"),
        }
    )
    return row


def parse_args() -> tuple[argparse.Namespace, GenerationConfig, dict[str, tuple[str, ...]]]:
    parser = argparse.ArgumentParser(
        description="Generate LightFM-ready synthetic events by using LLM persona profiles and the current rule-based ProfileReranker as teacher."
    )
    parser.add_argument("--persona-profile-path", required=True)
    parser.add_argument("--sample-size", type=int, default=100)
    parser.add_argument("--patterns", type=int, default=1)
    parser.add_argument("--strict-counts", action="store_true")
    parser.add_argument("--created-at-start", default="2026-01-01T00:00:00Z")

    parser.add_argument("--qdrant-url", default=os.getenv("QDRANT_URL", "http://127.0.0.1:6333"))
    parser.add_argument("--qdrant-api-key", default=os.getenv("QDRANT_API_KEY", ""))
    parser.add_argument("--qdrant-collection", default=os.getenv("QDRANT_KURE_COLLECTION", os.getenv("QDRANT_COLLECTION", "books_kure")))
    parser.add_argument("--qdrant-timeout-seconds", type=float, default=float(os.getenv("QDRANT_TIMEOUT_SECONDS", "60")))
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
    parser.add_argument("--action-candidate-limit", type=int, default=120)
    parser.add_argument("--action-candidate-multiplier", type=float, default=3.0)
    parser.add_argument("--action-candidate-extra", type=int, default=40)
    parser.add_argument("--rule-mode", choices=("QUERY_FIRST", "HYBRID", "PROFILE_FIRST", "DISABLED"), default="PROFILE_FIRST")
    parser.add_argument("--rule-term-limit", type=int, default=24)
    parser.add_argument("--enable-age-group", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--fallback-to-cross-action-candidates", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--enable-shared-pools", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--shared-group-ratio", type=float, default=0.25)
    parser.add_argument("--shared-global-ratio", type=float, default=0.05)
    parser.add_argument("--shared-group-buckets", type=int, default=12)
    parser.add_argument("--shared-group-query-profiles", type=int, default=12)
    parser.add_argument("--shared-global-query-profiles", type=int, default=48)
    parser.add_argument("--shared-pool-candidate-limit", type=int, default=120)
    parser.add_argument("--shared-query-max-chars", type=int, default=1800)

    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--failure-policy", choices=("abort", "skip"), default="skip")
    parser.add_argument("--max-failed-personas", type=int, default=100)
    parser.add_argument("--failure-cooldown-seconds", type=float, default=5.0)
    parser.add_argument("--output-candidates-path", default="data/lightfm/nemotron_rule_based_candidates.jsonl")
    parser.add_argument("--output-events-path", default="data/lightfm/nemotron_rule_based_synthetic_events.jsonl")

    args = parser.parse_args()
    event_counts = parse_map(args.event_counts, DEFAULT_EVENT_COUNTS, int)
    config = build_reader_config(args, event_counts)
    action_search_fields = parse_action_search_fields(args.action_search_fields)
    return args, config, action_search_fields


def main() -> int:
    args, config, action_search_fields = parse_args()
    profile_path = Path(args.persona_profile_path)
    profiles = read_jsonl(profile_path)
    if not profiles:
        raise ProfileSyntheticEventError(f"persona profile 파일에 row가 없습니다. path={profile_path}")

    prepared_profiles = prepare_profile_records(
        profiles,
        group_buckets=max(1, int(args.shared_group_buckets)),
        enable_age_group=bool(args.enable_age_group),
    )
    if not prepared_profiles:
        raise ProfileSyntheticEventError(f"persona profile 파일에서 사용할 수 있는 row가 없습니다. path={profile_path}")
    group_index = build_group_index(prepared_profiles)
    print(
        "[RULE SHARED POOL READY] "
        f"profiles={len(prepared_profiles)} groups={len(group_index)} "
        f"shared_enabled={bool(args.enable_shared_pools)} group_ratio={args.shared_group_ratio} global_ratio={args.shared_global_ratio}"
    )

    embedder = KureEmbeddingClient(
        base_url=config.kure_base_url,
        internal_api_key=config.kure_internal_api_key,
        header_name=config.kure_internal_header_name,
        timeout_seconds=config.embedding_timeout_seconds,
    )
    qdrant_reader = QdrantBookReader(config, embedder)
    reranker = ProfileReranker()
    shared_candidate_cache: dict[tuple[str, str, str], tuple[str, str, list[Any]]] = {}

    def get_shared_candidates(scope: str, group_key: str, event_type: str) -> tuple[str, str, list[Any]]:
        cache_key = (scope, group_key, event_type)
        if cache_key in shared_candidate_cache:
            return shared_candidate_cache[cache_key]
        if scope == "GROUP_SHARED":
            source_profiles = group_index.get(group_key, [])
            max_profiles = int(args.shared_group_query_profiles)
        else:
            source_profiles = prepared_profiles
            max_profiles = int(args.shared_global_query_profiles)
        query_text = build_shared_pool_query_text(
            profiles=source_profiles,
            event_type=event_type,
            action_search_fields=action_search_fields,
            max_profiles=max_profiles,
            max_chars=max(400, int(args.shared_query_max_chars)),
        )
        if not query_text:
            query_text = event_type
        limit = max(1, int(args.shared_pool_candidate_limit))
        candidates = qdrant_reader.search_by_persona(query_text, limit=limit)
        field_name = f"{scope.lower()}_query"
        shared_candidate_cache[cache_key] = (query_text, field_name, candidates)
        print(
            "[RULE SHARED POOL FETCHED] "
            f"scope={scope} group_key={group_key or 'GLOBAL'} event_type={event_type} "
            f"limit={limit} candidates={len(candidates)} query_chars={len(query_text)}"
        )
        return shared_candidate_cache[cache_key]

    if config.resume:
        completed_persona_ids, event_counter, existing_event_count = read_existing_event_state(config.output_events_path)
        print(
            "[RULE SYNTHETIC RESUME] "
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

    for prepared in prepared_profiles:
        if generated_personas >= config.sample_size:
            break
        persona_id = prepared.persona_id
        if persona_id in completed_persona_ids:
            print(f"[SKIP DONE] persona_id={persona_id}")
            continue

        persona_fields = prepared.persona_fields
        profile = prepared.profile
        profile_record = prepared.profile_record
        persona_hash = prepared.persona_hash
        rule_profile = build_rule_based_profile(
            profile,
            profile_record,
            max_terms=max(3, int(args.rule_term_limit)),
            enable_age_group=bool(args.enable_age_group),
        )
        age_info = resolve_age_group(profile_record, profile)
        print(
            f"[RULE PERSONA] {generated_personas + 1}/{config.sample_size} "
            f"persona_id={persona_id} age_group={age_info['age_group']} "
            f"age_source={age_info['source']} group_key={prepared.shared_group_key}"
        )

        try:
            ranked_by_event_type: dict[str, list[RuleRankedCandidate]] = {}
            ranked_sources_by_event_type: dict[str, dict[str, list[RuleRankedCandidate]]] = {}
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
                personal_ranked_candidates = rerank_candidates(
                    reranker=reranker,
                    candidates=candidates,
                    rule_profile=rule_profile,
                    event_type=event_type,
                    rule_mode=args.rule_mode,
                    profile_text_field=profile_text_field,
                    profile_query_text=profile_query_text,
                    limit=max(limit, target_per_pattern * max(1, config.patterns)),
                    candidate_pool_scope="PERSONAL",
                )

                group_ranked_candidates: list[RuleRankedCandidate] = []
                global_ranked_candidates: list[RuleRankedCandidate] = []
                if bool(args.enable_shared_pools):
                    group_query_text, group_field, group_candidates = get_shared_candidates(
                        "GROUP_SHARED", prepared.shared_group_key, event_type
                    )
                    group_ranked_candidates = rerank_candidates(
                        reranker=reranker,
                        candidates=group_candidates,
                        rule_profile=rule_profile,
                        event_type=event_type,
                        rule_mode=args.rule_mode,
                        profile_text_field=group_field,
                        profile_query_text=group_query_text,
                        limit=max(int(args.shared_pool_candidate_limit), target_per_pattern * max(1, config.patterns)),
                        candidate_pool_scope="GROUP_SHARED",
                        shared_group_key=prepared.shared_group_key,
                        shared_pool_query_text=group_query_text,
                    )
                    global_query_text, global_field, global_candidates = get_shared_candidates("GLOBAL_SHARED", "GLOBAL", event_type)
                    global_ranked_candidates = rerank_candidates(
                        reranker=reranker,
                        candidates=global_candidates,
                        rule_profile=rule_profile,
                        event_type=event_type,
                        rule_mode=args.rule_mode,
                        profile_text_field=global_field,
                        profile_query_text=global_query_text,
                        limit=max(int(args.shared_pool_candidate_limit), target_per_pattern * max(1, config.patterns)),
                        candidate_pool_scope="GLOBAL_SHARED",
                        shared_group_key="GLOBAL",
                        shared_pool_query_text=global_query_text,
                    )

                ranked_candidates = merge_ranked_candidates(
                    [personal_ranked_candidates, group_ranked_candidates, global_ranked_candidates],
                    negative=event_type in NEGATIVE_EVENT_TYPES,
                )
                ranked_sources_by_event_type[event_type] = {
                    "personal": personal_ranked_candidates,
                    "group": group_ranked_candidates,
                    "global": global_ranked_candidates,
                }
                if config.strict_counts and len(ranked_candidates) < target_per_pattern:
                    raise ProfileSyntheticEventError(
                        f"persona_id={persona_id} event_type={event_type} 룰베이스 후보가 부족합니다. "
                        f"required={target_per_pattern} actual={len(ranked_candidates)}"
                    )
                ranked_by_event_type[event_type] = ranked_candidates
                for ranked in ranked_candidates:
                    local_candidate_rows.append(
                        build_rule_candidate_row(
                            persona_id=persona_id,
                            persona_hash=persona_hash,
                            ranked=ranked,
                            rule_mode=args.rule_mode,
                            profile_record=profile_record,
                            profile=profile,
                        )
                    )

            positive_fallback = merge_ranked_candidates(
                [items for event, items in ranked_by_event_type.items() if event in POSITIVE_EVENT_TYPES],
                negative=False,
            )
            negative_fallback = merge_ranked_candidates(
                [items for event, items in ranked_by_event_type.items() if event in NEGATIVE_EVENT_TYPES] or ranked_by_event_type.values(),
                negative=True,
            )
            all_positive_fallback = positive_fallback if args.fallback_to_cross_action_candidates else []
            all_negative_fallback = negative_fallback if args.fallback_to_cross_action_candidates else []

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
                    source_groups = ranked_sources_by_event_type.get(event_type, {})
                    if event_type in NEGATIVE_EVENT_TYPES:
                        fallback = all_negative_fallback
                    else:
                        fallback = all_positive_fallback
                    selected = select_mixed_rule_ranked_candidates(
                        personal=source_groups.get("personal", []),
                        group_shared=source_groups.get("group", []),
                        global_shared=source_groups.get("global", []),
                        fallback=fallback,
                        target_count=target,
                        used_item_ids=used_item_ids,
                        strict_counts=config.strict_counts,
                        persona_id=persona_id,
                        event_type=event_type,
                        shared_enabled=bool(args.enable_shared_pools),
                        group_ratio=float(args.shared_group_ratio),
                        global_ratio=float(args.shared_global_ratio),
                    )
                    for ranked in selected:
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
                            candidate=ranked.candidate,
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
                            enrich_rule_event_row(
                                row,
                                ranked=ranked,
                                profile_record=profile_record,
                                profile=profile,
                                rule_mode=args.rule_mode,
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
                "[RULE PERSONA DONE] "
                f"persona_id={persona_id} events_added={len(local_event_rows)} candidates={len(local_candidate_rows)} "
                f"progress={generated_personas}/{config.sample_size} flushed=true"
            )
        except (SyntheticDataError, ProfileSyntheticEventError) as exc:
            failed_personas += 1
            global_sequence = existing_event_count + sum(event_counter.values())
            print(
                "[RULE PERSONA ERROR] "
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
            f"profiles_available={len(prepared_profiles)}, failed={failed_personas}. profile 파일을 더 생성하거나 --resume으로 이어서 실행해주세요."
        )

    print(
        "[RULE SYNTHETIC DONE] "
        f"personas={generated_personas} patterns={config.patterns} events_total={sum(event_counter.values())} "
        f"failed_personas={failed_personas} event_counts={dict(event_counter)} output_events={config.output_events_path}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SyntheticDataError, ProfileSyntheticEventError) as exc:
        print(f"[RULE SYNTHETIC ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
