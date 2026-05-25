# Nemotron persona subset + Qdrant 기반 LightFM synthetic event 생성

이 문서는 `nvidia/Nemotron-Personas-Korea`를 로컬 파일로 다운로드하지 않고 Hugging Face streaming으로 읽어 persona subset을 만들고, `books_kure` Qdrant 컬렉션에 이미 들어 있는 실제 도서 payload만 사용해 LightFM 학습용 합성 행동 데이터를 생성하는 절차입니다.

```text
Hugging Face streaming dataset
→ data/persona/persona_subset_*.jsonl
→ persona payload text를 KURE embedding으로 변환
→ Qdrant books_kure vector read/search + scroll 연결 검증
→ backend UserBehaviorEventType 기준 synthetic event JSONL
→ script/train_lightfm.py
```

## 현재 소스 기준 확인 결과

- `apps/ai-server/script` 폴더가 기존 학습/색인 스크립트 위치입니다. 별도 `scripts` 폴더가 아니라 `script`를 유지했습니다.
- `create_persona_subset.py`는 기존에 없어서 새로 추가했습니다.
- 기존 `generate_nemotron_persona_synthetic_events.py`는 `.env.local`을 자동 로드하지 않았기 때문에 수정했습니다.
- `train_lightfm.py`는 `user_key,user_id,persona_id`와 `isbn13,isbn,book_key,book_id,item_id`를 읽을 수 있는 구조라 synthetic JSONL을 바로 받을 수 있습니다.
- 현재 backend 행동 enum은 `FAVORITE_ADD`, `READING_ADD`, `READ_ADD`, `RATING_ADD`, `REVIEW_ADD`, `DISLIKE_ADD`입니다. synthetic event의 `event_type`은 이 값을 사용하고, 사람이 이해하기 쉬운 `action_type`은 별도 컬럼으로 같이 남깁니다.
- `books_kure` payload는 현재 KURE indexer 기준으로 `isbn`, `title`, `author`, `publisher`, `description`, `categories`, `cate_depth1`, `kcid`, `document` 등이 들어갑니다. 실제 LightFM item key는 우선순위 `book_id → item_id → isbn13 → isbn → id`로 잡고, 현재 컬렉션에서는 보통 `isbn`이 사용됩니다.

## 설치

### A. persona subset / synthetic event 생성만 할 때

Git Bash에서 `apps/ai-server`로 이동한 뒤 실행합니다. 이 단계에서는 LightFM을 설치하지 않습니다.

```bash
cd apps/ai-server
py -3.11 -m pip install --upgrade pip setuptools wheel
py -3.11 -m pip install -r requirements-synthetic-data.txt
```

`create_persona_subset.py`와 `generate_nemotron_persona_synthetic_events.py`는 Hugging Face streaming, Qdrant read, KURE embedding 호출만 필요하므로 `requirements-synthetic-data.txt`만으로 실행됩니다.

### B. LightFM 학습까지 로컬에서 할 때

LightFM은 C 확장 모듈을 빌드하는 패키지라 Windows에서는 컴파일러/빌드 도구 상태에 따라 설치가 실패할 수 있습니다. 먼저 아래를 실행합니다.

```bash
cd apps/ai-server
py -3.11 -m pip install --upgrade pip setuptools wheel cython
py -3.11 -m pip install -r requirements-lightfm-training.txt
```

위 명령에서 `AttributeError: 'dict' object has no attribute '__LIGHTFM_SETUP__'`가 계속 발생하면, synthetic event 생성은 `requirements-synthetic-data.txt`로 진행하고 LightFM 학습은 Colab/WSL/Linux 환경에서 실행하는 것을 권장합니다.

## 환경변수

`apps/ai-server/.env.local`을 자동으로 읽습니다. 명령어에 키값을 직접 쓰지 마세요.

필수 확인 항목:

```bash
cd apps/ai-server

py -3.11 - <<'PY'
from dotenv import dotenv_values
for key in [
    "QDRANT_URL",
    "QDRANT_API_KEY",
    "QDRANT_KURE_COLLECTION",
    "KURE_EMBEDDING_BASE_URL",
    "KURE_INTERNAL_API_KEY",
    "KURE_INTERNAL_HEADER_NAME",
]:
    value = dotenv_values(".env.local").get(key)
    print(key, "=", "SET" if value else "EMPTY")
PY
```

## 1. persona subset만 생성

### 10명 테스트

```bash
cd apps/ai-server
mkdir -p data/persona

py -3.11 script/create_persona_subset.py \
  --sample-size 10 \
  --seed 42 \
  --shuffle-buffer-size 10000 \
  --output-path data/persona/persona_subset_10.jsonl
```

### 100명 생성

```bash
cd apps/ai-server
mkdir -p data/persona

py -3.11 script/create_persona_subset.py \
  --sample-size 100 \
  --seed 42 \
  --shuffle-buffer-size 10000 \
  --output-path data/persona/persona_subset_100.jsonl
```

확인:

```bash
wc -l data/persona/persona_subset_10.jsonl
head -n 2 data/persona/persona_subset_10.jsonl
```

## 2. persona subset + synthetic interaction events 동시 생성

