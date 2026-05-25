from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List


class PersonalizationProvider(str, Enum):
    NONE = "NONE"
    PROFILE_VECTOR = "PROFILE_VECTOR"
    LIGHTFM = "LIGHTFM"


class SequenceProvider(str, Enum):
    NONE = "NONE"
    SASREC = "SASREC"
    BERT4REC = "BERT4REC"


class RerankerProvider(str, Enum):
    NONE = "NONE"
    RULE_FINAL = "RULE_FINAL"
    CROSS_ENCODER = "CROSS_ENCODER"
    ALIBABA_GTE = "ALIBABA_GTE"
    GTE_MULTILINGUAL = "GTE_MULTILINGUAL"
    CLOVA_RERANKER = "CLOVA_RERANKER"
    HCX_RERANKER = "HCX_RERANKER"


@dataclass(frozen=True)
class RecommendationPipelineConfig:
    qdrant_candidate_limit: int = 100
    rule_candidate_limit: int = 50
    personalization_candidate_limit: int = 20
    final_recommendation_limit: int = 5
    personalization_provider: PersonalizationProvider = PersonalizationProvider.PROFILE_VECTOR
    sequence_provider: SequenceProvider = SequenceProvider.NONE
    reranker_provider: RerankerProvider = RerankerProvider.NONE

    def as_metadata(self) -> Dict[str, Any]:
        return {
            "qdrantCandidateLimit": self.qdrant_candidate_limit,
            "ruleCandidateLimit": self.rule_candidate_limit,
            "personalizationCandidateLimit": self.personalization_candidate_limit,
            "finalRecommendationLimit": self.final_recommendation_limit,
            "personalizationProvider": self.personalization_provider.value,
            "sequenceProvider": self.sequence_provider.value,
            "rerankerProvider": self.reranker_provider.value,
        }


