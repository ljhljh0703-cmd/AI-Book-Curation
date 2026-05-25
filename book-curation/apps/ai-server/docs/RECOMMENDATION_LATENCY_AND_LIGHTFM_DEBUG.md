# 추천 지연 개선 및 LightFM 적용 확인 가이드

## 1. 이번 수정의 목적

기존 추천 응답은 후보 도서 검색, audience label 부여, 추천 이유 LLM 생성이 모두 끝난 뒤에야 프론트로 반환되었습니다. 운영 로그 기준으로 `qdrant_search_ms`는 수백 ms 수준이지만, `intent_classification_ms`, `audience_label_ms`, `reason_generation_ms`가 합쳐져 수십 초가 걸릴 수 있었습니다.

이번 수정은 다음 정책으로 바꿉니다.

1. 추천 후보 카드는 먼저 반환합니다.
2. 추천 이유는 `PENDING` 상태로 내려보내고 백그라운드에서 생성합니다.
3. 프론트는 추천 카드와 loading 표시를 먼저 보여준 뒤, 이유 생성 상태 API를 polling해 답변/카드를 갱신합니다.
4. audience label LLM은 기본적으로 비활성화하고, 명시적 대상 독자 요청이 있을 때만 수행합니다.
5. LightFM 적용 여부를 응답 metadata와 로그에서 확인할 수 있게 노출합니다.

## 2. audience label 역할

`audience_label`은 사용자의 검색어를 만드는 단계가 아닙니다. 이미 검색된 후보 도서마다 다음과 같은 구조화 label을 붙이는 단계입니다.

- `target_age_group`
- `education_stage`
- `difficulty_level`

이 label은 “초등학생용 책”, “청소년에게 적합한 책”, “입문서” 같은 대상 독자/난이도 신호를 프로필 rerank에 반영하기 위한 보조 feature입니다.

기존 설정에서 후보 payload에 label이 없고 `AUDIENCE_LABEL_PROVIDER=LLM`이면, 후보 여러 권의 제목/카테고리/설명을 LLM에 보내 label을 생성했습니다. 그래서 `audience_label_ms`가 20초 이상 나올 수 있습니다.

이번 수정에서는 기본값을 아래처럼 둡니다.

```env
AUDIENCE_LABEL_PROVIDER=PAYLOAD_ONLY
AUDIENCE_LABEL_ENABLE_FOR_PROFILE_RERANK=false
AUDIENCE_LABEL_CANDIDATE_LIMIT=12
```

따라서 일반 추천 또는 개인화 rerank에서는 audience label LLM을 호출하지 않습니다. 사용자가 명시적으로 대상 독자를 요청한 경우에만 audience stage가 수행됩니다.

예:

```text
초등학생이 읽기 좋은 과학책 추천해줘
청소년이 보기 좋은 판타지소설 추천해줘
```

## 3. 추천 이유 비동기 생성

기본 설정은 다음과 같습니다.

```env
RECOMMENDATION_REASON_ASYNC_ENABLED=true
RECOMMENDATION_REASON_ASYNC_WORKERS=2
RECOMMENDATION_REASON_ASYNC_TTL_SECONDS=900
```

응답 직후 후보 카드에는 다음 상태가 포함됩니다.

```json
{
  "recommendation_reason_status": "PENDING",
  "pipeline": {
    "recommendationReasonStatus": "PENDING",
    "recommendationReasonAsync": true
  }
}
```

프론트는 아래 API를 polling합니다.

```http
GET /api/chats/recommendation-reasons/{requestId}
GET /api/public/chats/recommendation-reasons/{requestId}
```

생성 완료 시 상태는 `COMPLETED`가 되고, 로그인 사용자는 저장된 assistant message 본문과 metadata가 갱신됩니다. 비로그인 사용자는 로컬 저장소의 assistant message를 갱신합니다.

## 4. 다중 pod 주의사항

현재 추천 이유 job은 ai-server 프로세스 메모리에 저장됩니다. ai-server pod를 여러 개 운영할 경우, 추천 요청을 처리한 pod와 polling 요청을 처리한 pod가 달라지면 `MISSING`이 발생할 수 있습니다.