이 명령은 Hugging Face streaming으로 persona를 읽고, Qdrant `books_kure`에서 실제 도서만 읽어서 합성 이벤트를 생성합니다. Qdrant에는 upsert/write를 하지 않습니다.

### 10명 × 63개 = 630건 테스트

```bash
cd apps/ai-server
mkdir -p data/persona data/lightfm

py -3.11 script/generate_nemotron_persona_synthetic_events.py \
  --sample-size 10 \
  --patterns 1 \
  --strict-counts \
  --output-persona-subset-path data/persona/persona_subset_10.jsonl \
  --output-candidates-path data/lightfm/nemotron_candidates_10.jsonl \
  --output-events-path data/lightfm/nemotron_synthetic_events_10x63.jsonl
```

### 100명 × 63개 = 6,300건

```bash
cd apps/ai-server
mkdir -p data/persona data/lightfm

py -3.11 script/generate_nemotron_persona_synthetic_events.py \
  --sample-size 100 \
  --patterns 1 \
  --strict-counts \
  --output-persona-subset-path data/persona/persona_subset_100.jsonl \
  --output-candidates-path data/lightfm/nemotron_candidates_100.jsonl \
  --output-events-path data/lightfm/nemotron_synthetic_events_100x63.jsonl
```

### 100명 × 63개 × 10패턴 = 63,000건

```bash
cd apps/ai-server
mkdir -p data/persona data/lightfm

py -3.11 script/generate_nemotron_persona_synthetic_events.py \
  --sample-size 100 \
  --patterns 10 \
  --candidate-pool-size 1600 \
  --strict-counts \
  --output-persona-subset-path data/persona/persona_subset_100.jsonl \
  --output-candidates-path data/lightfm/nemotron_candidates_100x10patterns.jsonl \
  --output-events-path data/lightfm/nemotron_synthetic_events_100x63x10.jsonl
```

## 3. 생성 파일 확인

```bash
wc -l data/persona/persona_subset_100.jsonl
wc -l data/lightfm/nemotron_synthetic_events_100x63.jsonl
head -n 2 data/lightfm/nemotron_synthetic_events_100x63.jsonl
```

이벤트 타입별 개수 확인:

```bash
py -3.11 - <<'PY'
import json
from collections import Counter

path = "data/lightfm/nemotron_synthetic_events_100x63.jsonl"
users = set()
counter = Counter()

with open(path, "r", encoding="utf-8") as f:
    for line in f:
        row = json.loads(line)
        users.add(row["user_key"])
        counter[row["event_type"]] += 1

print("user_count:", len(users))
print("event_counts:", dict(counter))
print("total:", sum(counter.values()))
PY
```

## 4. LightFM 학습

```bash
cd apps/ai-server
mkdir -p artifacts/lightfm

py -3.11 script/train_lightfm.py \
  --events-path data/lightfm/nemotron_synthetic_events_100x63.jsonl \
  --output-dir artifacts/lightfm/nemotron_100x63 \
  --loss warp \
  --epochs 30 \
  --components 64 \
  --learning-rate 0.05 \
  --num-threads 2
```

검증:

```bash
py -3.11 script/validate_lightfm_artifact.py \
  --artifact-dir artifacts/lightfm/nemotron_100x63
```

운영에서 이 artifact를 보게 하려면 배포 환경의 `LIGHTFM_ARTIFACT_PATH`가 해당 디렉터리를 바라보게 해야 합니다.

## 옵션 조정

기본 63건 구성은 아래입니다.

```text
FAVORITE_ADD:20,READING_ADD:3,READ_ADD:10,RATING_ADD:10,REVIEW_ADD:10,DISLIKE_ADD:10
```

변경 예시:

```bash
py -3.11 script/generate_nemotron_persona_synthetic_events.py \
  --sample-size 10 \
  --event-counts "FAVORITE_ADD:20,READING_ADD:3,READ_ADD:20,RATING_ADD:5,REVIEW_ADD:5,DISLIKE_ADD:10" \
  --output-events-path data/lightfm/custom_events.jsonl
```

`DISLIKE_ADD`는 `train_lightfm.py`의 기본 excluded event type에 포함되어 WARP positive interaction 학습에서는 제외됩니다. 파일에는 남겨두기 때문에 이후 negative evaluation/filter/penalty 용도로 확장할 수 있습니다.

## 오류 확인 포인트

- `datasets 패키지가 없습니다`: `py -3.11 -m pip install -r requirements-synthetic-data.txt` 실행
- `LightFM 설치 중 AttributeError: 'dict' object has no attribute '__LIGHTFM_SETUP__'`: 데이터 생성 단계에서는 `requirements-synthetic-data.txt`만 설치하고, 학습은 Colab/WSL/Linux 환경에서 진행
- `Qdrant 연결 확인에 실패`: `QDRANT_URL`, `QDRANT_API_KEY`, Tailscale/NodePort 접근성 확인
- `Qdrant 컬렉션이 없습니다`: `QDRANT_KURE_COLLECTION=books_kure` 확인
- `KURE embedding 호출에 실패`: `KURE_EMBEDDING_BASE_URL`, 내부 API key/header 확인
- `후보가 부족합니다`: `--candidate-pool-size`를 늘리거나 `--strict-counts` 제거
