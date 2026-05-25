import threading
import time
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Optional

import requests

from app.core.config import settings


class _EndpointThrottle:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.cooldown_until = 0.0
        self.last_request_at = 0.0


class ClovaClient:
    RETRY_STATUS_CODES = {429, 500, 502, 503, 504}

    # 수정 포인트: FastAPI 요청마다 ClovaClient 인스턴스가 달라도 CLOVA 호출 간격/쿨다운은 프로세스 전체에서 공유합니다.
    _embedding_throttle = _EndpointThrottle()
    _chat_throttle = _EndpointThrottle()

    # 수정 포인트: 같은 질문/문서 임베딩을 반복 호출하지 않도록 프로세스 단위 LRU 캐시를 공유합니다.
    _embedding_cache: OrderedDict[str, list[float]] = OrderedDict()
    _embedding_cache_lock = threading.Lock()

    def __init__(self):
        self.api_key = settings.CLOVA_API_KEY
        self.chat_url = settings.CLOVA_CHAT_URL
        self.embed_url = settings.CLOVA_EMBED_URL
        self.chat_model = settings.CLOVA_CHAT_MODEL
        self.embed_model = settings.CLOVA_EMBED_MODEL

        self.session = requests.Session()

    @staticmethod
    def _normalize_text(text: str) -> str:
        return " ".join((text or "").strip().lower().split())

    @staticmethod
    def _is_openai_compatible_url(url: str) -> bool:
        return "/v1/openai" in (url or "")

    @classmethod
    def _build_native_model_url(cls, url: str, model: str) -> str:
        # 수정 포인트: CLOVA Studio v3 네이티브 API는 모델명을 body가 아니라 URL 경로에 포함합니다.
        # 로컬 .env.local에 예전 OpenAI식 경로(/v3/chat/completions)가 남아 있어도 404가 나지 않도록 보정합니다.
        base_url = (url or "").strip().rstrip("/")
        model_name = (model or "").strip()

        if not base_url:
            return base_url

        base_url = base_url.replace("/v3/chat/completions", "/v3/chat-completions")

        if not model_name:
            return base_url

        if base_url.endswith(f"/{model_name}"):
            return base_url

        return f"{base_url}/{model_name}"

    def _resolve_chat_request(self) -> tuple[str, bool]:
        # 반환값: (실제 호출 URL, OpenAI 호환 API 여부)
        if self._is_openai_compatible_url(self.chat_url):
            return self.chat_url.rstrip("/"), True
        return self._build_native_model_url(self.chat_url, self.chat_model), False

    @staticmethod
    def _now() -> float:
        return time.time()

    @staticmethod
    def _clamp_delay(seconds: float) -> float:
        return max(0.0, min(float(seconds), settings.CLOVA_RETRY_MAX_DELAY_SECONDS))

    @classmethod
    def _get_sleep_time(cls, response: requests.Response, fallback_delay: float) -> float:
        retry_after = response.headers.get("Retry-After")
        if not retry_after:
            return cls._clamp_delay(fallback_delay)

        retry_after = retry_after.strip()
        try:
            return cls._clamp_delay(float(retry_after))
        except ValueError:
            pass

        try:
            retry_datetime = parsedate_to_datetime(retry_after)
            if retry_datetime.tzinfo is None:
                retry_datetime = retry_datetime.replace(tzinfo=timezone.utc)
            seconds = (retry_datetime - datetime.now(timezone.utc)).total_seconds()
            return cls._clamp_delay(seconds)
        except Exception:
            return cls._clamp_delay(fallback_delay)

    @classmethod
    def _get_cached_embedding(cls, text: str) -> Optional[list[float]]:
        with cls._embedding_cache_lock:
            value = cls._embedding_cache.get(text)
            if value is None:
                return None
            cls._embedding_cache.move_to_end(text)
            return value

    @classmethod
    def _put_cached_embedding(cls, text: str, vector: list[float]) -> None:
        cache_size = max(1, settings.CLOVA_EMBEDDING_CACHE_SIZE)
        with cls._embedding_cache_lock:
            cls._embedding_cache[text] = vector
            cls._embedding_cache.move_to_end(text)
            while len(cls._embedding_cache) > cache_size:
                cls._embedding_cache.popitem(last=False)

    @classmethod
    def _wait_for_turn(cls, throttle: _EndpointThrottle, min_interval_seconds: float, label: str) -> None:
        with throttle.lock:
            now = cls._now()
            wait_seconds = max(
                0.0,
                throttle.cooldown_until - now,
                float(min_interval_seconds) - (now - throttle.last_request_at),
            )
            if wait_seconds > 0:
                print(f"[CLOVA {label} WAIT] sleep={round(wait_seconds, 3)}s")
                time.sleep(wait_seconds)
            throttle.last_request_at = cls._now()

    @classmethod
    def _set_cooldown(cls, throttle: _EndpointThrottle, seconds: float, label: str) -> None:
        cooldown_seconds = max(float(settings.CLOVA_429_COOLDOWN_SECONDS), float(seconds), 0.0)
        until = cls._now() + cooldown_seconds
        with throttle.lock:
            throttle.cooldown_until = max(throttle.cooldown_until, until)
        print(f"[CLOVA {label} COOLDOWN] seconds={round(cooldown_seconds, 3)}")

    def _post_with_retry(
        self,
        *,
        label: str,
        url: str,
        headers: dict[str, str],
        body: dict[str, Any],
        timeout_seconds: float,
        throttle: _EndpointThrottle,
        min_interval_seconds: float,
    ) -> Optional[dict[str, Any]]:
        max_retries = max(1, settings.CLOVA_MAX_RETRIES)
        delay = max(0.1, settings.CLOVA_RETRY_INITIAL_DELAY_SECONDS)

        for attempt in range(1, max_retries + 1):
            try:
                self._wait_for_turn(throttle, min_interval_seconds, label)

                response = self.session.post(
                    url,
                    headers=headers,
                    json=body,
                    timeout=timeout_seconds,
                )

                if response.status_code in self.RETRY_STATUS_CODES:
                    sleep_time = self._get_sleep_time(response, delay)
                    print(
                        f"[CLOVA {label} RETRY] "
                        f"status={response.status_code}, "
                        f"retry={attempt}/{max_retries}, "
                        f"sleep={round(sleep_time, 3)}s"
                    )

                    if response.status_code == 429:
                        self._set_cooldown(throttle, sleep_time, label)

                    if attempt == max_retries:
                        print(f"[CLOVA {label} FAILED] status={response.status_code}")
                        return None

                    time.sleep(sleep_time)
                    delay = min(delay * 2, settings.CLOVA_RETRY_MAX_DELAY_SECONDS)
                    continue

                response.raise_for_status()
                return response.json()

            except requests.RequestException as e:
                print(
                    f"[CLOVA {label} ERROR] "
                    f"error={e}, "
                    f"retry={attempt}/{max_retries}, "
                    f"sleep={round(delay, 3)}s"
                )

                if attempt == max_retries:
                    return None

                time.sleep(self._clamp_delay(delay))
                delay = min(delay * 2, settings.CLOVA_RETRY_MAX_DELAY_SECONDS)

            except Exception as e:
                print(f"[CLOVA {label} UNKNOWN ERROR] error={e}")
                return None

        return None

    def embedding(self, text: str) -> Optional[list[float]]:
        text = self._normalize_text(text)

        if not text:
            return None

        cached = self._get_cached_embedding(text)
        if cached is not None:
            return cached

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json; charset=utf-8",
            "X-NCP-CLOVASTUDIO-REQUEST-ID": uuid.uuid4().hex,
        }

        body = {
            "text": text,
        }

        data = self._post_with_retry(
            label="EMBEDDING",
            url=self.embed_url,
            headers=headers,
            body=body,
            timeout_seconds=settings.CLOVA_EMBED_TIMEOUT_SECONDS,
            throttle=self._embedding_throttle,
            min_interval_seconds=settings.CLOVA_EMBED_MIN_INTERVAL_SECONDS,
        )
        if data is None:
            return None

        if "result" in data and "embedding" in data["result"]:
            embedding_vector = data["result"]["embedding"]
            self._put_cached_embedding(text, embedding_vector)
            return embedding_vector

        if "embedding" in data:
            embedding_vector = data["embedding"]
            self._put_cached_embedding(text, embedding_vector)
            return embedding_vector

        print(f"[CLOVA EMBEDDING INVALID RESPONSE] data={data}")
        return None

    def embedding_many(
        self,
        texts: list[str],
        max_workers: int = 1,
    ) -> list[Optional[list[float]]]:
        # 수정 포인트: 기존 ThreadPool 방식은 실패한 벡터를 제거해 책과 벡터가 어긋날 수 있었습니다.
        # 순서를 보존하고 실패 위치는 None으로 남겨 인덱싱에서 해당 책만 건너뛰게 합니다.
        results: list[Optional[list[float]]] = []
        for idx, text in enumerate(texts):
            try:
                results.append(self.embedding(text))
            except Exception as e:
                print(f"[CLOVA EMBEDDING MANY ERROR] index={idx}, error={e}")
                results.append(None)
        return results

    def chat_completion(self, system_prompt: str, user_prompt: str) -> str:
        chat_url, is_openai_compatible = self._resolve_chat_request()

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json; charset=utf-8",
            "X-NCP-CLOVASTUDIO-REQUEST-ID": uuid.uuid4().hex,
        }

        body: dict[str, Any] = {
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
        }

        # 수정 포인트: /v1/openai 호환 API를 쓰는 경우에만 model을 body에 넣습니다.
        # CLOVA Studio v3 네이티브 API는 /v3/chat-completions/{modelName} URL 경로로 모델을 지정합니다.
        if is_openai_compatible:
            body["model"] = self.chat_model

        data = self._post_with_retry(
            label="CHAT",
            url=chat_url,
            headers=headers,
            body=body,
            timeout_seconds=settings.CLOVA_CHAT_TIMEOUT_SECONDS,
            throttle=self._chat_throttle,
            min_interval_seconds=settings.CLOVA_CHAT_MIN_INTERVAL_SECONDS,
        )
        if data is None:
            return ""

        if "result" in data and "message" in data["result"]:
            return data["result"]["message"].get("content", "")

        if "choices" in data:
            return data["choices"][0]["message"]["content"]

        if "message" in data:
            return data["message"].get("content", "")

        print(f"[CLOVA CHAT INVALID RESPONSE] data={data}")
        return ""
