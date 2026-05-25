from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Tuple

from app.services.intent.chat_intent_classifier import ChatIntent
from app.services.intent.query_intent_parser import QueryIntent


class PersonalizationMode(str, Enum):
    QUERY_FIRST = "QUERY_FIRST"
    PROFILE_FIRST = "PROFILE_FIRST"
    HYBRID = "HYBRID"
    DISABLED = "DISABLED"


@dataclass(frozen=True)
class PersonalizationDecision:
    mode: PersonalizationMode
    query_score: float
    profile_score: float
    reason: str
    core_terms: Tuple[str, ...] = field(default_factory=tuple)
    exploration_intent: bool = False
    diversity_required: bool = False
    avoid_profile_dominance: bool = False
    source: str = "rule"


class QueryPersonalizationRouter:
    """질의 구조화 결과와 LLM 추천 intent를 기준으로 검색 전략을 선택합니다.

    수정 포인트:
    - 탐색형 요청 표현 키워드를 소스나 config에 누적하지 않습니다.
    - 기존 intent classifier LLM 응답에 포함된 personalization_mode/diversity 신호를 우선 사용합니다.
    - LLM 결과가 없거나 실패하면 deterministic parser 결과로 안전하게 후퇴합니다.
    """

    _SCORE_PRESETS = {
        PersonalizationMode.QUERY_FIRST: (0.90, 0.35),
        PersonalizationMode.HYBRID: (0.70, 0.45),
        PersonalizationMode.PROFILE_FIRST: (0.35, 0.90),
        PersonalizationMode.DISABLED: (1.00, 0.00),
    }

    def decide(
        self,
        query: str,
        profile: Dict[str, Any] | None,
        profile_enabled: bool,
        query_intent: QueryIntent | None = None,
        chat_intent: ChatIntent | None = None,
        context_reference_detected: bool = False,
    ) -> PersonalizationDecision:
        _ = query
        if not profile_enabled or not profile:
            return self._decision(
                mode=PersonalizationMode.DISABLED,
                reason="PERSONALIZATION_DISABLED",
                source="rule",
            )

        if context_reference_detected:
            # 수정 포인트: 참조형 후속 질문에서는 최근 대화/추천 카드가 온보딩 profile보다 우선입니다.
            # 프로필은 이후 reranking 보조 신호로만 쓰고, 검색 seed를 프로필 중심으로 바꾸지 않습니다.
            return self._decision(
                mode=PersonalizationMode.QUERY_FIRST,
                reason="MULTITURN_CONTEXT_FIRST",
                source="multiturn_context_policy",
            )

        if query_intent and query_intent.has_required_filters:
            return self._decision(
                mode=PersonalizationMode.QUERY_FIRST,
                reason="EXPLICIT_FILTER_THEN_PROFILE_RERANK",
                core_terms=tuple(query_intent.retrieval_query.split()) if query_intent.retrieval_query else tuple(),
                source="deterministic_filter",
            )

        if query_intent and getattr(query_intent, "consumption_context", None):
            # 수정 포인트: 소비 상황형 질의는 온보딩/profile이 검색 seed를 덮지 않게 합니다.
            # 프로필은 후보가 나온 뒤 보조 리랭킹 신호로만 쓰입니다.
            return self._decision(
                mode=PersonalizationMode.QUERY_FIRST,
                reason="CONSUMPTION_CONTEXT_QUERY_FIRST",
                core_terms=tuple(query_intent.retrieval_query.split()) if query_intent.retrieval_query else tuple(),
                source="consumption_context_policy",
            )

        llm_mode = self._mode_from_chat_intent(chat_intent)
        if llm_mode and llm_mode != PersonalizationMode.DISABLED:
            # 수정 포인트: 현재 질의 검색어가 구조화된 경우에는 BROAD 판정만으로 프로필 우선으로 덮지 않습니다.
            # 붙여 쓴 장르/주제 표현이 explicit_filter로 안 잡혀도 LLM search_query를 우선 존중합니다.
            return self._decision(
                mode=llm_mode,
                reason="LLM_INTENT_MODE",
                exploration_intent=bool(chat_intent and chat_intent.recommendation_exploration_intent),
                diversity_required=bool(chat_intent and chat_intent.recommendation_diversity_required),
                avoid_profile_dominance=bool(chat_intent and chat_intent.recommendation_avoid_profile_dominance),
                source="llm_intent",
            )

        if query_intent and query_intent.broad_recommendation:
            return self._decision(
                mode=PersonalizationMode.PROFILE_FIRST,
                reason="BROAD_PROFILE",
                diversity_required=True,
                source="deterministic_broad_profile",
            )

        return self._decision(
            mode=PersonalizationMode.PROFILE_FIRST,
            reason="PROFILE_FALLBACK",
            diversity_required=True,
            source="rule_fallback",
        )

    @classmethod
    def _decision(
        cls,
        mode: PersonalizationMode,
        reason: str,
        core_terms: Tuple[str, ...] = tuple(),
        exploration_intent: bool = False,
        diversity_required: bool = False,
        avoid_profile_dominance: bool = False,
        source: str = "rule",
    ) -> PersonalizationDecision:
        query_score, profile_score = cls._SCORE_PRESETS.get(mode, cls._SCORE_PRESETS[PersonalizationMode.HYBRID])
        if mode == PersonalizationMode.QUERY_FIRST:
            avoid_profile_dominance = True
        if mode == PersonalizationMode.HYBRID:
            diversity_required = True if diversity_required is False else diversity_required
        return PersonalizationDecision(
            mode=mode,
            query_score=query_score,
            profile_score=profile_score,
            reason=reason,
            core_terms=core_terms,
            exploration_intent=exploration_intent,
            diversity_required=diversity_required,
            avoid_profile_dominance=avoid_profile_dominance,
            source=source,
        )

    @staticmethod
    def _mode_from_chat_intent(chat_intent: ChatIntent | None) -> PersonalizationMode | None:
        if chat_intent is None:
            return None
        raw_mode = str(chat_intent.recommendation_personalization_mode or "").strip().upper()
        try:
            return PersonalizationMode(raw_mode)
        except ValueError:
            return None

    @staticmethod
    def build_decision_metadata(decision: PersonalizationDecision) -> Dict[str, Any]:
        return {
            "personalization_mode": decision.mode.value,
            "personalization_query_score": round(decision.query_score, 4),
            "personalization_profile_score": round(decision.profile_score, 4),
            "personalization_reason": decision.reason,
            "personalization_core_terms": list(decision.core_terms),
            "personalization_source": decision.source,
            "personalization_exploration_intent": decision.exploration_intent,
            "personalization_diversity_required": decision.diversity_required,
            "personalization_avoid_profile_dominance": decision.avoid_profile_dominance,
        }
