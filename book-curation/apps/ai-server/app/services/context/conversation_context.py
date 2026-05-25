from __future__ import annotations

from typing import Any, Dict, List

from app.services.common.text_utils import normalize_text


class ConversationContext:
    """Conversation history helpers.

    Recommendation history is restored from structured candidate metadata instead of
    parsing assistant natural-language output.
    """

    # 수정 포인트: 후속 질문 해석은 최근 3턴만 사용합니다.
    # 오래된 온보딩/대화가 현재 참조형 질의를 덮어쓰지 않게 user+assistant 기준 최대 6개 메시지로 제한합니다.
    DEFAULT_RECENT_TURN_LIMIT = 3
    MESSAGES_PER_TURN = 2

    @classmethod
    def recent_turn_messages(
        cls,
        history: List[Dict[str, Any]] | None = None,
        turn_limit: int = DEFAULT_RECENT_TURN_LIMIT,
    ) -> List[Dict[str, Any]]:
        if not history:
            return []
        max_messages = max(1, int(turn_limit or cls.DEFAULT_RECENT_TURN_LIMIT)) * cls.MESSAGES_PER_TURN
        return list(history)[-max_messages:]

    @classmethod
    def make_history_text(
        cls,
        history: List[Dict[str, Any]] | None = None,
        limit: int = 10,
    ) -> str:
        history_texts: List[str] = []

        for item in (history or [])[-limit:]:
            role = str(item.get("role") or "").strip().lower()
            content = str(item.get("content") or "")

            if role not in ["user", "assistant"] or not content:
                continue

            history_texts.append(f"{role}: {content}")

        return "\n".join(history_texts)

    @classmethod
    def make_structured_history_text(
        cls,
        history: List[Dict[str, Any]] | None = None,
        turn_limit: int = DEFAULT_RECENT_TURN_LIMIT,
        content_limit: int = 700,
        max_candidates_per_message: int = 5,
    ) -> str:
        """Build a compact history block with assistant recommendation card metadata.

        수정 포인트: 멀티턴 참조형 질의는 assistant 본문보다 카드 metadata가 더 정확합니다.
        따라서 최근 3턴의 role/content와 직전 추천 카드의 rank/title/author/category/description을 함께 전달합니다.
        """
        history_texts: List[str] = []
        for item in cls.recent_turn_messages(history, turn_limit=turn_limit):
            role = str(item.get("role") or "").strip().lower()
            content = str(item.get("content") or "").strip()
            if role not in ["user", "assistant"]:
                continue
            if content:
                compact_content = " ".join(content.split())[:content_limit]
                history_texts.append(f"{role}: {compact_content}")

            if role != "assistant":
                continue
            candidates = cls._extract_structured_candidates(item)[:max_candidates_per_message]
            if not candidates:
                continue
            history_texts.append("assistant_recommendation_cards:")
            for fallback_rank, candidate in enumerate(candidates, start=1):
                rank = cls._safe_rank(candidate.get("rank"), fallback_rank)
                title = cls._clean_text(candidate.get("title"), 80)
                author = cls._clean_text(candidate.get("author"), 60)
                category = cls._candidate_category_text(candidate)
                isbn = cls._clean_text(candidate.get("isbn") or candidate.get("isbn13"), 20)
                description = cls._clean_text(
                    candidate.get("description") or candidate.get("simple_intro") or candidate.get("book_intro"),
                    160,
                )
                parts = [f"rank={rank}"]
                if title:
                    parts.append(f"title={title}")
                if author:
                    parts.append(f"author={author}")
                if category:
                    parts.append(f"category={category}")
                if isbn:
                    parts.append(f"isbn={isbn}")
                if description:
                    parts.append(f"description={description}")
                history_texts.append("- " + "; ".join(parts))

        return "\n".join(history_texts)

    @classmethod
    def make_history_search_hint(
        cls,
        history: List[Dict[str, Any]] | None = None,
        turn_limit: int = DEFAULT_RECENT_TURN_LIMIT,
    ) -> str:
        hints: List[str] = []

        for item in cls.recent_turn_messages(history, turn_limit=turn_limit):
            role = str(item.get("role") or "").strip().lower()
            content = str(item.get("content") or "").strip()

            if role == "user" and content:
                hints.append(content)

        return " ".join(hints).replace("\n", " ")[:700]

    @classmethod
    def extract_previous_recommended_books(
        cls,
        history: List[Dict[str, Any]] | None = None,
        turn_limit: int = DEFAULT_RECENT_TURN_LIMIT,
    ) -> List[Dict[str, Any]]:
        books: List[Dict[str, Any]] = []

        for item in cls.recent_turn_messages(history, turn_limit=turn_limit):
            if str(item.get("role") or "").strip().lower() != "assistant":
                continue

            message_recommended_at = item.get("created_at") or item.get("createdAt")
            for fallback_rank, candidate in enumerate(cls._extract_structured_candidates(item), start=1):
                title = str(candidate.get("title") or "").strip()
                isbn = str(candidate.get("isbn") or candidate.get("isbn13") or candidate.get("isbn10") or "").strip()
                book_id = candidate.get("book_id") or candidate.get("bookId") or candidate.get("id")
                candidate_recommended_at = (
                    candidate.get("recommended_at")
                    or candidate.get("recommendedAt")
                    or candidate.get("created_at")
                    or candidate.get("createdAt")
                    or message_recommended_at
                )
                if title or isbn or book_id:
                    books.append({
                        "title": title,
                        "isbn": isbn,
                        "book_id": book_id,
                        "rank": cls._safe_rank(candidate.get("rank"), fallback_rank),
                        "recommended_at": candidate_recommended_at,
                    })

        deduped: List[Dict[str, Any]] = []
        seen = set()

        for book in books:
            key = normalize_text(book.get("isbn")) or normalize_text(book.get("book_id")) or normalize_text(book.get("title"))
            if not key or key in seen:
                continue

            seen.add(key)
            deduped.append(book)

        return deduped

    @classmethod
    def extract_recent_recommendation_candidates(
        cls,
        history: List[Dict[str, Any]] | None = None,
        turn_limit: int = DEFAULT_RECENT_TURN_LIMIT,
        max_candidates: int = 15,
    ) -> List[Dict[str, Any]]:
        """Return recent assistant candidates with stable rank/order metadata."""
        candidates: List[Dict[str, Any]] = []
        for item in cls.recent_turn_messages(history, turn_limit=turn_limit):
            if str(item.get("role") or "").strip().lower() != "assistant":
                continue
            message_recommended_at = item.get("created_at") or item.get("createdAt")
            for fallback_rank, candidate in enumerate(cls._extract_structured_candidates(item), start=1):
                normalized = dict(candidate)
                normalized["rank"] = cls._safe_rank(normalized.get("rank"), fallback_rank)
                normalized["recommended_at"] = (
                    normalized.get("recommended_at")
                    or normalized.get("recommendedAt")
                    or message_recommended_at
                )
                candidates.append(normalized)
        return candidates[-max_candidates:]

    @staticmethod
    def _extract_structured_candidates(item: Dict[str, Any]) -> List[Dict[str, Any]]:
        candidates = item.get("candidates")
        if candidates is None and isinstance(item.get("metadata"), dict):
            candidates = item["metadata"].get("candidates")
        if not isinstance(candidates, list):
            return []
        return [candidate for candidate in candidates if isinstance(candidate, dict)]

    @staticmethod
    def _clean_text(value: Any, max_length: int) -> str:
        text = " ".join(str(value or "").strip().split())
        return text[:max_length]

    @classmethod
    def _candidate_category_text(cls, candidate: Dict[str, Any]) -> str:
        for field in ["category_full_name", "category_path", "categoryName", "category_name", "categories", "cate_depth1", "kcid"]:
            value = candidate.get(field)
            values = value if isinstance(value, list) else [value]
            texts = [cls._clean_text(item, 50) for item in values]
            texts = [text for text in texts if text]
            if texts:
                return " > ".join(texts[:3])[:120]
        return ""

    @staticmethod
    def _safe_rank(value: Any, fallback: int) -> int:
        try:
            rank = int(value)
            return rank if rank > 0 else fallback
        except (TypeError, ValueError):
            return fallback
