from __future__ import annotations

import re
from typing import Any, Dict, List

from app.services.common.text_utils import normalize_text


class RecommendationPolicy:
    """Language-agnostic recommendation validation utilities.

    Natural-language intent decisions are delegated to the LLM intent classifier. This
    class only performs structural validation and numeric/count parsing.
    """

    def normalize_search_query(self, query: str) -> str:
        return re.sub(r"\s+", " ", str(query or "").strip())

    @staticmethod
    def looks_like_book_lookup(query: str) -> bool:
        compact = re.sub(r"[^0-9Xx]", "", str(query or ""))
        return len(compact) >= 10 and compact.startswith(("978", "979"))

    @staticmethod
    def is_recommendation_explanation_request(query: str) -> bool:
        _ = query
        return False

    @staticmethod
    def get_recommend_count(query: str, max_count: int = 3) -> int:
        numbers = [int(match) for match in re.findall(r"\d+", str(query or ""))]
        if not numbers:
            return max_count
        requested = min(numbers)
        return max(1, min(requested, max_count))

    @staticmethod
    def contains_forbidden_answer_text(answer: str) -> bool:
        _ = answer
        return False

    def is_valid_recommendation_answer(
        self,
        answer: str,
        candidates: List[Dict[str, Any]],
    ) -> bool:
        if not answer or not answer.strip():
            return False

        normalized_answer = normalize_text(answer)
        for idx, book in enumerate(candidates, start=1):
            title = str(book.get("title") or "").strip()
            if title:
                normalized_title = normalize_text(title)
                if normalized_title and normalized_title not in normalized_answer:
                    return False
            if f"{idx}" not in answer:
                return False
        return True

    @staticmethod
    def is_no_matching_book_answer(answer: str) -> bool:
        _ = answer
        return False

    @staticmethod
    def renumber_recommendation_answer(answer: str) -> str:
        if not answer:
            return answer

        lines = answer.splitlines()
        result: List[str] = []
        number = 1

        for line in lines:
            if re.match(r"^\s*\d+\.\s+", line):
                line = re.sub(r"^\s*\d+\.\s+", f"{number}. ", line, count=1)
                number += 1
            result.append(line)

        return "\n".join(result)

    @staticmethod
    def extract_lookup_keywords(query: str) -> List[str]:
        tokens = re.split(r"[^0-9A-Za-z가-힣]+", str(query or ""))
        result: List[str] = []
        for token in tokens:
            token = token.strip()
            if len(token) < 2:
                continue
            result.append(token)
        return result[:8]

    @staticmethod
    def is_explicit_previous_recommendation_replay_request(query: str) -> bool:
        _ = query
        return False

    def should_exclude_previous_recommendations(
        self,
        query: str,
        query_type: str,
        history: List[Dict[str, Any]] | None = None,
    ) -> bool:
        _ = query
        return query_type == "recommend" and bool(history)
