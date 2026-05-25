# LightFM 학습 스크립트 사용법

팀원별 synthetic subset 파일 경로만 다르게 넣어 LightFM artifact를 만들 수 있습니다.

## 지원 입력 형식

- `.jsonl`
- `.json`
- `.csv`
- 디렉터리 경로를 넣으면 해당 디렉터리 바로 아래의 `.jsonl`, `.json`, `.csv`를 모두 읽습니다.

기본 필드명은 여러 후보를 허용합니다.

| 의미 | 기본 후보 필드 |
|---|---|
| 사용자 | `user_key,user_id,persona_id` |
| 도서 | `isbn13,isbn,book_key,book_id,item_id` |
| 이벤트 타입 | `event_type,type,action` |
| 가중치 | `final_weight,weight,base_weight` |
| 출처 | `user_source,source` |

`DISLIKED`, `NOT_INTERESTED`, `UNLIKE`, `BLOCK`, `NEGATIVE`는 기본적으로 WARP positive 학습에서 제외됩니다.

## 실행 예시

```bash
cd apps/ai-server
python script/train_lightfm.py \
  --events-path /path/to/team-a/synthetic_events.jsonl \
  --output-dir artifacts/lightfm/latest \
  --epochs 30 \
  --components 64
```

여러 파일을 합칠 수 있습니다.

```bash
python script/train_lightfm.py \
  --events-path /path/to/synthetic_events.jsonl \
  --events-path /path/to/real_user_events.csv \
  --output-dir artifacts/lightfm/latest
```

환경변수로도 경로를 줄 수 있습니다.

```bash
export LIGHTFM_TRAIN_EVENTS_PATH=/path/to/a.jsonl,/path/to/b.csv
python script/train_lightfm.py --output-dir artifacts/lightfm/latest
```

필드명이 다르면 실행 시 바꿀 수 있습니다.

```bash
python script/train_lightfm.py \
  --events-path /path/to/events.jsonl \
  --user-field persona_user_id \
  --item-field isbn \
  --event-type-field behavior_type \
  --weight-field event_weight
```

생성되는 artifact 구조는 아래와 같습니다.

```text
artifacts/lightfm/latest/
  model.joblib
  mappings.json
  metadata.json
```

운영 ai-server는 `LIGHTFM_ARTIFACT_PATH` 환경변수로 이 디렉터리를 읽습니다.