현재 k8s 기본 deployment는 `replicas: 1`을 권장합니다. 다중 replica를 사용할 예정이면 Redis/PostgreSQL 기반 shared job store로 바꾸는 것이 안전합니다.

## 5. LightFM 적용 확인 방법

LightFM은 최종 Top-10 생성기가 아니라, Qdrant/룰베이스 후보를 압축하는 ranking stage입니다.

### 5.1 환경변수 확인

```bash
sudo k3s kubectl exec -n book-curation-dev deploy/ai-server -- printenv | grep LIGHTFM
```

필수 값:

```text
LIGHTFM_ENABLED=true
LIGHTFM_ARTIFACT_DIR=/app/artifacts/lightfm/current
LIGHTFM_TOP_N=20
LIGHTFM_CANDIDATE_LIMIT=50
```

### 5.2 artifact mount 확인

```bash
sudo k3s kubectl exec -n book-curation-dev deploy/ai-server -- \
  ls -lh /app/artifacts/lightfm/current
```

필수 파일:

```text
model.joblib
mappings.json
metadata.json
metrics.json
user_features.npz
item_features.npz
feature_sources.json
```

### 5.3 관리자 설정 확인

`model_ranking_stage_ms=0`이 계속 나오고 LightFM 로그가 없다면, 가장 먼저 관리자 설정의 ranking model이 `LIGHTFM`인지 확인하세요. ranking model이 `RULE_BASED`면 LightFM은 사용되지 않습니다.

### 5.4 로그 확인

추천 요청 후 아래 명령어로 확인합니다.

```bash
sudo k3s kubectl logs -n book-curation-dev deploy/ai-server --tail=300 | \
  grep -Ei "RANKING MODEL|LIGHTFM|fallback|UNKNOWN_USER|INSUFFICIENT"
```

대표 로그:

```text
[RANKING MODEL ROUTER] requested=LIGHTFM user_present=true candidate_count=50 ...
[LIGHTFM ARTIFACT] loaded path=/app/artifacts/lightfm/current ...
[RANKING MODEL FALLBACK] requested=LIGHTFM ... reason=UNKNOWN_USER
```

### 5.5 응답 metadata 확인

프론트 Network 탭 또는 backend에 저장된 chat message metadata에서 아래 값을 확인합니다.

```json
{
  "rankingModel": "LIGHTFM",
  "rankingModelApplied": true,
  "rankingModelFallback": false,
  "rankingModelFallbackReason": null,
  "rankingModelAppliedModel": "LIGHTFM",
  "rankingArtifactVersion": "...",
  "pipeline": {
    "rankingModelStage": {
      "requestedModel": "LIGHTFM",
      "appliedModel": "LIGHTFM",
      "applied": true,
      "fallback": false
    }
  }
}
```

fallback이 정상인 케이스:

| reason | 의미 |
|---|---|
| `MISSING_USER_ID` | 비로그인 요청이라 LightFM 사용 불가 |
| `UNKNOWN_USER` | 로그인했지만 artifact user mapping에 없는 사용자 |
| `NO_KNOWN_ITEMS` | 후보 item이 전부 artifact item mapping에 없음 |
| `INSUFFICIENT_KNOWN_ITEMS` | LightFM으로 scoring 가능한 후보가 `LIGHTFM_TOP_N`보다 적음 |
| `ARTIFACT_LOAD_FAILED` | artifact 파일/권한/경로 문제 |
| `PREDICT_FAILED` | LightFM predict 실행 중 오류 |

## 6. `판타지소설 추천해줘` 같은 붙임 질의 처리

특정 장르명을 코드에 하드코딩하지 않고, 검색 질의를 여러 변형으로 검색합니다.

- 원문 query
- LLM intent parser의 `retrieval_query`
- parser가 추출한 genre / soft genre
- genre 조합 query

즉, “판타지소설 추천해줘”처럼 붙여 쓴 질의에서도 원문 검색과 해석된 retrieval query를 함께 사용해 후보 회수율을 높입니다.
