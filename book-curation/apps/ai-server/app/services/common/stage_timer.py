from __future__ import annotations

from contextlib import contextmanager
from time import perf_counter
from typing import Dict, Iterator


class StageTimer:
    """요청 단위 stage별 소요 시간을 수집하는 작은 유틸리티입니다.

    수정 포인트:
    - 추천 파이프라인에 LightFM/reranker가 추가될 때 어느 stage가 병목인지 즉시 확인할 수 있게 합니다.
    - 서버 동작에는 영향을 주지 않고, 응답 metadata와 로그에 숫자만 추가합니다.
    """

    def __init__(self) -> None:
        self._started_at = perf_counter()
        self._entries: Dict[str, int] = {}

    @contextmanager
    def measure(self, name: str) -> Iterator[None]:
        started_at = perf_counter()
        try:
            yield
        finally:
            self.record(name=name, started_at=started_at)

    def record(self, *, name: str, started_at: float) -> None:
        elapsed_ms = max(0, int((perf_counter() - started_at) * 1000))
        key = self._normalize_key(name)
        self._entries[key] = self._entries.get(key, 0) + elapsed_ms

    def snapshot(self) -> Dict[str, int]:
        values = dict(self._entries)
        values["total_ms"] = max(0, int((perf_counter() - self._started_at) * 1000))
        return values

    @staticmethod
    def _normalize_key(name: str) -> str:
        normalized = str(name or "stage").strip().lower().replace("-", "_").replace(" ", "_")
        if not normalized:
            normalized = "stage"
        return normalized if normalized.endswith("_ms") else f"{normalized}_ms"
