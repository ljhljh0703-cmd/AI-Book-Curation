# LightFM 50개 후보 → 20개 압축 평가

## 목적

기존 `train_evaluate_lightfm_701_hybrid.py`는 전체 item universe에서 `Top-K`를 평가했다.
이번 수정은 운영 구조에 맞춰 아래 상황을 별도로 평가하기 위한 것이다.

```text
Qdrant / 룰베이스 후보 50개
→ LightFM score로 정렬
→ 상위 20개만 선택
→ 이후 최종 리랭커 또는 응답 로직으로 전달
```

즉, LightFM을 최종 Top-10 추천기가 아니라 **후보 압축기(candidate compressor)** 로 사용할 때의 성능을 확인한다.

## 추가된 CLI 옵션

| 옵션 | 의미 | 예시 |
|---|---|---|
| `--candidate-eval-pool-size` | 사용자별 후보 pool 크기 | `50` |
| `--candidate-eval-top-k` | 후보 pool에서 LightFM이 남길 개수 | `20` |
| `--candidate-eval-random-state` | 후보 pool에 neutral item을 채울 때 사용하는 seed | `42` |

`--candidate-eval-pool-size`가 `0`이면 기존 전체 item 기준 평가만 수행한다.

## 평가 방식

이 평가는 Qdrant를 다시 호출하지 않는다.
대신 각 사용자별 후보 pool을 다음 방식으로 구성한다.

1. held-out positive item을 후보 pool에 포함한다.
2. held-out dislike item을 후보 pool에 포함한다.
3. 나머지 자리는 학습에 사용된 positive item을 제외한 neutral item으로 채운다.
4. LightFM이 해당 후보 pool만 scoring한다.
5. 후보 50개 중 상위 20개를 선택한다.
6. 상위 20개 안에 positive/dislike가 얼마나 남았는지 측정한다.

따라서 이 평가는 운영의 Qdrant/룰베이스 후보 50개를 완전히 재현하는 것은 아니며, **LightFM이 50개 후보 안에서 20개를 남기는 압축 능력을 보기 위한 offline approximation**이다.

## 추가되는 metric 예시

`--candidate-eval-pool-size 50 --candidate-eval-top-k 20`을 주면 `metrics.json`에 아래와 같은 metric이 추가된다.

| Metric | 의미 | 판단 방향 |
|---|---|---|
| `positive_candidate@20_in_50_hit_rate` | 50개 중 20개를 남겼을 때 positive가 1개 이상 남은 사용자 비율 | 높을수록 좋음 |
| `positive_candidate@20_in_50_precision` | 남긴 20개 중 positive 비율 | 높을수록 좋음 |
| `positive_candidate@20_in_50_recall` | 후보 pool에 있던 positive 중 20개 안에 남은 비율 | 높을수록 좋음 |
| `dislike_candidate@20_in_50_hit_rate` | 남긴 20개 안에 dislike가 1개 이상 포함된 사용자 비율 | 낮을수록 좋음 |
| `dislike_candidate@20_in_50_item_rate` | 남긴 20개 중 dislike item 비율 | 낮을수록 좋음 |

후보 압축 단계에서는 특히 `positive_candidate@20_in_50_recall`과 `dislike_candidate@20_in_50_hit_rate`를 중요하게 본다.

## 기존 dataset + identity-only 50→20 평가

```bash
python -u script/train_evaluate_lightfm_701_hybrid.py \
  --events-path data/lightfm/nemotron_rule_based_synthetic_events_1000x63.jsonl \
  --output-dir artifacts/lightfm/nemotron_rule_based_1000x63_identity_50to20_eval \
  --feature-mode identity \
  --loss warp \
  --epochs 40 \
  --components 32 \
  --learning-rate 0.03 \
  --num-threads 8 \
  --k 20 \
  --candidate-eval-pool-size 50 \
  --candidate-eval-top-k 20 \
  --train-ratio 0.7 \
  --validation-ratio 0.2 \
  --test-ratio 0.1 \
  --excluded-event-types DISLIKE_ADD,DISLIKE_REMOVE,DISLIKED,NOT_INTERESTED,UNLIKE,BLOCK,NEGATIVE \
  --dislike-event-types DISLIKE_ADD,DISLIKED,NOT_INTERESTED,NEGATIVE
```

