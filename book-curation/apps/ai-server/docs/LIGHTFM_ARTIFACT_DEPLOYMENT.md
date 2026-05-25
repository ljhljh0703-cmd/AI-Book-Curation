# LightFM artifact 배포 가이드

## 역할

LightFM은 최종 Top-10 추천기가 아닙니다. ai-server에서는 다음 흐름의 후보 압축 단계로만 사용합니다.

```text
Qdrant 검색 후보 100개
→ 룰베이스/필터 후보 50개
→ LightFM 후보 20개 압축
→ 기존 최종 리랭킹/응답 생성
```

LightFM이 비활성화되었거나 artifact를 읽지 못하면 추천 API는 실패하지 않고 기존 RULE_BASED/Qdrant fallback을 사용합니다.

## 이번 artifact 분석 결과

첨부된 `shared_hybrid_lite_50to20_eval.zip` 내부 파일은 아래와 같습니다.

```text
model.joblib
mappings.json
metadata.json
metrics.json
feature_sources.json
user_features.npz
item_features.npz
```

`metadata.json` 기준 주요 값은 다음과 같습니다.

```text
artifact_version: lightfm_701_hybrid_20260515T023734Z
feature_mode: hybrid
user_count: 1000
item_count: 18045
user_feature_count: 1006
item_feature_count: 18083
loss: warp
epochs: 40
```

파일명은 `shared_hybrid_lite_50to20_eval`이고, `metrics.json`의 feature summary는 사용자/아이템 categorical feature만 포함하며 text feature가 없습니다. 따라서 운영 관점에서는 identity-only가 아니라 shared-pool hybrid-lite 계열 artifact로 취급해야 합니다. 추론에는 `model.joblib`, `mappings.json`, `metadata.json`, `user_features.npz`, `item_features.npz`가 필요합니다. `metrics.json`, `feature_sources.json`은 추론 필수는 아니지만 배포 검증과 감사 로그 추적을 위해 같이 보관하는 것을 권장합니다.

## 환경변수

Secret이 아닌 ConfigMap/env로 관리해도 되는 값입니다.

```bash
LIGHTFM_ENABLED=true
LIGHTFM_ARTIFACT_DIR=/app/artifacts/lightfm/current
LIGHTFM_TOP_N=20
LIGHTFM_CANDIDATE_LIMIT=50
LIGHTFM_ITEM_ID_FIELDS=isbn,isbn13,book_id,bookId,itemId
LIGHTFM_NUM_THREADS=2
LIGHTFM_SCORE_MODEL_WEIGHT=0.8
LIGHTFM_SCORE_RULE_WEIGHT=0.2
LIGHTFM_FALLBACK_TO_RULE_BASED=true
QDRANT_ENSURE_PAYLOAD_INDEXES=false
```

Secret에 넣어야 하는 값은 API Key, DB 비밀번호, OAuth secret, 내부 호출용 공유키입니다. LightFM artifact 경로와 limit 값은 secret이 아닙니다. `QDRANT_ENSURE_PAYLOAD_INDEXES=false`가 기본값이면 추천 요청 경로에서 Qdrant payload index 생성/write/upsert를 수행하지 않습니다.

## 로컬 실행

```bash
cd apps/ai-server
cp .env.local.example .env.local
mkdir -p artifacts/lightfm/current
unzip /path/to/shared_hybrid_lite_50to20_eval.zip -d artifacts/lightfm/current

export LIGHTFM_ENABLED=true
export LIGHTFM_ARTIFACT_DIR="$PWD/artifacts/lightfm/current"
export LIGHTFM_TOP_N=20
export LIGHTFM_CANDIDATE_LIMIT=50

python script/validate_lightfm_runtime.py --artifact-dir "$LIGHTFM_ARTIFACT_DIR"
uvicorn app.main:app --host 0.0.0.0 --port 8001
```

`apps/ai-server/.env.local`은 로컬 전용 파일이므로 Git에 올리지 않습니다. 이미 추적 중이면 아래 명령으로 index에서 제거해야 `.gitignore`가 적용됩니다.

