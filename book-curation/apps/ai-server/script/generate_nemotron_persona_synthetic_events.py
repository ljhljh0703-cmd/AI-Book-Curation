#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

import requests
from common_env import load_ai_server_env

# 수정 포인트: 운영 FastAPI 설정과 동일하게 .env → .env.local 순서로 읽어 로컬 실행 시 키값 하드코딩을 제거합니다.
AI_SERVER_ROOT = load_ai_server_env(Path(__file__))

try:
    from datasets import load_dataset
except Exception:  # pragma: no cover - 실행 시 명확한 메시지를 출력합니다.
    load_dataset = None  # type: ignore[assignment]

try:
    from qdrant_client import QdrantClient
except Exception:  # pragma: no cover - 실행 시 명확한 메시지를 출력합니다.
    QdrantClient = None  # type: ignore[assignment]


CURRENT_PROJECT_EVENT_TYPES: tuple[str, ...] = (
    "FAVORITE_ADD",
    "READING_ADD",
    "READ_ADD",
    "RATING_ADD",
    "REVIEW_ADD",
    "DISLIKE_ADD",
)

# 수정 포인트: 현재 backend UserBehaviorEventType enum 기준 기본값입니다.
# 63건은 "관심 20 + 읽는중 3 + 읽은책 20 + 비선호 20"의 고유 도서 행동 기준으로 맞춥니다.
# 평점/리뷰는 별도 도서 슬롯을 차지하는 이벤트가 아니라 READ_ADD 20건 중 일부에 붙는 확장 속성으로 생성합니다.
DEFAULT_EVENT_COUNTS: dict[str, int] = {
    "FAVORITE_ADD": 20,
    "READING_ADD": 3,
    "READ_ADD": 20,
    "RATING_ADD": 0,
    "REVIEW_ADD": 0,
    "DISLIKE_ADD": 20,
}

# 수정 포인트: 읽은 책 20권 중 일부에 평점/리뷰 속성을 붙입니다.
# 기본값은 "읽은책 20권 중 평점 10권, 리뷰 10권"이며 CLI 옵션으로 조정 가능합니다.
DEFAULT_RATED_READ_COUNT = 10
DEFAULT_REVIEWED_READ_COUNT = 10
DEFAULT_RATING_WEIGHT_BONUS = 1.5
DEFAULT_REVIEW_WEIGHT_BONUS = 1.5

DEFAULT_EVENT_WEIGHTS: dict[str, float] = {
    "FAVORITE_ADD": 3.0,
    "READING_ADD": 3.0,
    "READ_ADD": 1.0,
    "RATING_ADD": 4.0,
    "REVIEW_ADD": 4.0,
    # 수정 포인트: 부정 이벤트는 파일에는 남기되 train_lightfm.py의 기본 제외 목록에서 제외합니다.
    "DISLIKE_ADD": 1.0,
}

# 수정 포인트: 외부로 노출되는 action_type은 도메인 의미를 유지하고, event_type은 현재 backend enum과 맞춥니다.
ACTION_TYPE_BY_EVENT_TYPE: dict[str, str] = {
    "FAVORITE_ADD": "INTEREST_REGISTER",
    "READING_ADD": "READING_REGISTER",
    "READ_ADD": "READ_COMPLETE",
    "RATING_ADD": "RATING",
    "REVIEW_ADD": "REVIEW",
    "DISLIKE_ADD": "DISLIKE_REGISTER",
}

POSITIVE_EVENT_TYPES = {"FAVORITE_ADD", "READING_ADD", "READ_ADD", "RATING_ADD", "REVIEW_ADD"}
NEGATIVE_EVENT_TYPES = {"DISLIKE_ADD"}
SCALAR_TYPES = (str, int, float, bool)
BOOK_ID_FIELDS: tuple[str, ...] = ("book_id", "item_id", "isbn13", "isbn", "id")
BOOK_TEXT_FIELDS: tuple[str, ...] = (
    "title",
    "author",
    "publisher",
    "description",
    "simple_intro",
    "book_intro",
    "categories",
    "cate_depth1",
    "cate_depth2",
    "cate_depth3",
    "kcid",
    "category",
    "categoryName",
    "category_name",
    "category_path",
    "genre",
    "genres",
    "target_audience",
    "audience_profile",
    "document",
)


class SyntheticDataError(RuntimeError):
    pass


@dataclass(frozen=True)
class BookCandidate:
    point_id: str
    item_id: str
    isbn: str
    isbn13: str
    title: str
    author: str
    publisher: str
    category: Any
    categories: Any
    description: str
    qdrant_score: float
    payload: dict[str, Any]


