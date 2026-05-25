import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int
    remaining: int


class FixedWindowRateLimiter:
    """Thread-safe fixed-window limiter for a single FastAPI worker process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, tuple[int, float]] = {}
        self._next_cleanup_at = 0.0

    def consume(self, key: str, capacity: int, window_seconds: int) -> RateLimitDecision:
        # 수정 포인트: 잘못된 환경변수 값 때문에 전체 서비스가 막히지 않도록 최소값을 보정합니다.
        capacity = max(1, int(capacity))
        window_seconds = max(1, int(window_seconds))

        now = time.time()
        with self._lock:
            self._cleanup_expired(now)

            count, window_ends_at = self._counters.get(key, (0, now + window_seconds))
            if now >= window_ends_at:
                self._counters[key] = (1, now + window_seconds)
                return RateLimitDecision(True, window_seconds, capacity - 1)

            retry_after = max(1, int(window_ends_at - now + 0.999))
            if count >= capacity:
                return RateLimitDecision(False, retry_after, 0)

            count += 1
            self._counters[key] = (count, window_ends_at)
            return RateLimitDecision(True, retry_after, max(0, capacity - count))

    def _cleanup_expired(self, now: float) -> None:
        if now < self._next_cleanup_at:
            return

        self._next_cleanup_at = now + 60
        expired_keys = [key for key, (_, window_ends_at) in self._counters.items() if now >= window_ends_at]
        for key in expired_keys:
            self._counters.pop(key, None)
