from __future__ import annotations

from typing import Any, Dict, List

from app.services.reranking.types import RerankResult


class NoopRerankerProvider:
    def rerank(self, *, query: str, candidates: List[Dict[str, Any]], user_profile: Dict[str, Any] | None, guest: bool, request_id: str | None = None) -> RerankResult:
        _ = query, user_profile, guest, request_id
        return RerankResult(
            candidates=list(candidates or []),
            provider="NONE",
            applied=False,
            fallback=False,
            fallback_reason="DISABLED",
            input_count=len(candidates or []),
            output_count=len(candidates or []),
        )
