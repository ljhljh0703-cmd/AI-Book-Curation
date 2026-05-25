# Nemotron LLM Profile + Rule-Based Shared Pool Synthetic Events

## 목적

기존 `persona_profiles_llm_1000.jsonl`은 그대로 재사용하고, 3단계 합성 행동 데이터 생성에서만 사용자 간 item overlap을 늘립니다.

기존 방식은 각 persona가 개인 Qdrant 후보만 사용해서 사용자별 도서가 지나치게 고립될 수 있었습니다. 이 방식은 LightFM identity-only 협업 필터링이 사용자 간 관계를 학습하기 어렵게 만듭니다.

이번 shared pool 방식은 다음 비율로 후보를 섞습니다.

```text
개인 후보: LLM profile action text로 조회한 개인 Qdrant 후보
그룹 공유 후보: 같은 age_group + profile hash bucket 그룹의 shared query로 조회한 후보
전역 공유 후보: 전체 LLM profile에서 만든 shared query로 조회한 후보
```

기본 비율은 다음과 같습니다.

```text
personal: 약 70%
group shared: 약 25%
global shared: 약 5%
```

개인화는 유지하면서, 비슷한 사용자에게 일부 같은 책이 반복 등장하도록 만드는 것이 목적입니다.

## 실행 전제

- `data/persona/persona_profiles_llm_1000.jsonl` 생성 완료
- KURE embedding server 실행 중
- `apps/ai-server/.env.local`에 Qdrant/KURE 환경변수 존재
- Qdrant 컬렉션: `books_kure`

## 기존 rule-based output 백업

기존 파일과 섞이지 않도록 새 파일명 사용을 권장합니다.

```bash
cd apps/ai-server
mkdir -p data/lightfm
```

## 1000명 shared pool 합성데이터 생성

```bash
python script/generate_nemotron_rule_based_synthetic_events.py \
  --persona-profile-path data/persona/persona_profiles_llm_1000.jsonl \
  --sample-size 1000 \
  --patterns 1 \
  --strict-counts \
  --rule-mode PROFILE_FIRST \
  --action-candidate-limit 120 \
  --action-candidate-multiplier 3 \
  --action-candidate-extra 40 \
  --enable-shared-pools \
  --shared-group-ratio 0.25 \
  --shared-global-ratio 0.05 \
  --shared-group-buckets 12 \
  --shared-group-query-profiles 12 \
  --shared-global-query-profiles 48 \
  --shared-pool-candidate-limit 120 \
  --shared-query-max-chars 1800 \
  --qdrant-timeout-seconds 60 \
  --qdrant-search-retries 5 \
  --qdrant-retry-backoff-seconds 1 \
  --qdrant-search-delay-seconds 0.03 \
  --failure-policy skip \
  --max-failed-personas 200 \
  --failure-cooldown-seconds 5 \
  --resume \
  --output-candidates-path data/lightfm/nemotron_rule_based_shared_candidates_1000.jsonl \
  --output-events-path data/lightfm/nemotron_rule_based_shared_synthetic_events_1000x63.jsonl
```

## 결과 확인

```bash
wc -l data/lightfm/nemotron_rule_based_shared_synthetic_events_1000x63.jsonl
```

정상 기대값:

```text
63000
```

candidate pool scope 분포 확인:

```bash
python - <<'PY'
import json
from collections import Counter

path = "data/lightfm/nemotron_rule_based_shared_synthetic_events_1000x63.jsonl"
scopes = Counter()
events = Counter()
users = set()
items = Counter()

with open(path, "r", encoding="utf-8") as f:
    for line in f:
        row = json.loads(line)
        users.add(row.get("user_key"))
        events[row.get("event_type")] += 1
        scopes[row.get("candidate_pool_scope")] += 1
        items[row.get("item_id"))] += 1

print("users:", len(users))
print("events:", dict(events))
print("scopes:", dict(scopes))
print("unique_items:", len(items))
print("top_repeated_items:", items.most_common(10))
PY
```

> 위 명령어에 오타가 있다면 `items[row.get("item_id")] += 1`로 고쳐 실행하세요.

간단 버전:

