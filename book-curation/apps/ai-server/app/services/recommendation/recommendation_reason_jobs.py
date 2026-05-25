from __future__ import annotations

import copy
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any, Callable, Dict, List

from app.core.config import settings
from app.services.common.redis_cache import redis_cache


ReasonGenerator = Callable[[], Dict[str, Any]]
IncrementalReasonGenerator = Callable[[int, Dict[str, Any], List[Dict[str, Any]]], Dict[str, Any]]
IncrementalAnswerBuilder = Callable[[List[Dict[str, Any]]], str]


@dataclass
class RecommendationReasonJob:
    request_id: str
    status: str = "PENDING"
    answer: str | None = None
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    error_message: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def as_response(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "status": self.status,
            "answer": self.answer,
            "candidates": self._sanitize_candidates(self.candidates),
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat().replace("+00:00", "Z"),
            "updated_at": self.updated_at.isoformat().replace("+00:00", "Z"),
        }

    @staticmethod
    def from_response(data: Dict[str, Any]) -> "RecommendationReasonJob" | None:
        request_id = str(data.get("request_id") or data.get("requestId") or "").strip()
        if not request_id:
            return None
        return RecommendationReasonJob(
            request_id=request_id,
            status=str(data.get("status") or "PENDING").strip().upper() or "PENDING",
            answer=str(data.get("answer") or "").strip() or None,
            candidates=RecommendationReasonJob._sanitize_candidates(data.get("candidates") if isinstance(data.get("candidates"), list) else []),
            error_message=str(data.get("error_message") or data.get("errorMessage") or "").strip() or None,
            created_at=RecommendationReasonJob._parse_datetime(data.get("created_at") or data.get("createdAt")),
            updated_at=RecommendationReasonJob._parse_datetime(data.get("updated_at") or data.get("updatedAt")),
        )

    @staticmethod
    def _parse_datetime(value: Any) -> datetime:
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc)
        text = str(value or "").strip()
        if text:
            try:
                return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
            except Exception:
                pass
        return datetime.now(timezone.utc)

    @staticmethod
    def _sanitize_candidates(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # 수정 포인트: 비동기 추천 이유 조회 API는 response_model 검증을 거치므로,
        # 백그라운드 job에 저장된 후보의 dict/list 필드가 None이면 500으로 응답됩니다.
        # 추천 카드 자체는 유지하되 스키마 필수 컨테이너 필드만 안전한 기본값으로 정규화합니다.
        sanitized: List[Dict[str, Any]] = []
        list_fields = {"categories", "cate_depth1", "kcid", "cate_depth2", "cate_depth3", "genres"}
        dict_fields = {"audience_profile", "score_detail"}
        for candidate in candidates or []:
            if not isinstance(candidate, dict):
                continue
            next_candidate = dict(candidate)
            for field_name in list_fields:
                if not isinstance(next_candidate.get(field_name), list):
                    next_candidate[field_name] = []
            for field_name in dict_fields:
                if not isinstance(next_candidate.get(field_name), dict):
                    next_candidate[field_name] = {}
            sanitized.append(next_candidate)
        return sanitized


class RecommendationReasonJobStore:
    """Async recommendation reason job store.

    In-memory state is still used for worker coordination, but job snapshots are
    also mirrored to Valkey/Redis. This prevents 비로그인 추천 이유 polling from
    returning MISSING when the first recommend request and the polling request are
    routed to different ai-server pods.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, int(getattr(settings, "RECOMMENDATION_REASON_ASYNC_WORKERS", 2))),
            thread_name_prefix="recommendation-reason",
        )
        self._jobs: Dict[str, RecommendationReasonJob] = {}
        self._futures: Dict[str, Future[Any]] = {}

    def submit(
        self,
        *,
        request_id: str | None,
        candidates: List[Dict[str, Any]],
        generator: ReasonGenerator,
    ) -> str | None:
        normalized_request_id = str(request_id or "").strip()
        if not normalized_request_id:
            return None
        self._cleanup_expired()
        with self._lock:
            existing = self._jobs.get(normalized_request_id)
            if existing and existing.status in {"PENDING", "PARTIAL", "COMPLETED"}:
                return normalized_request_id
            job = RecommendationReasonJob(
                request_id=normalized_request_id,
                candidates=RecommendationReasonJob._sanitize_candidates(copy.deepcopy(candidates)),
            )
            self._jobs[normalized_request_id] = job
        self._persist_job(job)
        print(
            f"[RECOMMENDATION REASON JOB][{normalized_request_id}] "
            f"submitted mode=batch candidate_count={len(job.candidates)}"
        )
        # 수정 포인트: requestId마다 daemon thread를 무제한 생성하면 추천 이유 생성 요청이 몰릴 때
        # CLOVA 대기 thread가 누적되어 ai-server 메모리/스케줄링 병목이 됩니다.
        # 설정된 worker 수만큼만 병렬 처리하고 나머지는 queue에서 순차 처리합니다.
        future = self._executor.submit(self._run_job, normalized_request_id, generator)
        with self._lock:
            self._futures[normalized_request_id] = future
        return normalized_request_id

    def submit_incremental(
        self,
        *,
        request_id: str | None,
        candidates: List[Dict[str, Any]],
        item_generator: IncrementalReasonGenerator,
        answer_builder: IncrementalAnswerBuilder,
    ) -> str | None:
        normalized_request_id = str(request_id or "").strip()
        if not normalized_request_id:
            return None
        self._cleanup_expired()
        initial_candidates = RecommendationReasonJob._sanitize_candidates(copy.deepcopy(candidates))
        with self._lock:
            existing = self._jobs.get(normalized_request_id)
            if existing and existing.status in {"PENDING", "PARTIAL", "COMPLETED"}:
                return normalized_request_id
            job = RecommendationReasonJob(
                request_id=normalized_request_id,
                candidates=initial_candidates,
                answer=answer_builder(initial_candidates),
            )
            self._jobs[normalized_request_id] = job
        self._persist_job(job)
        future = self._executor.submit(
            self._run_incremental_job,
            normalized_request_id,
            item_generator,
            answer_builder,
        )
        with self._lock:
            self._futures[normalized_request_id] = future
        return normalized_request_id

    def get(self, request_id: str) -> Dict[str, Any]:
        self._cleanup_expired()
        normalized_request_id = str(request_id or "").strip()
        redis_job = self._load_job(normalized_request_id)

        with self._lock:
            local_job = self._jobs.get(normalized_request_id)

            # 수정 포인트: polling Pod가 Redis의 초기 PENDING snapshot을 메모리에 캐시한 뒤,
            # 실제 worker Pod가 Redis에 PARTIAL/COMPLETED를 저장해도 기존 코드는 local PENDING만 계속 반환했습니다.
            # 비로그인 추천 이유가 화면에서 계속 "생성 중"으로 남는 원인이므로, Redis snapshot이 더 최신이거나
            # terminal 상태이면 local snapshot을 갱신하고 Redis 상태를 우선 반환합니다.
            if redis_job is not None:
                if local_job is None or self._should_replace_local_job(local_job, redis_job):
                    self._jobs[normalized_request_id] = copy.deepcopy(redis_job)
                    return copy.deepcopy(redis_job.as_response())

            if local_job is not None:
                return copy.deepcopy(local_job.as_response())

        return {
            "request_id": normalized_request_id,
            "status": "MISSING",
            "answer": None,
            "candidates": [],
            "error_message": "reason job is not available in this ai-server process or redis ttl store",
            "created_at": None,
            "updated_at": None,
        }

    @staticmethod
    def _should_replace_local_job(local_job: RecommendationReasonJob, redis_job: RecommendationReasonJob) -> bool:
        local_status = str(local_job.status or "").upper()
        redis_status = str(redis_job.status or "").upper()
        terminal_statuses = {"COMPLETED", "FAILED"}
        if redis_status in terminal_statuses and local_status != redis_status:
            return True
        if redis_job.updated_at > local_job.updated_at:
            return True
        if redis_status == "PARTIAL" and local_status == "PENDING":
            return True
        local_reason_count = RecommendationReasonJobStore._completed_reason_count(local_job.candidates)
        redis_reason_count = RecommendationReasonJobStore._completed_reason_count(redis_job.candidates)
        return redis_reason_count > local_reason_count

    @staticmethod
    def _completed_reason_count(candidates: List[Dict[str, Any]]) -> int:
        count = 0
        for candidate in candidates or []:
            if not isinstance(candidate, dict):
                continue
            status = str(candidate.get("recommendation_reason_status") or "").upper()
            reason = str(candidate.get("recommendation_reason") or "").strip()
            if status == "COMPLETED" and reason:
                count += 1
        return count

    def _run_job(self, request_id: str, generator: ReasonGenerator) -> None:
        print(f"[RECOMMENDATION REASON JOB][{request_id}] worker_start mode=batch")
        try:
            result = generator()
            answer = str(result.get("answer") or "").strip()
            candidates = result.get("candidates") if isinstance(result.get("candidates"), list) else []
            job_to_persist = None
            with self._lock:
                job = self._jobs.get(request_id)
                if job is None:
                    return
                job.status = "COMPLETED" if answer else "FAILED"
                job.answer = answer or None
                job.candidates = copy.deepcopy(RecommendationReasonJob._sanitize_candidates(candidates))
                job.error_message = None if answer else "empty reason generation result"
                job.updated_at = datetime.now(timezone.utc)
                job_to_persist = copy.deepcopy(job)
            self._persist_job(job_to_persist)
            print(
                f"[RECOMMENDATION REASON JOB][{request_id}] "
                f"worker_done mode=batch status={job_to_persist.status} "
                f"candidate_count={len(job_to_persist.candidates)}"
            )
        except Exception as exc:  # pragma: no cover - defensive background boundary
            job_to_persist = None
            with self._lock:
                job = self._jobs.get(request_id)
                if job is None:
                    return
                job.status = "FAILED"
                job.error_message = str(exc)
                job.updated_at = datetime.now(timezone.utc)
                job_to_persist = copy.deepcopy(job)
            self._persist_job(job_to_persist)
            print(f"[RECOMMENDATION REASON JOB][{request_id}] worker_failed mode=batch reason={exc}")

    def _run_incremental_job(
        self,
        request_id: str,
        item_generator: IncrementalReasonGenerator,
        answer_builder: IncrementalAnswerBuilder,
    ) -> None:
        try:
            with self._lock:
                job = self._jobs.get(request_id)
                if job is None:
                    return
                candidates = copy.deepcopy(job.candidates)

            if not candidates:
                job_to_persist = None
                with self._lock:
                    job = self._jobs.get(request_id)
                    if job is not None:
                        job.status = "FAILED"
                        job.error_message = "empty candidate list"
                        job.updated_at = datetime.now(timezone.utc)
                        job_to_persist = copy.deepcopy(job)
                self._persist_job(job_to_persist)
                return

            completed_count = 0
            for index, candidate in enumerate(candidates):
                try:
                    result = item_generator(index, copy.deepcopy(candidate), copy.deepcopy(candidates))
                    next_candidate = result.get("candidate") if isinstance(result, dict) else None
                    if not isinstance(next_candidate, dict):
                        next_candidate = copy.deepcopy(candidate)
                    next_candidate = RecommendationReasonJob._sanitize_candidates([next_candidate])[0]
                    if not str(next_candidate.get("recommendation_reason_status") or "").strip():
                        next_candidate["recommendation_reason_status"] = "COMPLETED"
                    candidates[index] = next_candidate
                    completed_count += 1
                except Exception as exc:  # pragma: no cover - per-candidate isolation
                    failed_candidate = copy.deepcopy(candidate)
                    failed_candidate["recommendation_reason_status"] = "FAILED"
                    failed_candidate["recommendation_reason_error_message"] = str(exc)
                    candidates[index] = RecommendationReasonJob._sanitize_candidates([failed_candidate])[0]

                answer = str(answer_builder(candidates) or "").strip()
                job_to_persist = None
                with self._lock:
                    job = self._jobs.get(request_id)
                    if job is None:
                        return
                    job.candidates = copy.deepcopy(RecommendationReasonJob._sanitize_candidates(candidates))
                    job.answer = answer or job.answer
                    job.status = "COMPLETED" if index == len(candidates) - 1 else "PARTIAL"
                    job.error_message = None
                    job.updated_at = datetime.now(timezone.utc)
                    job_to_persist = copy.deepcopy(job)
                self._persist_job(job_to_persist)

            job_to_persist = None
            with self._lock:
                job = self._jobs.get(request_id)
                if job is None:
                    return
                if completed_count <= 0:
                    job.status = "FAILED"
                    job.error_message = "all recommendation reason generation failed"
                else:
                    job.status = "COMPLETED"
                    job.error_message = None
                job.updated_at = datetime.now(timezone.utc)
                job_to_persist = copy.deepcopy(job)
            self._persist_job(job_to_persist)
        except Exception as exc:  # pragma: no cover - defensive background boundary
            job_to_persist = None
            with self._lock:
                job = self._jobs.get(request_id)
                if job is None:
                    return
                job.status = "FAILED"
                job.error_message = str(exc)
                job.updated_at = datetime.now(timezone.utc)
                job_to_persist = copy.deepcopy(job)
            self._persist_job(job_to_persist)

    def _persist_job(self, job: RecommendationReasonJob | None) -> None:
        if job is None or not job.request_id:
            return
        ttl_seconds = max(60, int(getattr(settings, "RECOMMENDATION_REASON_ASYNC_TTL_SECONDS", 900)))
        key = self._redis_key(job.request_id)
        try:
            redis_cache.set_json(key, job.as_response(), ttl_seconds)
            completed_count = self._completed_reason_count(job.candidates)
            print(
                f"[RECOMMENDATION REASON STORE][{job.request_id}] "
                f"status={job.status} completed_count={completed_count} "
                f"candidate_count={len(job.candidates)} ttl_seconds={ttl_seconds}"
            )
        except Exception as exc:  # pragma: no cover - fail-open cache boundary
            print(f"[RECOMMENDATION REASON STORE][{job.request_id}] redis_persist_failed reason={exc}")

    def _load_job(self, request_id: str) -> RecommendationReasonJob | None:
        if not request_id:
            return None
        try:
            data = redis_cache.get_json(self._redis_key(request_id))
            if not isinstance(data, dict):
                return None
            return RecommendationReasonJob.from_response(data)
        except Exception as exc:  # pragma: no cover - fail-open cache boundary
            print(f"[RECOMMENDATION REASON STORE][{request_id}] redis_load_failed reason={exc}")
            return None

    @staticmethod
    def _redis_key(request_id: str) -> str:
        return redis_cache.key("recommendation", "reason-job", request_id)

    def _cleanup_expired(self) -> None:
        ttl_seconds = max(60, int(getattr(settings, "RECOMMENDATION_REASON_ASYNC_TTL_SECONDS", 900)))
        expires_before = datetime.now(timezone.utc) - timedelta(seconds=ttl_seconds)
        with self._lock:
            expired_keys = [
                key for key, job in self._jobs.items()
                if job.updated_at < expires_before or job.created_at < expires_before
            ]
            for key in expired_keys:
                self._jobs.pop(key, None)
                self._futures.pop(key, None)


recommendation_reason_jobs = RecommendationReasonJobStore()
