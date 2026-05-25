from __future__ import annotations

import hashlib
import json
from typing import Any

try:
    import redis
except Exception:  # pragma: no cover - dependency may be absent in local partial installs
    redis = None  # type: ignore

from app.core.config import settings


class RedisCacheClient:
    """Valkey/Redis TTL cache helper. All methods fail open to keep recommendation available."""

    def __init__(self) -> None:
        self._client = None

    @property
    def enabled(self) -> bool:
        return bool(getattr(settings, "REDIS_ENABLED", False)) and redis is not None

    def _get_client(self):
        if not self.enabled:
            return None
        if self._client is None:
            self._client = redis.Redis(
                host=str(getattr(settings, "REDIS_HOST", "localhost")),
                port=int(getattr(settings, "REDIS_PORT", 6379)),
                username=(getattr(settings, "REDIS_USERNAME", "") or None),
                password=(getattr(settings, "REDIS_PASSWORD", "") or None),
                db=int(getattr(settings, "REDIS_DATABASE", 0)),
                socket_timeout=float(getattr(settings, "REDIS_SOCKET_TIMEOUT_SECONDS", 1.0)),
                socket_connect_timeout=float(getattr(settings, "REDIS_SOCKET_TIMEOUT_SECONDS", 1.0)),
                decode_responses=True,
            )
        return self._client

    def key(self, *parts: Any) -> str:
        prefix = str(getattr(settings, "REDIS_KEY_PREFIX", "book-curation") or "book-curation").strip().rstrip(":")
        normalized = [self._safe_part(str(part)) for part in parts if str(part or "").strip()]
        return ":".join([prefix, *normalized])

    def digest(self, value: Any) -> str:
        try:
            payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        except Exception:
            payload = str(value)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get_json(self, key: str) -> Any | None:
        client = self._get_client()
        if client is None:
            return None
        try:
            value = client.get(key)
            if not value:
                return None
            return json.loads(value)
        except Exception as exc:
            print(f"[REDIS CACHE MISS][error] key={key} reason={exc}")
            return None

    def set_json(self, key: str, value: Any, ttl_seconds: int | float | None) -> None:
        client = self._get_client()
        if client is None:
            return
        ttl = int(ttl_seconds or 0)
        if ttl <= 0:
            return
        try:
            client.setex(key, ttl, json.dumps(value, ensure_ascii=False, default=str))
        except Exception as exc:
            print(f"[REDIS CACHE SET FAILED] key={key} reason={exc}")

    @staticmethod
    def _safe_part(value: str) -> str:
        safe = "".join(ch.lower() if ch.isalnum() or ch in "._-" else "-" for ch in value.strip())
        while "--" in safe:
            safe = safe.replace("--", "-")
        return safe[:120] if len(safe) <= 120 else hashlib.sha256(safe.encode("utf-8")).hexdigest()[:32]


redis_cache = RedisCacheClient()