```bash
git rm --cached apps/ai-server/.env.local
```

## NAS/Kubernetes 배포

NAS 또는 K3s 노드의 hostPath에 artifact를 풀어 둡니다.

```bash
sudo mkdir -p /volume1/apps/book-curation/artifacts/lightfm/current
sudo unzip /path/to/shared_hybrid_lite_50to20_eval.zip \
  -d /volume1/apps/book-curation/artifacts/lightfm/current
sudo ls -lh /volume1/apps/book-curation/artifacts/lightfm/current
```

컨테이너에서는 k8s manifest의 `volumeMount`를 통해 아래 경로로 읽습니다.

```text
/app/artifacts/lightfm/current
```

배포 반영:

```bash
cd book-curation-k8s
sudo k3s kubectl apply -k k8s/overlays/dev
sudo k3s kubectl rollout restart deploy/ai-server -n book-curation-dev
sudo k3s kubectl rollout status deploy/ai-server -n book-curation-dev
```

로그 확인:

```bash
sudo k3s kubectl logs -n book-curation-dev deploy/ai-server --tail=200 | grep -E "LIGHTFM|RANKING MODEL"
```

정상 로드 예시:

```text
[LIGHTFM ARTIFACT] loaded path=/app/artifacts/lightfm/current version=... feature_mode=hybrid files=...
```

fallback 예시:

```text
[RANKING MODEL FALLBACK] requested=LIGHTFM applied=RULE_BASED reason=UNKNOWN_USER
```

## fallback 정책

- 신규 사용자 또는 LightFM `user_id_to_index`에 없는 사용자는 LightFM scoring을 건너뛰고 기존 RULE_BASED/Qdrant 후보 압축으로 fallback합니다.
- 후보 item이 일부 `item_id_to_index`에 없으면 해당 후보는 LightFM 후보 압축 결과에서 제외합니다.
- 제외 후 LightFM으로 score 계산 가능한 후보가 `LIGHTFM_TOP_N`보다 적으면 `INSUFFICIENT_KNOWN_ITEMS` 사유로 전체 LightFM 단계를 RULE_BASED로 fallback합니다.
- 후보 item이 전부 mapping에 없으면 `NO_KNOWN_ITEMS` 사유로 전체 LightFM 단계를 RULE_BASED로 fallback합니다.
- artifact 경로가 없거나 로딩 실패, hybrid feature matrix 누락, predict 실패가 발생해도 서버 프로세스는 죽지 않습니다.

## 검증 명령어

artifact 경로가 없는 경우 fallback 확인:

```bash
cd apps/ai-server
python script/validate_lightfm_runtime.py --artifact-dir /tmp/not-exists --expect-missing-artifact
```

artifact 정상 로드, unknown user, unknown item 제외 및 fallback 처리 확인:

```bash
cd apps/ai-server
python script/validate_lightfm_runtime.py --artifact-dir artifacts/lightfm/current
```

추천 API 응답에서 확인할 필드:

```text
ranking_model_applied
ranking_model_fallback
ranking_model_fallback_reason
ranking_model_applied_model
ranking_artifact_version
pipeline.rankingModelStage
```

## Git에 올리지 말아야 하는 파일

아래 파일은 백업/NAS/외부 artifact 저장소에만 두고 Git에는 올리지 않습니다.

```text
apps/ai-server/data/lightfm/**
apps/ai-server/data/persona/**
apps/ai-server/artifacts/lightfm/**
apps/ai-server/**/*.tar
apps/ai-server/**/*.tar.gz
apps/ai-server/**/*.zip
apps/ai-server/**/*.joblib
apps/ai-server/**/*.pkl
apps/ai-server/**/*.pickle
apps/ai-server/**/*.npz
apps/ai-server/**/*.bin
apps/ai-server/**/*.pt
apps/ai-server/**/*.onnx
apps/ai-server/.env.local
.env
.env.local
.env.*
```

필요하면 `README_*.md`, `.gitkeep`, `.env.example`, `.env.local.example`만 예외로 커밋합니다.
