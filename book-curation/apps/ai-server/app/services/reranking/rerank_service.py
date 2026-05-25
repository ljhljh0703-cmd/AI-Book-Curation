from __future__ import annotations

from typing import Any, Dict, List

from app.core.config import settings
from app.services.reranking.hcx_reranker_provider import HcxRerankerProvider
from app.services.reranking.http_gte_provider import HttpGteRerankerProvider
from app.services.reranking.noop_provider import NoopRerankerProvider
from app.services.reranking.types import RerankResult


class RerankService:
    def __init__(self) -> None:
        self.noop_provider = NoopRerankerProvider()
        self.gte_provider = HttpGteRerankerProvider()
        self.hcx_provider = HcxRerankerProvider()

    def rerank(
        self,
        *,
        provider: str | None,
        query: str,
        candidates: List[Dict[str, Any]],
        user_profile: Dict[str, Any] | None,
        guest: bool,
        request_id: str | None = None,
    ) -> RerankResult:
        requested_provider = str(provider if provider is not None else settings.RERANKER_PROVIDER or "NONE").strip().upper()
        env_provider = str(settings.RERANKER_PROVIDER or "NONE").strip().upper()
        normalized_provider = requested_provider or env_provider or "NONE"
        reranker_enabled = bool(settings.RERANKER_ENABLED)

        if not reranker_enabled:
            print(
                f"[RERANKER SKIPPED][{request_id or '-'}] "
                f"reason=RERANKER_DISABLED requested_provider={requested_provider} "
                f"env_provider={env_provider} candidate_count={len(candidates or [])}"
            )
            return self.noop_provider.rerank(
                query=query,
                candidates=candidates,
                user_profile=user_profile,
                guest=guest,
                request_id=request_id,
            )

        if normalized_provider in {"", "NONE"}:
            print(
                f"[RERANKER SKIPPED][{request_id or '-'}] "
                f"reason=RERANKER_PROVIDER_NONE requested_provider={requested_provider} "
                f"env_provider={env_provider} candidate_count={len(candidates or [])}"
            )
            return self.noop_provider.rerank(
                query=query,
                candidates=candidates,
                user_profile=user_profile,
                guest=guest,
                request_id=request_id,
            )
        if normalized_provider in {"GTE_MULTILINGUAL", "ALIBABA_GTE", "CROSS_ENCODER"}:
            return self.gte_provider.rerank(
                query=query,
                candidates=candidates,
                user_profile=user_profile,
                guest=guest,
                request_id=request_id,
            )
        if normalized_provider in {"HCX_RERANKER", "CLOVA_RERANKER"}:
            return self.hcx_provider.rerank(
                query=query,
                candidates=candidates,
                user_profile=user_profile,
                guest=guest,
                request_id=request_id,
            )
        print(
            f"[RERANKER SKIPPED][{request_id or '-'}] "
            f"reason=UNSUPPORTED_RERANKER_PROVIDER requested_provider={requested_provider} "
            f"env_provider={env_provider} candidate_count={len(candidates or [])}"
        )
        result = self.noop_provider.rerank(
            query=query,
            candidates=candidates,
            user_profile=user_profile,
            guest=guest,
            request_id=request_id,
        )
        return RerankResult(
            candidates=result.candidates,
            provider=normalized_provider,
            applied=False,
            fallback=True,
            fallback_reason="UNSUPPORTED_RERANKER_PROVIDER",
            input_count=len(candidates or []),
            output_count=len(candidates or []),
        )