class RecommendationPipeline:
    """추천 후보를 단계별로 축소하는 오케스트레이션 레이어입니다.

    수정 포인트:
    - 현재는 실제 LightFM/SASRec/Cross-Encoder를 호출하지 않고 provider enum과 단계별 limit만 적용합니다.
    - 이후 provider별 scorer/reranker를 이 클래스 내부 strategy로 교체하면 100 → 50 → 20 → 5 흐름을 유지한 채 모델을 붙일 수 있습니다.
    """

    def __init__(self, config: RecommendationPipelineConfig) -> None:
        self.config = config

    def prepare_qdrant_candidates(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # 수정 포인트: Qdrant 원점수는 qdrantScore로 보존해 이후 모델 점수와 분리합니다.
        prepared: List[Dict[str, Any]] = []
        for index, candidate in enumerate(candidates[: self.config.qdrant_candidate_limit], start=1):
            item = dict(candidate)
            qdrant_score = self._safe_float(item.get("qdrantScore", item.get("score", 0.0)))
            item["qdrantScore"] = qdrant_score
            item.setdefault("score", qdrant_score)
            item["qdrantRank"] = index
            prepared.append(item)
        return prepared

    def apply_rule_stage(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # 수정 포인트: 현재 rule stage는 기존 필터/정렬 결과를 유지하면서 ruleScore/preScore 필드만 채웁니다.
        staged: List[Dict[str, Any]] = []
        for candidate in candidates:
            item = dict(candidate)
            raw_rule_score = self._safe_float(item.get("ruleScore", item.get("rerank_score", item.get("qdrantScore", item.get("score", 0.0)))))
            relevance_score = self._safe_float(item.get("candidateRelevanceScore"))
            if relevance_score > 0:
                raw_rule_score = max(raw_rule_score, (raw_rule_score * 0.72) + (relevance_score * 0.28))
            policy_penalty = self._safe_float(item.get("policyPenalty", 0.0))
            rule_score = max(0.0, raw_rule_score - policy_penalty)
            item["ruleScore"] = rule_score
            item["preScore"] = self._safe_float(item.get("preScore", rule_score))
            if policy_penalty > 0:
                item["preScore"] = max(0.0, item["preScore"] - policy_penalty)
                item["score_detail"] = {
                    **dict(item.get("score_detail") or {}),
                    "policy_penalty": round(policy_penalty, 6),
                }
            staged.append(item)
        return staged[: self.config.rule_candidate_limit]

    def apply_personalization_stage(self, candidates: List[Dict[str, Any]], enabled: bool) -> List[Dict[str, Any]]:
        # 수정 포인트: PROFILE_VECTOR는 기존 profile_reranker 점수를 profileVectorScore로 승격하고,
        # LightFM/SASRec 필드는 None으로 남겨 이후 실제 모델 연결 지점을 명확히 합니다.
        staged: List[Dict[str, Any]] = []
        for candidate in candidates:
            item = dict(candidate)
            fallback_score = self._safe_float(item.get("preScore", item.get("ruleScore", item.get("qdrantScore", 0.0))))
            profile_score = self._safe_float(item.get("profileVectorScore", item.get("rerank_score", fallback_score)))
            item["profileVectorScore"] = profile_score if enabled else fallback_score
            item.setdefault("lightfmScore", None)
            item.setdefault("sasrecScore", None)
            item["preScore"] = self._safe_float(item.get("preScore", item["profileVectorScore"]))
            staged.append(item)
        staged.sort(key=lambda value: self._safe_float(value.get("profileVectorScore", value.get("preScore", 0.0))), reverse=True)
        return staged[: self.config.personalization_candidate_limit]

    def apply_final_reranker_stage(self, candidates: List[Dict[str, Any]], final_limit: int | None = None) -> List[Dict[str, Any]]:
        # 수정 포인트: 현재 rerankerProvider는 NONE/Rule Final 형태의 no-op입니다.
        # Cross-Encoder를 붙일 때 rerankerScore를 모델 점수로 덮어쓰고 finalScore 계산식만 교체하면 됩니다.
        # 수정 포인트: 최종 추천 개수는 환경변수 기본값만 보지 않고, 사용자 질의에서 명시한 개수도 반영합니다.
        effective_limit = max(1, int(final_limit or self.config.final_recommendation_limit))
        staged: List[Dict[str, Any]] = []
        for candidate in candidates:
            item = dict(candidate)
            fallback_score = self._safe_float(item.get("profileVectorScore", item.get("preScore", item.get("qdrantScore", 0.0))))
            reranker_score = item.get("rerankerScore")
            if reranker_score is None:
                reranker_score = item.get("rerank_score") if self.config.reranker_provider == RerankerProvider.RULE_FINAL else None
            item["rerankerScore"] = None if reranker_score is None else self._safe_float(reranker_score)
            final_score = item["rerankerScore"] if item["rerankerScore"] is not None else fallback_score
            policy_penalty = self._safe_float(item.get("policyPenalty", 0.0))
            item["finalScore"] = max(0.0, self._safe_float(item.get("finalScore", final_score)) - policy_penalty)
            staged.append(item)
        staged.sort(key=lambda value: self._safe_float(value.get("finalScore", 0.0)), reverse=True)
        # 수정 포인트: 최종 후보를 단순 점수순으로만 자르면 한 장르/한 서재 신호에 결과가 고정될 수 있어,
        # 사용자 요청 개수 범위 안에서 가능한 카테고리 다양성을 먼저 확보합니다. 후보가 부족하면 억지로 무관 후보를 채우지 않습니다.
        final_candidates = self._select_diverse_final_candidates(staged, effective_limit)
        for rank, item in enumerate(final_candidates, start=1):
            item["rank"] = rank
            item["score_detail"] = {
                **dict(item.get("score_detail") or {}),
                "pipeline": self.config.as_metadata(),
                "qdrantScore": item.get("qdrantScore"),
                "candidate_relevance_score": item.get("candidateRelevanceScore"),
                "ruleScore": item.get("ruleScore"),
                "profileVectorScore": item.get("profileVectorScore"),
                "lightfmScore": item.get("lightfmScore"),
                "sasrecScore": item.get("sasrecScore"),
                "rerankerScore": item.get("rerankerScore"),
                "preScore": item.get("preScore"),
                "policyPenalty": item.get("policyPenalty", 0.0),
                "finalScore": item.get("finalScore"),
                "final_rerank_score": item.get("finalScore"),
            }
        return final_candidates

    def _select_diverse_final_candidates(self, candidates: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
        if limit <= 0 or len(candidates) <= limit:
            return candidates[:limit]

        selected: List[Dict[str, Any]] = []
        category_counts: Dict[str, int] = {}
        max_per_category = 2 if limit >= 5 else 1

        for candidate in candidates:
            key = self._primary_category_key(candidate)
            if key and category_counts.get(key, 0) >= max_per_category:
                continue
            selected.append(candidate)
            if key:
                category_counts[key] = category_counts.get(key, 0) + 1
            if len(selected) >= limit:
                return selected

        selected_keys = {id(candidate) for candidate in selected}
        for candidate in candidates:
            if id(candidate) in selected_keys:
                continue
            selected.append(candidate)
            if len(selected) >= limit:
                break
        return selected

    @staticmethod
    def _primary_category_key(candidate: Dict[str, Any]) -> str:
        for field in ["cate_depth1", "categories", "kcid"]:
            value = candidate.get(field)
            values = value if isinstance(value, list) else [value]
            for item in values:
                text = str(item or "").strip().lower()
                if text:
                    return text
        return ""

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
