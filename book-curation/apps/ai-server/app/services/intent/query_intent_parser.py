from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Dict, List

from app.services.common.text_utils import normalize_text
from app.services.intent.chat_intent_classifier import ChatIntent
from app.services.intent.reading_mode_policy import ReadingModePolicy


@dataclass(frozen=True)
class QueryIntent:
    """Structured representation of a recommendation query."""

    raw_query: str
    isbn: str | None = None
    title: str | None = None
    author: str | None = None
    genres: List[str] = field(default_factory=list)
    soft_genres: List[str] = field(default_factory=list)
    purpose_terms: List[str] = field(default_factory=list)
    avoid_terms: List[str] = field(default_factory=list)
    audience_terms: List[str] = field(default_factory=list)
    requested_purpose: str | None = None
    requested_audience: str | None = None
    requested_audience_group: str = "UNKNOWN"
    requested_education_stage: str = "UNKNOWN"
    target_reader: str = "UNKNOWN"
    required_filters: List[str] = field(default_factory=list)
    retrieval_query: str | None = None
    topic_query: str | None = None
    reranker_query: str | None = None
    general_recommendation: bool = False
    query_specificity: str = "UNKNOWN"
    explicit_filter_fields: List[str] = field(default_factory=list)
    requested_recommendation_count: int | None = None
    consumption_context: str | None = None
    consumption_context_type: str | None = None
    visual_attention_limited: bool | None = None
    hands_free_preferred: bool | None = None
    requires_visual_reference: bool | None = None
    reading_mode: str = ReadingModePolicy.MODE_UNKNOWN
    consumption_positive_terms: List[str] = field(default_factory=list)
    consumption_negative_terms: List[str] = field(default_factory=list)
    consumption_weight: float = 0.0
    # 수정 포인트: 멀티턴 후속 질의에서 이전 추천의 소비 상황/청취 모드가 승계됐는지 추적합니다.
    multiturn_context_inherited: bool = False
    multiturn_context_source: str | None = None
    multiturn_context_reason: str | None = None
    inherited_reading_mode: str | None = None
    inherited_consumption_context: str | None = None
    inherited_requested_audience_group: str | None = None

    @property
    def has_required_filters(self) -> bool:
        return bool(self.required_filters)

    @property
    def is_precise_lookup(self) -> bool:
        return any(key in self.required_filters for key in ("isbn", "title", "author"))

    @property
    def fully_parsed(self) -> bool:
        return self.has_required_filters and bool(self.retrieval_query)

    @property
    def broad_recommendation(self) -> bool:
        return self.general_recommendation and self.query_specificity == "BROAD"

    @property
    def context_policy_applied(self) -> bool:
        return bool(
            self.consumption_context
            or self.reading_mode not in {ReadingModePolicy.MODE_UNKNOWN, ReadingModePolicy.MODE_ANY}
        )

    def metadata(self) -> Dict[str, Any]:
        return {
            "query_parse_author": self.author,
            "query_parse_title": self.title,
            "query_parse_isbn": self.isbn,
            "query_parse_genres": self.genres,
            "query_soft_genres": self.soft_genres,
            "query_purpose_terms": self.purpose_terms,
            "query_avoid_terms": self.avoid_terms,
            "query_audience_terms": self.audience_terms,
            "query_requested_purpose": self.requested_purpose,
            "query_requested_audience": self.requested_audience,
            "query_requested_audience_group": self.requested_audience_group,
            "query_requested_education_stage": self.requested_education_stage,
            "query_target_reader": self.target_reader,
            "query_required_filters": self.required_filters,
            "query_general_recommendation": self.general_recommendation,
            "query_fully_parsed": self.fully_parsed,
            "query_retrieval_query": self.retrieval_query,
            "query_topic_query": self.topic_query,
            "query_reranker_query": self.reranker_query,
            "query_specificity": self.query_specificity,
            "query_explicit_filter_fields": self.explicit_filter_fields,
            "query_broad_recommendation": self.broad_recommendation,
            "query_requested_recommendation_count": self.requested_recommendation_count,
            "query_consumption_context": self.consumption_context,
            "query_consumption_context_type": self.consumption_context_type,
            "query_visual_attention_limited": self.visual_attention_limited,
            "query_hands_free_preferred": self.hands_free_preferred,
            "query_requires_visual_reference": self.requires_visual_reference,
            "query_reading_mode": self.reading_mode,
            "query_consumption_positive_terms": self.consumption_positive_terms,
            "query_consumption_negative_terms": self.consumption_negative_terms,
            "query_consumption_weight": self.consumption_weight,
            "multi_turn_context_inherited": self.multiturn_context_inherited,
            "multi_turn_context_source": self.multiturn_context_source,
            "multi_turn_context_reason": self.multiturn_context_reason,
            "inherited_reading_mode": self.inherited_reading_mode,
            "inherited_consumption_context": self.inherited_consumption_context,
            "inherited_requested_audience_group": self.inherited_requested_audience_group,
            "detected_consumption_context": self.consumption_context,
            "consumption_context_type": self.consumption_context_type,
            "visual_attention_limited": self.visual_attention_limited,
            "hands_free_preferred": self.hands_free_preferred,
            "requires_visual_reference": self.requires_visual_reference,
            "detected_reading_mode": self.reading_mode,
            "topic_query": self.topic_query,
            "retrieval_query": self.retrieval_query,
            "reranker_query": self.reranker_query,
            "context_policy_applied": self.context_policy_applied,
        }


