import re
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter
from typing import Any, Dict, List, Tuple

from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models
from qdrant_client.http.models import FieldCondition, Filter, MatchText, MatchValue, PayloadSchemaType

from app.core.config import settings
from app.services.common.redis_cache import redis_cache
from app.services.clients.kure_client import KureClient
from app.services.intent.query_intent_parser import QueryIntent, QueryIntentParser
from app.services.common.source_format_policy import SourceFormatPolicy
from app.services.retrieval.sparse_bm25 import SparseTextVectorizer, rrf_fuse


class BookKureQdrantSearcher:
    """
    KURE-v1 임베딩으로 만든 Qdrant 컬렉션 검색 전용 클래스입니다.

    기존 BookQdrantSearcher / qdrant_search.py 는 수정하지 않습니다.
    기존 books 컬렉션은 CLOVA 임베딩용으로 유지하고,
    이 클래스는 books_kure 컬렉션만 조회합니다.

    CLOVA BookQdrantSearcher 구조와 동일한 public interface를 제공합니다.
    - search(query, limit)
    - is_precise_lookup_query(query)
    - author/title/isbn 명시 질의는 payload 검색만 수행
    - 일반 추천 질의는 KURE /embed 호출 후 books_kure vector search 수행
    """

    DEFAULT_COLLECTION_NAME = "books_kure"
    _payload_indexes_ensured = False
    _payload_indexes: Tuple[Tuple[str, PayloadSchemaType], ...] = (
        ("isbn", PayloadSchemaType.KEYWORD),
        ("title", PayloadSchemaType.TEXT),
        ("author", PayloadSchemaType.TEXT),
        ("categories", PayloadSchemaType.KEYWORD),
        ("cate_depth1", PayloadSchemaType.KEYWORD),
        ("kcid", PayloadSchemaType.KEYWORD),
        ("format", PayloadSchemaType.TEXT),
        ("book_format", PayloadSchemaType.TEXT),
        ("media_type", PayloadSchemaType.TEXT),
        ("content_format", PayloadSchemaType.TEXT),
        ("is_audio_book", getattr(PayloadSchemaType, "BOOL", PayloadSchemaType.KEYWORD)),
    )

    def __init__(
        self,
        collection_name: str | None = None,
        *,
        hybrid_enabled: bool = False,
        fallback_collection_name: str | None = None,
    ) -> None:
        self.qdrant_url = getattr(settings, "QDRANT_URL", "http://qdrant:6333")
        self.qdrant_api_key = getattr(settings, "QDRANT_API_KEY", "")

        default_collection_name = getattr(
            settings,
            "QDRANT_KURE_COLLECTION",
            getattr(settings, "KURE_QDRANT_COLLECTION", self.DEFAULT_COLLECTION_NAME),
        )
        self.collection_name = collection_name or default_collection_name
        self.fallback_collection_name = fallback_collection_name or default_collection_name
        self.hybrid_enabled = bool(hybrid_enabled)
        self.dense_vector_name = getattr(settings, "QDRANT_HYBRID_DENSE_VECTOR_NAME", "dense")
        self.sparse_vector_name = getattr(settings, "QDRANT_HYBRID_SPARSE_VECTOR_NAME", "bm25_text")
        self.sparse_vectorizer = SparseTextVectorizer()
        self.last_retrieval_metadata: Dict[str, Any] = {
            "requested_strategy": "dense_lookup",
            "used_strategy": "dense_lookup",
            "collection": self.collection_name,
            "fallback": False,
        }

        if self.qdrant_api_key:
            self.client = QdrantClient(
                url=self.qdrant_url,
                api_key=self.qdrant_api_key,
                timeout=float(getattr(settings, "QDRANT_SEARCH_TIMEOUT_SECONDS", 5.0)),
            )
        else:
            self.client = QdrantClient(
                url=self.qdrant_url,
                timeout=float(getattr(settings, "QDRANT_SEARCH_TIMEOUT_SECONDS", 5.0)),
            )

        self.embedder = KureClient()
        self.query_parser = QueryIntentParser()
        if bool(settings.QDRANT_ENSURE_PAYLOAD_INDEXES):
            self._ensure_payload_indexes_once()

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        query = str(query or "").strip()
        if not query:
            print(f"[KURE VECTOR SEARCH] skipped empty query")
            return []
        search_mode = self._detect_search_mode(query)

        if search_mode in {"author", "title", "isbn"}:
            keywords = self._extract_keywords(query)
            if not keywords:
                print(
                    f"[KURE PRECISE SEARCH SKIPPED] "
                    f"collection={self.collection_name}, "
                    f"mode={search_mode}, "
                    f"query={query!r}, "
                    "reason=no keyword"
                )
                return []

            keyword_results = self._search_by_keyword(
                keywords=keywords,
                query=query,
                limit=max(limit, 100 if search_mode in {"author", "title"} else limit),
            )

            if keyword_results:
                print(
                    f"[KURE PRECISE SEARCH HIT] "
                    f"collection={self.collection_name}, "
                    f"mode={search_mode}, "
                    f"keywords={keywords}, "
                    f"count={len(keyword_results)}"
                )
                return keyword_results

            print(
                f"[KURE PRECISE SEARCH MISS] "
                f"collection={self.collection_name}, "
                f"mode={search_mode}, "
                f"keywords={keywords} "
                "→ no vector fallback"
            )
            return []

        print(f"[KURE VECTOR SEARCH] collection={self.collection_name}, query={query!r}, limit={limit}")
        return self._search_by_vector(query=query, limit=limit)

    def search_by_intent(self, query_intent: QueryIntent, limit: int = 5) -> List[Dict[str, Any]]:
        """Use the already structured query intent instead of reparsing natural language."""
        search_mode = self._detect_search_mode_from_intent(query_intent)
        query = (query_intent.retrieval_query or query_intent.raw_query or "").strip()

        if search_mode in {"author", "title", "isbn"}:
            keywords = self._keywords_from_intent(query_intent)
            if not keywords:
                print(f"[KURE PRECISE SEARCH SKIPPED] mode={search_mode}, reason=no structured keyword")
                return []

            keyword_results = self._search_by_keyword(
                keywords=keywords,
                query=query,
                limit=max(limit, 100 if search_mode in {"author", "title"} else limit),
                search_mode_override=search_mode,
            )
            if keyword_results:
                print(f"[KURE PRECISE SEARCH HIT] mode={search_mode}, count={len(keyword_results)}")
                return keyword_results

            print(f"[KURE PRECISE SEARCH MISS] mode={search_mode} → no vector fallback")
            return []

        if not query:
            print(f"[KURE VECTOR SEARCH] skipped empty structured query")
            return []
        print(f"[KURE VECTOR SEARCH] mode={search_mode}, query={query!r}, limit={limit}")
        return self._search_by_vector(query=query, limit=limit)

    def search_dense_bm25_rrf(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        # 수정 포인트: 평가관리에서 hybrid variant를 직접 호출할 수 있는 명시 API입니다.
        query = str(query or "").strip()
        if not query:
            print(f"[KURE QDRANT HYBRID SEARCH] skipped empty query")
            return []
        return self._search_by_vector(query=query, limit=limit)

    def search_vector_only(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        query = str(query or "").strip()
        if not query:
            print(f"[KURE VECTOR SEARCH][vector_only] skipped empty query")
            return []
        if self.hybrid_enabled:
            # 수정 포인트: 평가관리 dense variant는 BM25 ON 비교 중에도 기존 운영 dense collection 기준으로 측정합니다.
            return self._search_dense_vector_on_collection(
                query=query,
                limit=limit,
                query_filter=None,
                collection_name=self.fallback_collection_name,
                match_type="kure_vector",
                cache_namespace="kure_dense_only",
            )
        print(f"[KURE VECTOR SEARCH][vector_only] collection={self.collection_name}, query={query!r}, limit={limit}")
        return self._search_by_vector(query=query, limit=limit)

    def search_listening_mode(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Return only candidates with source-backed audiobook format evidence.

        The caller has already received structured LISTENING_FRIENDLY intent. This
        method therefore treats audiobook/source-format evidence as a hard retrieval
        requirement and never fills the result set with ordinary paper-book candidates.
        """
        safe_limit = max(1, int(limit or 5))
        query = str(query or "").strip()
        query_filter = self._audio_payload_filter()

        vector_candidates: List[Dict[str, Any]] = []
        if query:
            vector_candidates = self._retain_audiobook_payloads(
                self._search_by_vector(
                    query=query,
                    limit=max(safe_limit * 3, safe_limit),
                    query_filter=query_filter,
                    match_type="listening_format_vector",
                    cache_namespace="listening",
                )
            )

        payload_candidates = self._scroll_audiobook_payloads(limit=max(safe_limit * 3, safe_limit))
        merged = self._merge_formatted_candidates(vector_candidates, payload_candidates)[:safe_limit]
        print(
            f"[LISTENING FORMAT SEARCH] collection={self.collection_name} "
            f"vector={len(vector_candidates)} payload={len(payload_candidates)} final={len(merged)}"
        )
        return merged

    def search_general(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Return a broad deterministic candidate pool without adding language keywords.

        This is used only when the structured intent says the request is broad and
        vector search returned too few candidates. The low default score prevents
        these fallback candidates from outranking vector candidates.
        """
        try:
            points, _ = self.client.scroll(
                collection_name=self.collection_name,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
        except Exception as exc:
            print(f"[KURE GENERAL SEARCH FALLBACK FAILED] error={exc}")
            return []
        return self._format_points(points, match_type="general_payload", default_score=0.01)

    def is_precise_lookup_query(self, query: str) -> bool:
        """저자/제목/ISBN처럼 명확한 payload 검색 질의인지 확인합니다."""
        return self._detect_search_mode(query) in {"author", "title", "isbn"}

    def _ensure_payload_indexes_once(self) -> None:
        if BookKureQdrantSearcher._payload_indexes_ensured:
            return

        BookKureQdrantSearcher._payload_indexes_ensured = True
        try:
            if not self.client.collection_exists(self.collection_name):
                print(f"[KURE QDRANT PAYLOAD INDEX SKIPPED] collection not found: {self.collection_name}")
                return
        except Exception as exc:
            print(f"[KURE QDRANT PAYLOAD INDEX CHECK SKIPPED] error={exc}")
            return

        for field_name, schema in self._payload_indexes:
            try:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field_name,
                    field_schema=schema,
                    wait=False,
                )
                print(f"[KURE QDRANT PAYLOAD INDEX ENSURED] field={field_name}, schema={schema}")
            except Exception as exc:
                # 이미 존재하는 index, Qdrant 버전 차이, 권한 문제는 검색 자체를 막지 않습니다.
                print(f"[KURE QDRANT PAYLOAD INDEX SKIPPED] field={field_name}, reason={exc}")

    def _search_by_vector(
        self,
        query: str,
        limit: int = 5,
        *,
        query_filter: Filter | None = None,
        match_type: str = "vector",
        cache_namespace: str = "search",
    ) -> List[Dict[str, Any]]:
        query = str(query or "").strip()
        if not query:
            print("[KURE QDRANT VECTOR SEARCH SKIPPED] reason=empty_query")
            return []
        if self.hybrid_enabled:
            # 수정 포인트: BM25 ON 요청에서만 KURE hybrid collection의 dense/sparse 결과를 내부 RRF로 결합합니다.
            return self._search_by_hybrid_vector(
                query=query,
                limit=limit,
                query_filter=query_filter,
                match_type=match_type,
                cache_namespace=cache_namespace,
            )

        configured_limit = int(getattr(settings, "QDRANT_SEARCH_LIMIT", limit) or limit)
        safe_limit = max(1, min(int(limit or configured_limit), configured_limit))
        cache_key = redis_cache.key(
            "qdrant",
            cache_namespace,
            self.collection_name,
            redis_cache.digest(query)[:32],
            str(safe_limit),
        )
        if bool(getattr(settings, "QDRANT_CACHE_ENABLED", True)):
            cached = redis_cache.get_json(cache_key)
            if cached is not None:
                self._set_retrieval_metadata(
                    requested_strategy="dense_lookup",
                    used_strategy="dense_lookup",
                    fallback=False,
                    result_count=len(cached or []),
                    cache_hit=True,
                )
                print(
                    f"[KURE QDRANT SEARCH TIMING] collection={self.collection_name} cache_hit=true "
                    f"embedding_ms=0 qdrant_search_ms=0 result_count={len(cached or [])} limit={safe_limit}"
                )
                return list(cached or [])

        embedding_started_at = perf_counter()
        query_vector = self.embedder.embedding(query)
        embedding_ms = int((perf_counter() - embedding_started_at) * 1000)

        if query_vector is None:
            print(f"[KURE QDRANT SEARCH FALLBACK] embedding failed → return empty list embedding_ms={embedding_ms}")
            return []

        qdrant_started_at = perf_counter()
        try:
            response = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                query_filter=query_filter,
                limit=safe_limit,
                with_payload=True,
            )
        except Exception as e:
            qdrant_ms = int((perf_counter() - qdrant_started_at) * 1000)
            print(f"[KURE QDRANT VECTOR SEARCH ERROR] embedding_ms={embedding_ms} qdrant_search_ms={qdrant_ms} error={e}")
            return []

        qdrant_ms = int((perf_counter() - qdrant_started_at) * 1000)
        formatted = self._format_points(response.points, match_type="kure_vector")
        self._set_retrieval_metadata(
            requested_strategy="dense_lookup",
            used_strategy="dense_lookup",
            fallback=False,
            result_count=len(formatted),
        )
        print(
            f"[KURE QDRANT SEARCH TIMING] collection={self.collection_name} cache_hit=false "
            f"embedding_ms={embedding_ms} qdrant_search_ms={qdrant_ms} result_count={len(formatted)} limit={safe_limit}"
        )
        redis_cache.set_json(cache_key, formatted, int(getattr(settings, "QDRANT_SEARCH_CACHE_TTL_SECONDS", 600)))
        return formatted

    def _search_by_hybrid_vector(
        self,
        query: str,
        limit: int = 5,
        *,
        query_filter: Filter | None = None,
        match_type: str = "vector",
        cache_namespace: str = "search",
    ) -> List[Dict[str, Any]]:
        configured_limit = int(getattr(settings, "QDRANT_SEARCH_LIMIT", limit) or limit)
        safe_limit = max(1, min(int(limit or configured_limit), configured_limit))
        hash_method = str(getattr(settings, "QDRANT_BM25_HASH_METHOD", "")).strip().lower()
        rrf_k = float(getattr(settings, "QDRANT_RRF_K", 60.0))
        cache_key = redis_cache.key(
            "qdrant",
            cache_namespace,
            "kure_dense_bm25_rrf",
            self.collection_name,
            self.dense_vector_name,
            self.sparse_vector_name,
            hash_method,
            str(int(getattr(settings, "QDRANT_BM25_HASH_MOD", 2_000_000_000))),
            str(rrf_k),
            redis_cache.digest(query)[:32],
            str(safe_limit),
        )
        if bool(getattr(settings, "QDRANT_CACHE_ENABLED", True)):
            cached = redis_cache.get_json(cache_key)
            if cached is not None:
                self._set_retrieval_metadata(
                    requested_strategy="dense_bm25_rrf",
                    used_strategy="dense_bm25_rrf",
                    fallback=False,
                    result_count=len(cached or []),
                    cache_hit=True,
                    payload_hydrated=True,
                )
                print(
                    f"[KURE QDRANT HYBRID SEARCH TIMING] collection={self.collection_name} cache_hit=true "
                    f"strategy=dense_bm25_rrf fallback=false payload_hydrated=true "
                    f"result_count={len(cached or [])} limit={safe_limit}"
                )
                return list(cached or [])

        embedding_started_at = perf_counter()
        query_vector = self.embedder.embedding(query)
        embedding_ms = int((perf_counter() - embedding_started_at) * 1000)
        if query_vector is None:
            return self._fallback_dense_lookup(query, safe_limit, query_filter, "embedding_failed")

        sparse_vector = self.sparse_vectorizer.vector(query)
        if not sparse_vector.get("indices"):
            print(
                f"[KURE QDRANT HYBRID SPARSE SKIPPED] collection={self.collection_name} "
                "reason=empty_sparse_vector used_strategy=dense"
            )
            return self._search_named_dense_vector(
                query_vector=query_vector,
                query=query,
                safe_limit=safe_limit,
                query_filter=query_filter,
                embedding_ms=embedding_ms,
                match_type=match_type,
            )

        try:
            dense_response, dense_ms, sparse_response, sparse_ms, parallel_mode = self._run_hybrid_search_requests(
                query_vector=query_vector,
                sparse_vector=sparse_vector,
                query_filter=query_filter,
                safe_limit=safe_limit,
            )
        except Exception as exc:
            return self._fallback_dense_lookup(query, safe_limit, query_filter, str(exc))

        # 수정 포인트: RRF에는 point id와 score만 필요합니다. dense/sparse 검색 단계에서 full payload를 두 번 받지 않고,
        # fusion 이후 살아남은 후보만 retrieve로 hydrate해 추천 품질은 유지하면서 Qdrant payload I/O를 줄입니다.
        dense_candidates = self._format_points(dense_response, match_type="kure_dense")
        sparse_candidates = self._format_points(sparse_response, match_type="kure_bm25_text")
        fused = rrf_fuse(
            [dense_candidates, sparse_candidates],
            ["dense", "bm25"],
            limit=safe_limit,
            rrf_k=rrf_k,
        )
        for item in fused:
            item["match_type"] = "kure_dense_bm25_rrf" if match_type == "vector" else f"{match_type}_kure_dense_bm25_rrf"

        try:
            hydrate_started_at = perf_counter()
            fused = self._hydrate_fused_candidates(fused, match_type="kure_dense_bm25_rrf")
            hydrate_ms = int((perf_counter() - hydrate_started_at) * 1000)
        except Exception as exc:
            return self._fallback_dense_lookup(query, safe_limit, query_filter, f"payload_hydration_failed:{exc}")

        self._set_retrieval_metadata(
            requested_strategy="dense_bm25_rrf",
            used_strategy="dense_bm25_rrf",
            fallback=False,
            result_count=len(fused),
            dense_count=len(dense_candidates),
            sparse_count=len(sparse_candidates),
            parallel=parallel_mode,
            payload_hydrated=True,
            payload_hydrate_ms=hydrate_ms,
        )
        print(
            f"[KURE QDRANT HYBRID SEARCH TIMING] collection={self.collection_name} cache_hit=false "
            f"strategy=dense_bm25_rrf fallback=false parallel={parallel_mode} payload_hydrated=true "
            f"embedding_ms={embedding_ms} dense_search_ms={dense_ms} sparse_search_ms={sparse_ms} "
            f"payload_hydrate_ms={hydrate_ms} dense_count={len(dense_candidates)} sparse_count={len(sparse_candidates)} "
            f"result_count={len(fused)} limit={safe_limit}"
        )
        redis_cache.set_json(cache_key, fused, int(getattr(settings, "QDRANT_SEARCH_CACHE_TTL_SECONDS", 600)))
        return fused

    def _run_hybrid_search_requests(
        self,
        *,
        query_vector: List[float],
        sparse_vector: Dict[str, Any],
        query_filter: Filter | None,
        safe_limit: int,
    ) -> tuple[Any, int, Any, int, bool]:
        def run_dense() -> tuple[Any, int]:
            started_at = perf_counter()
            response = self.client.search(
                collection_name=self.collection_name,
                query_vector=self._named_dense_vector(query_vector),
                query_filter=query_filter,
                limit=safe_limit,
                with_payload=False,
                with_vectors=False,
            )
            return response, int((perf_counter() - started_at) * 1000)

        def run_sparse() -> tuple[Any, int]:
            started_at = perf_counter()
            response = self.client.search(
                collection_name=self.collection_name,
                query_vector=self._named_sparse_vector(sparse_vector),
                query_filter=query_filter,
                limit=safe_limit,
                with_payload=False,
                with_vectors=False,
            )
            return response, int((perf_counter() - started_at) * 1000)

        if bool(getattr(settings, "QDRANT_HYBRID_PARALLEL_SEARCH_ENABLED", True)):
            with ThreadPoolExecutor(max_workers=2, thread_name_prefix="qdrant-kure-hybrid") as executor:
                dense_future = executor.submit(run_dense)
                sparse_future = executor.submit(run_sparse)
                dense_response, dense_ms = dense_future.result()
                sparse_response, sparse_ms = sparse_future.result()
            return dense_response, dense_ms, sparse_response, sparse_ms, True

        dense_response, dense_ms = run_dense()
        sparse_response, sparse_ms = run_sparse()
        return dense_response, dense_ms, sparse_response, sparse_ms, False

    def _hydrate_fused_candidates(self, candidates: List[Dict[str, Any]], *, match_type: str) -> List[Dict[str, Any]]:
        if not candidates:
            return []
        point_ids = [self._coerce_qdrant_point_id(item.get("point_id") or item.get("qdrant_id")) for item in candidates]
        point_ids = [point_id for point_id in point_ids if point_id is not None]
        if not point_ids:
            raise ValueError("missing_point_ids")

        records = self.client.retrieve(
            collection_name=self.collection_name,
            ids=point_ids,
            with_payload=True,
            with_vectors=False,
        )
        formatted_rows = self._format_points(records, match_type=match_type)
        formatted_by_id = {str(row.get("point_id") or row.get("qdrant_id") or ""): row for row in formatted_rows}
        hydrated: List[Dict[str, Any]] = []
        missing_ids: List[str] = []
        for item in candidates:
            point_id = str(item.get("point_id") or item.get("qdrant_id") or "")
            row = formatted_by_id.get(point_id)
            if row is None:
                missing_ids.append(point_id)
                continue
            merged = dict(row)
            # 수정 포인트: payload hydrate 후에도 RRF 점수/출처를 그대로 보존해야 hybrid ranking 품질이 바뀌지 않습니다.
            for key in ("score", "rrf_score", "retrieval_sources", "score_detail"):
                if key in item:
                    merged[key] = item[key]
            merged["match_type"] = item.get("match_type") or row.get("match_type") or match_type
            hydrated.append(merged)

        if missing_ids:
            raise ValueError(f"missing_hydrated_payloads:{','.join(missing_ids[:5])}")
        return hydrated

    @staticmethod
    def _coerce_qdrant_point_id(value: Any) -> Any:
        if value in (None, ""):
            return None
        if isinstance(value, int):
            return value
        text = str(value).strip()
        if text.isdigit():
            return int(text)
        return text

    def _search_named_dense_vector(
        self,
        *,
        query_vector: List[float],
        query: str,
        safe_limit: int,
        query_filter: Filter | None,
        embedding_ms: int,
        match_type: str,
    ) -> List[Dict[str, Any]]:
        started_at = perf_counter()
        try:
            response = self.client.search(
                collection_name=self.collection_name,
                query_vector=self._named_dense_vector(query_vector),
                query_filter=query_filter,
                limit=safe_limit,
                with_payload=True,
                with_vectors=False,
            )
        except Exception as exc:
            return self._fallback_dense_lookup(query, safe_limit, query_filter, str(exc))
        qdrant_ms = int((perf_counter() - started_at) * 1000)
        formatted = self._format_points(response, match_type=match_type)
        self._set_retrieval_metadata(
            requested_strategy="dense_bm25_rrf",
            used_strategy="dense",
            fallback=False,
            result_count=len(formatted),
        )
        print(
            f"[KURE QDRANT HYBRID DENSE SEARCH TIMING] collection={self.collection_name} "
            f"strategy=dense fallback=false embedding_ms={embedding_ms} "
            f"qdrant_search_ms={qdrant_ms} result_count={len(formatted)} limit={safe_limit}"
        )
        return formatted

    def _fallback_dense_lookup(
        self,
        query: str,
        safe_limit: int,
        query_filter: Filter | None,
        reason: str,
    ) -> List[Dict[str, Any]]:
        self._set_retrieval_metadata(
            requested_strategy="dense_bm25_rrf",
            used_strategy="dense_lookup",
            fallback=True,
            fallback_reason=reason,
            collection=self.fallback_collection_name,
        )
        print(
            f"[KURE QDRANT HYBRID FALLBACK] requested_strategy=dense_bm25_rrf used_strategy=dense_lookup "
            f"collection={self.collection_name} fallback_collection={self.fallback_collection_name} reason={reason}"
        )
        results = self._search_dense_vector_on_collection(
            query=query,
            limit=safe_limit,
            query_filter=query_filter,
            collection_name=self.fallback_collection_name,
            match_type="kure_vector_fallback_dense_lookup",
            cache_namespace="kure_hybrid_fallback_dense",
        )
        self._set_retrieval_metadata(
            requested_strategy="dense_bm25_rrf",
            used_strategy="dense_lookup",
            fallback=True,
            fallback_reason=reason,
            collection=self.fallback_collection_name,
            result_count=len(results),
        )
        return results

    def _search_dense_vector_on_collection(
        self,
        *,
        query: str,
        limit: int,
        query_filter: Filter | None,
        collection_name: str,
        match_type: str,
        cache_namespace: str,
    ) -> List[Dict[str, Any]]:
        original_collection = self.collection_name
        original_hybrid = self.hybrid_enabled
        try:
            self.collection_name = collection_name
            self.hybrid_enabled = False
            return self._search_by_vector(
                query=query,
                limit=limit,
                query_filter=query_filter,
                match_type=match_type,
                cache_namespace=cache_namespace,
            )
        finally:
            self.collection_name = original_collection
            self.hybrid_enabled = original_hybrid

    def _named_dense_vector(self, vector: List[float]) -> Any:
        named_vector_cls = getattr(qdrant_models, "NamedVector", None)
        if named_vector_cls is not None:
            return named_vector_cls(name=self.dense_vector_name, vector=vector)
        return (self.dense_vector_name, vector)

    def _named_sparse_vector(self, sparse_vector: Dict[str, Any]) -> Any:
        sparse_vector_cls = getattr(qdrant_models, "SparseVector", None)
        named_sparse_cls = getattr(qdrant_models, "NamedSparseVector", None)
        if sparse_vector_cls is not None and named_sparse_cls is not None:
            return named_sparse_cls(
                name=self.sparse_vector_name,
                vector=sparse_vector_cls(indices=sparse_vector.get("indices") or [], values=sparse_vector.get("values") or []),
            )
        return {
            "name": self.sparse_vector_name,
            "vector": {"indices": sparse_vector.get("indices") or [], "values": sparse_vector.get("values") or []},
        }

    def _set_retrieval_metadata(self, **values: Any) -> None:
        metadata = {
            "requested_strategy": values.get("requested_strategy", "dense_lookup"),
            "used_strategy": values.get("used_strategy", "dense_lookup"),
            "collection": values.get("collection", self.collection_name),
            "fallback_collection": self.fallback_collection_name,
            "fallback": bool(values.get("fallback", False)),
            "fallback_reason": values.get("fallback_reason"),
        }
        for key, value in values.items():
            if key not in metadata:
                metadata[key] = value
        self.last_retrieval_metadata = metadata



    def _scroll_audiobook_payloads(self, *, limit: int) -> List[Dict[str, Any]]:
        safe_limit = max(1, int(limit or 5))
        query_filter = self._audio_payload_filter()
        candidates = self._retain_audiobook_payloads(
            self._scroll_by_filter(
                query_filter=query_filter,
                limit=safe_limit,
                match_type="listening_format_payload",
            )
        )
        if candidates:
            return candidates

        # Qdrant text filtering can vary by payload index/version. As a defensive
        # fallback, scan payloads client-side and keep only source-backed audiobook
        # evidence. This path runs only for structured listening-mode requests.
        return self._scan_audiobook_payloads(limit=safe_limit)

    def _scan_audiobook_payloads(self, *, limit: int) -> List[Dict[str, Any]]:
        safe_limit = max(1, int(limit or 5))
        max_scan = max(safe_limit, int(getattr(settings, "QDRANT_AUDIOBOOK_SCAN_LIMIT", 100000) or 100000))
        hits: List[Any] = []
        offset = None
        scanned = 0
        while len(hits) < safe_limit and scanned < max_scan:
            try:
                points, offset = self.client.scroll(
                    collection_name=self.collection_name,
                    limit=min(512, max_scan - scanned),
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
            except Exception as exc:
                print(f"[LISTENING FORMAT PAYLOAD SCAN FAILED] error={exc}")
                break

            if not points:
                break

            scanned += len(points)
            for point in points:
                if SourceFormatPolicy.is_audiobook_payload(point.payload or {}):
                    hits.append(point)
                    if len(hits) >= safe_limit:
                        break

            if offset is None:
                break

        formatted = self._format_points(hits, match_type="listening_format_payload_scan", default_score=0.32)
        print(
            f"[LISTENING FORMAT PAYLOAD SCAN] collection={self.collection_name} "
            f"scanned={scanned} hits={len(formatted)} limit={safe_limit}"
        )
        return formatted

    @staticmethod
    def _retain_audiobook_payloads(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [candidate for candidate in candidates or [] if SourceFormatPolicy.is_audiobook_payload(candidate)]

    @staticmethod
    def _merge_formatted_candidates(
        primary_candidates: List[Dict[str, Any]],
        secondary_candidates: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        merged: List[Dict[str, Any]] = []
        seen = set()
        for candidate in [*(primary_candidates or []), *(secondary_candidates or [])]:
            key = (
                str(candidate.get("isbn") or candidate.get("isbn13") or "").strip(),
                str(candidate.get("title") or "").strip(),
                str(candidate.get("author") or "").strip(),
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(candidate)
        return merged


    def _scroll_by_filter(
        self,
        *,
        query_filter: Filter,
        limit: int,
        match_type: str,
    ) -> List[Dict[str, Any]]:
        safe_limit = max(1, int(limit or 5))
        try:
            points, _ = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=query_filter,
                limit=safe_limit,
                with_payload=True,
                with_vectors=False,
            )
        except Exception as exc:
            print(f"[LISTENING FORMAT PAYLOAD SEARCH FAILED] error={exc}")
            return []
        return self._format_points(points, match_type=match_type, default_score=0.35)

    @staticmethod
    def _audio_payload_filter() -> Filter:
        # 수정 포인트: 사용자의 자연어를 직접 판정하지 않고, 이미 구조화된 reading_mode가
        # LISTENING_FRIENDLY일 때 후보 payload의 format evidence만 확인합니다.
        # 원천 카탈로그가 제목에 format 표식을 넣는 경우가 있어 title/subtitle 표식도 보조 evidence로 사용합니다.
        should = [
            FieldCondition(key="is_audio_book", match=MatchValue(value=True)),
            FieldCondition(key="isAudioBook", match=MatchValue(value=True)),
            FieldCondition(key="audiobook", match=MatchValue(value=True)),
            FieldCondition(key="format", match=MatchText(text="오디오")),
            FieldCondition(key="format", match=MatchText(text="audio")),
            FieldCondition(key="book_format", match=MatchText(text="오디오")),
            FieldCondition(key="book_format", match=MatchText(text="audio")),
            FieldCondition(key="media_type", match=MatchText(text="오디오")),
            FieldCondition(key="media_type", match=MatchText(text="audio")),
            FieldCondition(key="content_format", match=MatchText(text="오디오")),
            FieldCondition(key="content_format", match=MatchText(text="audio")),
        ]
        for marker in SourceFormatPolicy.title_marker_terms():
            should.append(FieldCondition(key="title", match=MatchText(text=marker)))
            should.append(FieldCondition(key="subtitle", match=MatchText(text=marker)))
        return Filter(should=should)

    def _search_by_keyword(
        self,
        keywords: List[str],
        query: str,
        limit: int = 5,
        search_mode_override: str | None = None,
    ) -> List[Dict[str, Any]]:
        """CLOVA retriever와 동일하게 명확한 payload 검색만 처리합니다."""
        search_mode = search_mode_override or self._detect_search_mode(query)
        if search_mode not in {"author", "title", "isbn"}:
            return []

        normalized_keywords = self._normalize_keywords(keywords)
        if not normalized_keywords:
            return []

        return self._search_by_payload_filter(
            keywords=keywords,
            normalized_keywords=normalized_keywords,
            search_mode=search_mode,
            limit=limit,
        )

    def _search_by_payload_filter(
        self,
        keywords: List[str],
        normalized_keywords: List[str],
        search_mode: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        field_names = self._payload_filter_fields(search_mode)
        if not field_names:
            return []

        matched_points = []
        seen_ids = set()

        for raw_keyword, normalized_keyword in zip(keywords, normalized_keywords):
            if not normalized_keyword:
                continue

            for field_name in field_names:
                query_filters = self._build_payload_filters(
                    field_name=field_name,
                    keyword=raw_keyword,
                    normalized_keyword=normalized_keyword,
                    search_mode=search_mode,
                )

                for query_filter in query_filters:
                    try:
                        points, _ = self.client.scroll(
                            collection_name=self.collection_name,
                            scroll_filter=query_filter,
                            limit=limit,
                            with_payload=True,
                            with_vectors=False,
                        )
                    except Exception as e:
                        print(
                            f"[KURE QDRANT PAYLOAD FILTER SEARCH FAILED] "
                            f"collection={self.collection_name}, "
                            f"mode={search_mode}, "
                            f"field={field_name}, "
                            f"keyword={raw_keyword!r}, "
                            f"error={e}"
                        )
                        continue

                    for point in points:
                        point_id = getattr(point, "id", None)
                        if point_id in seen_ids:
                            continue

                        payload = point.payload or {}
                        if not self._payload_matches_keywords(
                            payload=payload,
                            keywords=normalized_keywords,
                            search_mode=search_mode,
                        ):
                            continue

                        seen_ids.add(point_id)
                        matched_points.append(point)

                        if len(matched_points) >= limit:
                            return self._format_points(
                                matched_points,
                                match_type=f"kure_payload_{search_mode}",
                            )

        return self._format_points(
            matched_points,
            match_type=f"kure_payload_{search_mode}",
        )

    @staticmethod
    def _payload_filter_fields(search_mode: str) -> List[str]:
        if search_mode == "isbn":
            return ["isbn"]

        if search_mode == "title":
            return ["title"]

        if search_mode == "author":
            return ["author"]

        return []

    def _build_payload_filters(
        self,
        field_name: str,
        keyword: str,
        normalized_keyword: str,
        search_mode: str,
    ) -> List[Filter]:
        if search_mode == "isbn":
            values = [normalized_keyword]
            compact = re.sub(r"[^0-9Xx]", "", keyword)
            if compact and compact not in values:
                values.append(compact)
            return [
                Filter(
                    must=[
                        FieldCondition(
                            key=field_name,
                            match=MatchValue(value=value),
                        )
                    ]
                )
                for value in values
            ]

        keyword = keyword.strip()
        if not keyword:
            return []

        return [
            Filter(
                must=[
                    FieldCondition(
                        key=field_name,
                        match=MatchText(text=keyword),
                    )
                ]
            )
        ]

    def _payload_matches_keywords(
        self,
        payload: Dict[str, Any],
        keywords: List[str],
        search_mode: str,
    ) -> bool:
        title = self._normalize_text(payload.get("title"))
        author = self._normalize_text(payload.get("author"))
        isbn = self._normalize_text(payload.get("isbn"))

        if search_mode == "author":
            return any(keyword in author for keyword in keywords)

        if search_mode == "title":
            return any(keyword in title for keyword in keywords)

        if search_mode == "isbn":
            return any(keyword in isbn for keyword in keywords)

        searchable_text = self._normalize_text(
            " ".join(
                [
                    str(payload.get("title") or ""),
                    str(payload.get("author") or ""),
                    str(payload.get("isbn") or ""),
                    str(payload.get("publisher") or ""),
                    str(payload.get("description") or ""),
                    str(payload.get("simple_intro") or ""),
                    str(payload.get("book_intro") or ""),
                    str(payload.get("author_intro") or ""),
                    str(payload.get("book_index") or ""),
                    str(payload.get("pub_review") or ""),
                    str(payload.get("document") or ""),
                    self._join_payload_list(payload.get("categories")),
                    self._join_payload_list(payload.get("cate_depth1")),
                    self._join_payload_list(payload.get("kcid")),
                ]
            )
        )

        return any(keyword in searchable_text for keyword in keywords)

    def _detect_search_mode(self, query: str) -> str:
        return self._detect_search_mode_from_intent(self.query_parser.parse(query))

    def _extract_keywords(self, query: str) -> List[str]:
        return self._keywords_from_intent(self.query_parser.parse(query))

    @staticmethod
    def _detect_search_mode_from_intent(intent: QueryIntent) -> str:
        if intent.isbn:
            return "isbn"
        if intent.author:
            return "author"
        if intent.title:
            return "title"
        return "general"

    @staticmethod
    def _keywords_from_intent(intent: QueryIntent) -> List[str]:
        if intent.isbn:
            return [intent.isbn]
        if intent.author:
            return [intent.author]
        if intent.title:
            return [intent.title]
        return []

    @staticmethod
    def _normalize_keywords(keywords: List[str]) -> List[str]:
        normalized: List[str] = []
        for keyword in keywords:
            value = BookKureQdrantSearcher._normalize_text(keyword)
            if value and value not in normalized:
                normalized.append(value)
        return normalized

    @staticmethod
    def _normalize_text(value: Any) -> str:
        if value is None:
            return ""

        text = str(value).lower().strip()
        text = re.sub(r"\s+", "", text)
        text = text.replace("-", "")
        text = text.replace("_", "")
        text = text.replace("·", "")
        text = text.replace(".", "")
        text = text.replace(",", "")
        text = text.replace(":", "")
        text = text.replace(";", "")
        text = text.replace("!", "")
        text = text.replace("?", "")
        text = text.replace("'", "")
        text = text.replace('"', "")

        return text

    @staticmethod
    def _join_payload_list(value: Any) -> str:
        if isinstance(value, list):
            return " ".join(str(item) for item in value if item is not None)
        if value is None:
            return ""
        return str(value)

    def _is_strict_keyword_query(self, query: str) -> bool:
        intent = self.query_parser.parse(query)
        return intent.is_precise_lookup

    @staticmethod
    def _first_payload_value(value: Any) -> Any:
        if isinstance(value, list):
            return next((item for item in value if item not in (None, "")), None)
        return value

    def _resolve_payload_category_code(self, payload: Dict[str, Any]) -> Any:
        return (
            payload.get("categoryCode")
            or payload.get("category_code")
            or self._first_payload_value(payload.get("categories"))
            or self._first_payload_value(payload.get("cate_depth1"))
            or self._first_payload_value(payload.get("kcid"))
        )

    def _format_points(self, points: Any, match_type: str, default_score: float = 1.0) -> List[Dict[str, Any]]:
        output: List[Dict[str, Any]] = []

        for item in points:
            payload = item.payload or {}
            format_evidence = SourceFormatPolicy.audiobook_evidence(payload)

            category_code = self._resolve_payload_category_code(payload)

            output.append(
                {
                    "score": getattr(item, "score", default_score),
                    "qdrant_id": str(getattr(item, "id", "")),
                    "point_id": str(getattr(item, "id", "")),
                    "source_format": format_evidence.get("normalized_format"),
                    "source_format_evidence": format_evidence,
                    "match_type": match_type,
                    "categoryCode": category_code,
                    "category_code": category_code,
                    "isbn": payload.get("isbn"),
                    "title": payload.get("title"),
                    "author": payload.get("author"),
                    "publisher": payload.get("publisher"),
                    "publish_date": payload.get("publish_date"),
                    "page": payload.get("page"),
                    "price": payload.get("price"),
                    "format": payload.get("format"),
                    "book_format": payload.get("book_format") or payload.get("bookFormat"),
                    "media_type": payload.get("media_type") or payload.get("mediaType"),
                    "content_format": payload.get("content_format") or payload.get("contentFormat"),
                    "is_audio_book": True if format_evidence.get("matched") else (payload.get("is_audio_book") or payload.get("isAudioBook") or payload.get("audiobook")),
                    "is_ebook": payload.get("is_ebook") or payload.get("isEbook") or payload.get("ebook"),
                    "description": payload.get("description"),
                    "simple_intro": payload.get("simple_intro"),
                    "book_intro": payload.get("book_intro"),
                    "categories": payload.get("categories", []),
                    "cate_depth1": payload.get("cate_depth1", []),
                    "cate_depth2": payload.get("cate_depth2", []),
                    "cate_depth3": payload.get("cate_depth3", []),
                    "kcid": payload.get("kcid", []),
                    "genre": payload.get("genre"),
                    "genres": payload.get("genres", []),
                    "category": payload.get("category"),
                    "categoryName": payload.get("categoryName"),
                    "category_name": payload.get("category_name"),
                    "category_full_name": payload.get("category_full_name"),
                    "category_path": payload.get("category_path"),
                    "className": payload.get("className"),
                    "class_name": payload.get("class_name"),
                    "audience_profile": payload.get("audience_profile") or payload.get("audienceProfile"),
                    "target_audience": payload.get("target_audience") or payload.get("targetAudience"),
                    "ori_cover_s": payload.get("ori_cover_s")
                    or payload.get("cover_url")
                    or payload.get("cover"),
                    "cover_url": payload.get("cover_url")
                    or payload.get("ori_cover_s")
                    or payload.get("cover"),
                    "cover": payload.get("cover")
                    or payload.get("cover_url")
                    or payload.get("ori_cover_s"),
                    "author_intro": payload.get("author_intro"),
                    "book_index": payload.get("book_index"),
                    "pub_review": payload.get("pub_review"),
                    "document": payload.get("document"),
                    "embedding_model": payload.get("embedding_model"),
                }
            )

        return output