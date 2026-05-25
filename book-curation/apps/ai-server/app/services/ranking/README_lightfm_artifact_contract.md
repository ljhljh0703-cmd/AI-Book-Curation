# LightFM artifact contract

ai-server runtime은 요청 시점에 LightFM 학습을 하지 않습니다. 학습 완료 artifact를 읽어 Qdrant/룰베이스 후보를 scoring하고, 후보 50개를 20개로 압축하는 단계에서만 사용합니다.

## 필수 디렉터리 구조

`LIGHTFM_ARTIFACT_DIR`가 가리키는 디렉터리 안에는 아래 파일이 있어야 합니다.

```text
artifacts/lightfm/current/
  model.joblib
  mappings.json
  metadata.json
```

이번 shared-pool hybrid-lite artifact처럼 `metadata.json`의 `feature_mode`가 `hybrid`, `hybrid-lite` 계열이면 아래 파일도 추론에 필요합니다.

```text
  user_features.npz
  item_features.npz
```

아래 파일은 추론 필수는 아니지만 운영 확인과 재현성 추적을 위해 함께 배포하는 것을 권장합니다.

```text
  metrics.json
  feature_sources.json
```

## mappings.json

```json
{
  "user_id_to_index": {
    "1": 0,
    "persona:001": 1
  },
  "item_id_to_index": {
    "9780000000001": 0,
    "9780000000002": 1
  }
}
```

## metadata.json

```json
{
  "artifact_version": "lightfm_20260515T000000Z",
  "trained_at": "2026-05-15T00:00:00Z",
  "feature_mode": "hybrid",
  "user_count": 1000,
  "item_count": 18045,
  "loss": "warp",
  "epochs": 40
}
```

## serving fallback

아래 상황에서는 추천 실패 대신 RULE_BASED fallback을 유지합니다.

```text
LIGHTFM_ENABLED=false
user_id 없음
artifact dir 없음
model.joblib 없음
mappings.json 없음
hybrid artifact인데 user_features.npz 또는 item_features.npz 없음
user mapping 없음
candidate item mapping이 전부 없음
known item 후보 수가 LIGHTFM_TOP_N보다 적음
LightFM predict 실패
```

item mapping에 없는 후보는 LightFM scoring 대상에서 제외합니다. 제외 후 score 계산 가능한 후보가 `LIGHTFM_TOP_N`보다 적으면 `INSUFFICIENT_KNOWN_ITEMS` 사유로 RULE_BASED fallback합니다.

fallback 여부는 응답의 `ranking_model_fallback`, `ranking_model_fallback_reason`, `pipeline.rankingModelStage`에서 확인할 수 있습니다.

## candidate item key

runtime은 `LIGHTFM_ITEM_ID_FIELDS` 순서대로 후보의 item key를 찾습니다.

기본값:

```text
isbn,isbn13,book_id,bookId,itemId
```

학습 artifact의 `item_id_to_index`와 ai-server 후보의 item key가 반드시 같아야 합니다.
