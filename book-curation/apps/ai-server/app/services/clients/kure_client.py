from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any, Optional

import requests

from app.core.config import settings


class KureClient:
    """
    분리형 KURE 임베딩 서버 HTTP client입니다.

    수정 포인트:
    - ai-server는 sentence-transformers/torch/KURE 모델을 직접 import하지 않습니다.
    - KURE 모델 실행은 별도 kure-embedding-server의 /embed API에만 위임합니다.
    - 장애 시 ai-server 프로세스가 죽지 않도록 timeout/retry 후 None을 반환합니다.
    """

    _embedding_cache: OrderedDict[str, list[float]] = OrderedDict()
    _cache_size = 2048

    def __init__(self) -> None:
        self.base_url = settings.KURE_EMBEDDING_BASE_URL.rstrip("/")
        self.internal_api_key = settings.KURE_INTERNAL_API_KEY.strip()
        self.internal_header_name = settings.KURE_INTERNAL_HEADER_NAME
        self.timeout_seconds = float(settings.KURE_REQUEST_TIMEOUT_SECONDS)
        self.max_retries = max(1, int(settings.KURE_MAX_RETRIES))
        self.retry_initial_delay_seconds = max(0.0, float(settings.KURE_RETRY_INITIAL_DELAY_SECONDS))
        self.retry_max_delay_seconds = max(0.0, float(settings.KURE_RETRY_MAX_DELAY_SECONDS))
        self.expected_dimension = int(settings.KURE_EXPECTED_DIMENSION)
        self.session = requests.Session()

    @staticmethod
    def _normalize_text(text: str) -> str:
        return " ".join((text or "").strip().lower().split())

    @classmethod
    def _get_cached_embedding(cls, text: str) -> Optional[list[float]]:
        value = cls._embedding_cache.get(text)
        if value is None:
            return None
        cls._embedding_cache.move_to_end(text)
        return value

    @classmethod
    def _put_cached_embedding(cls, text: str, vector: list[float]) -> None:
        cls._embedding_cache[text] = vector
        cls._embedding_cache.move_to_end(text)
        while len(cls._embedding_cache) > cls._cache_size:
            cls._embedding_cache.popitem(last=False)

    def _headers(self) -> dict[str, str]:
        if not self.internal_api_key:
            return {}
        return {self.internal_header_name: self.internal_api_key}

    def _request_embedding(self, text: str) -> Optional[dict[str, Any]]:
        delay = self.retry_initial_delay_seconds

        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.post(
                    f"{self.base_url}/embed",
                    json={"text": text},
                    headers=self._headers(),
                    timeout=self.timeout_seconds,
                )

                if response.status_code == 401:
                    print("[KURE EMBEDDING AUTH ERROR] invalid internal API key")
                    return None

                if response.status_code >= 500:
                    raise requests.HTTPError(f"KURE server status={response.status_code}")

                if response.status_code >= 400:
                    print(f"[KURE EMBEDDING BAD REQUEST] status={response.status_code}, body={response.text[:300]}")
                    return None

                return response.json()

            except Exception as exc:
                print(
                    "[KURE EMBEDDING REQUEST ERROR] "
                    f"attempt={attempt}/{self.max_retries}, "
                    f"base_url={self.base_url}, "
                    f"error={exc}"
                )
                if attempt >= self.max_retries:
                    return None
                if delay > 0:
                    time.sleep(min(delay, self.retry_max_delay_seconds))
                delay = min(max(delay * 2, 0.1), self.retry_max_delay_seconds)

        return None

    def embedding(self, text: str) -> Optional[list[float]]:
        text = self._normalize_text(text)
        if not text:
            return None

        cached = self._get_cached_embedding(text)
        if cached is not None:
            return cached

        payload = self._request_embedding(text)
        if not payload:
            return None

        vector = payload.get("vector")
        if not isinstance(vector, list):
            print("[KURE EMBEDDING INVALID RESPONSE] vector field is missing")
            return None

        try:
            embedding_vector = [float(value) for value in vector]
        except Exception as exc:
            print(f"[KURE EMBEDDING CONVERT ERROR] error={exc}")
            return None

        if len(embedding_vector) != self.expected_dimension:
            print(
                "[KURE EMBEDDING INVALID DIMENSION] "
                f"expected={self.expected_dimension}, actual={len(embedding_vector)}"
            )
            return None

        self._put_cached_embedding(text, embedding_vector)
        return embedding_vector

    def embedding_many(self, texts: list[str], max_workers: int = 1) -> list[Optional[list[float]]]:
        # 수정 포인트: 기존 indexer 인터페이스 호환용입니다. 실시간 검색은 단건 /embed만 사용합니다.
        _ = max_workers
        return [self.embedding(text) for text in texts]
