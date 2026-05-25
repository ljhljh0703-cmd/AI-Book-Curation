from __future__ import annotations

from typing import Any, Dict, Iterable, List

from app.core.config import settings
from app.services.reranking.types import RerankDocument


class GteDocumentBuilder:
    """도서 후보를 GTE reranker 입력 문서로 변환합니다.

    수정 포인트: 모델 입력에는 제목/저자/카테고리/설명 같은 도서 메타데이터만 사용합니다.
    qdrantScore, ruleScore, lightfmScore 같은 숫자 feature는 문서 텍스트에 넣지 않고 final fusion에서만 반영합니다.
    """

    def __init__(self, max_chars: int | None = None) -> None:
        self.max_chars = max(120, int(max_chars or settings.GTE_RERANKER_MAX_DOC_CHARS))

    def build(self, candidates: List[Dict[str, Any]]) -> List[RerankDocument]:
        documents: List[RerankDocument] = []
        for index, candidate in enumerate(candidates or []):
            text = self._candidate_text(candidate)
            if not text:
                text = str(candidate.get("title") or candidate.get("isbn") or f"candidate-{index}").strip()
            documents.append(RerankDocument(index=index, text=text[: self.max_chars], candidate=candidate))
        return documents

    def _candidate_text(self, candidate: Dict[str, Any]) -> str:
        parts: List[str] = []
        self._append(parts, "제목", candidate.get("title"))
        self._append(parts, "저자", candidate.get("author"))
        self._append(parts, "출판사", candidate.get("publisher"))
        categories = self._flatten_values(
            candidate.get("categories"),
            candidate.get("cate_depth1"),
            candidate.get("cate_depth2"),
            candidate.get("cate_depth3"),
            candidate.get("genres"),
            candidate.get("categoryName"),
            candidate.get("category_name"),
            candidate.get("category_full_name"),
            candidate.get("category_path"),
        )
        if categories:
            self._append(parts, "분류", " > ".join(categories[:8]))
        self._append(parts, "소개", candidate.get("simple_intro") or candidate.get("description") or candidate.get("book_intro"))
        self._append(parts, "목차", candidate.get("book_index"))
        self._append(parts, "출판사 리뷰", candidate.get("pub_review"))
        return "\n".join(parts)

    @staticmethod
    def _append(parts: List[str], label: str, value: Any) -> None:
        text = " ".join(str(value or "").split())
        if text:
            parts.append(f"{label}: {text}")

    @classmethod
    def _flatten_values(cls, *values: Any) -> List[str]:
        flattened: List[str] = []
        for value in values:
            if value is None:
                continue
            if isinstance(value, (list, tuple, set)):
                items: Iterable[Any] = value
            else:
                items = [value]
            for item in items:
                text = " ".join(str(item or "").split())
                if text and text not in flattened:
                    flattened.append(text)
        return flattened
