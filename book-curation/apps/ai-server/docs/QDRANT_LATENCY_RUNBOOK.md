# Qdrant 검색 지연 운영 점검 가이드

이 문서는 추천 API 요청 중 Qdrant 검색이 10초 이상 지연될 때 운영자가 확인할 항목과 수동으로 실행할 수 있는 Qdrant payload index 명령을 정리합니다.

## 1. 자동 실행하지 않는 이유

Qdrant collection 설정과 payload index 변경은 운영 중 I/O와 메모리 사용량을 증가시킬 수 있습니다. 따라서 애플리케이션 시작 시 자동 변경하지 않고, 운영자가 로그와 리소스를 확인한 뒤 수동으로 실행합니다.

현재 ai-server는 다음 structured timing log를 남깁니다.

```text
[QDRANT SEARCH TIMING] collection=books cache_hit=false embedding_ms=... qdrant_search_ms=... result_count=... limit=...
[KURE QDRANT SEARCH TIMING] collection=books_kure cache_hit=false embedding_ms=... qdrant_search_ms=... result_count=... limit=...
[RECOMMENDATION TIMINGS] {... qdrant_search_time_ms, candidate_filter_time_ms, reranker_time_ms, reason_generation_time_ms, total_recommendation_time_ms ...}
```

## 2. 우선 확인 순서

1. `embedding_ms`가 큰지 확인합니다. 크면 KURE/CLOVA embedding 서버 또는 API 지연입니다.
2. `qdrant_search_ms`가 큰지 확인합니다. 크면 Qdrant collection/index/filter 쪽 병목입니다.
3. `reranker_time_ms`가 큰지 확인합니다. 크면 로컬 GPU primary 또는 NAS CPU fallback 지연입니다.
4. `reason_generation_time_ms`가 큰지 확인합니다. 크면 추천 이유 LLM 생성을 비동기 유지하거나 worker 수를 조정합니다.
5. `cache_hit=true` 비율이 낮으면 TTL 또는 key hash 기준을 확인합니다.

## 3. payload index 수동 생성 예시

아래 명령은 Qdrant HTTP API 기준입니다. 운영 전 `QDRANT_URL`, `QDRANT_API_KEY`, collection 이름을 실제 환경에 맞게 설정하세요.

```bash
export QDRANT_URL="http://qdrant:6333"
export QDRANT_API_KEY=""

create_payload_index() {
  local collection="$1"
  local field_name="$2"
  local field_schema="$3"

  curl -sS -X PUT "${QDRANT_URL}/collections/${collection}/index" \
    -H "Content-Type: application/json" \
    ${QDRANT_API_KEY:+-H "api-key: ${QDRANT_API_KEY}"} \
    -d "{\"field_name\":\"${field_name}\",\"field_schema\":\"${field_schema}\"}"
}

for collection in books books_kure; do
  create_payload_index "${collection}" "isbn" "keyword"
  create_payload_index "${collection}" "title" "text"
  create_payload_index "${collection}" "author" "text"
  create_payload_index "${collection}" "categories" "keyword"
  create_payload_index "${collection}" "cate_depth1" "keyword"
  create_payload_index "${collection}" "kcid" "keyword"
done
```

## 4. 추천 지연 관련 환경변수

```text
QDRANT_SEARCH_TIMEOUT_SECONDS=5.0
QDRANT_SEARCH_LIMIT=80
QDRANT_PREFETCH_LIMIT=100
QDRANT_CACHE_ENABLED=true
QDRANT_SEARCH_CACHE_TTL_SECONDS=600
RECOMMENDATION_CANDIDATE_LIMIT=80
GTE_RERANK_TOP_K=20
GTE_RERANK_CACHE_TTL_SECONDS=600
```

## 5. 운영 판단 기준

- 검색 품질 저하가 보이면 `QDRANT_SEARCH_LIMIT`과 `RECOMMENDATION_CANDIDATE_LIMIT`을 80 → 100으로 올려 비교합니다.
- Qdrant가 느리고 embedding/reranker는 빠르면 payload index, collection HNSW 설정, on-disk payload/vector 설정을 별도 점검합니다.
- 동일 질의 반복이 많은데 cache hit가 낮으면 query hash, candidate hash, profile hash 기준이 너무 세분화되어 있는지 확인합니다.
- 운영 중 collection 재생성이나 HNSW 재구성은 자동화하지 말고 백업/스냅샷 확인 후 별도 작업으로 진행합니다.
