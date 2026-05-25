from __future__ import annotations

import os
import threading
from typing import Any

from sentence_transformers import SentenceTransformer

from app.core.config import settings


class KureEmbeddingService:
    """프로세스 단위 singleton KURE embedding service입니다."""

    _model: SentenceTransformer | None = None
    _model_lock = threading.Lock()
    _encode_lock = threading.Lock()
    _loaded_model_name: str | None = None

    def __init__(self) -> None:
        os.environ.setdefault("HF_HOME", settings.KURE_MODEL_CACHE_DIR)
        os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", settings.KURE_MODEL_CACHE_DIR)
        os.environ.setdefault("TRANSFORMERS_CACHE", settings.KURE_MODEL_CACHE_DIR)
        self.model_name = settings.KURE_MODEL_PATH.strip() or settings.KURE_MODEL_NAME
        self.expected_dimension = int(settings.KURE_EXPECTED_DIMENSION)
        self.batch_size = max(1, int(settings.KURE_BATCH_SIZE))
        self.device = settings.KURE_DEVICE
        self.normalize_embeddings = bool(settings.KURE_NORMALIZE_EMBEDDINGS)
        self._configure_torch_threads()

    @classmethod
    def is_loaded(cls) -> bool:
        return cls._model is not None

    @classmethod
    def loaded_model_name(cls) -> str | None:
        return cls._loaded_model_name

    def warmup(self) -> int:
        model = self._load_model()
        vector = self._encode("warmup")
        _ = model
        return len(vector)

    def embed(self, text: str) -> list[float]:
        normalized = " ".join((text or "").strip().split())
        if not normalized:
            raise ValueError("text는 비어 있을 수 없습니다.")
        return self._encode(normalized)

    def _load_model(self) -> SentenceTransformer:
        if self.__class__._model is not None:
            return self.__class__._model

        with self.__class__._model_lock:
            if self.__class__._model is None:
                print(
                    "[KURE MODEL LOAD] "
                    f"model={self.model_name}, device={self.device}, cache_dir={settings.KURE_MODEL_CACHE_DIR}"
                )
                self.__class__._model = SentenceTransformer(
                    self.model_name,
                    device=self.device,
                    cache_folder=settings.KURE_MODEL_CACHE_DIR,
                )
                self.__class__._loaded_model_name = self.model_name
                print(f"[KURE MODEL READY] model={self.model_name}")

        return self.__class__._model

    def _encode(self, text: str) -> list[float]:
        model = self._load_model()
        with self.__class__._encode_lock:
            result: Any = model.encode(
                [text],
                batch_size=1,
                normalize_embeddings=self.normalize_embeddings,
                show_progress_bar=False,
            )

        try:
            vector = result[0]
            if hasattr(vector, "tolist"):
                vector = vector.tolist()
            embedding_vector = [float(value) for value in vector]
        except Exception as exc:
            raise RuntimeError(f"KURE embedding 결과를 float list로 변환하지 못했습니다: {exc}") from exc

        if len(embedding_vector) != self.expected_dimension:
            raise RuntimeError(
                "KURE embedding dimension이 예상값과 다릅니다. "
                f"expected={self.expected_dimension}, actual={len(embedding_vector)}"
            )

        return embedding_vector

    @staticmethod
    def _configure_torch_threads() -> None:
        try:
            import torch

            threads = max(1, int(settings.KURE_TORCH_NUM_THREADS))
            torch.set_num_threads(threads)
        except Exception as exc:
            print(f"[KURE TORCH THREAD CONFIG SKIPPED] error={exc}")
