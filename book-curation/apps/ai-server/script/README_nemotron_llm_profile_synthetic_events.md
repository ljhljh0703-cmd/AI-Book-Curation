# Nemotron Persona LLM Profile Synthetic Events

이 파이프라인은 Nemotron persona 원문을 그대로 Qdrant에 넣지 않고, 현재 ai-server의 CLOVA LLM 설정으로 persona별 독서 성향 프로필을 먼저 생성한 뒤, action별 검색 문장으로 `books_kure`를 조회해 LightFM 학습용 합성 행동 데이터를 생성합니다.

## 구조

```text
Nemotron-Personas-Korea streaming
→ CLOVA LLM persona reading profile JSON 생성
→ interest / reading_now / read_completed / dislike action별 search text 생성
→ KURE embedding
→ Qdrant books_kure read-only vector search
→ LightFM-ready synthetic event JSONL 생성
```

LLM은 실제 책을 만들지 않습니다. 실제 도서 후보는 반드시 Qdrant `books_kure` payload에서 읽습니다.

## 1. 의존성 설치

Windows Git Bash 기준입니다.

```bash
cd apps/ai-server
py -3.11 -m pip install -r requirements-synthetic-data.txt
```

`.env.local`에 아래 값이 있어야 합니다.

```env
CLOVA_API_KEY=...
CLOVA_CHAT_URL=...
CLOVA_CHAT_MODEL=...
KURE_EMBEDDING_BASE_URL=http://localhost:8002
QDRANT_URL=...
QDRANT_API_KEY=...
QDRANT_KURE_COLLECTION=books_kure
```

## 2. 100명 LLM profile 생성

```bash
cd apps/ai-server
mkdir -p data/persona data/lightfm

py -3.11 script/enrich_nemotron_persona_profiles.py \
  --sample-size 100 \
  --resume \
  --failure-policy skip \
  --max-failed-personas 50 \
  --failure-cooldown-seconds 5 \
  --max-source-scan 500 \
  --llm-min-interval-seconds 1.2 \
  --output-persona-subset-path data/persona/persona_subset_100.jsonl \
  --output-profile-path data/persona/persona_profiles_llm_100.jsonl
```

확인:

```bash
wc -l data/persona/persona_profiles_llm_100.jsonl
head -n 1 data/persona/persona_profiles_llm_100.jsonl
```

## 3. 100명 × 63개 합성 행동 생성

```bash
py -3.11 script/generate_nemotron_profile_synthetic_events.py \
  --persona-profile-path data/persona/persona_profiles_llm_100.jsonl \
  --sample-size 100 \
  --patterns 1 \
  --strict-counts \
  --action-candidate-limit 80 \
  --action-candidate-multiplier 2 \
  --action-candidate-extra 20 \
  --qdrant-timeout-seconds 60 \
  --qdrant-search-retries 5 \
  --qdrant-retry-backoff-seconds 1 \
  --qdrant-search-delay-seconds 0.03 \
  --failure-policy skip \
  --max-failed-personas 50 \
  --failure-cooldown-seconds 5 \
  --resume \
  --output-candidates-path data/lightfm/nemotron_profile_candidates_100.jsonl \
  --output-events-path data/lightfm/nemotron_profile_synthetic_events_100x63.jsonl
```

정상 기대값:

```text
profiles: 100
synthetic events: 6300
```

## 4. 1000명 LLM profile 생성

1000명은 LLM 호출이 1000회라 오래 걸립니다. 중간에 멈춰도 `--resume`으로 이어서 실행할 수 있습니다.

```bash
py -3.11 script/enrich_nemotron_persona_profiles.py \
  --sample-size 1000 \
  --resume \
  --failure-policy skip \
  --max-failed-personas 200 \
  --failure-cooldown-seconds 5 \
  --max-source-scan 3000 \
  --llm-min-interval-seconds 1.2 \
  --output-persona-subset-path data/persona/persona_subset_1000.jsonl \
  --output-profile-path data/persona/persona_profiles_llm_1000.jsonl
```

## 5. 1000명 × 63개 합성 행동 생성

```bash
py -3.11 script/generate_nemotron_profile_synthetic_events.py \
  --persona-profile-path data/persona/persona_profiles_llm_1000.jsonl \
  --sample-size 1000 \
  --patterns 1 \
  --strict-counts \
  --action-candidate-limit 80 \
  --action-candidate-multiplier 2 \
  --action-candidate-extra 20 \
  --qdrant-timeout-seconds 60 \
  --qdrant-search-retries 5 \
  --qdrant-retry-backoff-seconds 1 \
  --qdrant-search-delay-seconds 0.03 \
  --failure-policy skip \
  --max-failed-personas 200 \
  --failure-cooldown-seconds 5 \
  --resume \
  --output-candidates-path data/lightfm/nemotron_profile_candidates_1000.jsonl \
  --output-events-path data/lightfm/nemotron_profile_synthetic_events_1000x63.jsonl
```

## 6. 결과 검증

```bash
wc -l data/persona/persona_profiles_llm_1000.jsonl
wc -l data/lightfm/nemotron_profile_synthetic_events_1000x63.jsonl

py -3.11 - <<'PY'
import json
from collections import Counter

path = "data/lightfm/nemotron_profile_synthetic_events_1000x63.jsonl"
users = set()
events = Counter()
rating_count = 0
review_count = 0

with open(path, "r", encoding="utf-8") as f:
    for line in f:
        row = json.loads(line)
        users.add(row["user_key"])
        events[row["event_type"]] += 1
        rating_count += 1 if row.get("has_rating") else 0
        review_count += 1 if row.get("has_review") else 0

print("users:", len(users))
print("events:", dict(events))
print("has_rating:", rating_count)
print("has_review:", review_count)
print("total:", sum(events.values()))
PY
```

1000명 기준 기대값입니다.

```text
users: 1000
FAVORITE_ADD: 20000
READING_ADD: 3000
READ_ADD: 20000
DISLIKE_ADD: 20000
has_rating: 10000
has_review: 10000
total: 63000
```

## 7. LightFM 학습

Windows에서 LightFM 설치가 실패하면 WSL/Linux/Colab에서 학습하세요.

```bash
py -3.11 script/train_lightfm.py \
  --events-path data/lightfm/nemotron_profile_synthetic_events_1000x63.jsonl \
  --output-dir artifacts/lightfm/nemotron_profile_1000x63 \
  --loss warp \
  --epochs 30 \
  --components 64 \
  --learning-rate 0.05 \
  --num-threads 2
```

검증:

```bash
py -3.11 script/validate_lightfm_artifact.py \
  --artifact-dir artifacts/lightfm/nemotron_profile_1000x63
```

## resume 기준

두 단계 모두 `--resume`이 있습니다.

- profile 생성 단계는 `output-profile-path` 기준으로 완료 persona를 건너뜁니다.
- event 생성 단계는 `output-events-path` 기준으로 완료 persona를 건너뜁니다.

중간에 `Ctrl + C`로 멈춘 뒤 같은 명령어를 다시 실행하면 이어서 진행합니다.
