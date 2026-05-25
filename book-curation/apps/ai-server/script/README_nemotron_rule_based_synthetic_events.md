# Nemotron LLM Profile → Rule-Based Teacher Synthetic Events

이 문서는 `persona_profiles_llm_*.jsonl` 생성이 끝난 뒤, 현재 `ai-server`의 `ProfileReranker` 룰베이스 점수를 teacher signal로 사용해 LightFM 학습용 합성 행동 데이터를 만드는 실행 절차입니다.

## 구조

```text
1. Nemotron persona subset 생성
2. LLM으로 persona 독서 프로필 생성
3. LLM profile search text로 Qdrant books_kure 후보 조회
4. 현재 app/services/recommendation/profile_reranker.py 룰베이스로 후보 재정렬
5. rule score 상위 후보 → 관심/읽는중/읽은책
6. rule score 하위 후보 → 비선호
7. LightFM 학습용 JSONL 저장
```

주의: 이 스크립트는 LLM이 책을 직접 만들지 않습니다. 실제 책은 항상 Qdrant `books_kure`의 payload에서만 가져옵니다.

## 100명 테스트

```bash
cd apps/ai-server
source .venv/Scripts/activate
mkdir -p data/persona data/lightfm

python script/generate_nemotron_rule_based_synthetic_events.py \
  --persona-profile-path data/persona/persona_profiles_llm_100.jsonl \
  --sample-size 100 \
  --patterns 1 \
  --strict-counts \
  --rule-mode PROFILE_FIRST \
  --action-candidate-limit 120 \
  --action-candidate-multiplier 3 \
  --action-candidate-extra 40 \
  --qdrant-timeout-seconds 60 \
  --qdrant-search-retries 5 \
  --qdrant-retry-backoff-seconds 1 \
  --qdrant-search-delay-seconds 0.03 \
  --failure-policy skip \
  --max-failed-personas 50 \
  --failure-cooldown-seconds 5 \
  --resume \
  --output-candidates-path data/lightfm/nemotron_rule_based_candidates_100.jsonl \
  --output-events-path data/lightfm/nemotron_rule_based_synthetic_events_100x63.jsonl
```

확인:

```bash
wc -l data/lightfm/nemotron_rule_based_synthetic_events_100x63.jsonl
```

정상 기대값은 `6300`입니다.

## 1000명 본작업

```bash
cd apps/ai-server
source .venv/Scripts/activate
mkdir -p data/persona data/lightfm

python script/generate_nemotron_rule_based_synthetic_events.py \
  --persona-profile-path data/persona/persona_profiles_llm_1000.jsonl \
  --sample-size 1000 \
  --patterns 1 \
  --strict-counts \
  --rule-mode PROFILE_FIRST \
  --action-candidate-limit 120 \
  --action-candidate-multiplier 3 \
  --action-candidate-extra 40 \
  --qdrant-timeout-seconds 60 \
  --qdrant-search-retries 5 \
  --qdrant-retry-backoff-seconds 1 \
  --qdrant-search-delay-seconds 0.03 \
  --failure-policy skip \
  --max-failed-personas 200 \
  --failure-cooldown-seconds 5 \
  --resume \
  --output-candidates-path data/lightfm/nemotron_rule_based_candidates_1000.jsonl \
  --output-events-path data/lightfm/nemotron_rule_based_synthetic_events_1000x63.jsonl
```

확인:

```bash
wc -l data/lightfm/nemotron_rule_based_synthetic_events_1000x63.jsonl
```

정상 기대값은 `63000`입니다.

## 진행률 확인

```bash
python - <<'PY'
import json
from collections import Counter

path = "data/lightfm/nemotron_rule_based_synthetic_events_1000x63.jsonl"
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

1000명 기준 정상 기대값:

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

## 중간 중지와 재실행

`--resume`을 사용하면 기존 output events 파일을 읽고 이미 완료된 persona는 건너뜁니다.

중지:

```text
Ctrl + C
```

재개:

```bash
# 같은 명령어를 그대로 다시 실행
```

## LightFM 학습

`DISLIKE_ADD`는 positive interaction이 아니므로 학습에서 제외해야 합니다. 최신 `train_lightfm.py` 기본값에는 `DISLIKE_ADD`가 제외 목록에 포함되어 있습니다. 명령어에서 명시하고 싶다면 아래처럼 실행하세요.

```bash
python script/train_lightfm.py \
  --events-path data/lightfm/nemotron_rule_based_synthetic_events_1000x63.jsonl \
  --output-dir artifacts/lightfm/nemotron_rule_based_1000x63 \
  --loss warp \
  --epochs 30 \
  --components 64 \
  --learning-rate 0.05 \
  --num-threads 2 \
  --excluded-event-types DISLIKE_ADD,DISLIKE_REMOVE,DISLIKED,NOT_INTERESTED,UNLIKE,BLOCK,NEGATIVE
```

## Age group 반영

`generate_nemotron_rule_based_synthetic_events.py`는 Nemotron 원본 `persona_fields`의 `age` 계열 값을 읽어 현재 `ProfileReranker`가 사용하는 audience group으로 변환합니다.

```text
0~12   -> CHILD
13~18  -> TEEN
19~29  -> YOUNG_ADULT
30~64  -> ADULT
65~    -> SENIOR
```

이 값은 룰베이스 입력의 `demographicProfile.userAgeGroup`, `userAgeGroup`, `ageGroup`으로 전달됩니다. 따라서 현재 `profile_reranker.py`의 audience alignment 점수/패널티가 합성데이터 생성에도 반영됩니다.

기본값은 활성화입니다. 끄고 싶을 때만 아래 옵션을 추가합니다.

```bash
--no-enable-age-group
```

생성 이벤트에는 확인용으로 아래 필드가 추가됩니다.

```text
user_age
user_age_group
age_group_source
```

## LLM profile JSONL의 `\"` 표기

JSONL 원문에서 보이는 `\"`는 대부분 JSON 문자열 내부 따옴표를 표현하기 위한 escape입니다. 원본 파일에서 전역 replace로 `\"`를 `"`로 바꾸면 JSON 문법이 깨질 수 있습니다.

이 스크립트는 `json.loads` 이후 Python 문자열 상태에서만 이중 인코딩된 따옴표를 정리합니다. 따라서 `persona_profiles_llm_*.jsonl` 파일을 직접 치환하지 마세요.
