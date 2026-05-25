# LightFM 7:2:1 Hybrid-Lite Evaluation

이 스크립트는 기존 `train_evaluate_lightfm_701_hybrid.py`를 재사용하되, 기본 feature set을 더 보수적으로 제한한 실행 진입점입니다.

## 왜 hybrid-lite가 필요한가

기존 full hybrid는 LLM profile text, title, description token을 많이 넣을 수 있어 작은 합성 데이터셋에서는 feature 공간이 커지고 identity feature가 희석될 수 있습니다. 실제 fast evaluation에서 identity-only보다 Top-K 지표가 낮아졌으므로, 먼저 다음 구조로 줄여서 재실험합니다.

- user feature: `user_age_group`, `rule_mode`, `profile_strategy`, `profile_schema_version`
- item feature: `category`, `categories`
- text token feature: 기본 비활성화
- feature matrix normalization: 기본 비활성화
- DISLIKE 이벤트: positive 학습 제외, negative avoidance 평가에만 사용

## 로컬에서 Colab bundle 생성

`apps/ai-server`에서 실행합니다.

```bash
cd /c/book-curation/apps/ai-server

wc -l data/lightfm/nemotron_rule_based_synthetic_events_1000x63.jsonl

rm -rf colab_lightfm_hybrid_lite_bundle
mkdir -p colab_lightfm_hybrid_lite_bundle/script
mkdir -p colab_lightfm_hybrid_lite_bundle/data/lightfm
mkdir -p colab_lightfm_hybrid_lite_bundle/artifacts/lightfm

cp script/train_evaluate_lightfm_701_hybrid.py colab_lightfm_hybrid_lite_bundle/script/
cp script/train_evaluate_lightfm_701_hybrid_lite.py colab_lightfm_hybrid_lite_bundle/script/
cp data/lightfm/nemotron_rule_based_synthetic_events_1000x63.jsonl \
  colab_lightfm_hybrid_lite_bundle/data/lightfm/

tar -czf colab_lightfm_hybrid_lite_bundle.tar.gz colab_lightfm_hybrid_lite_bundle
ls -lh colab_lightfm_hybrid_lite_bundle.tar.gz
```

## Colab에서 실행

CPU가 많이 붙는 런타임을 사용합니다. L4/A100 런타임을 잡으면 GPU 자체를 쓰지는 않더라도 CPU/RAM이 더 넉넉하게 붙을 수 있습니다.

```python
from google.colab import files
uploaded = files.upload()
```

```python
!tar -xzf colab_lightfm_hybrid_lite_bundle.tar.gz
%cd colab_lightfm_hybrid_lite_bundle
!wc -l data/lightfm/nemotron_rule_based_synthetic_events_1000x63.jsonl
```

```python
!pip install -q condacolab
import condacolab
condacolab.install()
```

런타임 재시작 후:

```python
%cd /content/colab_lightfm_hybrid_lite_bundle
!mamba create -y -n lightfm311 -c conda-forge python=3.11 lightfm numpy scipy scikit-learn joblib
!mamba run -n lightfm311 python -c "from lightfm import LightFM; print('LightFM env OK')"
```

## 빠른 hybrid-lite 평가

```python
!mamba run -n lightfm311 python -u script/train_evaluate_lightfm_701_hybrid_lite.py \
  --events-path data/lightfm/nemotron_rule_based_synthetic_events_1000x63.jsonl \
  --output-dir artifacts/lightfm/nemotron_rule_based_1000x63_701_hybrid_lite_fast_eval \
  --loss warp \
  --epochs 10 \
  --components 16 \
  --learning-rate 0.03 \
  --item-alpha 1e-6 \
  --user-alpha 1e-6 \
  --num-threads 8 \
  --k 10 \
  --train-ratio 0.7 \
  --validation-ratio 0.2 \
  --test-ratio 0.1 \
  --no-save-final-model \
  --excluded-event-types DISLIKE_ADD,DISLIKE_REMOVE,DISLIKED,NOT_INTERESTED,UNLIKE,BLOCK,NEGATIVE \
  --dislike-event-types DISLIKE_ADD,DISLIKED,NOT_INTERESTED,NEGATIVE
```

결과 확인:

```python
!cat artifacts/lightfm/nemotron_rule_based_1000x63_701_hybrid_lite_fast_eval/metrics.json
```

## 비교 기준

먼저 identity-only fast_eval과 비교합니다.

- `positive_hit_rate@10`: 높을수록 좋음
- `positive_precision@10`: 높을수록 좋음
- `positive_recall@10`: 높을수록 좋음
- `auc`: 높을수록 좋음
- `dislike_hit_rate@10`: 낮을수록 좋음
- `dislike_item_rate@10`: 낮을수록 좋음

hybrid-lite가 identity-only보다 Top-K 지표에서 개선되지 않으면 최종 artifact는 identity-only로 가는 것이 안전합니다.

## hybrid-lite 최종 학습

빠른 평가가 identity-only보다 좋을 때만 실행합니다.

```python
!mamba run -n lightfm311 python -u script/train_evaluate_lightfm_701_hybrid_lite.py \
  --events-path data/lightfm/nemotron_rule_based_synthetic_events_1000x63.jsonl \
  --output-dir artifacts/lightfm/nemotron_rule_based_1000x63_701_hybrid_lite_final \
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

다운로드:

```python
!tar -czf nemotron_rule_based_1000x63_701_hybrid_lite_final.tar.gz artifacts/lightfm/nemotron_rule_based_1000x63_701_hybrid_lite_final
from google.colab import files
files.download("nemotron_rule_based_1000x63_701_hybrid_lite_final.tar.gz")
```
