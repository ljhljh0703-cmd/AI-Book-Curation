from __future__ import annotations

from typing import Any, Dict, List

from app.services.ranking.score_utils import normalize_min_max, safe_float


class AnonymousCandidateSelector:
    """비로그인/개인화 모델 미사용 사용자를 위한 50→20 후보 압축기입니다."""

    def select(self, candidates: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
        safe_candidates = [dict(candidate) for candidate in (candidates or [])]
        if not safe_candidates:
            return []
        qdrant_scores = normalize_min_max([safe_float(row.get("qdrantScore", row.get("score", 0.0))) for row in safe_candidates])
        rule_scores = normalize_min_max([safe_float(row.get("ruleScore", row.get("preScore", 0.0))) for row in safe_candidates])
        selected: List[Dict[str, Any]] = []
        for index, item in enumerate(safe_candidates):
            metadata_quality = self._metadata_quality(item)
            score = (qdrant_scores[index] * 0.45) + (rule_scores[index] * 0.45) + (metadata_quality * 0.10)
            item["anonymousScore"] = round(score, 6)
            item["preScore"] = round(score, 6)
            item["score_detail"] = {
                **dict(item.get("score_detail") or {}),
                "anonymous_score": round(score, 6),
                "anonymous_qdrant_score": round(qdrant_scores[index], 6),
                "anonymous_rule_score": round(rule_scores[index], 6),
                "anonymous_metadata_quality": round(metadata_quality, 6),
            }
            selected.append(item)
        selected.sort(key=lambda row: safe_float(row.get("anonymousScore", 0.0)), reverse=True)
        return selected[: max(1, int(limit))]

    @staticmethod
    def _metadata_quality(candidate: Dict[str, Any]) -> float:
        fields = ["title", "author", "categories", "description", "simple_intro", "book_intro", "cover_url", "ori_cover_s"]
        present = 0
        for field in fields:
            value = candidate.get(field)
            if isinstance(value, list):
                present += 1 if any(str(item or "").strip() for item in value) else 0
            elif str(value or "").strip():
                present += 1
        return min(1.0, present / max(1, len(fields)))
