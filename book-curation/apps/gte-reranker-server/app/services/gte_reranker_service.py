from __future__ import annotations

import math
import os
import threading
from typing import Any, List

from sentence_transformers import CrossEncoder

from app.core.config import settings


class GteRerankerService:
    """Alibaba-NLP/gte-multilingual-reranker-base CrossEncoder 서빙 서비스입니다."""

    _model: CrossEncoder | None = None
    _model_lock = threading.Lock()
    _predict_lock = threading.Lock()
    _loaded_model_name: str | None = None

    def __init__(self) -> None:
        os.environ.setdefault("HF_HOME", settings.GTE_RERANKER_MODEL_CACHE_DIR)
        os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", settings.GTE_RERANKER_MODEL_CACHE_DIR)
        os.environ.setdefault("TRANSFORMERS_CACHE", settings.GTE_RERANKER_MODEL_CACHE_DIR)
        self.model_name = settings.GTE_RERANKER_MODEL_PATH.strip() or settings.GTE_RERANKER_MODEL_NAME
        self.batch_size = max(1, int(settings.GTE_RERANKER_BATCH_SIZE))
        self.device = settings.GTE_RERANKER_DEVICE
        self.max_text_chars = max(120, int(settings.GTE_RERANKER_MAX_TEXT_CHARS))
        self._configure_torch_threads()

    @classmethod
    def is_loaded(cls) -> bool:
        return cls._model is not None

    @classmethod
    def loaded_model_name(cls) -> str | None:
        return cls._loaded_model_name

    def warmup(self) -> float:
        scores = self.rerank("warmup", ["warmup document"])
        return scores[0] if scores else 0.0

    def rerank(self, query: str, texts: List[str]) -> list[float]:
        normalized_query = " ".join(str(query or "").split())
        normalized_texts = [" ".join(str(text or "").split())[: self.max_text_chars] for text in texts]
        if not normalized_query:
            raise ValueError("query는 비어 있을 수 없습니다.")
        if not normalized_texts or not any(normalized_texts):
            raise ValueError("texts는 비어 있을 수 없습니다.")
        pairs = [[normalized_query, text or " "] for text in normalized_texts]
        model = self._load_model()
        with self.__class__._predict_lock:
            raw_scores: Any = model.predict(pairs, batch_size=self.batch_size, show_progress_bar=False)
        return self._normalize_scores(raw_scores)

    def _load_model(self) -> CrossEncoder:
        if self.__class__._model is not None:
            return self.__class__._model

        with self.__class__._model_lock:
            if self.__class__._model is None:
                print(
                    "[GTE RERANKER MODEL LOAD] "
                    f"model={self.model_name}, device={self.device}, cache_dir={settings.GTE_RERANKER_MODEL_CACHE_DIR}, "
                    f"trust_remote_code={settings.GTE_RERANKER_TRUST_REMOTE_CODE}"
                )
                # sentence-transformers 3.x CrossEncoder는 config_kwargs 인자를 지원하지 않습니다.
                # trust_remote_code는 CrossEncoder의 공식 인자로 전달하고, 모델/토크나이저 세부 옵션만 각각 분리합니다.
                self.__class__._model = CrossEncoder(
                    self.model_name,
                    device=self.device,
                    trust_remote_code=bool(settings.GTE_RERANKER_TRUST_REMOTE_CODE),
                    automodel_args={"torch_dtype": "auto"},
                    tokenizer_args={"padding_side": "right"},
                )
                self.__class__._loaded_model_name = self.model_name
                print(f"[GTE RERANKER MODEL READY] model={self.model_name}")
        return self.__class__._model

    @staticmethod
    def _normalize_scores(raw_scores: Any) -> list[float]:
        if hasattr(raw_scores, "tolist"):
            raw_scores = raw_scores.tolist()
        values = [float(value) for value in raw_scores]
        if not values:
            return []
        # 모델 출력은 raw logit일 수 있으므로 sigmoid 후 요청 단위 min-max로 0~1 정규화합니다.
        sigmoid_values = [1.0 / (1.0 + math.exp(-max(min(value, 60.0), -60.0))) for value in values]
        min_value = min(sigmoid_values)
        max_value = max(sigmoid_values)
        if max_value <= min_value:
            return [0.5 for _ in sigmoid_values]
        return [(value - min_value) / (max_value - min_value) for value in sigmoid_values]

    @staticmethod
    def _configure_torch_threads() -> None:
        try:
            import torch

            torch.set_num_threads(max(1, int(settings.GTE_RERANKER_TORCH_NUM_THREADS)))
        except Exception as exc:
            print(f"[GTE TORCH THREAD CONFIG SKIPPED] error={exc}")