class QueryIntentParser:
    """Parse recommendation query intent without natural-language keyword rules.

    The parser trusts the LLM classifier for topic, consumption_context,
    reading_mode, and normalized retrieval/reranker queries. Local fallbacks are
    limited to language-agnostic ISBN and quoted-title extraction.
    """

    _TITLE_QUOTE_PATTERN = re.compile(r"[\"'`]+(.+?)[\"'`]+")
    _ISBN_PATTERN = re.compile(r"97[89][0-9\-\s]{10,}")

    def __init__(self, reading_mode_policy: ReadingModePolicy | None = None) -> None:
        self.reading_mode_policy = reading_mode_policy or ReadingModePolicy()

    def parse(self, query: str, chat_intent: ChatIntent | None = None) -> QueryIntent:
        raw_query = str(query or "").strip()
        isbn = self._first_non_empty(
            self._clean_isbn(getattr(chat_intent, "recommendation_filter_isbn", None)),
            self._extract_isbn(raw_query),
        )
        title = self._first_non_empty(
            getattr(chat_intent, "recommendation_filter_title", None),
            self._extract_quoted_title(raw_query),
        )
        author = self._first_non_empty(getattr(chat_intent, "recommendation_filter_author", None))
        topic_query = self._first_non_empty(getattr(chat_intent, "recommendation_topic_query", None))

        query_specificity = self._normalize_enum(
            getattr(chat_intent, "recommendation_query_specificity", "UNKNOWN"),
            {"BROAD", "CONSTRAINED", "UNKNOWN"},
            "UNKNOWN",
        )
        explicit_filter_fields = self._dedupe_field_names(
            list(getattr(chat_intent, "recommendation_explicit_filter_fields", []) or []),
            limit=8,
        )
        llm_genres = self._dedupe_texts(
            list(getattr(chat_intent, "recommendation_filter_genres", []) or []),
            limit=8,
        )
        llm_genre_terms = self._dedupe_texts(
            list(getattr(chat_intent, "recommendation_filter_genre_terms", []) or []),
            limit=12,
        )
        purpose_terms = self._dedupe_texts(
            list(getattr(chat_intent, "recommendation_purpose_positive_terms", []) or []),
            limit=12,
        )
        avoid_terms = self._dedupe_texts(
            list(getattr(chat_intent, "recommendation_purpose_negative_terms", []) or []),
            limit=12,
        )
        audience_terms = self._dedupe_texts(
            list(getattr(chat_intent, "recommendation_audience_terms", []) or []),
            limit=8,
        )
        requested_purpose = self._first_non_empty(getattr(chat_intent, "recommendation_requested_purpose", None))
        requested_audience = self._first_non_empty(getattr(chat_intent, "recommendation_requested_audience", None))
        requested_recommendation_count = self._normalize_count_value(
            getattr(chat_intent, "recommendation_count", None)
        )

        consumption_context = self._first_non_empty(
            getattr(chat_intent, "recommendation_consumption_context", None)
        )
        consumption_context_type = self._first_non_empty(
            getattr(chat_intent, "recommendation_consumption_context_type", None)
        )
        visual_attention_limited = getattr(chat_intent, "recommendation_visual_attention_limited", None)
        hands_free_preferred = getattr(chat_intent, "recommendation_hands_free_preferred", None)
        requires_visual_reference = getattr(chat_intent, "recommendation_requires_visual_reference", None)
        reading_mode = self.reading_mode_policy.normalize_mode(
            getattr(chat_intent, "recommendation_reading_mode", None)
        )
        consumption_positive_terms = self._dedupe_texts(
            list(getattr(chat_intent, "recommendation_consumption_positive_terms", []) or []),
            limit=12,
        )
        consumption_negative_terms = self._dedupe_texts(
            list(getattr(chat_intent, "recommendation_consumption_negative_terms", []) or []),
            limit=12,
        )
        consumption_weight = self.reading_mode_policy.normalize_weight(
            getattr(chat_intent, "recommendation_consumption_weight", 0.0),
            upper=0.2,
        )

        requested_audience_group = self._normalize_enum(
            getattr(chat_intent, "recommendation_requested_audience_group", "UNKNOWN"),
            {"CHILD", "TEEN", "YOUNG_ADULT", "ADULT", "SENIOR", "GENERAL", "ANY", "UNKNOWN"},
            "UNKNOWN",
        )
        requested_education_stage = self._normalize_enum(
            getattr(chat_intent, "recommendation_requested_education_stage", "UNKNOWN"),
            {"PRESCHOOL", "ELEMENTARY", "MIDDLE", "HIGH", "COLLEGE", "GENERAL", "UNKNOWN"},
            "UNKNOWN",
        )
        target_reader = self._normalize_enum(
            getattr(chat_intent, "recommendation_target_reader", "UNKNOWN"),
            {"SELF", "OTHER", "UNKNOWN"},
            "UNKNOWN",
        )

        required_filters: List[str] = []
        if isbn:
            required_filters.append("isbn")
        if title:
            required_filters.append("title")
        if author:
            required_filters.append("author")
        if llm_genres and "genre" in explicit_filter_fields:
            required_filters.append("genre")
        else:
            llm_genres = []

        retrieval_query = self._build_retrieval_query(
            raw_query=raw_query,
            isbn=isbn,
            title=title,
            author=author,
            genres=llm_genres,
            topic_query=topic_query,
            chat_intent=chat_intent,
            consumption_context=consumption_context,
            consumption_positive_terms=consumption_positive_terms,
        )
        reranker_query = self._build_reranker_query(
            raw_query=raw_query,
            chat_intent=chat_intent,
            retrieval_query=retrieval_query,
            consumption_context=consumption_context,
            consumption_positive_terms=consumption_positive_terms,
        )

        return QueryIntent(
            raw_query=raw_query,
            isbn=isbn,
            title=title,
            author=author,
            genres=llm_genres,
            soft_genres=self._dedupe_texts([*llm_genres, *llm_genre_terms], limit=12),
            purpose_terms=purpose_terms,
            avoid_terms=avoid_terms,
            audience_terms=audience_terms,
            requested_purpose=requested_purpose,
            requested_audience=requested_audience,
            requested_audience_group=requested_audience_group,
            requested_education_stage=requested_education_stage,
            target_reader=target_reader,
            required_filters=required_filters,
            retrieval_query=retrieval_query,
            topic_query=topic_query,
            reranker_query=reranker_query,
            general_recommendation=not required_filters and self._is_recommend_intent(chat_intent),
            query_specificity=query_specificity,
            explicit_filter_fields=explicit_filter_fields,
            requested_recommendation_count=requested_recommendation_count,
            consumption_context=consumption_context,
            consumption_context_type=consumption_context_type,
            visual_attention_limited=visual_attention_limited,
            hands_free_preferred=hands_free_preferred,
            requires_visual_reference=requires_visual_reference,
            reading_mode=reading_mode,
            consumption_positive_terms=consumption_positive_terms,
            consumption_negative_terms=consumption_negative_terms,
            consumption_weight=consumption_weight,
        )

    @staticmethod
    def _build_retrieval_query(
        *,
        raw_query: str,
        isbn: str | None,
        title: str | None,
        author: str | None,
        genres: List[str],
        topic_query: str | None,
        chat_intent: ChatIntent | None,
        consumption_context: str | None,
        consumption_positive_terms: List[str],
    ) -> str:
        if isbn:
            return isbn
        structured_terms = QueryIntentParser._join_unique_query_parts(consumption_positive_terms)
        llm_query = getattr(chat_intent, "recommendation_search_query", None)
        if topic_query and not consumption_context:
            return topic_query
        if llm_query:
            text = str(llm_query).strip()
            if not consumption_context:
                return text
            if not QueryIntentParser._is_consumption_context_contaminated_query(
                raw_query=raw_query,
                consumption_context=consumption_context,
                normalized_query=text,
            ):
                if structured_terms:
                    return QueryIntentParser._join_unique_query_parts([text, structured_terms])
                return text
        if consumption_context and structured_terms:
            return structured_terms
        parts = [part for part in [title, author, " ".join(genres), topic_query] if part]
        return " ".join(parts).strip() or raw_query.strip()

    @staticmethod
    def _build_reranker_query(
        *,
        raw_query: str,
        chat_intent: ChatIntent | None,
        retrieval_query: str | None,
        consumption_context: str | None,
        consumption_positive_terms: List[str],
    ) -> str:
        structured_terms = QueryIntentParser._join_unique_query_parts(consumption_positive_terms)
        llm_query = getattr(chat_intent, "recommendation_reranker_query", None)
        if llm_query:
            text = str(llm_query).strip()
            if not consumption_context:
                return text
            if not QueryIntentParser._is_consumption_context_contaminated_query(
                raw_query=raw_query,
                consumption_context=consumption_context,
                normalized_query=text,
            ):
                if structured_terms:
                    return QueryIntentParser._join_unique_query_parts([text, structured_terms])
                return text
        if retrieval_query:
            return retrieval_query
        if consumption_context and structured_terms:
            return structured_terms
        return raw_query.strip()

    @staticmethod
    def _is_consumption_context_contaminated_query(
        *,
        raw_query: str,
        consumption_context: str | None,
        normalized_query: str,
    ) -> bool:
        query_text = normalize_text(normalized_query)
        raw_text = normalize_text(raw_query)
        context_text = normalize_text(consumption_context or "")
        if not query_text:
            return True
        if query_text == raw_text:
            return True
        if context_text and (context_text in query_text or query_text in context_text):
            return True
        if raw_text and SequenceMatcher(None, query_text, raw_text).ratio() >= 0.72:
            return True
        return False

    @staticmethod
    def _join_unique_query_parts(values: List[str]) -> str:
        result: List[str] = []
        seen: set[str] = set()
        for value in values:
            for part in str(value or "").split():
                normalized = normalize_text(part)
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                result.append(part)
        return " ".join(result).strip()

    @staticmethod
    def _is_recommend_intent(chat_intent: ChatIntent | None) -> bool:
        return bool(chat_intent and getattr(chat_intent, "query_type", None) == "recommend")

    @staticmethod
    def _normalize_count_value(value: Any) -> int | None:
        try:
            count = int(value)
        except (TypeError, ValueError):
            return None
        return count if 1 <= count <= 20 else None

    def _extract_isbn(self, query: str) -> str | None:
        compact = re.sub(r"[^0-9Xx]", "", query)
        if len(compact) >= 10 and compact.startswith(("978", "979")):
            return compact
        match = self._ISBN_PATTERN.search(query)
        if not match:
            return None
        value = re.sub(r"[^0-9Xx]", "", match.group(0))
        return value if len(value) >= 10 else None

    def _extract_quoted_title(self, query: str) -> str | None:
        quoted = [item.strip() for item in self._TITLE_QUOTE_PATTERN.findall(query) if item.strip()]
        return quoted[0] if quoted else None

    @staticmethod
    def _clean_value(value: Any) -> str | None:
        cleaned = re.sub(r"\s+", " ", str(value or "")).strip()
        if not cleaned or cleaned.lower() in {"null", "none"}:
            return None
        return cleaned if len(cleaned) >= 2 else None

    @staticmethod
    def _clean_isbn(value: Any) -> str | None:
        if value is None:
            return None
        digits = re.sub(r"[^0-9Xx]", "", str(value))
        return digits if len(digits) >= 10 else None

    @classmethod
    def _dedupe_texts(cls, values: List[Any], limit: int) -> List[str]:
        result: List[str] = []
        seen = set()
        for value in values:
            text = cls._clean_value(value)
            if not text:
                continue
            normalized = normalize_text(text)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            result.append(text)
            if len(result) >= limit:
                break
        return result

    @classmethod
    def _dedupe_field_names(cls, values: List[Any], limit: int) -> List[str]:
        result: List[str] = []
        seen = set()
        for value in values:
            text = str(value or "").strip().lower()
            if text == "genres":
                text = "genre"
            if text not in {"isbn", "title", "author", "genre", "audience"}:
                continue
            if text in seen:
                continue
            seen.add(text)
            result.append(text)
            if len(result) >= limit:
                break
        return result

    @staticmethod
    def _normalize_enum(value: Any, allowed: set[str], default: str) -> str:
        normalized = str(value or default).strip().upper()
        return normalized if normalized in allowed else default

    @staticmethod
    def _first_non_empty(*values: Any) -> str | None:
        for value in values:
            text = str(value or "").strip()
            if text:
                return text
        return None
