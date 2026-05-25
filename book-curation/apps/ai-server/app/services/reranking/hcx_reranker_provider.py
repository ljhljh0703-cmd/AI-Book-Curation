from __future__ import annotations

import re
from time import perf_counter
from typing import Any, Dict, List, Tuple
from urllib.parse import urlsplit, urlunsplit

import requests

from app.core.config import settings
from app.services.common.redis_cache import redis_cache
from app.services.reranking.document_builder import GteDocumentBuilder
from app.services.reranking.query_builder import GteQueryBuilder
from app.services.reranking.types import RerankDocument, RerankResult


class HcxRerankerProvider:
    """CLOVA Studio Reranker API provider.

    CLOVA Studio Reranker는 query와 documents를 받아 관련 문서를 선택하고
    응답 본문에 <doc1>, <doc2> 같은 source tag를 남기는 RAG 도구입니다.
    추천 pipeline에서는 이 source tag의 최초 등장 순서를 relevance order로 해석하고,
    tag가 없는 응답이면 fail-open으로 기존 후보 순서를 유지합니다.
    """

    _DOC_TAG_PATTERN = re.compile(r"<\s*/?\s*doc\s*([0-9]+)\s*>", re.IGNORECASE)
    _DOC_COMPACT_TAG_PATTERN = re.compile(r"<\s*/?\s*doc([0-9]+)\s*>", re.IGNORECASE)

    def __init__(self) -> None:
        self.document_builder = GteDocumentBuilder(max_chars=settings.HCX_RERANKER_MAX_DOC_CHARS)
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
        max_documents = max(1, min(int(settings.HCX_RERANKER_MAX_DOCUMENTS), len(candidates or []) or 1))
        limited_candidates = list(candidates or [])[:max_documents]
        documents = self.document_builder.build(limited_candidates)
        rerank_query = self.query_builder.build(query=query, profile=user_profile or {}, guest=guest)
        total_doc_chars = sum(len(doc.text or "") for doc in documents)
        api_key = self._api_key()
        url = str(settings.HCX_RERANKER_URL or "").strip()

        cache_key = redis_cache.key(
            "hcx",
            "rerank",
            redis_cache.digest(rerank_query)[:32],
            redis_cache.digest([
                {
                    "isbn": item.get("isbn") or item.get("isbn13"),
                    "title": item.get("title"),
                    "score": item.get("score"),
                }
                for item in limited_candidates
            ])[:32],
            redis_cache.digest({"guest": guest, "profile": user_profile or {}})[:32],
            str(max_documents),
        )
        cached = redis_cache.get_json(cache_key)
        if cached is not None:
            result = RerankResult(
                candidates=list(cached or []),
                provider="HCX_RERANKER",
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
                    "maxDocChars": settings.HCX_RERANKER_MAX_DOC_CHARS,
                },
            )
            self._log_summary(request_id=request_id, result=result)
            return result

        if not documents:
            result = self._fallback(limited_candidates, started_at, "EMPTY_DOCUMENTS", len(documents))
            self._log_summary(request_id=request_id, result=result)
            return result
        if not url:
            result = self._fallback(limited_candidates, started_at, "EMPTY_HCX_RERANKER_URL", len(documents))
            self._log_summary(request_id=request_id, result=result)
            return result
        if not api_key:
            result = self._fallback(limited_candidates, started_at, "EMPTY_HCX_RERANKER_API_KEY", len(documents))
            self._log_summary(request_id=request_id, result=result)
            return result

        print(
            f"[HCX RERANKER START][{request_id or '-'}] "
            f"candidate_count={len(candidates or [])} input_count={len(documents)} "
            f"max_documents={max_documents} query_chars={len(rerank_query or '')} "
            f"total_doc_chars={total_doc_chars} max_doc_chars={settings.HCX_RERANKER_MAX_DOC_CHARS} "
            f"url={self._safe_url_label(url)}"
        )
        try:
            ranked, response_metadata = self._call_endpoint(
                url=url,
                api_key=api_key,
                query=rerank_query,
                documents=documents,
                timeout_seconds=float(settings.HCX_RERANKER_TIMEOUT_SECONDS),
                request_id=request_id,
            )
            latency_ms = int((perf_counter() - started_at) * 1000)
            result = RerankResult(
                candidates=ranked,
                provider="HCX_RERANKER",
                applied=True,
                fallback=False,
                fallback_reason=None,
                endpoint_role="clova-studio",
                latency_ms=latency_ms,
                input_count=len(documents),
                output_count=len(ranked),
                metadata={
                    "totalLatencyMs": latency_ms,
                    "queryChars": len(rerank_query or ""),
                    "totalDocChars": total_doc_chars,
                    "maxDocChars": settings.HCX_RERANKER_MAX_DOC_CHARS,
                    **response_metadata,
                },
            )
            redis_cache.set_json(cache_key, ranked, int(settings.HCX_RERANK_CACHE_TTL_SECONDS))
            self._log_summary(request_id=request_id, result=result)
            return result
        except Exception as exc:
            reason = f"{exc.__class__.__name__}: {str(exc)[:180]}"
            print(f"[HCX RERANKER FAILURE][{request_id or '-'}] reason={reason}")
            result = self._fallback(limited_candidates, started_at, reason, len(documents))
            self._log_summary(request_id=request_id, result=result)
            return result

    def _call_endpoint(
        self,
        *,
        url: str,
        api_key: str,
        query: str,
        documents: List[RerankDocument],
        timeout_seconds: float,
        request_id: str | None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        payload_documents = [
            {"id": str(position + 1), "doc": doc.text}
            for position, doc in enumerate(documents)
        ]
        payload = {
            "documents": payload_documents,
            "query": query,
            "maxTokens": max(1024, min(int(settings.HCX_RERANKER_MAX_TOKENS), 4095)),
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        response = requests.post(url, json=payload, headers=headers, timeout=timeout_seconds)
        print(
            f"[HCX RERANKER HTTP][{request_id or '-'}] "
            f"status_code={response.status_code} response_bytes={len(response.content or b'')}"
        )
        response.raise_for_status()
        data = response.json()
        result_text = self._extract_result_text(data)
        cited_positions = self._extract_cited_positions(result_text, len(documents))
        if not cited_positions:
            raise RuntimeError("NO_HCX_DOC_CITATIONS")

        ranked_positions = [position for position in cited_positions]
        cited_set = set(ranked_positions)
        ranked_positions.extend(position for position in range(len(documents)) if position not in cited_set)

        ranked_candidates: List[Dict[str, Any]] = []
        total = max(1, len(ranked_positions))
        for rank_index, position in enumerate(ranked_positions):
            if position < 0 or position >= len(documents):
                continue
            score = max(0.0, 1.0 - (rank_index / total))
            item = dict(documents[position].candidate)
            item["rerankerScore"] = round(float(score), 6)
            item["score_detail"] = {
                **dict(item.get("score_detail") or {}),
                "hcx_reranker_score": round(float(score), 6),
                "hcx_reranker_rank": rank_index + 1,
                "hcx_reranker_cited": position in cited_set,
            }
            ranked_candidates.append(item)
        if not ranked_candidates:
            raise RuntimeError("NO_VALID_HCX_RERANK_INDEX")
        return ranked_candidates, {
            "hcxResultChars": len(result_text or ""),
            "hcxCitedDocumentIds": [str(position + 1) for position in cited_positions],
            "hcxCitedCount": len(cited_positions),
        }

    @staticmethod
    def _extract_result_text(data: Any) -> str:
        if isinstance(data, dict):
            result = data.get("result")
            if isinstance(result, dict):
                for key in ["result", "text", "content", "answer"]:
                    value = result.get(key)
                    if isinstance(value, str) and value.strip():
                        return value
            for key in ["result", "text", "content", "answer"]:
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return value
        return str(data or "")

    @classmethod
    def _extract_cited_positions(cls, text: str, document_count: int) -> List[int]:
        seen: set[int] = set()
        positions: List[int] = []
        for pattern in [cls._DOC_TAG_PATTERN, cls._DOC_COMPACT_TAG_PATTERN]:
            for match in pattern.finditer(text or ""):
                try:
                    doc_id = int(match.group(1))
                except (TypeError, ValueError):
                    continue
                position = doc_id - 1
                if position < 0 or position >= document_count or position in seen:
                    continue
                seen.add(position)
                positions.append(position)
        return positions

    @staticmethod
    def _api_key() -> str:
        return str(settings.HCX_RERANKER_API_KEY or settings.CLOVA_API_KEY or "").strip()

    def _fallback(
        self,
        candidates: List[Dict[str, Any]],
        started_at: float,
        reason: str,
        input_count: int,
    ) -> RerankResult:
        latency_ms = int((perf_counter() - started_at) * 1000)
        return RerankResult(
            candidates=list(candidates or []),
            provider="HCX_RERANKER",
            applied=False,
            fallback=True,
            fallback_reason=reason,
            endpoint_role="none",
            latency_ms=latency_ms,
            input_count=input_count,
            output_count=len(candidates or []),
            metadata={"totalLatencyMs": latency_ms},
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
    def _log_summary(*, request_id: str | None, result: RerankResult) -> None:
        metadata = dict(result.metadata or {})
        print(
            f"[HCX RERANKER SUMMARY][{request_id or '-'}] "
            f"provider={result.provider} applied={result.applied} fallback={result.fallback} "
            f"reason={result.fallback_reason or '-'} latency_ms={result.latency_ms} "
            f"input_count={result.input_count} output_count={result.output_count} "
            f"cited_count={metadata.get('hcxCitedCount', '-') } query_chars={metadata.get('queryChars', '-')}"
        )