@dataclass(frozen=True)
class GenerationConfig:
    dataset_name: str
    dataset_split: str
    sample_size: int
    seed: int
    shuffle_buffer_size: int
    hf_token: str
    persona_id_field: str
    persona_fields: list[str]
    max_persona_field_chars: int
    qdrant_url: str
    qdrant_api_key: str
    qdrant_collection: str
    kure_base_url: str
    kure_internal_api_key: str
    kure_internal_header_name: str
    embedding_timeout_seconds: float
    qdrant_timeout_seconds: float
    qdrant_search_retries: int
    qdrant_retry_backoff_seconds: float
    qdrant_search_delay_seconds: float
    qdrant_min_candidate_pool_size: int
    candidate_pool_size: int
    event_counts: dict[str, int]
    event_weights: dict[str, float]
    source_weight: float
    rated_read_count: int
    reviewed_read_count: int
    rating_weight_bonus: float
    review_weight_bonus: float
    patterns: int
    strict_counts: bool
    # 수정 포인트: 1000명 이상 생성 중 Qdrant가 중간에 끊겨도 처음부터 다시 돌리지 않도록
    # 성공한 persona 단위로 JSONL을 즉시 flush하고, --resume으로 완료 persona를 건너뜁니다.
    resume: bool
    failure_policy: str
    max_failed_personas: int
    failure_cooldown_seconds: float
    max_source_scan: int
    output_persona_subset_path: Path | None
    output_events_path: Path
    output_candidates_path: Path | None
    created_at_start: datetime


