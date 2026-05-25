from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List
import math

from app.services.intent.chat_intent_classifier import ChatIntent
from app.services.context.conversation_context import ConversationContext


@dataclass(frozen=True)
class PreviousRecommendationScope:
    """Structured policy result for recent recommendations in the same conversation."""

    mode: str = "NONE"  # NONE | SOFT_DECAY | HARD_RECENT
    hard_books: List[Dict[str, Any]] = field(default_factory=list)
    soft_books: List[Dict[str, Any]] = field(default_factory=list)
    reason: str = ""

    @property
    def has_previous_signal(self) -> bool:
        return bool(self.hard_books or self.soft_books)


class MultiturnRecommendationPolicy:
    """Time-decay policy for previously recommended candidates.

    The policy never parses natural-language phrases directly. Request-level behavior is
    driven by ChatIntent fields produced by the intent classifier.
    """

    GENERIC_SOFT_DECAY_MINUTES = 60
    EXPLICIT_HARD_DECAY_MINUTES = 24 * 60
    SOFT_HALF_LIFE_MINUTES = 30
    GENERIC_HISTORY_LIMIT = 6
    EXPLICIT_HISTORY_LIMIT = 12

    def __init__(self, context: ConversationContext | None = None) -> None:
        self.context = context or ConversationContext()

    def resolve(
        self,
        *,
        intent: ChatIntent,
        history: List[Dict[str, Any]] | None = None,
    ) -> PreviousRecommendationScope:
        if intent.query_type != "recommend" or not history:
            return PreviousRecommendationScope(reason="not_recommend_or_no_history")

        action = self._resolve_action(intent)
        if action == "REPLAY":
            return PreviousRecommendationScope(reason="replay_request")
        if action == "NONE":
            return PreviousRecommendationScope(reason="policy_none")

        now = datetime.now(timezone.utc)
        books = self.context.extract_previous_recommended_books(history)
        if not books:
            return PreviousRecommendationScope(reason="no_previous_books")

        if action == "HARD_EXCLUDE":
            hard_books = self._recent_books(
                books=books,
                now=now,
                max_age_minutes=self.EXPLICIT_HARD_DECAY_MINUTES,
                limit=self.EXPLICIT_HISTORY_LIMIT,
                include_decay_weight=False,
            )
            return PreviousRecommendationScope(
                mode="HARD_RECENT" if hard_books else "NONE",
                hard_books=hard_books,
                reason="structured_hard_exclude",
            )

        soft_books = self._recent_books(
            books=books,
            now=now,
            max_age_minutes=self.GENERIC_SOFT_DECAY_MINUTES,
            limit=self.GENERIC_HISTORY_LIMIT,
            include_decay_weight=True,
        )
        return PreviousRecommendationScope(
            mode="SOFT_DECAY" if soft_books else "NONE",
            soft_books=soft_books,
            reason="structured_soft_decay",
        )

    @staticmethod
    def _resolve_action(intent: ChatIntent) -> str:
        explicit_action = str(getattr(intent, "recommendation_previous_action", "") or "").strip().upper()
        if explicit_action in {"NONE", "SOFT_DECAY", "HARD_EXCLUDE", "REPLAY"}:
            return explicit_action
        if intent.name == "list_previous_books":
            return "REPLAY"
        if intent.recommendation_diversity_required or intent.recommendation_exploration_intent:
            return "HARD_EXCLUDE"
        return "SOFT_DECAY"

    def _recent_books(
        self,
        books: List[Dict[str, Any]],
        now: datetime,
        max_age_minutes: int,
        limit: int,
        include_decay_weight: bool,
    ) -> List[Dict[str, Any]]:
        recent: List[Dict[str, Any]] = []
        for book in reversed(books):
            recommended_at = self._parse_time(book.get("recommended_at") or book.get("created_at") or book.get("createdAt"))
            age_minutes = max_age_minutes / 2 if recommended_at is None else max(0.0, (now - recommended_at).total_seconds() / 60.0)
            if age_minutes > max_age_minutes:
                continue
            item = dict(book)
            item["age_minutes"] = round(age_minutes, 3)
            if include_decay_weight:
                item["decay_weight"] = round(math.pow(0.5, age_minutes / self.SOFT_HALF_LIFE_MINUTES), 6)
            recent.append(item)
            if len(recent) >= limit:
                break
        return list(reversed(recent))

    @staticmethod
    def _parse_time(value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
