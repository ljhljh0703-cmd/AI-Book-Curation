from __future__ import annotations

from dataclasses import dataclass, field
import re
from statistics import median
from typing import Any, Dict, Iterable, List

from app.services.intent.query_intent_parser import QueryIntent
from app.services.intent.reading_mode_policy import ReadingModePolicy
from app.services.common.text_utils import normalize_text, safe_join
from app.services.common.source_format_policy import SourceFormatPolicy


@dataclass(frozen=True)
class RelevanceGateResult:
    candidates: List[Dict[str, Any]]
    excluded_count: int = 0
    penalized_count: int = 0
    applied_rules: List[str] = field(default_factory=list)
    mode: str = "NONE"  # NONE | FILTER | PENALTY


class RecommendationGuardrails:
    """Data-driven candidate relevance guardrails.

    The gate does not embed domain/genre keyword lists. It compares structured intent
    fields and candidate metadata, then writes evidence scores that deterministic
    reranking and reason generation can reuse.
    """

    SELF_AUDIENCE_BLOCK_GROUPS = {"INFANT", "CHILD", "ELEMENTARY"}
    SELF_AUDIENCE_BLOCK_STAGES = {"PRESCHOOL", "ELEMENTARY"}

    GENERAL_ELIGIBILITY_FIELDS = (
        "general_recommendation_eligible",
        "generalRecommendationEligible",
        "recommendationEligible",
    )
    INTENT_REQUIRED_FIELDS = (
        "intent_required_group",
        "intentRequiredGroup",
        "recommendationIntentGroup",
        "specialPurposeGroup",
    )
    TITLE_FIELDS = (
        "title",
        "subtitle",
    )
    FORMAT_FIELDS = (
        "format",
        "book_format",
        "media_type",
        "content_format",
        "is_audio_book",
        "is_ebook",
    )
    SUPPORT_TEXT_FIELDS = (
        *FORMAT_FIELDS,
        "author",
        "publisher",
        "description",
        "simple_intro",
        "book_intro",
        "author_intro",
        "book_index",
        "pub_review",
        "document",
    )
    TEXT_FIELDS = (*TITLE_FIELDS, *SUPPORT_TEXT_FIELDS)
    CATEGORY_FIELDS = (
        "categories",
        "cate_depth1",
        "cate_depth2",
        "cate_depth3",
        "kcid",
        "genre",
        "genres",
        "category",
        "categoryName",
        "category_name",
        "category_full_name",
        "category_path",
    )

    def apply_relevance_gate(
        self,
        *,
        candidates: List[Dict[str, Any]],
        query_intent: QueryIntent,
        min_remaining: int = 5,
    ) -> RelevanceGateResult:
        if not candidates:
            return RelevanceGateResult(candidates=[])

        annotated = self._annotate_relevance_scores(candidates=candidates, query_intent=query_intent)
        explicit_token_result = self._apply_explicit_query_token_gate(
            annotated,
            query_intent=query_intent,
            min_remaining=min_remaining,
        )
        title_only_result = self._apply_title_only_intent_gate(
            explicit_token_result.candidates,
            query_intent=query_intent,
            min_remaining=min_remaining,
        )
        metadata_result = self._apply_metadata_gate(
            title_only_result.candidates,
            query_intent=query_intent,
            min_remaining=min_remaining,
        )
        listening_format_result = self._apply_listening_format_gate(
            metadata_result.candidates,
            query_intent=query_intent,
            min_remaining=min_remaining,
        )
        audience_context_result = self._apply_context_audience_gate(
            listening_format_result.candidates,
            query_intent=query_intent,
            min_remaining=min_remaining,
        )
        consumption_mode_result = self._apply_consumption_mode_gate(
            audience_context_result.candidates,
            query_intent=query_intent,
            min_remaining=min_remaining,
        )
        semantic_result = self._apply_semantic_floor(
            consumption_mode_result.candidates,
            min_remaining=min_remaining,
        )

        return RelevanceGateResult(
            candidates=semantic_result.candidates,
            excluded_count=(
                explicit_token_result.excluded_count
                + title_only_result.excluded_count
                + metadata_result.excluded_count
                + listening_format_result.excluded_count
                + audience_context_result.excluded_count
                + consumption_mode_result.excluded_count
                + semantic_result.excluded_count
            ),
            penalized_count=(
                explicit_token_result.penalized_count
                + title_only_result.penalized_count
                + metadata_result.penalized_count
                + listening_format_result.penalized_count
                + audience_context_result.penalized_count
                + consumption_mode_result.penalized_count
                + semantic_result.penalized_count
            ),
            applied_rules=[
                *explicit_token_result.applied_rules,
                *title_only_result.applied_rules,
                *metadata_result.applied_rules,
                *listening_format_result.applied_rules,
                *audience_context_result.applied_rules,
                *consumption_mode_result.applied_rules,
                *semantic_result.applied_rules,
            ],
            mode=self._merge_mode(
                explicit_token_result.mode,
                self._merge_mode(
                    title_only_result.mode,
                    self._merge_mode(
                        metadata_result.mode,
                        self._merge_mode(
                            listening_format_result.mode,
                            self._merge_mode(
                                audience_context_result.mode,
                                self._merge_mode(consumption_mode_result.mode, semantic_result.mode),
                            ),
                        ),
                    ),
                ),
            ),
        )

    def _annotate_relevance_scores(
        self,
        *,
        candidates: List[Dict[str, Any]],
        query_intent: QueryIntent,
    ) -> List[Dict[str, Any]]:
        explicit_terms = [
            query_intent.isbn,
            query_intent.title,
            query_intent.author,
            *query_intent.genres,
        ]
        intent_terms = [
            *(query_intent.soft_genres or []),
            *(query_intent.purpose_terms or []),
            *(query_intent.audience_terms or []),
            query_intent.requested_purpose,
            query_intent.requested_audience,
        ]
        avoid_terms = list(query_intent.avoid_terms or [])
        genre_terms = self._effective_genre_terms(query_intent)

        result: List[Dict[str, Any]] = []
        for candidate in candidates:
            item = dict(candidate)
            score_detail = dict(item.get("score_detail") or {})
            semantic_score = self._normalize_score(self._candidate_score(item))
            explicit_query_tokens = self._explicit_query_tokens(query_intent)
            explicit_query_token_match = self._explicit_query_token_match_score(item, explicit_query_tokens)
            explicit_filter_match = self._term_match_score(item, explicit_terms, category_weight=1.0)
            genre_support_score = self._term_match_score(
                item,
                genre_terms,
                category_weight=1.0,
                text_weight=0.72,
                title_weight=0.0,
            )
            genre_title_only_score = self._title_only_term_match_score(
                item,
                genre_terms,
            )
            title_partial_score = self._title_partial_term_match_score(
                item,
                genre_terms,
            )
            title_only_intent_penalty = 0.0
            if (
                explicit_query_token_match <= 0
                and genre_terms
                and max(genre_title_only_score, title_partial_score) > 0
                and genre_support_score <= 0
            ):
                title_only_intent_penalty = 0.42

            intent_relevance_score = max(
                genre_support_score,
                self._term_match_score(item, query_intent.purpose_terms, category_weight=0.8, title_weight=0.24),
                self._term_match_score(item, query_intent.audience_terms, category_weight=0.8, title_weight=0.24),
                explicit_filter_match,
                explicit_query_token_match,
                semantic_score * 0.72,
            )
            audience_match_score = self._term_match_score(item, query_intent.audience_terms, category_weight=0.6)
            purpose_match_score = self._term_match_score(item, query_intent.purpose_terms, category_weight=0.7)
            listening_format_evidence = self._listening_format_evidence(item)
            format_mode_score = 1.0 if listening_format_evidence.get("matched") else 0.0
            raw_consumption_mode_score = self._term_match_score(
                item,
                getattr(query_intent, "consumption_positive_terms", []) or [],
                category_weight=0.16,
                text_weight=0.48,
                title_weight=0.0,
            )
            consumption_mode_score = max(format_mode_score, raw_consumption_mode_score)
            consumption_negative_score = self._term_match_score(
                item,
                getattr(query_intent, "consumption_negative_terms", []) or [],
                category_weight=0.62,
                text_weight=0.72,
                title_weight=0.3,
            )
            profile_match_score = self._profile_match_score(item)
            off_intent_penalty = round(0.18 * self._term_match_score(item, avoid_terms, category_weight=0.7), 6)
            specialized_content_penalty = self._specialized_content_penalty(item, query_intent)
            consumption_negative_penalty = round(0.16 * consumption_negative_score, 6)
            consumption_mode_mismatch_penalty = round(
                0.22
                if self._has_structured_consumption_mode(query_intent)
                and consumption_mode_score < 0.15
                else 0.0,
                6,
            )
            candidate_relevance_score = max(
                0.0,
                min(
                    1.0,
                    (semantic_score * 0.36)
                    + (intent_relevance_score * 0.24)
                    + (explicit_filter_match * 0.18)
                    + (purpose_match_score * 0.08)
                    + (audience_match_score * 0.06)
                    + (consumption_mode_score * max(0.08, min(0.18, getattr(query_intent, "consumption_weight", 0.0) or 0.0)))
                    + (profile_match_score * 0.08)
                    - off_intent_penalty
                    - specialized_content_penalty
                    - consumption_negative_penalty
                    - consumption_mode_mismatch_penalty
                    - title_only_intent_penalty,
                ),
            )

            policy_penalty = self._safe_float(item.get("policyPenalty"))
            policy_penalty += (
                off_intent_penalty
                + specialized_content_penalty
                + consumption_negative_penalty
                + consumption_mode_mismatch_penalty
                + title_only_intent_penalty
            )
            item["policyPenalty"] = round(policy_penalty, 6)
            item["candidateRelevanceScore"] = round(candidate_relevance_score, 6)
            score_detail.update(
                {
                    "semantic_score": round(semantic_score, 6),
                    "explicit_query_tokens": explicit_query_tokens,
                    "explicit_query_token_match": round(explicit_query_token_match, 6),
                    "explicit_filter_match": round(explicit_filter_match, 6),
                    "intent_relevance_score": round(intent_relevance_score, 6),
                    "audience_match_score": round(audience_match_score, 6),
                    "purpose_match_score": round(purpose_match_score, 6),
                    "consumption_mode_score": round(consumption_mode_score, 6),
                    "raw_consumption_mode_score": round(raw_consumption_mode_score, 6),
                    "listening_format_score": round(format_mode_score, 6),
                    "listening_format_evidence": listening_format_evidence,
                    "consumption_negative_score": round(consumption_negative_score, 6),
                    "consumption_negative_penalty": consumption_negative_penalty,
                    "consumption_mode_mismatch_penalty": consumption_mode_mismatch_penalty,
                    "consumption_context": getattr(query_intent, "consumption_context", None),
                    "reading_mode": getattr(query_intent, "reading_mode", "UNKNOWN"),
                    "profile_match_score": round(profile_match_score, 6),
                    "off_intent_penalty": off_intent_penalty,
                    "specialized_content_penalty": specialized_content_penalty,
                    "title_only_intent_penalty": round(title_only_intent_penalty, 6),
                    "genre_terms_for_guardrail": genre_terms,
                    "genre_support_score": round(genre_support_score, 6),
                    "genre_title_only_score": round(genre_title_only_score, 6),
                    "genre_title_partial_score": round(title_partial_score, 6),
                    "title_only_intent_match": bool(title_only_intent_penalty > 0),
                    "candidate_relevance_score": round(candidate_relevance_score, 6),
                    "confidence": round(max(semantic_score, intent_relevance_score, explicit_filter_match, consumption_mode_score, profile_match_score), 6),
                }
            )
            item["score_detail"] = score_detail
            result.append(item)
        return result

    def _apply_explicit_query_token_gate(
        self,
        candidates: List[Dict[str, Any]],
        *,
        query_intent: QueryIntent,
        min_remaining: int,
    ) -> RelevanceGateResult:
        # 수정 포인트: ETF, SQL, AI처럼 사용자가 명시한 영문 약어/기호 토큰은
        # 문자 포함(E/T/F)이나 부분 문자열이 아니라 독립 토큰 exact match로만 판단합니다.
        # 예: "ETF"는 "ETF 투자"에는 매칭되지만 "TOEFL/TOFEL"에는 매칭되지 않습니다.
        # 다만 검색 데이터에 약어가 누락된 정상 후보를 모두 제거하면 결과 0건 회귀가 생기므로,
        # exact match 후보가 충분할 때만 top 후보군을 필터링하고 부족하면 non-match는 강한 penalty로만 낮춥니다.
        explicit_tokens = self._explicit_query_tokens(query_intent)
        if not explicit_tokens or not candidates:
            return RelevanceGateResult(candidates=candidates)

        fully_matched: List[Dict[str, Any]] = []
        partially_matched: List[Dict[str, Any]] = []
        unmatched: List[Dict[str, Any]] = []
        for candidate in candidates:
            matched_count = self._explicit_query_token_match_count(candidate, explicit_tokens)
            if matched_count >= len(explicit_tokens):
                fully_matched.append(candidate)
            elif matched_count > 0:
                partially_matched.append(candidate)
            else:
                unmatched.append(candidate)

        token_supported = [*fully_matched, *partially_matched]
        if not token_supported:
            # 후보 전체에 명시 토큰이 전혀 없으면 Qdrant payload/소개에 약어가 누락됐을 가능성이 있습니다.
            # 이 경우 전체 결과를 날리지 않고 기존 semantic/rerank 흐름에 맡깁니다.
            return RelevanceGateResult(candidates=candidates)

        # 수정 포인트: 명시 영문 토큰이 있는 질의에서는 토큰 exact match 후보가 1개라도 있으면
        # 그 후보만 top 후보군으로 넘깁니다. 부족한 수량을 채우려고 TOEFL/TOEIC 같은 non-match 후보를
        # 다시 섞으면 LLM이 "ETF 입문서"라는 잘못된 이유를 붙이는 문제가 생깁니다.
        # 단, exact match 후보가 0개일 때만 결과 0건 방지를 위해 semantic fallback을 유지합니다.
        return RelevanceGateResult(
            candidates=token_supported,
            excluded_count=len(unmatched),
            applied_rules=["explicit_query_token_exact_top_guardrail"],
            mode="FILTER",
        )

    def _apply_title_only_intent_gate(
        self,
        candidates: List[Dict[str, Any]],
        *,
        query_intent: QueryIntent,
        min_remaining: int,
    ) -> RelevanceGateResult:
        # 수정 포인트: 구조화된 장르/주제 intent가 있을 때 제목에만 우연히 걸린 후보는
        # 후보가 충분하면 제거하고, 부족하면 soft penalty로만 처리합니다.
        # 특정 장르명을 if문으로 박지 않고, intent term이 제목 외 근거(카테고리/소개/목차/리뷰)에
        # 존재하는지 여부만 일반화해서 판단합니다.
        if not self._effective_genre_terms(query_intent):
            return RelevanceGateResult(candidates=candidates)

        title_only: List[Dict[str, Any]] = []
        kept: List[Dict[str, Any]] = []
        for candidate in candidates:
            score_detail = candidate.get("score_detail") if isinstance(candidate.get("score_detail"), dict) else {}
            if bool(score_detail.get("title_only_intent_match")):
                title_only.append(candidate)
            else:
                kept.append(candidate)

        if not title_only:
            return RelevanceGateResult(candidates=candidates)

        if len(kept) >= min_remaining:
            return RelevanceGateResult(
                candidates=kept,
                excluded_count=len(title_only),
                applied_rules=["title_only_intent_match"],
                mode="FILTER",
            )

        return RelevanceGateResult(
            candidates=self._penalize(candidates, title_only, penalty=0.22, penalty_type="title_only_intent_match"),
            penalized_count=len(title_only),
            applied_rules=["title_only_intent_match"],
            mode="PENALTY",
        )

    def _apply_metadata_gate(
        self,
        candidates: List[Dict[str, Any]],
        *,
        query_intent: QueryIntent,
        min_remaining: int,
    ) -> RelevanceGateResult:
        if not query_intent.general_recommendation:
            return RelevanceGateResult(candidates=candidates)

        blocked: List[Dict[str, Any]] = []
        kept: List[Dict[str, Any]] = []
        for candidate in candidates:
            if self._is_general_recommendation_blocked(candidate):
                blocked.append(candidate)
            else:
                kept.append(candidate)

        if not blocked:
            return RelevanceGateResult(candidates=candidates)

        if len(kept) >= min_remaining:
            return RelevanceGateResult(
                candidates=kept,
                excluded_count=len(blocked),
                applied_rules=["metadata_general_eligibility"],
                mode="FILTER",
            )

        return RelevanceGateResult(
            candidates=self._penalize(candidates, blocked, penalty=0.18, penalty_type="metadata_general_eligibility"),
            penalized_count=len(blocked),
            applied_rules=["metadata_general_eligibility"],
            mode="PENALTY",
        )

    def _apply_listening_format_gate(
        self,
        candidates: List[Dict[str, Any]],
        *,
        query_intent: QueryIntent,
        min_remaining: int,
    ) -> RelevanceGateResult:
        if not self._is_listening_mode(query_intent):
            return RelevanceGateResult(candidates=candidates)

        matched: List[Dict[str, Any]] = []
        unmatched: List[Dict[str, Any]] = []
        for candidate in candidates:
            evidence = self._listening_format_evidence(candidate)
            if evidence.get("matched"):
                matched.append(candidate)
            else:
                unmatched.append(candidate)

        if not matched:
            return RelevanceGateResult(candidates=candidates)

        # 수정 포인트: 실제 format metadata 또는 원천 카탈로그의 제목 format 표식이 있는 후보가 1건이라도 있으면
        # 임의의 유아책/자동차책으로 개수를 채우지 않고, 검증 가능한 후보만 우선 반환합니다.
        return RelevanceGateResult(
            candidates=matched,
            excluded_count=len(unmatched),
            applied_rules=["listening_format_source_required"],
            mode="FILTER",
        )

    def _apply_context_audience_gate(
        self,
        candidates: List[Dict[str, Any]],
        *,
        query_intent: QueryIntent,
        min_remaining: int,
    ) -> RelevanceGateResult:
        if not self._is_listening_mode(query_intent):
            return RelevanceGateResult(candidates=candidates)
        if self._requested_child_or_other_reader(query_intent):
            return RelevanceGateResult(candidates=candidates)

        blocked: List[Dict[str, Any]] = []
        kept: List[Dict[str, Any]] = []
        for candidate in candidates:
            if self._is_child_or_elementary_candidate(candidate):
                blocked.append(candidate)
            else:
                kept.append(candidate)

        if not blocked:
            return RelevanceGateResult(candidates=candidates)
        if kept:
            return RelevanceGateResult(
                candidates=kept,
                excluded_count=len(blocked),
                applied_rules=["self_listening_audience_guardrail"],
                mode="FILTER",
            )

        return RelevanceGateResult(
            candidates=self._penalize(candidates, blocked, penalty=0.35, penalty_type="self_listening_audience_guardrail"),
            penalized_count=len(blocked),
            applied_rules=["self_listening_audience_guardrail"],
            mode="PENALTY",
        )

    def _apply_consumption_mode_gate(
        self,
        candidates: List[Dict[str, Any]],
        *,
        query_intent: QueryIntent,
        min_remaining: int,
    ) -> RelevanceGateResult:
        if not self._has_structured_consumption_mode(query_intent):
            return RelevanceGateResult(candidates=candidates)

        matched: List[Dict[str, Any]] = []
        unmatched: List[Dict[str, Any]] = []
        for candidate in candidates:
            score_detail = candidate.get("score_detail") if isinstance(candidate.get("score_detail"), dict) else {}
            if self._safe_float(score_detail.get("consumption_mode_score")) >= 0.15:
                matched.append(candidate)
            else:
                unmatched.append(candidate)

        if not matched or not unmatched:
            return RelevanceGateResult(candidates=candidates)

        if len(matched) >= min_remaining:
            return RelevanceGateResult(
                candidates=matched,
                excluded_count=len(unmatched),
                applied_rules=["structured_consumption_mode_match"],
                mode="FILTER",
            )

        return RelevanceGateResult(
            candidates=self._penalize(
                candidates,
                unmatched,
                penalty=0.14,
                penalty_type="structured_consumption_mode_match",
            ),
            penalized_count=len(unmatched),
            applied_rules=["structured_consumption_mode_match"],
            mode="PENALTY",
        )

    def _apply_semantic_floor(self, candidates: List[Dict[str, Any]], *, min_remaining: int) -> RelevanceGateResult:
        if len(candidates) <= min_remaining:
            return RelevanceGateResult(candidates=candidates)

        scored = [(candidate, self._candidate_score(candidate)) for candidate in candidates]
        valid_scores = [score for _, score in scored if score is not None]
        if len(valid_scores) < min_remaining:
            return RelevanceGateResult(candidates=candidates)

        top_score = max(valid_scores)
        median_score = median(valid_scores)
        if top_score <= 0:
            return RelevanceGateResult(candidates=candidates)

        cutoff = max(top_score * 0.55, median_score * 0.8)
        rejected = [candidate for candidate, score in scored if score is not None and score < cutoff]

        if not rejected:
            return RelevanceGateResult(candidates=candidates)

        return RelevanceGateResult(
            candidates=self._penalize(candidates, rejected, penalty=0.12, penalty_type="semantic_score_floor"),
            penalized_count=len(rejected),
            applied_rules=["semantic_score_floor"],
            mode="PENALTY",
        )

    def _is_general_recommendation_blocked(self, candidate: Dict[str, Any]) -> bool:
        for field in self.GENERAL_ELIGIBILITY_FIELDS:
            value = candidate.get(field)
            if isinstance(value, bool):
                return not value
        return any(candidate.get(field) for field in self.INTENT_REQUIRED_FIELDS)

    @staticmethod
    def _is_listening_mode(query_intent: QueryIntent) -> bool:
        mode = str(getattr(query_intent, "reading_mode", ReadingModePolicy.MODE_UNKNOWN) or "").strip().upper()
        return mode == ReadingModePolicy.MODE_LISTENING_FRIENDLY

    @classmethod
    def _listening_format_evidence(cls, candidate: Dict[str, Any]) -> Dict[str, Any]:
        return SourceFormatPolicy.audiobook_evidence(candidate)

    @classmethod
    def _requested_child_or_other_reader(cls, query_intent: QueryIntent) -> bool:
        requested_group = str(getattr(query_intent, "requested_audience_group", "UNKNOWN") or "UNKNOWN").strip().upper()
        target_reader = str(getattr(query_intent, "target_reader", "UNKNOWN") or "UNKNOWN").strip().upper()
        requested_stage = str(getattr(query_intent, "requested_education_stage", "UNKNOWN") or "UNKNOWN").strip().upper()
        return bool(
            target_reader == "OTHER"
            or requested_group in {"CHILD", "TEEN"}
            or requested_stage in {"PRESCHOOL", "ELEMENTARY", "MIDDLE", "HIGH"}
        )

    @classmethod
    def _is_child_or_elementary_candidate(cls, candidate: Dict[str, Any]) -> bool:
        audience_profile = candidate.get("audience_profile") or candidate.get("audienceProfile") or {}
        if isinstance(audience_profile, dict):
            candidate_group = str(
                audience_profile.get("target_age_group")
                or audience_profile.get("targetAgeGroup")
                or audience_profile.get("audience_group")
                or audience_profile.get("audienceGroup")
                or "UNKNOWN"
            ).strip().upper()
            candidate_stage = str(
                audience_profile.get("education_stage")
                or audience_profile.get("educationStage")
                or "UNKNOWN"
            ).strip().upper()
            confidence = cls._safe_float(audience_profile.get("confidence"))
            if confidence >= 0.45 and (
                candidate_group in cls.SELF_AUDIENCE_BLOCK_GROUPS
                or candidate_stage in cls.SELF_AUDIENCE_BLOCK_STAGES
            ):
                return True

        target = str(candidate.get("target_audience") or candidate.get("targetAudience") or "").strip().upper()
        return target in cls.SELF_AUDIENCE_BLOCK_GROUPS

    @staticmethod
    def _has_structured_consumption_mode(query_intent: QueryIntent) -> bool:
        mode = str(getattr(query_intent, "reading_mode", "UNKNOWN") or "UNKNOWN").strip().upper()
        return bool(
            mode not in {"", "UNKNOWN", "ANY"}
            and getattr(query_intent, "consumption_positive_terms", None)
        )

    @classmethod
    def _effective_genre_terms(cls, query_intent: QueryIntent) -> List[str]:
        # 수정 포인트: LLM intent parser가 장르 용어를 누락해도 원문/검색어의 비교적 구체적인 토큰을
        # guardrail 보조 신호로 사용합니다. 특정 장르명을 하드코딩하지 않고, 후보 제목에만 우연히
        # 걸린 경우를 줄이기 위한 보조 근거입니다.
        values: List[Any] = [
            *(query_intent.soft_genres or []),
            *(query_intent.genres or []),
        ]
        sources = [query_intent.retrieval_query]
        if not getattr(query_intent, "consumption_context", None):
            sources.append(query_intent.raw_query)
        for source in sources:
            values.extend(cls._query_terms(source))

        result: List[str] = []
        seen = set()
        for value in values:
            text = str(value or "").strip()
            normalized = normalize_text(text)
            if not text or len(normalized) < 3 or normalized in seen:
                continue
            seen.add(normalized)
            result.append(text)
            if len(result) >= 12:
                break
        return result

    @classmethod
    def _explicit_query_tokens(cls, query_intent: QueryIntent) -> List[str]:
        values = [
            query_intent.retrieval_query,
            query_intent.title,
            *(query_intent.genres or []),
            *(query_intent.soft_genres or []),
        ]
        if not getattr(query_intent, "consumption_context", None):
            values.insert(0, query_intent.raw_query)
        result: List[str] = []
        seen: set[str] = set()
        for value in values:
            text = str(value or "")
            for token in re.findall(r"(?<![A-Za-z0-9])[A-Za-z][A-Za-z0-9+#.]{1,11}(?![A-Za-z0-9])", text):
                # 전체 소문자 일반 영어 단어는 강한 검색 제약으로 보지 않습니다.
                # 대문자 약어, 숫자/기호 포함 토큰만 exact token guardrail 대상으로 삼습니다.
                # 특정 도메인 단어 목록을 두지 않고 토큰 형태만 사용합니다.
                if token.islower() and not any(ch.isdigit() or ch in "+#." for ch in token):
                    continue
                normalized = token.lower()
                if normalized in seen:
                    continue
                seen.add(normalized)
                result.append(token)
                if len(result) >= 4:
                    return result
        return result

    @classmethod
    def _explicit_query_token_match_count(cls, candidate: Dict[str, Any], tokens: List[str]) -> int:
        if not tokens:
            return 0
        text = str(cls._candidate_full_text(candidate) or "")
        return sum(1 for token in tokens if cls._contains_latin_token(text, token))

    @classmethod
    def _explicit_query_token_match_score(cls, candidate: Dict[str, Any], tokens: List[str]) -> float:
        if not tokens:
            return 0.0
        return min(1.0, cls._explicit_query_token_match_count(candidate, tokens) / max(1, len(tokens)))

    @staticmethod
    def _contains_latin_token(text: Any, token: Any) -> bool:
        raw_text = str(text or "")
        raw_token = str(token or "").strip()
        if not raw_text or not raw_token:
            return False
        escaped = re.escape(raw_token)
        return re.search(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", raw_text, flags=re.IGNORECASE) is not None

    @staticmethod
    def _query_terms(value: Any) -> List[str]:
        raw = str(value or "").strip()
        if not raw:
            return []
        tokens = [token for token in re.split(r"[^0-9a-zA-Z가-힣]+", raw) if token]
        terms: List[str] = []
        for token in tokens:
            if len(normalize_text(token)) >= 3:
                terms.append(token)
        compact = normalize_text(raw)
        if len(compact) >= 4:
            terms.append(compact)
        return terms

    @classmethod
    def _title_partial_term_match_score(cls, candidate: Dict[str, Any], terms: Iterable[Any] | None) -> float:
        raw_terms = [str(term or "").strip() for term in (terms or []) if str(term or "").strip()]
        if not raw_terms:
            return 0.0
        title_text = normalize_text(cls._candidate_title_text(candidate))
        if not title_text:
            return 0.0

        matched = 0.0
        for term in raw_terms:
            normalized_term = normalize_text(term)
            if len(normalized_term) < 3:
                continue
            if normalized_term in title_text:
                matched += 1.0
                continue
            grams = cls._ngrams(normalized_term, size=3)
            if grams and any(gram in title_text for gram in grams):
                matched += 0.75
        return min(1.0, matched / max(1, len(raw_terms)))

    @staticmethod
    def _ngrams(value: str, *, size: int) -> List[str]:
        normalized = normalize_text(value)
        if len(normalized) < size:
            return []
        return [normalized[index:index + size] for index in range(0, len(normalized) - size + 1)]

    @classmethod
    def _support_contains_non_title_intent_term(cls, candidate: Dict[str, Any], term: Any) -> bool:
        support_text = cls._candidate_support_text(candidate)
        if not support_text:
            return False
        normalized_support = normalize_text(support_text)
        if not normalized_support:
            return False

        stripped_support = normalized_support
        for title_variant in cls._candidate_title_variants(candidate):
            normalized_variant = normalize_text(title_variant)
            if len(normalized_variant) >= 4:
                stripped_support = stripped_support.replace(normalized_variant, " ")

        return cls._contains_intent_term(stripped_support, term)

    @classmethod
    def _candidate_title_variants(cls, candidate: Dict[str, Any]) -> List[str]:
        raw_title = cls._candidate_title_text(candidate)
        if not raw_title:
            return []
        variants = [raw_title]
        for delimiter in ["-", "–", "—", ":", "：", "(", "[", "|"]:
            head = raw_title.split(delimiter, 1)[0].strip()
            if head and head != raw_title:
                variants.append(head)
        return variants

    @classmethod
    def _title_only_term_match_score(cls, candidate: Dict[str, Any], terms: Iterable[Any] | None) -> float:
        raw_terms = [str(term or "").strip() for term in (terms or []) if str(term or "").strip()]
        if not raw_terms:
            return 0.0
        title_text = normalize_text(cls._candidate_title_text(candidate))
        if not title_text:
            return 0.0
        matched = 0.0
        for term in raw_terms:
            normalized_term = normalize_text(term)
            if normalized_term and normalized_term in title_text:
                matched += 1.0
        return min(1.0, matched / max(1, len(raw_terms)))

    @classmethod
    def _term_match_score(
        cls,
        candidate: Dict[str, Any],
        terms: Iterable[Any] | None,
        *,
        category_weight: float,
        text_weight: float = 0.72,
        title_weight: float = 0.18,
    ) -> float:
        raw_terms = [str(term or "").strip() for term in (terms or []) if str(term or "").strip()]
        if not raw_terms:
            return 0.0

        category_text = cls._candidate_category_text(candidate)
        support_text = cls._candidate_support_text(candidate)
        title_text = cls._candidate_title_text(candidate)
        if not title_text and not support_text and not category_text:
            return 0.0

        matched = 0.0
        for term in raw_terms:
            if category_weight > 0 and cls._contains_intent_term(category_text, term):
                matched += category_weight
            elif text_weight > 0 and cls._support_contains_non_title_intent_term(candidate, term):
                matched += text_weight
            elif title_weight > 0 and cls._contains_intent_term(title_text, term):
                matched += title_weight
        return min(1.0, matched / max(1, len(raw_terms)))

    @classmethod
    def _candidate_full_text(cls, candidate: Dict[str, Any]) -> str:
        parts = [safe_join(candidate.get(field)) for field in [*cls.TEXT_FIELDS, *cls.CATEGORY_FIELDS] if candidate.get(field)]
        return " ".join(parts)

    @classmethod
    def _candidate_support_text(cls, candidate: Dict[str, Any]) -> str:
        parts = [safe_join(candidate.get(field)) for field in cls.SUPPORT_TEXT_FIELDS if candidate.get(field)]
        return " ".join(parts)

    @classmethod
    def _candidate_title_text(cls, candidate: Dict[str, Any]) -> str:
        parts = [safe_join(candidate.get(field)) for field in cls.TITLE_FIELDS if candidate.get(field)]
        return " ".join(parts)

    @classmethod
    def _candidate_category_text(cls, candidate: Dict[str, Any]) -> str:
        parts = [safe_join(candidate.get(field)) for field in cls.CATEGORY_FIELDS if candidate.get(field)]
        return " ".join(parts)

    @classmethod
    def _contains_intent_term(cls, text: Any, term: Any) -> bool:
        raw_text = str(text or "").strip().lower()
        raw_term = str(term or "").strip().lower()
        if not raw_text or not raw_term:
            return False

        normalized_text = normalize_text(raw_text)
        normalized_term = normalize_text(raw_term)
        if not normalized_text or not normalized_term:
            return False
        if normalized_term not in normalized_text:
            return False

        tokens = [token for token in re.split(r"[^0-9a-zA-Z가-힣]+", raw_text) if token]
        if not tokens:
            return True

        for token in tokens:
            normalized_token = normalize_text(token)
            if not normalized_token or normalized_term not in normalized_token:
                continue
            if normalized_token == normalized_term:
                return True
            if normalized_token.startswith(normalized_term) and len(normalized_token) >= len(normalized_term) + 2:
                return True
            if normalized_token.endswith(normalized_term) and len(normalized_token) >= len(normalized_term) + 2:
                return True
            if len(normalized_token) >= len(normalized_term) + 3:
                return True
        return False

    @classmethod
    def _specialized_content_penalty(cls, candidate: Dict[str, Any], query_intent: QueryIntent) -> float:
        required_value = next((candidate.get(field) for field in cls.INTENT_REQUIRED_FIELDS if candidate.get(field)), None)
        if not required_value:
            return 0.0
        if query_intent.has_required_filters:
            return 0.0
        structured_terms = [
            *query_intent.soft_genres,
            *query_intent.purpose_terms,
            *query_intent.audience_terms,
            query_intent.requested_purpose,
            query_intent.requested_audience,
        ]
        if cls._term_match_score(candidate, structured_terms, category_weight=1.0, title_weight=0.24) >= 0.5:
            return 0.0
        return 0.16

    @staticmethod
    def _profile_match_score(candidate: Dict[str, Any]) -> float:
        score_detail = candidate.get("score_detail") or {}
        if not isinstance(score_detail, dict):
            score_detail = {}
        values = [
            candidate.get("profileVectorScore"),
            candidate.get("rerank_score"),
            candidate.get("profile_score"),
            score_detail.get("profileVectorScore"),
            score_detail.get("profile_match_score"),
            score_detail.get("purpose_score"),
            score_detail.get("genre_score"),
            score_detail.get("review_score"),
        ]
        return max(0.0, min(1.0, max(RecommendationGuardrails._safe_float(value) for value in values)))

    @staticmethod
    def _candidate_score(candidate: Dict[str, Any]) -> float | None:
        for field in ["candidateRelevanceScore", "qdrantScore", "score", "rerank_score", "preScore"]:
            value = candidate.get(field)
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _normalize_score(value: float | None) -> float:
        if value is None:
            return 0.0
        if value <= 0:
            return 0.0
        if value <= 1:
            return float(value)
        return min(1.0, float(value) / (float(value) + 1.0))

    @staticmethod
    def _penalize(
        candidates: List[Dict[str, Any]],
        targets: List[Dict[str, Any]],
        *,
        penalty: float,
        penalty_type: str,
    ) -> List[Dict[str, Any]]:
        target_ids = {id(candidate) for candidate in targets}
        result: List[Dict[str, Any]] = []
        for candidate in candidates:
            if id(candidate) not in target_ids:
                result.append(candidate)
                continue
            item = dict(candidate)
            current_penalty = RecommendationGuardrails._safe_float(item.get("policyPenalty"))
            item["policyPenalty"] = round(current_penalty + penalty, 6)
            score_detail = dict(item.get("score_detail") or {})
            penalties = list(score_detail.get("policy_penalties") or [])
            penalties.append({"type": penalty_type, "penalty": round(penalty, 6)})
            score_detail["policy_penalties"] = penalties
            item["score_detail"] = score_detail
            result.append(item)
        return result

    @staticmethod
    def _merge_mode(first: str, second: str) -> str:
        if "FILTER" in {first, second}:
            return "FILTER"
        if "PENALTY" in {first, second}:
            return "PENALTY"
        return "NONE"

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