```bash
python - <<'PY'
import json
from collections import Counter
path = "data/lightfm/nemotron_rule_based_shared_synthetic_events_1000x63.jsonl"
scopes = Counter()
items = Counter()
rows = 0
with open(path, "r", encoding="utf-8") as f:
    for line in f:
        row = json.loads(line)
        scopes[row.get("candidate_pool_scope")] += 1
        items[row.get("item_id")] += 1
        rows += 1
print("rows:", rows)
print("scopes:", dict(scopes))
print("unique_items:", len(items))
print("top_repeated_items:", items.most_common(10))
PY
```

## Colab 학습용 bundle 생성

identity-only 평가/학습부터 다시 비교하는 것을 권장합니다.

```bash
cd apps/ai-server

rm -rf colab_lightfm_shared_bundle
mkdir -p colab_lightfm_shared_bundle/script
mkdir -p colab_lightfm_shared_bundle/data/lightfm
mkdir -p colab_lightfm_shared_bundle/artifacts/lightfm

cp script/train_evaluate_lightfm_701_hybrid.py colab_lightfm_shared_bundle/script/
cp script/train_evaluate_lightfm_701_hybrid_lite.py colab_lightfm_shared_bundle/script/ 2>/dev/null
cp data/lightfm/nemotron_rule_based_shared_synthetic_events_1000x63.jsonl \
  colab_lightfm_shared_bundle/data/lightfm/

tar -czf colab_lightfm_shared_bundle.tar.gz colab_lightfm_shared_bundle
ls -lh colab_lightfm_shared_bundle.tar.gz
```

## Colab identity-only 평가

```python
!mamba run -n lightfm311 python -u script/train_evaluate_lightfm_701_hybrid.py \
  --events-path data/lightfm/nemotron_rule_based_shared_synthetic_events_1000x63.jsonl \
  --output-dir artifacts/lightfm/nemotron_rule_based_shared_1000x63_701_identity_eval \
  --feature-mode identity \
  --loss warp \
  --epochs 40 \
  --components 32 \
  --learning-rate 0.03 \
  --num-threads 8 \
  --k 10 \
  --train-ratio 0.7 \
  --validation-ratio 0.2 \
  --test-ratio 0.1 \
  --excluded-event-types DISLIKE_ADD,DISLIKE_REMOVE,DISLIKED,NOT_INTERESTED,UNLIKE,BLOCK,NEGATIVE \
  --dislike-event-types DISLIKE_ADD,DISLIKED,NOT_INTERESTED,NEGATIVE
```

## Colab hybrid-lite 평가

shared pool 데이터는 identity-only 성능 개선을 먼저 기대합니다. 그 후 hybrid-lite도 비교합니다.

```python
!mamba run -n lightfm311 python -u script/train_evaluate_lightfm_701_hybrid_lite.py \
  --events-path data/lightfm/nemotron_rule_based_shared_synthetic_events_1000x63.jsonl \
  --output-dir artifacts/lightfm/nemotron_rule_based_shared_1000x63_701_hybrid_lite_eval \
  --loss warp \
  --epochs 40 \
  --components 32 \
  --learning-rate 0.03 \
  --item-alpha 1e-6 \
  --user-alpha 1e-6 \
  --num-threads 8 \
  --k 10 \
  --train-ratio 0.7 \
  --validation-ratio 0.2 \
  --test-ratio 0.1 \
  --excluded-event-types DISLIKE_ADD,DISLIKE_REMOVE,DISLIKED,NOT_INTERESTED,UNLIKE,BLOCK,NEGATIVE \
  --dislike-event-types DISLIKE_ADD,DISLIKED,NOT_INTERESTED,NEGATIVE
```

## 판단 기준

기존 identity-only final 기준:

```text
TEST auc ~= 0.785
TEST positive_hit_rate@10 ~= 0.320
TEST positive_precision@10 ~= 0.0273
TEST positive_recall@10 ~= 0.06825
TEST dislike_hit_rate@10 ~= 0.003
```

shared pool 데이터로 이 값을 넘으면 shared pool 방식이 개선된 것입니다.

## 주의

- shared pool은 평가를 쉽게 만들기 위한 복제 데이터가 아닙니다.
- 같은 persona를 여러 user로 복제하지 않고, 1000명의 서로 다른 LLM profile을 유지합니다.
- 비슷한 사용자끼리만 일부 도서를 공유하게 만들어 협업 필터링 신호를 보강합니다.
- `DISLIKE_ADD`는 학습 positive interaction에서 제외하고 evaluation negative label로만 사용합니다.
