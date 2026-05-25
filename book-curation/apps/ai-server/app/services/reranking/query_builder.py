from __future__ import annotations

from typing import Any, Dict, List


class GteQueryBuilder:
    """현재 질의를 우선하고 사용자 프로필은 동률 후보 보정 신호로만 쓰는 rerank query를 만듭니다."""

    MAX_PROFILE_CHARS = 360

    def build(self, *, query: str, profile: Dict[str, Any] | None, guest: bool) -> str:
        current_query = " ".join(str(query or "").split())
        profile_summary = "" if guest else self._profile_summary(profile or {})
        if not profile_summary:
            return current_query
        return (
            f"사용자 현재 요청: {current_query}\n"
            "우선순위: 현재 요청과 직접 관련된 도서를 가장 우선합니다. "
            "사용자 취향 정보는 관련성이 비슷한 후보 간 우선순위 조정에만 참고합니다.\n"
            f"사용자 취향 요약: {profile_summary}"
        )

    def _profile_summary(self, profile: Dict[str, Any]) -> str:
        values: List[str] = []
        for key in [
            "readingPurpose",
            "readingPurposeText",
            "preferredGenres",
            "favoriteCategories",
            "likedBooks",
            "readingBooks",
            "readBooks",
            "preferenceTerms",
            "preferredMood",
        ]:
            self._collect(values, profile.get(key))
        text = "; ".join(values)
        return text[: self.MAX_PROFILE_CHARS]

    def _collect(self, values: List[str], value: Any) -> None:
        if value is None:
            return
        if isinstance(value, dict):
            for child in value.values():
                self._collect(values, child)
            return
        if isinstance(value, (list, tuple, set)):
            for child in value:
                self._collect(values, child)
            return
        text = " ".join(str(value or "").split())
        if text and text not in values:
            values.append(text)
