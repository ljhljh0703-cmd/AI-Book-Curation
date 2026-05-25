from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Protocol

from app.services.common.config_loader import load_text_resource
from app.services.common.text_utils import normalize_text
from app.services.intent.reading_mode_policy import ReadingModePolicy


class ChatCompletionClient(Protocol):
    def chat_completion(self, system_prompt: str, user_prompt: str) -> str:
        ...


@dataclass(frozen=True)
class ChatIntent:
    """멀티턴/추천/서비스 분류 결과 값 객체입니다.

    수정 포인트:
    - 추천 라우팅, 검색어, hard filter, 독서 목적 해석, 리뷰/평점 취향 해석을 기존 intent classifier LLM 응답에 함께 담습니다.
    - 별도 LLM 호출을 추가하지 않고, 추천 파이프라인은 이 구조화 결과만 읽어 deterministic하게 동작합니다.
    """

    name: str
    query_type: str
    requires_history: bool
    source: str
    reason: str = ""
    recommendation_personalization_mode: str | None = None
    recommendation_exploration_intent: bool = False
    recommendation_diversity_required: bool = False
    recommendation_avoid_profile_dominance: bool = False
    recommendation_previous_action: str = "AUTO"
    recommendation_reason: str = ""
    recommendation_search_query: str | None = None
    recommendation_normalized_query: str | None = None
    recommendation_topic_query: str | None = None
    recommendation_reranker_query: str | None = None
    recommendation_query_specificity: str = "UNKNOWN"
    recommendation_explicit_filter_fields: List[str] = field(default_factory=list)
    recommendation_filter_isbn: str | None = None
    recommendation_filter_title: str | None = None
    recommendation_filter_author: str | None = None
    recommendation_filter_genres: List[str] = field(default_factory=list)
    recommendation_filter_genre_terms: List[str] = field(default_factory=list)
    recommendation_purpose_summary: str | None = None
    recommendation_requested_purpose: str | None = None
    recommendation_requested_audience: str | None = None
    recommendation_requested_audience_group: str = "UNKNOWN"
    recommendation_requested_education_stage: str = "UNKNOWN"
    recommendation_target_reader: str = "UNKNOWN"
    recommendation_purpose_positive_terms: List[str] = field(default_factory=list)
    recommendation_purpose_negative_terms: List[str] = field(default_factory=list)
    recommendation_audience_terms: List[str] = field(default_factory=list)
    recommendation_purpose_weight: float = 0.0
    recommendation_review_signal_available: bool = False
    recommendation_high_rating_positive_terms: List[str] = field(default_factory=list)
    recommendation_low_rating_negative_terms: List[str] = field(default_factory=list)
    recommendation_liked_aspects: List[str] = field(default_factory=list)
    recommendation_disliked_aspects: List[str] = field(default_factory=list)
    recommendation_preferred_mood: List[str] = field(default_factory=list)
    recommendation_avoid_mood: List[str] = field(default_factory=list)
    recommendation_strong_positive_books: List[Dict[str, Any]] = field(default_factory=list)
    recommendation_strong_negative_books: List[Dict[str, Any]] = field(default_factory=list)
    recommendation_count: int | None = None
    recommendation_consumption_context: str | None = None
    recommendation_consumption_context_type: str | None = None
    recommendation_visual_attention_limited: bool | None = None
    recommendation_hands_free_preferred: bool | None = None
    recommendation_requires_visual_reference: bool | None = None
    recommendation_reading_mode: str = "UNKNOWN"
    recommendation_consumption_positive_terms: List[str] = field(default_factory=list)
    recommendation_consumption_negative_terms: List[str] = field(default_factory=list)
    recommendation_consumption_weight: float = 0.0

    def recommendation_metadata(self) -> Dict[str, Any]:
        return {
            "llm_recommendation_personalization_mode": self.recommendation_personalization_mode,
            "llm_recommendation_exploration_intent": self.recommendation_exploration_intent,
            "llm_recommendation_diversity_required": self.recommendation_diversity_required,
            "llm_recommendation_avoid_profile_dominance": self.recommendation_avoid_profile_dominance,
            "llm_recommendation_previous_action": self.recommendation_previous_action,
            "llm_recommendation_reason": self.recommendation_reason,
            "llm_recommendation_search_query": self.recommendation_search_query,
            "llm_recommendation_normalized_query": self.recommendation_normalized_query,
            "llm_recommendation_topic_query": self.recommendation_topic_query,
            "llm_recommendation_reranker_query": self.recommendation_reranker_query,
            "llm_recommendation_query_specificity": self.recommendation_query_specificity,
            "llm_recommendation_explicit_filter_fields": self.recommendation_explicit_filter_fields,
            "llm_recommendation_filter_isbn": self.recommendation_filter_isbn,
            "llm_recommendation_filter_title": self.recommendation_filter_title,
            "llm_recommendation_filter_author": self.recommendation_filter_author,
            "llm_recommendation_filter_genres": self.recommendation_filter_genres,
            "llm_recommendation_filter_genre_terms": self.recommendation_filter_genre_terms,
            "llm_recommendation_purpose_summary": self.recommendation_purpose_summary,
            "llm_recommendation_requested_purpose": self.recommendation_requested_purpose,
            "llm_recommendation_requested_audience": self.recommendation_requested_audience,
            "llm_recommendation_requested_audience_group": self.recommendation_requested_audience_group,
            "llm_recommendation_requested_education_stage": self.recommendation_requested_education_stage,
            "llm_recommendation_target_reader": self.recommendation_target_reader,
            "llm_recommendation_purpose_positive_terms": self.recommendation_purpose_positive_terms,
            "llm_recommendation_purpose_negative_terms": self.recommendation_purpose_negative_terms,
            "llm_recommendation_audience_terms": self.recommendation_audience_terms,
            "llm_recommendation_purpose_weight": self.recommendation_purpose_weight,
            "llm_recommendation_review_signal_available": self.recommendation_review_signal_available,
            "llm_recommendation_high_rating_positive_terms": self.recommendation_high_rating_positive_terms,
            "llm_recommendation_low_rating_negative_terms": self.recommendation_low_rating_negative_terms,
            "llm_recommendation_liked_aspects": self.recommendation_liked_aspects,
            "llm_recommendation_disliked_aspects": self.recommendation_disliked_aspects,
            "llm_recommendation_preferred_mood": self.recommendation_preferred_mood,
            "llm_recommendation_avoid_mood": self.recommendation_avoid_mood,
            "llm_recommendation_strong_positive_books": self.recommendation_strong_positive_books,
            "llm_recommendation_strong_negative_books": self.recommendation_strong_negative_books,
            "llm_recommendation_count": self.recommendation_count,
            "llm_recommendation_consumption_context": self.recommendation_consumption_context,
            "llm_recommendation_consumption_context_type": self.recommendation_consumption_context_type,
            "llm_recommendation_visual_attention_limited": self.recommendation_visual_attention_limited,
            "llm_recommendation_hands_free_preferred": self.recommendation_hands_free_preferred,
            "llm_recommendation_requires_visual_reference": self.recommendation_requires_visual_reference,
            "llm_recommendation_reading_mode": self.recommendation_reading_mode,
            "llm_recommendation_consumption_positive_terms": self.recommendation_consumption_positive_terms,
            "llm_recommendation_consumption_negative_terms": self.recommendation_consumption_negative_terms,
            "llm_recommendation_consumption_weight": self.recommendation_consumption_weight,
        }


