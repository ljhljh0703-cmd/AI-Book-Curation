from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List

from app.services.context.conversation_context import ConversationContext
from app.services.intent.chat_intent_classifier import ChatIntent
from app.services.intent.query_intent_parser import QueryIntent
from app.services.common.text_utils import normalize_text


@dataclass(frozen=True)
class ResolvedReferenceContext:
    """Structured context extracted from recent recommendation cards.

    수정 포인트: "두 번째 책", "방금 추천한 책" 같은 후속 질문을 LLM 검색어 하나에 맡기지 않고,
    최근 3턴의 실제 추천 카드 metadata를 seed/exclude context로 변환합니다.
    """

    detected: bool = False
    requires_context_priority: bool = False
    reference_type: str = "NONE"  # NONE | ORDINAL | DEICTIC | PREVIOUS_SET | EXCLUDE_PREVIOUS
    target_candidates: List[Dict[str, Any]] = field(default_factory=list)
    exclude_candidates: List[Dict[str, Any]] = field(default_factory=list)
    seed_query: str | None = None
    constraint_query: str | None = None
    reason: str = ""
    confidence: float = 0.0

    def metadata(self) -> Dict[str, Any]:
        return {
            "contextReferenceDetected": self.detected,
            "contextReferenceType": self.reference_type,
            "contextReferenceRequiresPriority": self.requires_context_priority,
            "contextReferenceConfidence": round(self.confidence, 4),
            "contextReferenceReason": self.reason,
            "contextReferenceTargetCount": len(self.target_candidates),
            "contextReferenceExcludeCount": len(self.exclude_candidates),
            "contextReferenceSeedQuery": self.seed_query,
            "contextReferenceConstraintQuery": self.constraint_query,
            "contextReferenceTargets": [self._candidate_summary(candidate) for candidate in self.target_candidates[:5]],
        }

    @staticmethod
    def _candidate_summary(candidate: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "rank": candidate.get("rank"),
            "title": candidate.get("title"),
            "author": candidate.get("author"),
            "isbn": candidate.get("isbn") or candidate.get("isbn13"),
        }


