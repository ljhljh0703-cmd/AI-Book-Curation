from __future__ import annotations

from time import perf_counter
from typing import Any, Dict, List, Tuple
from urllib.parse import urlsplit, urlunsplit

import requests

from app.core.config import settings
from app.services.common.redis_cache import redis_cache
from app.services.reranking.document_builder import GteDocumentBuilder
from app.services.reranking.query_builder import GteQueryBuilder
from app.services.reranking.types import RerankDocument, RerankResult


class HttpGteRerankerProvider:
    """Local PC primary → NAS k3s fallback 순서로 GTE reranker HTTP endpoint를 호출합니다."""

    def __init__(self) -> None:
        self.document_builder = GteDocumentBuilder()
        self.query_builder = GteQueryBuilder()

    def rerank(
        self,
        *,
        query: str,
        candidates: List[Dict[str, Any]],
        user_profile: Dict[str, Any] | None,
        guest: bool,
        request_id: str | None = None,
    ) -> RerankResult:
        started_at = perf_counter()
        max_documents = max(1, min(
            int(settings.GTE_RERANKER_MAX_DOCUMENTS),
            int(getattr(settings, "GTE_RERANK_TOP_K", settings.GTE_RERANKER_MAX_DOCUMENTS)),
        ))
        limited_candidates = list(candidates or [])[:max_documents]
        documents = self.document_builder.build(limited_candidates)
        rerank_query = self.query_builder.build(query=query, profile=user_profile or {}, guest=guest)
        total_doc_chars = sum(len(doc.text or "") for doc in documents)
        candidate_hash = redis_cache.digest([
            {
                "isbn": item.get("isbn") or item.get("isbn13"),
                "title": item.get("title"),
                "score": item.get("score"),
            }
            for item in limited_candidates
        ])[:32]
        profile_hash = redis_cache.digest({"guest": guest, "profile": user_profile or {}})[:32]
        cache_key = redis_cache.key(
            "gte",
            "rerank",
            redis_cache.digest(rerank_query)[:32],
            candidate_hash,
            profile_hash,
            str(max_documents),
            settings.GTE_RERANKER_MODEL_NAME,
        )
        cached = redis_cache.get_json(cache_key)
        if cached is not None:
            result = RerankResult(
                candidates=list(cached or []),
                provider="GTE_MULTILINGUAL",
                applied=True,
                fallback=False,
                fallback_reason=None,
                endpoint_role="cache",
                latency_ms=int((perf_counter() - started_at) * 1000),
                input_count=len(documents),
                output_count=len(cached or []),
                metadata={
                    "cacheHit": True,
                    "queryChars": len(rerank_query or ""),
                    "totalDocChars": total_doc_chars,
                    "maxDocChars": settings.GTE_RERANKER_MAX_DOC_CHARS,
                },
            )
            self._log_summary(request_id=request_id, result=result)
            return result

        if not documents:
            result = self._fallback(limited_candidates, started_at, "EMPTY_DOCUMENTS", len(documents), "none")
            self._log_summary(request_id=request_id, result=result, extra={"queryChars": len(rerank_query or ""), "totalDocChars": total_doc_chars})
            return result

        endpoints = [
            ("primary", settings.GTE_RERANKER_PRIMARY_URL, float(settings.GTE_RERANKER_PRIMARY_TIMEOUT_SECONDS)),
            ("fallback", settings.GTE_RERANKER_FALLBACK_URL, float(settings.GTE_RERANKER_FALLBACK_TIMEOUT_SECONDS)),
        ]
        errors: List[Dict[str, Any]] = []
        attempts: List[Dict[str, Any]] = []
        endpoint_latencies: Dict[str, int] = {"primary": 0, "fallback": 0}

        print(
            f"[GTE RERANKER START][{request_id or '-'}] "
            f"candidate_count={len(candidates or [])} input_count={len(documents)} "
            f"max_documents={max_documents} query_chars={len(rerank_query or '')} "
            f"total_doc_chars={total_doc_chars} max_doc_chars={settings.GTE_RERANKER_MAX_DOC_CHARS}"
        )

        for role, url, timeout_seconds in endpoints:
            normalized_url = str(url or "").strip()
            safe_url = self._safe_url_label(normalized_url)
            if not normalized_url:
                reason = "EMPTY_URL"
                errors.append({"role": role, "reason": reason})
                attempts.append({"role": role, "success": False, "latencyMs": 0, "reason": reason})
                print(f"[GTE RERANKER SKIP][{request_id or '-'}] role={role} reason={reason}")
                continue

            endpoint_started_at = perf_counter()
            print(
                f"[GTE RERANKER ATTEMPT][{request_id or '-'}] "
                f"role={role} url={safe_url} timeout_seconds={timeout_seconds} input_count={len(documents)}"
            )
            try:
                ranked = self._call_endpoint(
                    url=normalized_url,
                    query=rerank_query,
                    documents=documents,
                    timeout_seconds=timeout_seconds,
                    request_id=request_id,
                    endpoint_role=role,
                )
                endpoint_latency_ms = int((perf_counter() - endpoint_started_at) * 1000)
                endpoint_latencies[role] = endpoint_latency_ms
                total_latency_ms = int((perf_counter() - started_at) * 1000)
                attempts.append({"role": role, "success": True, "latencyMs": endpoint_latency_ms})
                result = RerankResult(
                    candidates=ranked,
                    provider="GTE_MULTILINGUAL",
                    applied=True,
                    fallback=role != "primary",
                    fallback_reason=None if role == "primary" else "PRIMARY_ENDPOINT_FAILED",
                    endpoint_role=role,
                    latency_ms=total_latency_ms,
                    input_count=len(documents),
                    output_count=len(ranked),
                    metadata={
                        "errorsBeforeSuccess": errors,
                        "endpointAttempts": attempts,
                        "primaryLatencyMs": endpoint_latencies.get("primary", 0),
                        "fallbackLatencyMs": endpoint_latencies.get("fallback", 0),
                        "totalLatencyMs": total_latency_ms,
                        "endpointLatencyMs": endpoint_latency_ms,
                        "queryChars": len(rerank_query or ""),
                        "totalDocChars": total_doc_chars,
                        "maxDocChars": settings.GTE_RERANKER_MAX_DOC_CHARS,
                    },
                )
                redis_cache.set_json(cache_key, ranked, int(getattr(settings, "GTE_RERANK_CACHE_TTL_SECONDS", 600)))
                self._log_summary(request_id=request_id, result=result)
                return result
            except Exception as exc:
                endpoint_latency_ms = int((perf_counter() - endpoint_started_at) * 1000)
                endpoint_latencies[role] = endpoint_latency_ms
                reason = f"{exc.__class__.__name__}: {str(exc)[:180]}"
                print(
                    f"[GTE RERANKER FAILURE][{request_id or '-'}] "
                    f"role={role} latency_ms={endpoint_latency_ms} reason={reason}"
                )
                errors.append({"role": role, "reason": reason, "latencyMs": endpoint_latency_ms})
                attempts.append({"role": role, "success": False, "latencyMs": endpoint_latency_ms, "reason": reason})

        result = self._fallback(
            candidates=limited_candidates,
            started_at=started_at,
            reason="ALL_ENDPOINTS_FAILED",
            input_count=len(documents),
            endpoint_role="none",
            extra={
                "errors": errors,
                "endpointAttempts": attempts,
                "primaryLatencyMs": endpoint_latencies.get("primary", 0),
                "fallbackLatencyMs": endpoint_latencies.get("fallback", 0),
                "queryChars": len(rerank_query or ""),
                "totalDocChars": total_doc_chars,
                "maxDocChars": settings.GTE_RERANKER_MAX_DOC_CHARS,
            },
        )
        self._log_summary(request_id=request_id, result=result)
        return result

    def _call_endpoint(
        self,
        *,
        url: str,
        query: str,
        documents: List[RerankDocument],
        timeout_seconds: float,
        request_id: str | None,
        endpoint_role: str,
    ) -> List[Dict[str, Any]]:
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        api_key = str(settings.GTE_RERANKER_API_KEY or "").strip()
        header_name = str(settings.GTE_RERANKER_HEADER_NAME or "X-GTE-Reranker-Key").strip()
        if api_key:
            headers[header_name] = api_key
        payload = {
            "query": query,
            "texts": [doc.text for doc in documents],
            "documents": [doc.text for doc in documents],
            "return_documents": False,
        }
        response = requests.post(url, json=payload, headers=headers, timeout=timeout_seconds)
        print(
            f"[GTE RERANKER HTTP][{request_id or '-'}] "
            f"role={endpoint_role} status_code={response.status_code} response_bytes={len(response.content or b'')}"
        )
        response.raise_for_status()
        data = response.json()
        scored = self._parse_scores(data, len(documents))
        if not scored:
            raise RuntimeError("EMPTY_RERANK_RESPONSE")
        ranked_docs: List[Tuple[int, float]] = sorted(scored, key=lambda row: row[1], reverse=True)
        ranked_candidates: List[Dict[str, Any]] = []
        for index, score in ranked_docs:
            if index < 0 or index >= len(documents):
                continue
            item = dict(documents[index].candidate)
            item["rerankerScore"] = round(float(score), 6)
            item["score_detail"] = {
                **dict(item.get("score_detail") or {}),
                "gte_reranker_score": round(float(score), 6),
                "gte_reranker_endpoint_role": endpoint_role,
            }
            ranked_candidates.append(item)
        if not ranked_candidates:
            raise RuntimeError("NO_VALID_RERANK_INDEX")
        return ranked_candidates

    def _parse_scores(self, data: Any, expected_count: int) -> List[Tuple[int, float]]:
        results = data
        if isinstance(data, dict):
            results = data.get("results") or data.get("data") or data.get("rankings") or data.get("scores") or []
        if isinstance(results, list) and results and isinstance(results[0], (int, float)):
            return [(index, float(score)) for index, score in enumerate(results[:expected_count])]
        parsed: List[Tuple[int, float]] = []
        if isinstance(results, list):
            for fallback_index, row in enumerate(results):
                if not isinstance(row, dict):
                    continue
                index = row.get("index", row.get("document_index", row.get("corpus_id", fallback_index)))
                score = row.get("score", row.get("relevance_score", row.get("rerank_score")))
                try:
                    parsed.append((int(index), float(score)))
                except (TypeError, ValueError):
                    continue
        return parsed

    def _fallback(
        self,
        candidates: List[Dict[str, Any]],
        started_at: float,
        reason: str,
        input_count: int,
        endpoint_role: str | None,
        extra: Dict[str, Any] | None = None,
    ) -> RerankResult:
        latency_ms = int((perf_counter() - started_at) * 1000)
        metadata = {**dict(extra or {}), "totalLatencyMs": latency_ms}
        return RerankResult(
            candidates=list(candidates or []),
            provider="GTE_MULTILINGUAL",
            applied=False,
            fallback=True,
            fallback_reason=reason,
            endpoint_role=endpoint_role,
            latency_ms=latency_ms,
            input_count=input_count,
            output_count=len(candidates or []),
            metadata=metadata,
        )

    @staticmethod
    def _safe_url_label(url: str) -> str:
        if not url:
            return ""
        try:
            parts = urlsplit(url)
            return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
        except Exception:
            return "<invalid-url>"

    @staticmethod
    def _log_summary(*, request_id: str | None, result: RerankResult, extra: Dict[str, Any] | None = None) -> None:
        metadata = {**dict(result.metadata or {}), **dict(extra or {})}
        print(
            f"[GTE RERANKER SUMMARY][{request_id or '-'}] "
            f"provider={result.provider} applied={result.applied} fallback={result.fallback} "
            f"endpoint_role={result.endpoint_role or '-'} reason={result.fallback_reason or '-'} "
            f"latency_ms={result.latency_ms} primary_latency_ms={int(metadata.get('primaryLatencyMs') or 0)} "
            f"fallback_latency_ms={int(metadata.get('fallbackLatencyMs') or 0)} "
            f"input_count={result.input_count} output_count={result.output_count} "
            f"query_chars={metadata.get('queryChars', '-')} total_doc_chars={metadata.get('totalDocChars', '-')}"
        )