class KureEmbeddingClient:
    def __init__(self, base_url: str, internal_api_key: str, header_name: str, timeout_seconds: float) -> None:
        if not base_url.strip():
            raise SyntheticDataError("KURE_EMBEDDING_BASE_URL 값이 비어 있습니다. apps/ai-server/.env.local을 확인해주세요.")
        self.base_url = base_url.rstrip("/")
        self.internal_api_key = internal_api_key.strip()
        self.header_name = header_name.strip() or "X-KURE-Internal-Key"
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()

    def embed(self, text: str) -> list[float]:
        headers = {self.header_name: self.internal_api_key} if self.internal_api_key else {}
        try:
            response = self.session.post(
                f"{self.base_url}/embed",
                json={"text": text},
                headers=headers,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            raise SyntheticDataError(
                "KURE embedding 호출에 실패했습니다. "
                f"base_url={self.base_url}, error={exc}. "
                "KURE_EMBEDDING_BASE_URL, KURE_INTERNAL_API_KEY, KURE_INTERNAL_HEADER_NAME 값을 확인해주세요."
            ) from exc

        vector = data.get("vector") or data.get("embedding")
        if not isinstance(vector, list) or not vector:
            raise SyntheticDataError(f"KURE embedding 응답에 vector가 없습니다. response_keys={list(data.keys())}")
        return [float(value) for value in vector]


class QdrantBookReader:
    def __init__(self, config: GenerationConfig, embedder: KureEmbeddingClient) -> None:
        if QdrantClient is None:
            raise SyntheticDataError(
                "qdrant-client 패키지가 없습니다. apps/ai-server에서 `py -3.11 -m pip install -r requirements-lightfm-training.txt`를 실행해주세요."
            )
        self.config = config
        self.embedder = embedder
        self.client = self._create_client()
        self._validate_connection()

    def _create_client(self) -> QdrantClient:
        # 수정 포인트: 장시간 대량 검색 중 connection pool이 끊기는 경우가 있어, 재시도 시 client를 재생성할 수 있게 분리합니다.
        try:
            if self.config.qdrant_api_key:
                return QdrantClient(
                    url=self.config.qdrant_url,
                    api_key=self.config.qdrant_api_key,
                    timeout=self.config.qdrant_timeout_seconds,
                )
            return QdrantClient(url=self.config.qdrant_url, timeout=self.config.qdrant_timeout_seconds)
        except Exception as exc:
            raise SyntheticDataError(
                f"QdrantClient 생성에 실패했습니다. qdrant_url={self.config.qdrant_url}, error={exc}"
            ) from exc

    def _reset_client(self) -> None:
        # 수정 포인트: 끊어진 HTTP connection pool을 재사용하지 않도록 기존 client를 닫고 새로 만듭니다.
        close = getattr(self.client, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass
        self.client = self._create_client()

    def _validate_connection(self) -> None:
        try:
            exists = self.client.collection_exists(self.config.qdrant_collection)
        except Exception as exc:
            raise SyntheticDataError(
                "Qdrant 연결 확인에 실패했습니다. "
                f"qdrant_url={self.config.qdrant_url}, collection={self.config.qdrant_collection}, error={exc}. "
                "QDRANT_URL, QDRANT_API_KEY, 방화벽/Tailscale/NodePort 접근성을 확인해주세요."
            ) from exc
        if not exists:
            raise SyntheticDataError(
                f"Qdrant 컬렉션이 없습니다. collection={self.config.qdrant_collection}. "
                "QDRANT_KURE_COLLECTION 또는 QDRANT_COLLECTION 값을 확인해주세요."
            )

        try:
            self.client.scroll(
                collection_name=self.config.qdrant_collection,
                limit=1,
                with_payload=True,
                with_vectors=False,
            )
        except Exception as exc:
            raise SyntheticDataError(
                "Qdrant scroll/read 테스트에 실패했습니다. "
                f"collection={self.config.qdrant_collection}, error={exc}. "
                "API key 권한과 컬렉션 payload 접근 가능 여부를 확인해주세요."
            ) from exc

    def search_by_persona(self, persona_text: str, limit: int) -> list[BookCandidate]:
        vector = self.embedder.embed(persona_text)
        last_error: Exception | None = None

        # 수정 포인트: NAS/Tailscale/Qdrant 조합에서 장시간 vector search 시 간헐적으로
        # "Server disconnected without sending a response"가 발생할 수 있어 재시도와 limit fallback을 둡니다.
        search_limits = self._build_search_limits(limit)
        for current_limit in search_limits:
            for attempt in range(1, self.config.qdrant_search_retries + 1):
                try:
                    if self.config.qdrant_search_delay_seconds > 0:
                        time.sleep(self.config.qdrant_search_delay_seconds)
                    response = self.client.query_points(
                        collection_name=self.config.qdrant_collection,
                        query=vector,
                        limit=current_limit,
                        with_payload=True,
                        with_vectors=False,
                    )
                    candidates: list[BookCandidate] = []
                    for point in response.points:
                        payload = dict(point.payload or {})
                        candidate = to_book_candidate(
                            payload=payload,
                            point_id=str(getattr(point, "id", "")),
                            qdrant_score=float(getattr(point, "score", 0.0) or 0.0),
                        )
                        if candidate is not None:
                            candidates.append(candidate)
                    return dedupe_book_candidates(candidates)
                except Exception as exc:  # pragma: no cover - 실제 네트워크 장애 대응 경로입니다.
                    last_error = exc
                    print(
                        "[QDRANT SEARCH RETRY] "
                        f"collection={self.config.qdrant_collection} limit={current_limit} "
                        f"attempt={attempt}/{self.config.qdrant_search_retries} error={exc}",
                        file=sys.stderr,
                    )
                    # 수정 포인트: 끊어진 HTTP connection pool을 그대로 재사용하지 않도록 client를 재생성합니다.
                    self._reset_client()
                    sleep_seconds = self.config.qdrant_retry_backoff_seconds * attempt
                    if sleep_seconds > 0:
                        time.sleep(sleep_seconds)

        raise SyntheticDataError(
            "Qdrant vector read/search에 실패했습니다. "
            f"collection={self.config.qdrant_collection}, requested_limit={limit}, tried_limits={search_limits}, "
            f"last_error={last_error}. "
            "books_kure 벡터 차원, Qdrant 리소스, Tailscale/NodePort 연결 상태를 확인해주세요."
        )

    def _build_search_limits(self, requested_limit: int) -> list[int]:
        min_limit = max(1, int(self.config.qdrant_min_candidate_pool_size))
        requested = max(min_limit, int(requested_limit))
        limits = [requested, 160, 128, 96, 80, 64, min_limit]
        result: list[int] = []
        for value in limits:
            normalized = max(min_limit, min(requested, int(value)))
            if normalized not in result:
                result.append(normalized)
        return result


def stable_hash(value: Any, length: int = 16) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def parse_csv(value: str) -> list[str]:
    return [part.strip() for part in str(value or "").split(",") if part.strip()]


def parse_map(value: str, defaults: Mapping[str, int | float], cast: type) -> dict[str, Any]:
    result = dict(defaults)
    if not value:
        return result
    for part in str(value).split(","):
        if not part.strip():
            continue
        if ":" not in part:
            raise ValueError(f"Invalid map item: {part!r}. Expected KEY:VALUE")
        key, raw_value = part.split(":", 1)
        key = key.strip().upper()
        if key not in CURRENT_PROJECT_EVENT_TYPES:
            raise ValueError(f"Unsupported event type: {key}. Allowed: {','.join(CURRENT_PROJECT_EVENT_TYPES)}")
        result[key] = cast(raw_value.strip())
    return result


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


def first_payload(payload: Mapping[str, Any], field_names: Sequence[str]) -> str:
    for field_name in field_names:
        value = payload.get(field_name)
        if value not in (None, "", [], {}):
            return compact_value(value, max_chars=1000)
    return ""


def to_book_candidate(payload: dict[str, Any], point_id: str, qdrant_score: float) -> BookCandidate | None:
    item_id = first_payload(payload, BOOK_ID_FIELDS) or point_id
    isbn = first_payload(payload, ("isbn13", "isbn"))
    isbn13 = first_payload(payload, ("isbn13", "isbn"))
    title = first_payload(payload, ("title", "book_title", "name"))
    if not item_id:
        return None
    return BookCandidate(
        point_id=point_id,
        item_id=item_id,
        isbn=isbn,
        isbn13=isbn13,
        title=title,
        author=first_payload(payload, ("author", "authors", "writer")),
        publisher=first_payload(payload, ("publisher",)),
        category=payload.get("category") or payload.get("categoryName") or payload.get("category_name"),
        categories=payload.get("categories") or payload.get("cate_depth1") or payload.get("kcid") or [],
        description=first_payload(payload, ("description", "simple_intro", "book_intro", "document")),
        qdrant_score=qdrant_score,
        payload=payload,
    )


def dedupe_book_candidates(candidates: Iterable[BookCandidate]) -> list[BookCandidate]:
    seen: set[str] = set()
    result: list[BookCandidate] = []
    for candidate in sorted(candidates, key=lambda item: item.qdrant_score, reverse=True):
        key = candidate.item_id
        if key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return result


def select_persona_fields(row: Mapping[str, Any], fields: Sequence[str], max_chars: int) -> dict[str, Any]:
    selected_names = [field for field in fields if field in row] if fields else list(row.keys())
    selected: dict[str, Any] = {}
    for field_name in selected_names:
        text = compact_value(row.get(field_name), max_chars=max_chars)
        if text:
            selected[field_name] = text
    return selected


def persona_text(persona_fields: Mapping[str, Any]) -> str:
    # 수정 포인트: 특정 장르/키워드 목록 없이 persona row의 실제 payload만 조합해 dense retrieval query로 사용합니다.
    parts = [compact_value(value, max_chars=700) for value in persona_fields.values()]
    return " ".join(part for part in parts if part).strip()


def resolve_persona_id(row: Mapping[str, Any], index: int, persona_id_field: str) -> str:
    for field_name in [persona_id_field, "persona_id", "id", "user_id", "uuid", "record_id"]:
        if not field_name:
            continue
        value = row.get(field_name)
        if value not in (None, ""):
            return f"persona:{str(value).strip()}"
    return f"persona:nemotron:{index:06d}:{stable_hash(row)}"


def stream_personas(config: GenerationConfig) -> Iterator[tuple[int, dict[str, Any]]]:
    if load_dataset is None:
        raise SyntheticDataError(
            "datasets 패키지가 없습니다. apps/ai-server에서 `py -3.11 -m pip install -r requirements-lightfm-training.txt`를 먼저 실행해주세요."
        )
    dataset_kwargs: dict[str, Any] = {"split": config.dataset_split, "streaming": True}
    if config.hf_token:
        dataset_kwargs["token"] = config.hf_token
    dataset = load_dataset(config.dataset_name, **dataset_kwargs)
    if config.shuffle_buffer_size > 0:
        dataset = dataset.shuffle(buffer_size=config.shuffle_buffer_size, seed=config.seed)
    for index, row in enumerate(dataset):
        # 수정 포인트: 실패 persona를 건너뛰고도 목표 sample_size를 채울 수 있도록
        # dataset scan 한도는 sample_size가 아니라 max_source_scan으로 분리합니다.
        if index >= config.max_source_scan:
            break
        if isinstance(row, dict):
            yield index, row


def pattern_window(candidates: Sequence[BookCandidate], pattern_index: int, events_per_pattern: int) -> list[BookCandidate]:
    if not candidates:
        return []
    start = (pattern_index * events_per_pattern) % len(candidates)
    rotated = list(candidates[start:]) + list(candidates[:start])
    return rotated


def select_candidates_for_pattern(
    candidates: Sequence[BookCandidate],
    event_counts: Mapping[str, int],
    pattern_index: int,
    strict_counts: bool,
) -> dict[str, list[BookCandidate]]:
    total_needed = sum(max(0, int(value)) for value in event_counts.values())
    window = pattern_window(candidates, pattern_index=pattern_index, events_per_pattern=max(1, total_needed))
    used: set[str] = set()
    selected: dict[str, list[BookCandidate]] = {}

    for event_type in CURRENT_PROJECT_EVENT_TYPES:
        target = max(0, int(event_counts.get(event_type, 0)))
        if target <= 0:
            selected[event_type] = []
            continue

        if event_type in NEGATIVE_EVENT_TYPES:
            source = list(reversed(window))
        else:
            source = window

        bucket: list[BookCandidate] = []
        for candidate in source:
            if candidate.item_id in used:
                continue
            bucket.append(candidate)
            used.add(candidate.item_id)
            if len(bucket) >= target:
                break
        if strict_counts and len(bucket) < target:
            raise SyntheticDataError(
                f"pattern={pattern_index} event_type={event_type} expected={target} actual={len(bucket)}. "
                "--candidate-pool-size를 늘리거나 --strict-counts를 빼고 다시 실행해주세요."
            )
        selected[event_type] = bucket
    return selected


def build_rating(event_type: str, ordinal: int, pattern_index: int) -> float | None:
    if event_type not in {"RATING_ADD", "REVIEW_ADD"}:
        return None
    values = [3.5, 4.0, 4.5, 5.0]
    return values[(ordinal + pattern_index) % len(values)]


def build_read_rating(read_ordinal: int, pattern_index: int) -> float:
    # 수정 포인트: 리뷰 문장/장르 키워드를 하드코딩하지 않고, 순번 기반 결정론적 평점만 생성합니다.
    values = [3.5, 4.0, 4.5, 5.0]
    return values[(read_ordinal + pattern_index) % len(values)]


def build_review_sentiment_score(read_ordinal: int, pattern_index: int) -> float:
    # 수정 포인트: 감성분석 모델이 붙기 전까지 사용할 수 있는 확장 컬럼입니다.
    # 자연어 리뷰 텍스트는 생성하지 않고, 후속 sentiment/LLM 파이프라인이 채울 수 있게 비워둡니다.
    values = [0.55, 0.65, 0.75, 0.85]
    return values[(read_ordinal + pattern_index) % len(values)]


def build_event_row(
    *,
    persona_id: str,
    synthetic_user_id: str,
    persona_hash: str,
    candidate: BookCandidate,
    event_type: str,
    event_weight: float,
    source_weight: float,
    sequence: int,
    pattern_index: int,
    created_at: str,
    qdrant_collection: str,
    read_ordinal: int | None = None,
    rated_read_count: int = DEFAULT_RATED_READ_COUNT,
    reviewed_read_count: int = DEFAULT_REVIEWED_READ_COUNT,
    rating_weight_bonus: float = DEFAULT_RATING_WEIGHT_BONUS,
    review_weight_bonus: float = DEFAULT_REVIEW_WEIGHT_BONUS,
) -> dict[str, Any]:
    rating = build_rating(event_type, ordinal=sequence, pattern_index=pattern_index)
    review_sentiment_score: float | None = None
    has_rating = False
    has_review = False
    weight_multiplier = 1.0

    if event_type == "READ_ADD" and read_ordinal is not None:
        has_rating = read_ordinal <= max(0, int(rated_read_count))
        has_review = read_ordinal <= max(0, int(reviewed_read_count))
        if has_rating:
            rating = build_read_rating(read_ordinal=read_ordinal, pattern_index=pattern_index)
            weight_multiplier += max(0.0, float(rating_weight_bonus))
        if has_review:
            review_sentiment_score = build_review_sentiment_score(read_ordinal=read_ordinal, pattern_index=pattern_index)
            weight_multiplier += max(0.0, float(review_weight_bonus))

    final_weight = round(max(0.0, event_weight) * max(0.0, source_weight) * weight_multiplier, 6)
    return {
        "event_id": f"synthetic:{stable_hash([synthetic_user_id, candidate.item_id, event_type, sequence], length=24)}",
        "persona_id": persona_id,
        "synthetic_user_id": synthetic_user_id,
        "user_key": synthetic_user_id,
        "user_source": "SYNTHETIC_NEMOTRON_QDRANT",
        "event_source": "SYNTHETIC_NEMOTRON_QDRANT",
        "source": "SYNTHETIC_NEMOTRON_QDRANT",
        "pattern_index": pattern_index,
        "sequence": sequence,
        "event_type": event_type,
        "action_type": ACTION_TYPE_BY_EVENT_TYPE.get(event_type, event_type),
        "implicit_label": 0 if event_type in NEGATIVE_EVENT_TYPES else 1,
        "weight": final_weight,
        "base_weight": event_weight,
        "source_weight": source_weight,
        "final_weight": final_weight,
        "rating": rating,
        # 수정 포인트: 현재 감성분석 모델이 없으므로 review_text는 비워두고 확장 컬럼만 제공합니다.
        "has_rating": has_rating,
        "has_review": has_review,
        "review_text": None,
        "review_sentiment_score": review_sentiment_score,
        "sentiment_label": None,
        "created_at": created_at,
        "event_time": created_at,
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
        "qdrant_collection": qdrant_collection,
        "qdrant_point_id": candidate.point_id,
        "qdrant_score": candidate.qdrant_score,
        "profile_strategy": "dense_persona_text_v1",
        "persona_hash": persona_hash,
        "metadata": {
            "persona_hash": persona_hash,
            "qdrant_payload_item_field_priority": list(BOOK_ID_FIELDS),
            "book_text_fields": list(BOOK_TEXT_FIELDS),
            "negative_event_policy": "LOWER_RANKED_DENSE_CANDIDATE" if event_type in NEGATIVE_EVENT_TYPES else None,
            "read_enrichment_policy": "READ_ADD_ROWS_HAVE_OPTIONAL_RATING_AND_REVIEW_COLUMNS",
        },
    }


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            fp.write("\n")
            count += 1
    return count


def append_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> int:
    # 수정 포인트: 대량 생성 중 장애가 나도 성공한 persona 결과를 보존하기 위해 persona 단위로 append합니다.
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("a", encoding="utf-8") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            fp.write("\n")
            count += 1
    return count


def truncate_jsonl_if_needed(path: Path | None, *, resume: bool) -> None:
    if path is None or resume:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def read_existing_event_state(path: Path) -> tuple[set[str], Counter[str], int]:
    # 수정 포인트: --resume 실행 시 이미 완료된 persona를 event 파일 기준으로 건너뜁니다.
    completed_persona_ids: set[str] = set()
    event_counter: Counter[str] = Counter()
    line_count = 0
    if not path.exists():
        return completed_persona_ids, event_counter, line_count
    with path.open("r", encoding="utf-8") as fp:
        for line_number, line in enumerate(fp, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError as exc:
                raise SyntheticDataError(
                    f"--resume 대상 파일에 깨진 JSONL 라인이 있습니다. path={path}, line={line_number}, error={exc}"
                ) from exc
            persona_id = str(row.get("persona_id") or "").strip()
            event_type = str(row.get("event_type") or "").strip()
            if persona_id:
                completed_persona_ids.add(persona_id)
            if event_type:
                event_counter[event_type] += 1
            line_count += 1
    return completed_persona_ids, event_counter, line_count


def build_persona_record(
    *,
    persona_id: str,
    index: int,
    config: GenerationConfig,
    persona_fields: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "persona_id": persona_id,
        "synthetic_user_id": persona_id,
        "dataset_name": config.dataset_name,
        "dataset_split": config.dataset_split,
        "source_index": index,
        "persona_fields": dict(persona_fields),
        "persona_hash": stable_hash(persona_fields),
        "created_at": now_iso_from_base(config.created_at_start, index),
    }


def parse_args() -> GenerationConfig:
    parser = argparse.ArgumentParser(
        description="Stream Nemotron-Personas-Korea and generate LightFM-ready synthetic behavior events from Qdrant books_kure."
    )
    parser.add_argument("--dataset-name", default="nvidia/Nemotron-Personas-Korea")
    parser.add_argument("--dataset-split", default="train")
    parser.add_argument("--sample-size", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--shuffle-buffer-size", type=int, default=10_000)
    parser.add_argument("--hf-token", default=os.getenv("HF_TOKEN", ""))
    parser.add_argument("--persona-id-field", default="")
    parser.add_argument("--persona-fields", default="")
    parser.add_argument("--max-persona-field-chars", type=int, default=1200)

    parser.add_argument("--qdrant-url", default=os.getenv("QDRANT_URL", "http://127.0.0.1:6333"))
    parser.add_argument("--qdrant-api-key", default=os.getenv("QDRANT_API_KEY", ""))
    parser.add_argument("--qdrant-collection", default=os.getenv("QDRANT_KURE_COLLECTION", os.getenv("QDRANT_COLLECTION", "books_kure")))
    parser.add_argument("--qdrant-timeout-seconds", type=float, default=float(os.getenv("QDRANT_TIMEOUT_SECONDS", "20")))
    parser.add_argument("--qdrant-search-retries", type=int, default=int(os.getenv("QDRANT_SEARCH_RETRIES", "8")))
    parser.add_argument("--qdrant-retry-backoff-seconds", type=float, default=float(os.getenv("QDRANT_RETRY_BACKOFF_SECONDS", "3")))
    parser.add_argument("--qdrant-search-delay-seconds", type=float, default=float(os.getenv("QDRANT_SEARCH_DELAY_SECONDS", "0.5")))

    parser.add_argument("--kure-base-url", default=os.getenv("KURE_EMBEDDING_BASE_URL", "http://127.0.0.1:8002"))
    parser.add_argument("--kure-internal-api-key", default=os.getenv("KURE_INTERNAL_API_KEY", ""))
    parser.add_argument("--kure-internal-header-name", default=os.getenv("KURE_INTERNAL_HEADER_NAME", "X-KURE-Internal-Key"))
    parser.add_argument("--embedding-timeout-seconds", type=float, default=float(os.getenv("KURE_REQUEST_TIMEOUT_SECONDS", "10")))

    parser.add_argument("--candidate-pool-size", type=int, default=128)
    parser.add_argument("--event-counts", default=",".join(f"{key}:{value}" for key, value in DEFAULT_EVENT_COUNTS.items()))
    parser.add_argument("--event-weights", default=",".join(f"{key}:{value}" for key, value in DEFAULT_EVENT_WEIGHTS.items()))
    parser.add_argument("--source-weight", type=float, default=0.4)
    parser.add_argument("--rated-read-count", type=int, default=DEFAULT_RATED_READ_COUNT)
    parser.add_argument("--reviewed-read-count", type=int, default=DEFAULT_REVIEWED_READ_COUNT)
    parser.add_argument("--rating-weight-bonus", type=float, default=DEFAULT_RATING_WEIGHT_BONUS)
    parser.add_argument("--review-weight-bonus", type=float, default=DEFAULT_REVIEW_WEIGHT_BONUS)
    parser.add_argument("--patterns", type=int, default=1)
    parser.add_argument("--strict-counts", action="store_true")
    parser.add_argument("--created-at-start", default="2026-01-01T00:00:00Z")
    parser.add_argument("--resume", action="store_true", help="기존 output-events JSONL을 기준으로 완료 persona를 건너뛰고 이어서 생성합니다.")
    parser.add_argument(
        "--failure-policy",
        choices=("abort", "skip"),
        default="skip",
        help="persona 1건 생성 실패 시 abort는 즉시 중단, skip은 cooldown 후 다음 persona로 진행합니다.",
    )
    parser.add_argument("--max-failed-personas", type=int, default=100)
    parser.add_argument("--failure-cooldown-seconds", type=float, default=30.0)
    parser.add_argument(
        "--max-source-scan",
        type=int,
        default=0,
        help="실패/스킵을 감안해 HF dataset에서 최대 몇 row까지 볼지 지정합니다. 0이면 sample-size*5를 사용합니다.",
    )

    parser.add_argument("--output-persona-subset-path", default="")
    parser.add_argument("--output-events-path", required=True)
    parser.add_argument("--output-candidates-path", default="")
    args = parser.parse_args()

    event_counts = parse_map(args.event_counts, DEFAULT_EVENT_COUNTS, int)
    event_weights = parse_map(args.event_weights, DEFAULT_EVENT_WEIGHTS, float)
    total_events_per_pattern = sum(max(0, int(value)) for value in event_counts.values())
    min_pool_size = total_events_per_pattern * max(1, int(args.patterns))
    candidate_pool_size = max(int(args.candidate_pool_size), min_pool_size)

    return GenerationConfig(
        dataset_name=args.dataset_name,
        dataset_split=args.dataset_split,
        sample_size=max(1, int(args.sample_size)),
        seed=int(args.seed),
        shuffle_buffer_size=max(0, int(args.shuffle_buffer_size)),
        hf_token=args.hf_token,
        persona_id_field=args.persona_id_field,
        persona_fields=parse_csv(args.persona_fields),
        max_persona_field_chars=max(200, int(args.max_persona_field_chars)),
        qdrant_url=args.qdrant_url,
        qdrant_api_key=args.qdrant_api_key,
        qdrant_collection=args.qdrant_collection,
        qdrant_search_retries=max(1, int(args.qdrant_search_retries)),
        qdrant_retry_backoff_seconds=max(0.0, float(args.qdrant_retry_backoff_seconds)),
        qdrant_search_delay_seconds=max(0.0, float(args.qdrant_search_delay_seconds)),
        qdrant_min_candidate_pool_size=min_pool_size,
        kure_base_url=args.kure_base_url,
        kure_internal_api_key=args.kure_internal_api_key,
        kure_internal_header_name=args.kure_internal_header_name,
        embedding_timeout_seconds=float(args.embedding_timeout_seconds),
        qdrant_timeout_seconds=float(args.qdrant_timeout_seconds),
        candidate_pool_size=candidate_pool_size,
        event_counts={str(key): int(value) for key, value in event_counts.items()},
        event_weights={str(key): float(value) for key, value in event_weights.items()},
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
        max_source_scan=max(max(1, int(args.sample_size)), int(args.max_source_scan) if int(args.max_source_scan) > 0 else max(1, int(args.sample_size)) * 5),
        output_persona_subset_path=Path(args.output_persona_subset_path) if args.output_persona_subset_path else None,
        output_events_path=Path(args.output_events_path),
        output_candidates_path=Path(args.output_candidates_path) if args.output_candidates_path else None,
        created_at_start=parse_datetime_utc(args.created_at_start),
    )


def main() -> int:
    config = parse_args()
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
        truncate_jsonl_if_needed(config.output_persona_subset_path, resume=False)
        truncate_jsonl_if_needed(config.output_candidates_path, resume=False)
        truncate_jsonl_if_needed(config.output_events_path, resume=False)

    global_sequence = existing_event_count
    generated_personas = len(completed_persona_ids)
    failed_personas = 0
    scanned_personas = 0

    for index, raw_persona in stream_personas(config):
        scanned_personas += 1
        if generated_personas >= config.sample_size:
            break

        persona_fields = select_persona_fields(raw_persona, fields=config.persona_fields, max_chars=config.max_persona_field_chars)
        if not persona_fields:
            print(f"[SKIP PERSONA] source_index={index} reason=no usable fields", file=sys.stderr)
            continue

        persona_id = resolve_persona_id(raw_persona, index=index, persona_id_field=config.persona_id_field)
        if persona_id in completed_persona_ids:
            print(f"[SKIP DONE] persona_id={persona_id}")
            continue

        persona_record = build_persona_record(persona_id=persona_id, index=index, config=config, persona_fields=persona_fields)
        p_text = persona_text(persona_fields)
        p_hash = str(persona_record["persona_hash"])
        print(f"[PERSONA] {generated_personas + 1}/{config.sample_size} persona_id={persona_id} query_chars={len(p_text)}")

        try:
            candidates = qdrant_reader.search_by_persona(p_text, limit=config.candidate_pool_size)
            if config.strict_counts and len(candidates) < sum(config.event_counts.values()):
                raise SyntheticDataError(
                    f"persona_id={persona_id} 후보가 부족합니다. required={sum(config.event_counts.values())} actual={len(candidates)}"
                )

            local_candidate_rows: list[dict[str, Any]] = []
            local_event_rows: list[dict[str, Any]] = []
            local_counter: Counter[str] = Counter()
            local_sequence_start = global_sequence

            for candidate in candidates:
                local_candidate_rows.append(
                    {
                        "persona_id": persona_id,
                        "persona_hash": p_hash,
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
                        "qdrant_collection": config.qdrant_collection,
                        "qdrant_point_id": candidate.point_id,
                        "qdrant_score": candidate.qdrant_score,
                    }
                )

            for pattern_index in range(config.patterns):
                synthetic_user_id = persona_id if config.patterns == 1 else f"{persona_id}:pattern:{pattern_index:02d}"
                selected = select_candidates_for_pattern(
                    candidates,
                    event_counts=config.event_counts,
                    pattern_index=pattern_index,
                    strict_counts=config.strict_counts,
                )
                pattern_count = 0
                event_type_ordinals: Counter[str] = Counter()
                for event_type in CURRENT_PROJECT_EVENT_TYPES:
                    for candidate in selected.get(event_type, []):
                        global_sequence += 1
                        pattern_count += 1
                        event_type_ordinals[event_type] += 1
                        read_ordinal = event_type_ordinals[event_type] if event_type == "READ_ADD" else None
                        row = build_event_row(
                            persona_id=persona_id,
                            synthetic_user_id=synthetic_user_id,
                            persona_hash=p_hash,
                            candidate=candidate,
                            event_type=event_type,
                            event_weight=float(config.event_weights.get(event_type, 1.0)),
                            source_weight=config.source_weight,
                            sequence=pattern_count,
                            pattern_index=pattern_index,
                            created_at=now_iso_from_base(config.created_at_start, global_sequence),
                            qdrant_collection=config.qdrant_collection,
                            read_ordinal=read_ordinal,
                            rated_read_count=config.rated_read_count,
                            reviewed_read_count=config.reviewed_read_count,
                            rating_weight_bonus=config.rating_weight_bonus,
                            review_weight_bonus=config.review_weight_bonus,
                        )
                        local_event_rows.append(row)
                        local_counter[event_type] += 1

            # 수정 포인트: 모든 산출물을 persona 성공 단위로 즉시 flush합니다.
            # 이 시점 이후 장애가 나도 --resume으로 이어서 생성할 수 있습니다.
            if config.output_persona_subset_path:
                append_jsonl(config.output_persona_subset_path, [persona_record])
            if config.output_candidates_path:
                append_jsonl(config.output_candidates_path, local_candidate_rows)
            append_jsonl(config.output_events_path, local_event_rows)

            completed_persona_ids.add(persona_id)
            generated_personas += 1
            event_counter.update(local_counter)
            print(
                "[PERSONA DONE] "
                f"persona_id={persona_id} candidates={len(candidates)} events_added={len(local_event_rows)} "
                f"progress={generated_personas}/{config.sample_size} flushed=true"
            )

        except SyntheticDataError as exc:
            failed_personas += 1
            # 수정 포인트: 실패한 persona에서 증가시킨 sequence는 파일에 flush하지 않았으므로 되돌립니다.
            global_sequence = existing_event_count + sum(event_counter.values())
            print(
                "[PERSONA ERROR] "
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
        raise SyntheticDataError(
            "목표 persona 수를 채우지 못했습니다. "
            f"generated={generated_personas}, target={config.sample_size}, scanned={scanned_personas}, "
            f"max_source_scan={config.max_source_scan}, failed={failed_personas}. "
            "이미 성공한 결과는 output JSONL에 저장되어 있으므로 --resume으로 이어서 실행하거나 "
            "--max-source-scan 값을 늘려주세요."
        )

    print(
        "[DONE] "
        f"personas={generated_personas} patterns={config.patterns} events_total={sum(event_counter.values())} "
        f"failed_personas={failed_personas} scanned={scanned_personas} "
        f"event_counts={dict(event_counter)} output_events={config.output_events_path} ai_server_root={AI_SERVER_ROOT}"
    )
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SyntheticDataError as exc:
        print(f"[SYNTHETIC DATA ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
