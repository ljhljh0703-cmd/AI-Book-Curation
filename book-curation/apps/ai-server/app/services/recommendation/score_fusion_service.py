from __future__ import annotations

from typing import Any, Dict, List

from app.services.ranking.score_utils import normalize_min_max, safe_float


class ScoreFusionService:
    """Qdrant/Rule/개인화/GTE 점수를 요청 단위로 정규화한 뒤 finalScore를 계산합니다."""

    def fuse(
        self,
        *,
        candidates: List[Dict[str, Any]],
        guest: bool,
        personalization_available: bool,
        reranker_available: bool,
    ) -> List[Dict[str, Any]]:
        rows = [dict(candidate) for candidate in (candidates or [])]
        if not rows:
            return []
        normalized = {
            "qdrant": normalize_min_max([safe_float(row.get("qdrantScore", row.get("score", 0.0))) for row in rows]),
            "rule": normalize_min_max([safe_float(row.get("ruleScore", row.get("preScore", 0.0))) for row in rows]),
            "personalization": normalize_min_max([self._personalization_score(row) for row in rows]),
            "reranker": normalize_min_max([safe_float(row.get("rerankerScore")) for row in rows]),
        }
        weights = self._weights(guest=guest, personalization_available=personalization_available, reranker_available=reranker_available)
        fused: List[Dict[str, Any]] = []
        for index, row in enumerate(rows):
            final_score = 0.0
            for key, weight in weights.items():
                final_score += normalized[key][index] * weight
            row["finalScore"] = round(final_score, 6)
            row["score_detail"] = {
                **dict(row.get("score_detail") or {}),
                "fusion_weights": weights,
                "fusion_qdrant_score": round(normalized["qdrant"][index], 6),
                "fusion_rule_score": round(normalized["rule"][index], 6),
                "fusion_personalization_score": round(normalized["personalization"][index], 6),
                "fusion_reranker_score": round(normalized["reranker"][index], 6),
                "final_score": round(final_score, 6),
            }
            fused.append(row)
        fused.sort(key=lambda row: safe_float(row.get("finalScore", 0.0)), reverse=True)
        return fused

    @staticmethod
    def _personalization_score(candidate: Dict[str, Any]) -> float:
        for field in ["lightfmScore", "sasrecScore", "bert4recScore", "profileVectorScore", "anonymousScore", "preScore"]:
            value = candidate.get(field)
            if value is not None:
                return safe_float(value)
        return 0.0

    @staticmethod
    def _weights(*, guest: bool, personalization_available: bool, reranker_available: bool) -> Dict[str, float]:
        if reranker_available:
            if guest:
                base = {"reranker": 0.60, "qdrant": 0.30, "rule": 0.10, "personalization": 0.0}
            elif personalization_available:
                base = {"reranker": 0.40, "personalization": 0.25, "rule": 0.25, "qdrant": 0.10}
            else:
                base = {"reranker": 0.50, "rule": 0.30, "qdrant": 0.20, "personalization": 0.0}
        else:
            if guest:
                base = {"qdrant": 0.55, "rule": 0.35, "personalization": 0.10, "reranker": 0.0}
            elif personalization_available:
                base = {"personalization": 0.40, "rule": 0.40, "qdrant": 0.20, "reranker": 0.0}
            else:
                base = {"rule": 0.55, "qdrant": 0.35, "personalization": 0.10, "reranker": 0.0}
        total = sum(weight for weight in base.values() if weight > 0)
        if total <= 0:
            return {"qdrant": 1.0, "rule": 0.0, "personalization": 0.0, "reranker": 0.0}
        return {key: round(weight / total, 6) for key, weight in base.items()}
