from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any, Dict, List

from app.core.config import settings
from app.services.ranking.lightfm_artifact import LightFmArtifact
from app.services.ranking.ranking_result import RankingResult
from app.services.ranking.score_utils import candidate_item_key, normalize_min_max, safe_float


class LightFmRanker:
    """LightFM artifact를 이용해 rule stage 후보를 재정렬합니다.

    수정 포인트:
    - 요청 시점에는 학습을 수행하지 않고, 저장된 artifact만 메모리로 로드합니다.
    - artifact/user/item이 없으면 예외 대신 RULE_BASED fallback이 가능하도록 RankingResult로 사유를 반환합니다.
    """

    def __init__(self, artifact_path: str | None = None) -> None:
        self.artifact_path = artifact_path or settings.LIGHTFM_ARTIFACT_PATH
        self._artifact: LightFmArtifact | None = None
        self._load_error: str | None = None
        self._loaded_path: str | None = None

    def rerank(
        self,
        *,
        user_id: str | None,
        candidates: List[Dict[str, Any]],
        requested_model: str,
        limit: int,
        request_id: str | None = None,
    ) -> RankingResult:
        started_at = perf_counter()
        if not bool(settings.LIGHTFM_ENABLED):
            return self._fallback(
                candidates=candidates,
                requested_model=requested_model,
                reason="LIGHTFM_DISABLED",
                started_at=started_at,
            )
        if not user_id:
            return self._fallback(
                candidates=candidates,
                requested_model=requested_model,
                reason="MISSING_USER_ID",
                started_at=started_at,
            )
        if not candidates:
            return self._fallback(
                candidates=candidates,
                requested_model=requested_model,
                reason="EMPTY_CANDIDATES",
                started_at=started_at,
            )

        artifact = self._artifact_or_none()
        if artifact is None:
            return self._fallback(
                candidates=candidates,
                requested_model=requested_model,
                reason=self._load_error or "ARTIFACT_LOAD_FAILED",
                started_at=started_at,
            )

        normalized_user_id = str(user_id).strip()
        user_index = artifact.user_id_to_index.get(normalized_user_id)
        if user_index is None:
            return self._fallback(
                candidates=candidates,
                requested_model=requested_model,
                reason="UNKNOWN_USER",
                started_at=started_at,
                artifact=artifact,
            )

        item_fields = self._item_id_fields()
        matched_candidates: List[Dict[str, Any]] = []
        matched_item_indices: List[int] = []
        unknown_item_count = 0

        for candidate in candidates:
            item = dict(candidate)
            item_key = candidate_item_key(item, item_fields)
            item_index = artifact.item_id_to_index.get(item_key)
            if item_index is None:
                unknown_item_count += 1
                item["lightfmScore"] = None
                item["score_detail"] = {
                    **dict(item.get("score_detail") or {}),
                    "lightfm_item_key": item_key,
                    "lightfm_status": "UNKNOWN_ITEM",
                }
            else:
                item["score_detail"] = {
                    **dict(item.get("score_detail") or {}),
                    "lightfm_item_key": item_key,
                    "lightfm_item_index": item_index,
                }
                matched_item_indices.append(item_index)
            matched_candidates.append(item)

        if not matched_item_indices:
            return self._fallback(
                candidates=matched_candidates,
                requested_model=requested_model,
                reason="NO_KNOWN_ITEMS",
                started_at=started_at,
                artifact=artifact,
                extra={"unknownItemCount": unknown_item_count},
            )

        try:
            import numpy as np
        except ImportError as exc:
            self._load_error = f"NUMPY_IMPORT_FAILED: {exc}"
            return self._fallback(
                candidates=matched_candidates,
                requested_model=requested_model,
                reason="NUMPY_IMPORT_FAILED",
                started_at=started_at,
                artifact=artifact,
            )

        try:
            # Vectorised prediction using pure NumPy embeddings and biases:
            # score(u, i) = user_emb * item_emb + user_bias + item_bias
            user_emb = artifact.user_embeddings[user_index]  # (components,)
            item_embs = artifact.item_embeddings[matched_item_indices]  # (N, components)
            user_bias = artifact.user_biases[user_index]  # float
            item_biases = artifact.item_biases[matched_item_indices]  # (N,)

            raw_scores = (item_embs * user_emb).sum(axis=1) + user_bias + item_biases
        except Exception as exc:
            print(f"[LIGHTFM RANKER][{request_id or '-'}] predict failed: {exc}")
            return self._fallback(
                candidates=matched_candidates,
                requested_model=requested_model,
                reason="PREDICT_FAILED",
                started_at=started_at,
                artifact=artifact,
            )

        # KURE Embedding Client 연동 (미학습 도서 구제용)
        from app.services.clients.kure_client import KureClient
        kure_client = KureClient()

        normalized_scores = normalize_min_max([float(score) for score in raw_scores])
        known_cursor = 0
        ranked_candidates: List[Dict[str, Any]] = []
        rule_scores = normalize_min_max([
            safe_float(candidate.get("preScore", candidate.get("ruleScore", candidate.get("qdrantScore", 0.0))))
            for candidate in matched_candidates
        ])
        model_weight = min(max(float(settings.LIGHTFM_SCORE_MODEL_WEIGHT), 0.0), 1.0)
        rule_weight = min(max(float(settings.LIGHTFM_SCORE_RULE_WEIGHT), 0.0), 1.0)
        
        # [HYBRID STRATEGY] 미학습 도서에 대한 보정 가중치 대폭 상향
        # LightFM이 모르는 책이라도 Qdrant/Embedding 점수가 높으면 적극적으로 상위권 노출
        unknown_rescue_weight = 0.95 

        weight_sum = model_weight + rule_weight
        if weight_sum <= 0:
            model_weight = 0.5  # 가중치 분산
            rule_weight = 0.5
            weight_sum = 1.0

        for index, candidate in enumerate(matched_candidates):
            item = dict(candidate)
            item_key = candidate_item_key(item, item_fields)
            item_index = artifact.item_id_to_index.get(item_key)
            rule_score = rule_scores[index] if index < len(rule_scores) else 0.0
            
            if item_index is None:
                # [RESCUE LOGIC] 미학습 도서 구제
                # 임베딩 유사도(rule_score)를 핵심 지표로 사용
                blended_score = rule_score * unknown_rescue_weight
                item["lightfmScore"] = 0.0 
                item["preScore"] = round(blended_score, 6)
                item["finalScore"] = round(blended_score, 6)
                item["score_detail"] = {
                    **dict(item.get("score_detail") or {}),
                    "lightfm_status": "HYBRID_RESCUED",
                    "hybrid_reason": "Vector similarity fallback for unknown item",
                    "original_qdrant_score": rule_score
                }
                ranked_candidates.append(item)
                continue

            raw_score = float(raw_scores[known_cursor])
            normalized_score = float(normalized_scores[known_cursor])
            known_cursor += 1
            blended_score = ((normalized_score * model_weight) + (rule_score * rule_weight)) / weight_sum
            item["lightfmScore"] = round(normalized_score, 6)
            item["preScore"] = round(blended_score, 6)
            item["finalScore"] = round(blended_score, 6)
            item["score_detail"] = {
                **dict(item.get("score_detail") or {}),
                "lightfm_raw_score": round(raw_score, 6),
                "lightfm_score": round(normalized_score, 6),
                "lightfm_rule_score": round(rule_score, 6),
                "lightfm_model_weight": round(model_weight, 6),
                "lightfm_rule_weight": round(rule_weight, 6),
                "lightfm_status": "SCORED",
            }
            ranked_candidates.append(item)

        ranked_candidates.sort(
            key=lambda row: safe_float(row.get("preScore", row.get("finalScore", 0.0))),
            reverse=True,
        )
        elapsed_ms = int((perf_counter() - started_at) * 1000)
        return RankingResult(
            candidates=ranked_candidates[: max(1, limit)],
            requested_model=requested_model,
            applied_model="LIGHTFM",
            applied=True,
            fallback=False,
            fallback_reason=None,
            artifact_version=artifact.version,
            elapsed_ms=elapsed_ms,
            metadata={
                "knownItemCount": len(matched_item_indices),
                "unknownItemCount": unknown_item_count,
                "candidateLimit": max(1, limit),
                "artifactPath": str(Path(self.artifact_path).expanduser()),
            },
        )

    def _artifact_or_none(self) -> LightFmArtifact | None:
        current_path = str(Path(self.artifact_path).expanduser())
        if self._artifact is not None and self._loaded_path == current_path:
            return self._artifact
        try:
            self._artifact = LightFmArtifact.load(current_path)
            self._load_error = None
            self._loaded_path = current_path
            print(f"[LIGHTFM ARTIFACT] loaded path={current_path} version={self._artifact.version}")
        except Exception as exc:
            self._artifact = None
            self._load_error = f"ARTIFACT_LOAD_FAILED: {exc}"
            self._loaded_path = current_path
            print(f"[LIGHTFM ARTIFACT] load failed path={current_path} error={exc}")
        return self._artifact

    @staticmethod
    def _item_id_fields() -> List[str]:
        return [
            field.strip()
            for field in str(settings.LIGHTFM_ITEM_ID_FIELDS or "isbn,isbn13,book_id").split(",")
            if field.strip()
        ]

    @staticmethod
    def _fallback(
        *,
        candidates: List[Dict[str, Any]],
        requested_model: str,
        reason: str,
        started_at: float,
        artifact: LightFmArtifact | None = None,
        extra: Dict[str, Any] | None = None,
    ) -> RankingResult:
        elapsed_ms = int((perf_counter() - started_at) * 1000)
        return RankingResult(
            candidates=candidates,
            requested_model=requested_model,
            applied_model="RULE_BASED",
            applied=False,
            fallback=True,
            fallback_reason=reason,
            artifact_version=artifact.version if artifact is not None else None,
            elapsed_ms=elapsed_ms,
            metadata=dict(extra or {}),
        )
