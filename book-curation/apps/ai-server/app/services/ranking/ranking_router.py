from __future__ import annotations

from time import perf_counter
from typing import Any, Dict, List

from app.core.config import settings
from app.services.ranking.lightfm_ranker import LightFmRanker
from app.services.ranking.ranking_result import RankingResult


class RankingModelRouter:
    """추천 전략과 개인화 모델 설정에 따라 후보 압축/재정렬 strategy를 선택합니다.

    수정 포인트: 관리자가 LightFM 자체를 수동 선택하는 구조가 아니라, AUTO_HYBRID에서 선택된
    개인화 모델을 사용자별로 적용 가능할 때만 사용하고 불가능하면 fail-open fallback합니다.
    """

    def __init__(self) -> None:
        self.lightfm_ranker = LightFmRanker()

    def rerank(
        self,
        *,
        recommendation_strategy: str | None = None,
        personalization_model: str | None = None,
        ranking_model: str | None = None,
        user_id: str | None,
        candidates: List[Dict[str, Any]],
        limit: int,
        request_id: str | None = None,
    ) -> RankingResult:
        strategy = str(recommendation_strategy or "AUTO_HYBRID").strip().upper()
        selected_model = str(personalization_model or ranking_model or "NONE").strip().upper()
        if selected_model == "RULE_BASED":
            selected_model = "NONE"
        print(
            f"[RANKING MODEL ROUTER][{request_id or '-'}] "
            f"strategy={strategy} selected={selected_model} user_present={bool(user_id)} "
            f"candidate_count={len(candidates or [])} limit={limit} "
            f"lightfm_enabled={bool(settings.LIGHTFM_ENABLED)}"
        )

        safe_limit = self._positive_int(limit, 20)
        if strategy == "RULE_BASED_ONLY" or selected_model == "NONE":
            return self._rule_based_result(
                candidates=candidates,
                requested_model=selected_model,
                applied_model="RULE_BASED",
                safe_limit=safe_limit,
                started_at=perf_counter(),
                fallback=False,
                fallback_reason=None,
                metadata={"strategy": strategy},
            )

        if selected_model == "LIGHTFM":
            return self.lightfm_ranker.rerank(
                user_id=user_id,
                candidates=candidates[: self._positive_int(settings.LIGHTFM_CANDIDATE_LIMIT, 50)],
                requested_model=selected_model,
                limit=self._positive_int(settings.LIGHTFM_TOP_N, safe_limit),
                request_id=request_id,
            )

        started_at = perf_counter()
        if selected_model in {"SASREC", "BERT4REC"}:
            return self._rule_based_result(
                candidates=candidates,
                requested_model=selected_model,
                applied_model="RULE_BASED",
                safe_limit=safe_limit,
                started_at=started_at,
                fallback=True,
                fallback_reason=f"{selected_model}_NOT_IMPLEMENTED",
                metadata={"strategy": strategy},
            )

        return self._rule_based_result(
            candidates=candidates,
            requested_model=selected_model,
            applied_model="RULE_BASED",
            safe_limit=safe_limit,
            started_at=started_at,
            fallback=True,
            fallback_reason="UNSUPPORTED_PERSONALIZATION_MODEL",
            metadata={"strategy": strategy},
        )

    @staticmethod
    def _rule_based_result(
        *,
        candidates: List[Dict[str, Any]],
        requested_model: str,
        applied_model: str,
        safe_limit: int,
        started_at: float,
        fallback: bool,
        fallback_reason: str | None,
        metadata: Dict[str, Any] | None = None,
    ) -> RankingResult:
        return RankingResult(
            candidates=list(candidates or [])[:safe_limit],
            requested_model=requested_model,
            applied_model=applied_model,
            applied=not fallback,
            fallback=fallback,
            fallback_reason=fallback_reason,
            elapsed_ms=int((perf_counter() - started_at) * 1000),
            metadata={"candidateLimit": safe_limit, "topN": safe_limit, **dict(metadata or {})},
        )

    @staticmethod
    def _positive_int(value: Any, default: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        return max(1, parsed)
