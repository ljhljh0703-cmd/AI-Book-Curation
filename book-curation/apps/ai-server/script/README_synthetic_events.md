# Synthetic event 생성 스크립트

`generate_synthetic_events.py`는 LLM/Qdrant 단계에서 이미 만들어진 persona-book 후보 파일을 LightFM 학습용 event JSONL로 정규화합니다.

이 스크립트는 책을 새로 만들지 않습니다. 입력 파일에 존재하는 `isbn13/isbn/book_key`만 사용합니다.

## 입력 전제

입력 파일은 `.jsonl`, `.json`, `.csv`를 지원합니다.

기본 필드 후보는 아래와 같습니다.

| 의미 | 기본 후보 필드 |
|---|---|
| persona/user | `user_key,user_id,persona_id` |
| book/item | `isbn13,isbn,book_key,book_id,item_id` |
| 행동 타입 | `event_type,behavior_type,target_event_type,intent,bucket` |
| Qdrant 점수 | `qdrant_score,score,similarity` |

`event_type`은 기본적으로 아래 값을 사용합니다.

```text
READ
READING
PREFERRED
DISLIKED
```

## 기본 실행

```bash
cd apps/ai-server

python script/generate_synthetic_events.py \
  --input-path /path/to/persona-book-candidates \
  --output-path /path/to/synthetic_events.jsonl
```

기본 생성 개수는 persona당 아래와 같습니다.

```text
READ 20
READING 3
PREFERRED 20
DISLIKED 20
```

## 팀원별 후보 파일 합치기

```bash
python script/generate_synthetic_events.py \
  --input-path /path/to/team-a/candidates \
  --input-path /path/to/team-b/candidates \
  --input-path /path/to/team-c/candidates \
  --output-path /path/to/synthetic_events.jsonl
```

## 필드명이 다른 경우

```bash
python script/generate_synthetic_events.py \
  --input-path /path/to/candidates.jsonl \
  --output-path /path/to/synthetic_events.jsonl \
  --user-field "personaUserId" \
  --item-field "isbn" \
  --event-type-field "behaviorType"
```

## 생성 개수 변경

```bash
python script/generate_synthetic_events.py \
  --input-path /path/to/candidates \
  --output-path /path/to/synthetic_events.jsonl \
  --event-counts "READ:20,READING:3,PREFERRED:20,DISLIKED:20"
```

## 가중치 변경

`DISLIKED`는 LightFM WARP positive 학습에 직접 넣지 않는 전제라 기본 `final_weight=0.0`으로 생성됩니다. 학습 스크립트에서도 `DISLIKED`는 제외 대상입니다.

```bash
python script/generate_synthetic_events.py \
  --input-path /path/to/candidates \
  --output-path /path/to/synthetic_events.jsonl \
  --event-weights "READ:1.0,READING:3.0,PREFERRED:3.0,DISLIKED:0.0" \
  --source-weight 0.4
```

## 개수 부족 시 실패시키기

검증 단계에서는 persona별 후보 수가 부족하면 바로 실패하게 하는 것이 좋습니다.

```bash
python script/generate_synthetic_events.py \
  --input-path /path/to/candidates \
  --output-path /path/to/synthetic_events.jsonl \
  --strict-counts
```

## LightFM 학습 연결

```bash
python script/train_lightfm.py \
  --events-path /path/to/synthetic_events.jsonl \
  --output-dir artifacts/lightfm/latest
```