class ReferenceResolver:
    """Resolve generic multiturn references against recent recommendation cards."""

    _ORDINAL_WORDS = {
        "첫": 1,
        "첫째": 1,
        "일": 1,
        "한": 1,
        "두": 2,
        "둘": 2,
        "둘째": 2,
        "이": 2,
        "세": 3,
        "셋": 3,
        "셋째": 3,
        "삼": 3,
        "네": 4,
        "넷": 4,
        "넷째": 4,
        "사": 4,
        "다섯": 5,
        "다섯째": 5,
        "오": 5,
    }
    _DIGIT_ORDINAL_PATTERN = re.compile(r"(?<!\d)([1-9])\s*(?:번째|번|위)(?:\s*(?:책|도서))?")
    _WORD_ORDINAL_PATTERN = re.compile(
        r"(첫째|둘째|셋째|넷째|다섯째|첫|두|둘|세|셋|네|넷|다섯|일|이|삼|사|오)\s*(?:번째|번|위)?\s*(?:책|도서)"
    )
    _DEICTIC_PATTERN = re.compile(r"(?:이|그|해당|방금|아까|이전|직전)\s*(?:책|도서|추천|목록|결과)")
    _SET_PATTERN = re.compile(r"(?:그중|그 중|추천한 것들|추천 목록|추천 결과|방금 추천|아까 추천|이전 추천)")
    _EXCLUDE_PATTERN = re.compile(r"(?:제외|빼고|말고|다른|겹치지|중복 없이|새로운)")

    def __init__(self, context: ConversationContext | None = None) -> None:
        self.context = context or ConversationContext()

    def resolve(
        self,
        *,
        query: str,
        history: List[Dict[str, Any]] | None,
        intent: ChatIntent,
        query_intent: QueryIntent,
    ) -> ResolvedReferenceContext:
        recent_candidates = self.context.extract_recent_recommendation_candidates(history, turn_limit=3, max_candidates=15)
        if not recent_candidates:
            return ResolvedReferenceContext(reason="no_recent_candidates")

        raw_query = str(query or "").strip()
        normalized_query = normalize_text(raw_query)
        ordinal = self._extract_ordinal(raw_query)
        has_deictic = bool(self._DEICTIC_PATTERN.search(raw_query))
        has_set_reference = bool(self._SET_PATTERN.search(raw_query))
        wants_exclude = bool(self._EXCLUDE_PATTERN.search(raw_query))
        intent_requires_context = bool(
            getattr(intent, "requires_history", False)
            or getattr(intent, "name", "") in {"more_like_previous", "refine_condition", "list_previous_books"}
        )

        target_candidates: List[Dict[str, Any]] = []
        reference_type = "NONE"
        confidence = 0.0

        if ordinal is not None:
            target_candidates = self._find_by_rank(recent_candidates, ordinal)
            reference_type = "ORDINAL" if target_candidates else "NONE"
            confidence = 0.95 if target_candidates else 0.0
        elif has_set_reference or getattr(intent, "name", "") in {"more_like_previous", "refine_condition"}:
            target_candidates = self._latest_recommendation_set(recent_candidates)
            reference_type = "PREVIOUS_SET" if target_candidates else "NONE"
            confidence = 0.85 if target_candidates else 0.0
        elif has_deictic:
            target_candidates = self._latest_recommendation_set(recent_candidates)[:1]
            reference_type = "DEICTIC" if target_candidates else "NONE"
            confidence = 0.7 if target_candidates else 0.0

        detected = bool(target_candidates or wants_exclude or intent_requires_context)
        if not detected:
            return ResolvedReferenceContext(reason="no_reference_expression")

        exclude_candidates = target_candidates if wants_exclude and target_candidates else []
        if wants_exclude and not exclude_candidates:
            exclude_candidates = self._latest_recommendation_set(recent_candidates)
            reference_type = "EXCLUDE_PREVIOUS" if exclude_candidates else reference_type
            confidence = max(confidence, 0.75 if exclude_candidates else 0.0)

        seed_candidates = [] if wants_exclude and reference_type == "EXCLUDE_PREVIOUS" else target_candidates
        seed_query = self._build_seed_query(seed_candidates, raw_query)
        constraint_query = self._strip_reference_surface(raw_query).strip() or raw_query
        requires_context_priority = bool(seed_query or exclude_candidates or intent_requires_context)

        # 수정 포인트: 참조형 후속 질문에서는 현재 query + 최근 추천 카드 seed가 온보딩 profile보다 먼저 검색어가 됩니다.
        return ResolvedReferenceContext(
            detected=detected,
            requires_context_priority=requires_context_priority,
            reference_type=reference_type,
            target_candidates=target_candidates,
            exclude_candidates=exclude_candidates,
            seed_query=seed_query,
            constraint_query=constraint_query,
            reason="resolved_from_recent_recommendation_cards" if target_candidates or exclude_candidates else "context_required_by_intent",
            confidence=confidence if confidence > 0 else (0.6 if intent_requires_context else 0.0),
        )

    def _extract_ordinal(self, query: str) -> int | None:
        digit_match = self._DIGIT_ORDINAL_PATTERN.search(query)
        if digit_match:
            try:
                return int(digit_match.group(1))
            except ValueError:
                return None

        word_match = self._WORD_ORDINAL_PATTERN.search(query)
        if not word_match:
            return None
        return self._ORDINAL_WORDS.get(word_match.group(1))

    @staticmethod
    def _find_by_rank(candidates: List[Dict[str, Any]], rank: int) -> List[Dict[str, Any]]:
        for candidate in reversed(candidates):
            try:
                candidate_rank = int(candidate.get("rank") or 0)
            except (TypeError, ValueError):
                candidate_rank = 0
            if candidate_rank == rank:
                return [candidate]
        return []

    @staticmethod
    def _latest_recommendation_set(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not candidates:
            return []
        latest_group: List[Dict[str, Any]] = []
        for candidate in reversed(candidates):
            try:
                rank = int(candidate.get("rank") or 0)
            except (TypeError, ValueError):
                rank = 0
            if latest_group and rank >= 1 and rank >= int(latest_group[-1].get("rank") or 0):
                break
            latest_group.append(candidate)
            if rank == 1:
                break
        return list(reversed(latest_group)) or candidates[-5:]

    def _build_seed_query(self, candidates: List[Dict[str, Any]], query: str) -> str | None:
        if not candidates:
            return None
        candidate_parts = [self._candidate_seed(candidate) for candidate in candidates[:3]]
        candidate_parts = [part for part in candidate_parts if part]
        if not candidate_parts:
            return None
        constraint_query = self._strip_reference_surface(query)
        parts = [" ".join(candidate_parts)]
        if constraint_query:
            parts.append(constraint_query)
        return " ".join(parts).strip()[:900]

    @classmethod
    def _strip_reference_surface(cls, query: str) -> str:
        value = cls._DIGIT_ORDINAL_PATTERN.sub(" ", query)
        value = cls._WORD_ORDINAL_PATTERN.sub(" ", value)
        value = cls._DEICTIC_PATTERN.sub(" ", value)
        value = cls._SET_PATTERN.sub(" ", value)
        return re.sub(r"\s+", " ", value).strip()

    @staticmethod
    def _candidate_seed(candidate: Dict[str, Any]) -> str:
        parts: List[str] = []
        for field in ["title", "author", "category_full_name", "category_path", "categoryName", "category_name"]:
            text = ReferenceResolver._clean_text(candidate.get(field), 80)
            if text:
                parts.append(text)
        for field in ["categories", "cate_depth1", "kcid", "genres"]:
            value = candidate.get(field)
            values = value if isinstance(value, list) else [value]
            for item in values[:3]:
                text = ReferenceResolver._clean_text(item, 60)
                if text:
                    parts.append(text)
        description = ReferenceResolver._clean_text(
            candidate.get("description") or candidate.get("simple_intro") or candidate.get("book_intro"),
            180,
        )
        if description:
            parts.append(description)
        return " ".join(dict.fromkeys(parts))[:300]

    @staticmethod
    def _clean_text(value: Any, max_length: int) -> str:
        text = " ".join(str(value or "").strip().split())
        return text[:max_length]
