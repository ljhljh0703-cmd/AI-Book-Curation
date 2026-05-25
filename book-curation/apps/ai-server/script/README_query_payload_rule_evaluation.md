# Query payload / retrieval / rule weight evaluation

이 평가는 운영 추천 API와 분리된 관리자용 평가 기능입니다. 목적은 최종 답변 품질이 아니라 아래를 분리해서 확인하는 것입니다.

- query에 어떤 데이터를 담았을 때 후보군 품질이 좋아지는가
- dense / lookup / bm25 / hybrid retrieval 방식에 따라 후보군 품질이 달라지는가
- rule-based weight가 같은 후보군의 순위를 실제로 개선하는가

## 관리자 화면 입력 방식

관리자 화면의 `평가 질의 입력`이 비어 있으면 기본 파일을 사용합니다.

```text
apps/ai-server/script/evaluation/query_payload_eval_cases.example.jsonl
```

입력값이 있으면 그 내용을 우선 사용합니다. 한 줄에 일반 질의 하나를 넣어도 되고, JSONL을 넣어도 됩니다.

```text
운전하면서 듣기 좋은 책 추천해줘
재밌는 책 한 권만 추천해줘
{"id":"Q003","category":"audience","query":"초등학생 아이가 읽기 좋은 책 추천해줘"}
```

일반 텍스트 한 줄은 내부적으로 아래 JSONL 형태로 변환됩니다.

```json
{"id":"MANUAL001","category":"manual","query":"운전하면서 듣기 좋은 책 추천해줘"}
```

## Retrieval variants

```text
dense               Qdrant dense vector search
lookup              Qdrant payload corpus 기반 평가용 lookup
bm25                외부 의존성 없는 평가용 BM25
dense_lookup        dense + lookup RRF hybrid
dense_bm25          dense + BM25 RRF hybrid
dense_bm25_lookup   dense + BM25 + lookup RRF hybrid
```

BM25는 운영 의존성이 아니라 평가 스크립트 내부의 간이 lexical index입니다. 추가 pip install, OpenSearch, Elasticsearch는 필요하지 않습니다.

## 결과 저장 경로

관리자 화면에서는 결과 디렉터리를 직접 입력하지 않습니다. ai-server는 `QUERY_EVAL_OUTPUT_DIR` 고정 경로만 사용합니다. k3s에서는 NAS hostPath를 아래 컨테이너 경로로 마운트합니다.

```text
/app/evaluation/query-payload-rules
```

## 결과 파일

```text
raw_results.jsonl               원본 평가 row와 후보 payload
candidate_label_template.csv    관리자 화면 라벨링 대상 CSV
auto_summary.csv                라벨링 전 자동 메타 요약
labeled_summary.csv             query_id + 조합별 수동 점수 요약
dimension_summary.csv           query_variant × retrieval_variant × rule_variant 기준 집계 점수
```

관리자 화면에서 후보별 `human_relevance_0_2`를 저장하면 `labeled_summary.csv`와 `dimension_summary.csv`가 갱신됩니다.

점수 기준:

```text
2 = 질의에 매우 적합
1 = 어느 정도 관련 있음
0 = 부적합하거나 검색 의도 오염 후보
```

## CLI 실행 예시

```bash
PYTHONPATH=/app/apps/ai-server \
python apps/ai-server/script/evaluate_query_payload_and_rules.py run \
  --cases apps/ai-server/script/evaluation/query_payload_eval_cases.example.jsonl \
  --out-dir /app/evaluation/query-payload-rules \
  --embedding-model KURE \
  --top-k 10 \
  --max-corpus-docs 50000 \
  --query-variants original,retrieval_query,retrieval_plus_genre,retrieval_plus_purpose,retrieval_plus_context,retrieval_plus_profile \
  --retrieval-variants dense,lookup,bm25,dense_lookup,dense_bm25,dense_bm25_lookup \
  --rule-variants current
```

라벨링 후 요약:

```bash
PYTHONPATH=/app/apps/ai-server \
python apps/ai-server/script/evaluate_query_payload_and_rules.py summarize \
  --labels /app/evaluation/query-payload-rules/candidate_label_template.csv \
  --out-dir /app/evaluation/query-payload-rules \
  --top-k 10
```