## 기존 dataset + hybrid-lite 50→20 평가

```bash
python -u script/train_evaluate_lightfm_701_hybrid_lite.py \
  --events-path data/lightfm/nemotron_rule_based_synthetic_events_1000x63.jsonl \
  --output-dir artifacts/lightfm/nemotron_rule_based_1000x63_hybrid_lite_50to20_eval \
  --loss warp \
  --epochs 40 \
  --components 32 \
  --learning-rate 0.03 \
  --item-alpha 1e-6 \
  --user-alpha 1e-6 \
  --num-threads 8 \
  --k 20 \
  --candidate-eval-pool-size 50 \
  --candidate-eval-top-k 20 \
  --train-ratio 0.7 \
  --validation-ratio 0.2 \
  --test-ratio 0.1 \
  --excluded-event-types DISLIKE_ADD,DISLIKE_REMOVE,DISLIKED,NOT_INTERESTED,UNLIKE,BLOCK,NEGATIVE \
  --dislike-event-types DISLIKE_ADD,DISLIKED,NOT_INTERESTED,NEGATIVE
```

## shared-pool dataset + identity-only 50→20 평가

```bash
python -u script/train_evaluate_lightfm_701_hybrid.py \
  --events-path data/lightfm/nemotron_rule_based_shared_synthetic_events_1000x63.jsonl \
  --output-dir artifacts/lightfm/nemotron_rule_based_shared_1000x63_identity_50to20_eval \
  --feature-mode identity \
  --loss warp \
  --epochs 40 \
  --components 32 \
  --learning-rate 0.03 \
  --num-threads 8 \
  --k 20 \
  --candidate-eval-pool-size 50 \
  --candidate-eval-top-k 20 \
  --train-ratio 0.7 \
  --validation-ratio 0.2 \
  --test-ratio 0.1 \
  --excluded-event-types DISLIKE_ADD,DISLIKE_REMOVE,DISLIKED,NOT_INTERESTED,UNLIKE,BLOCK,NEGATIVE \
  --dislike-event-types DISLIKE_ADD,DISLIKED,NOT_INTERESTED,NEGATIVE
```

## shared-pool dataset + hybrid-lite 50→20 평가

```bash
python -u script/train_evaluate_lightfm_701_hybrid_lite.py \
  --events-path data/lightfm/nemotron_rule_based_shared_synthetic_events_1000x63.jsonl \
  --output-dir artifacts/lightfm/nemotron_rule_based_shared_1000x63_hybrid_lite_50to20_eval \
  --loss warp \
  --epochs 40 \
  --components 32 \
  --learning-rate 0.03 \
  --item-alpha 1e-6 \
  --user-alpha 1e-6 \
  --num-threads 8 \
  --k 20 \
  --candidate-eval-pool-size 50 \
  --candidate-eval-top-k 20 \
  --train-ratio 0.7 \
  --validation-ratio 0.2 \
  --test-ratio 0.1 \
  --excluded-event-types DISLIKE_ADD,DISLIKE_REMOVE,DISLIKED,NOT_INTERESTED,UNLIKE,BLOCK,NEGATIVE \
  --dislike-event-types DISLIKE_ADD,DISLIKED,NOT_INTERESTED,NEGATIVE
```

## Colab에서 결과 확인

```bash
cat artifacts/lightfm/nemotron_rule_based_shared_1000x63_identity_50to20_eval/metrics.json
```

중점적으로 볼 값:

```text
positive_candidate@20_in_50_hit_rate
positive_candidate@20_in_50_precision
positive_candidate@20_in_50_recall
dislike_candidate@20_in_50_hit_rate
dislike_candidate@20_in_50_item_rate
```

## 주의사항

- 이 평가는 실제 Qdrant/룰베이스 후보 50개를 그대로 쓰는 것은 아니다.
- 운영 후보 생성기를 완전히 반영하려면 실제 추천 후보 50개 로그를 저장한 뒤, 그 후보 목록을 기준으로 평가하는 별도 evaluator가 필요하다.
- 현재 코드는 빠르게 모델별 후보 압축 능력을 비교하기 위한 offline approximation이다.