class ChatIntentClassifier:
    """LLM 기반 intent 분류기입니다.

    수정 포인트:
    - intent 판단은 LLM 구조화 결과를 우선 사용합니다.
    - LLM 실패 시에도 운영자가 표현 목록을 누적 관리하지 않도록 최소 fallback만 제공합니다.
    """

    VALID_INTENTS = {
        "recommend_book": "recommend",
        "book_lookup": "recommend",
        "list_previous_books": "service",
        "more_like_previous": "recommend",
        "refine_condition": "recommend",
        "service_help": "service",
        "unsupported": "unsupported",
    }
    VALID_PERSONALIZATION_MODES = {"QUERY_FIRST", "HYBRID", "PROFILE_FIRST", "DISABLED"}
    VALID_PREVIOUS_ACTIONS = {"AUTO", "NONE", "SOFT_DECAY", "HARD_EXCLUDE", "REPLAY"}
    VALID_QUERY_SPECIFICITY = {"BROAD", "CONSTRAINED", "UNKNOWN"}
    VALID_EXPLICIT_FILTER_FIELDS = {"isbn", "title", "author", "genre", "audience"}
    VALID_AUDIENCE_GROUPS = {"CHILD", "TEEN", "YOUNG_ADULT", "ADULT", "SENIOR", "GENERAL", "ANY", "UNKNOWN"}
    VALID_EDUCATION_STAGES = {"PRESCHOOL", "ELEMENTARY", "MIDDLE", "HIGH", "COLLEGE", "GENERAL", "UNKNOWN"}
    VALID_TARGET_READERS = {"SELF", "OTHER", "UNKNOWN"}

    def __init__(self, clova: ChatCompletionClient) -> None:
        self.clova = clova

    def classify(
        self,
        query: str,
        history: List[Dict[str, Any]] | None = None,
        history_text: str | None = None,
        profile_context: str | None = None,
    ) -> ChatIntent:
        has_history = bool(history)
        history_text = history_text or ""
        llm_intent = self._classify_by_llm(
            query=query,
            history_text=history_text,
            has_history=has_history,
            profile_context=profile_context or "",
        )
        if llm_intent is not None:
            return llm_intent
        return self._classify_by_fallback(query=query, has_history=has_history)

    def _classify_by_llm(
        self,
        query: str,
        history_text: str,
        has_history: bool,
        profile_context: str,
    ) -> ChatIntent | None:
        history_block = f"이전 대화 내역:\n{history_text}\n\n" if history_text else ""
        profile_block = f"사용자 추천 프로필 요약:\n{profile_context}\n\n" if profile_context else "사용자 추천 프로필 요약: 없음\n\n"
        system_prompt = load_text_resource("prompts/intent_classifier_system.md")
        user_template = load_text_resource("prompts/intent_classifier_user.md")
        user_prompt = (
            user_template
            .replace("{{history_block}}", history_block)
            .replace("{{profile_block}}", profile_block)
            .replace("{{query}}", query)
        )

        try:
            result = self.clova.chat_completion(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except Exception:
            return None

        if not result.strip():
            return None

        parsed = self._parse_json_response(result)
        if parsed:
            return self._intent_from_json(parsed, has_history=has_history)

        return self._intent_from_legacy_text(result, has_history=has_history)

    def _intent_from_json(self, parsed: Dict[str, Any], has_history: bool) -> ChatIntent:
        intent_name = str(parsed.get("intent") or "").strip()
        if intent_name not in self.VALID_INTENTS:
            intent_name = "service_help"

        requires_history = self._to_bool(parsed.get("requires_history"))
        if intent_name in ["list_previous_books", "more_like_previous", "refine_condition"]:
            requires_history = has_history

        recommendation = parsed.get("recommendation") if isinstance(parsed.get("recommendation"), dict) else {}
        explicit_filters = recommendation.get("explicit_filters") if isinstance(recommendation.get("explicit_filters"), dict) else {}
        purpose_profile = self._first_dict(
            recommendation.get("reading_purpose_profile"),
            recommendation.get("purpose_profile"),
        )
        review_profile = self._first_dict(
            recommendation.get("review_rating_preference_profile"),
            recommendation.get("review_preference_profile"),
        )
        consumption_profile = self._first_dict(
            recommendation.get("consumption_context"),
            recommendation.get("reading_mode_profile"),
        )
        reading_mode_profile = self._first_dict(
            recommendation.get("reading_mode"),
            recommendation.get("readingMode"),
            recommendation.get("reading_mode_profile"),
        )
        topic_profile = self._first_dict(recommendation.get("topic"))

        mode = self._normalize_personalization_mode(recommendation.get("personalization_mode"))
        conversation_policy = recommendation.get("conversation_policy") if isinstance(recommendation.get("conversation_policy"), dict) else {}
        previous_action = self._normalize_previous_action(conversation_policy.get("previous_recommendation_action"))
        purpose_weight = self._normalize_purpose_weight(
            purpose_profile.get("weight_hint", purpose_profile.get("weight"))
        )
        query_specificity = self._normalize_query_specificity(recommendation.get("query_specificity"))
        explicit_filter_fields = self._normalize_explicit_filter_fields(
            recommendation.get("explicit_filter_fields")
            or explicit_filters.get("explicit_filter_fields")
            or explicit_filters.get("fields")
        )
        legacy_filter_allowed = not explicit_filter_fields and query_specificity != "BROAD"

        raw_isbn = self._clean_optional_text(explicit_filters.get("isbn"))
        raw_title = self._clean_optional_text(explicit_filters.get("title"))
        raw_author = self._clean_optional_text(explicit_filters.get("author"))
        raw_genres = self._clean_text_list(explicit_filters.get("genres"), limit=6)
        topic_value = recommendation.get("topic")
        topic_query = self._clean_optional_text(
            recommendation.get("topic_query")
            or recommendation.get("topicQuery")
            or (topic_profile.get("query") if topic_profile else None)
            or (topic_profile.get("text") if topic_profile else None)
            or (topic_value if isinstance(topic_value, str) else None)
        )
        normalized_query = self._clean_optional_text(
            recommendation.get("normalized_query")
            or recommendation.get("normalizedQuery")
            or recommendation.get("retrieval_query")
            or recommendation.get("retrievalQuery")
            or recommendation.get("search_query")
        )
        reranker_query = self._clean_optional_text(
            recommendation.get("reranker_query")
            or recommendation.get("rerankerQuery")
            or recommendation.get("gte_reranker_query")
            or normalized_query
        )

        return ChatIntent(
            name=intent_name,
            query_type=self.VALID_INTENTS[intent_name],
            requires_history=has_history and requires_history,
            source="llm",
            reason="llm_classification_with_recommendation_intent",
            recommendation_personalization_mode=mode,
            recommendation_exploration_intent=self._to_bool(recommendation.get("exploration_intent")),
            recommendation_diversity_required=self._to_bool(recommendation.get("diversity_required")),
            recommendation_avoid_profile_dominance=self._to_bool(recommendation.get("avoid_current_profile_dominance")),
            recommendation_previous_action=previous_action,
            recommendation_reason=str(recommendation.get("reason") or "").strip(),
            recommendation_search_query=normalized_query,
            recommendation_normalized_query=normalized_query,
            recommendation_topic_query=topic_query,
            recommendation_reranker_query=reranker_query,
            recommendation_count=self._normalize_recommendation_count(recommendation.get("recommendation_count")),
            recommendation_consumption_context=self._clean_optional_text(
                consumption_profile.get("situation")
                or consumption_profile.get("context")
                or consumption_profile.get("consumption_context")
            ),
            recommendation_consumption_context_type=self._clean_optional_text(
                consumption_profile.get("type")
                or consumption_profile.get("context_type")
                or consumption_profile.get("contextType")
            ),
            recommendation_visual_attention_limited=self._to_optional_bool(
                self._first_present(
                    consumption_profile.get("visual_attention_limited"),
                    consumption_profile.get("visualAttentionLimited"),
                )
            ),
            recommendation_hands_free_preferred=self._to_optional_bool(
                self._first_present(
                    consumption_profile.get("hands_free_preferred"),
                    consumption_profile.get("handsFreePreferred"),
                )
            ),
            recommendation_requires_visual_reference=self._to_optional_bool(
                self._first_present(
                    reading_mode_profile.get("requires_visual_reference"),
                    reading_mode_profile.get("requiresVisualReference"),
                    consumption_profile.get("requires_visual_reference"),
                )
            ),
            recommendation_reading_mode=self._normalize_reading_mode(
                reading_mode_profile.get("preferred_modality")
                or reading_mode_profile.get("preferredModality")
                or consumption_profile.get("reading_mode")
                or consumption_profile.get("mode")
                or reading_mode_profile.get("mode")
            ),
            recommendation_consumption_positive_terms=self._clean_text_list(consumption_profile.get("positive_terms"), limit=12),
            recommendation_consumption_negative_terms=self._clean_text_list(consumption_profile.get("negative_terms"), limit=12),
            recommendation_consumption_weight=self._normalize_consumption_weight(
                consumption_profile.get("weight_hint") or consumption_profile.get("weight")
            ),
            recommendation_query_specificity=query_specificity,
            recommendation_explicit_filter_fields=explicit_filter_fields,
            recommendation_filter_isbn=raw_isbn if ("isbn" in explicit_filter_fields or legacy_filter_allowed) else None,
            recommendation_filter_title=raw_title if ("title" in explicit_filter_fields or legacy_filter_allowed) else None,
            recommendation_filter_author=raw_author if ("author" in explicit_filter_fields or legacy_filter_allowed) else None,
            recommendation_filter_genres=raw_genres if "genre" in explicit_filter_fields else [],
            recommendation_filter_genre_terms=self._clean_text_list(explicit_filters.get("genre_terms"), limit=10),
            recommendation_purpose_summary=self._clean_optional_text(purpose_profile.get("summary")),
            recommendation_requested_purpose=self._clean_optional_text(
                recommendation.get("requested_purpose") or purpose_profile.get("requested_purpose") or purpose_profile.get("summary")
            ),
            recommendation_requested_audience=self._clean_optional_text(
                recommendation.get("requested_audience") or explicit_filters.get("audience")
            ),
            recommendation_requested_audience_group=self._normalize_audience_group(
                recommendation.get("requested_audience_group")
                or explicit_filters.get("audience_group")
                or explicit_filters.get("audienceGroup")
            ),
            recommendation_requested_education_stage=self._normalize_education_stage(
                recommendation.get("requested_education_stage")
                or explicit_filters.get("education_stage")
                or explicit_filters.get("educationStage")
            ),
            recommendation_target_reader=self._normalize_target_reader(recommendation.get("target_reader")),
            recommendation_purpose_positive_terms=self._clean_text_list(purpose_profile.get("positive_terms"), limit=12),
            recommendation_purpose_negative_terms=self._clean_text_list(purpose_profile.get("negative_terms"), limit=12),
            recommendation_audience_terms=self._clean_text_list(
                recommendation.get("audience_terms") or explicit_filters.get("audience_terms"),
                limit=8,
            ),
            recommendation_purpose_weight=purpose_weight,
            recommendation_review_signal_available=self._to_bool(review_profile.get("signal_available")),
            recommendation_high_rating_positive_terms=self._clean_text_list(review_profile.get("high_rating_positive_terms"), limit=12),
            recommendation_low_rating_negative_terms=self._clean_text_list(review_profile.get("low_rating_negative_terms"), limit=12),
            recommendation_liked_aspects=self._clean_text_list(review_profile.get("liked_aspects"), limit=12),
            recommendation_disliked_aspects=self._clean_text_list(review_profile.get("disliked_aspects"), limit=12),
            recommendation_preferred_mood=self._clean_text_list(review_profile.get("preferred_mood"), limit=8),
            recommendation_avoid_mood=self._clean_text_list(review_profile.get("avoid_mood"), limit=8),
            recommendation_strong_positive_books=self._clean_book_list(review_profile.get("strong_positive_books"), limit=8),
            recommendation_strong_negative_books=self._clean_book_list(review_profile.get("strong_negative_books"), limit=8),
        )

    def _intent_from_legacy_text(self, text: str, has_history: bool) -> ChatIntent | None:
        intent_name = self._extract_value(text, "intent")
        requires_history_value = self._extract_value(text, "requires_history")
        requires_history = requires_history_value.startswith("yes")

        if intent_name not in self.VALID_INTENTS:
            return None

        if intent_name in ["list_previous_books", "more_like_previous", "refine_condition"]:
            requires_history = has_history

        return ChatIntent(
            name=intent_name,
            query_type=self.VALID_INTENTS[intent_name],
            requires_history=has_history and requires_history,
            source="llm_legacy",
            reason="legacy_llm_classification",
        )

    def _classify_by_fallback(self, query: str, has_history: bool) -> ChatIntent:
        if not str(query or "").strip():
            return ChatIntent(
                name="unsupported",
                query_type="unsupported",
                requires_history=False,
                source="fallback",
                reason="empty_query",
                recommendation_personalization_mode="DISABLED",
            )

        return ChatIntent(
            name="recommend_book",
            query_type="recommend",
            requires_history=has_history,
            source="fallback",
            reason="llm_unavailable_default_recommendation",
            recommendation_personalization_mode="PROFILE_FIRST",
            recommendation_query_specificity="BROAD",
            recommendation_previous_action="SOFT_DECAY" if has_history else "NONE",
        )



    @classmethod
    def _normalize_reading_mode(cls, value: Any) -> str:
        return ReadingModePolicy().normalize_mode(value)

    @staticmethod
    def _normalize_consumption_weight(value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(0.2, number))

    @staticmethod
    def _normalize_recommendation_count(value: Any) -> int | None:
        try:
            count = int(value)
        except (TypeError, ValueError):
            return None
        return count if 1 <= count <= 20 else None

    @classmethod
    def _parse_json_response(cls, text: str) -> Dict[str, Any] | None:
        value = text.strip()
        if value.startswith("```"):
            value = re.sub(r"^```(?:json)?", "", value, flags=re.IGNORECASE).strip()
            value = re.sub(r"```$", "", value).strip()
        if not value.startswith("{"):
            match = re.search(r"\{.*\}", value, flags=re.DOTALL)
            value = match.group(0) if match else value
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    @staticmethod
    def _first_dict(*values: Any) -> Dict[str, Any]:
        for value in values:
            if isinstance(value, dict):
                return value
        return {}

    @staticmethod
    def _first_present(*values: Any) -> Any:
        for value in values:
            if value is not None:
                return value
        return None

    @classmethod
    def _normalize_query_specificity(cls, value: Any) -> str:
        specificity = str(value or "UNKNOWN").strip().upper()
        return specificity if specificity in cls.VALID_QUERY_SPECIFICITY else "UNKNOWN"

    @classmethod
    def _normalize_explicit_filter_fields(cls, value: Any) -> List[str]:
        raw_values = value if isinstance(value, list) else [value] if value is not None else []
        result: List[str] = []
        seen = set()
        for item in raw_values:
            normalized = str(item or "").strip().lower()
            if normalized == "genres":
                normalized = "genre"
            if normalized not in cls.VALID_EXPLICIT_FILTER_FIELDS or normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)
        return result


    @classmethod
    def _normalize_audience_group(cls, value: Any) -> str:
        group = str(value or "UNKNOWN").strip().upper()
        return group if group in cls.VALID_AUDIENCE_GROUPS else "UNKNOWN"

    @classmethod
    def _normalize_education_stage(cls, value: Any) -> str:
        stage = str(value or "UNKNOWN").strip().upper()
        return stage if stage in cls.VALID_EDUCATION_STAGES else "UNKNOWN"

    @classmethod
    def _normalize_target_reader(cls, value: Any) -> str:
        reader = str(value or "UNKNOWN").strip().upper()
        return reader if reader in cls.VALID_TARGET_READERS else "UNKNOWN"

    @classmethod
    def _normalize_personalization_mode(cls, value: Any) -> str | None:
        mode = str(value or "").strip().upper()
        return mode if mode in cls.VALID_PERSONALIZATION_MODES else None

    @classmethod
    def _normalize_previous_action(cls, value: Any) -> str:
        action = str(value or "AUTO").strip().upper()
        return action if action in cls.VALID_PREVIOUS_ACTIONS else "AUTO"

    @staticmethod
    def _normalize_purpose_weight(value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(0.12, number))

    @staticmethod
    def _to_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        return str(value or "").strip().lower() in {"true", "yes", "y", "1", "on"}

    @classmethod
    def _to_optional_bool(cls, value: Any) -> bool | None:
        if value is None:
            return None
        return cls._to_bool(value)

    @staticmethod
    def _clean_optional_text(value: Any) -> str | None:
        if value is None:
            return None
        text = re.sub(r"\s+", " ", str(value).strip())
        if not text or text.lower() in {"null", "none"}:
            return None
        return text[:120]

    @classmethod
    def _clean_text_list(cls, value: Any, limit: int) -> List[str]:
        if value is None:
            return []
        raw_values = value if isinstance(value, list) else [value]

        result: List[str] = []
        seen = set()
        for item in raw_values:
            text = cls._clean_optional_text(item)
            if not text:
                continue
            normalized = normalize_text(text)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            result.append(text[:60])
            if len(result) >= limit:
                break
        return result

    @classmethod
    def _clean_book_list(cls, value: Any, limit: int) -> List[Dict[str, Any]]:
        if value is None:
            return []
        raw_values = value if isinstance(value, list) else [value]
        result: List[Dict[str, Any]] = []
        seen = set()
        for item in raw_values:
            if isinstance(item, dict):
                title = cls._clean_optional_text(item.get("title") or item.get("bookTitle") or item.get("name"))
                author = cls._clean_optional_text(item.get("author") or item.get("authors"))
                isbn = cls._clean_optional_text(item.get("isbn") or item.get("isbn13"))
            else:
                title = cls._clean_optional_text(item)
                author = None
                isbn = None
            key = normalize_text(isbn or f"{title or ''}|{author or ''}")
            if not title and not isbn:
                continue
            if not key or key in seen:
                continue
            seen.add(key)
            book: Dict[str, Any] = {}
            if title:
                book["title"] = title
            if author:
                book["author"] = author
            if isbn:
                book["isbn13"] = isbn
            result.append(book)
            if len(result) >= limit:
                break
        return result

    @staticmethod
    def _extract_value(text: str, key: str) -> str:
        match = re.search(rf"{key}\s*=\s*([^;\n]+)", text.strip(), flags=re.IGNORECASE)
        if not match:
            return ""
        return match.group(1).strip().lower()
