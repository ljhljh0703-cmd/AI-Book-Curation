# LightFM 7:2:1 Hybrid 학습/평가 가이드

이 문서는 `nemotron_rule_based_synthetic_events_1000x63.jsonl`을 기준으로 LightFM을 **하이브리드 방식**으로 학습/평가하는 절차입니다.

## 핵심 구조

기존 `train_evaluate_lightfm_701.py`는 `user_id + item_id interaction` 중심입니다.

`train_evaluate_lightfm_701_hybrid.py`는 아래 feature를 추가로 사용합니다.

- user feature
  - `user_age_group`
  - `profile_query_text`
  - `profile_strategy`
  - `rule_mode`
  - 기타 LLM profile 계열 필드가 있을 경우 자동 feature화
- item feature
  - `category`, `categories`
  - `author`, `publisher`
  - `title`, `description` 기반 token feature

`DISLIKE_ADD`는 positive 학습에 넣지 않고, validation/test에서 추천 회피 지표로만 평가합니다.

## 지표 해석

높을수록 좋은 지표:

- `positive_hit_rate@10`
- `positive_precision@10`
- `positive_recall@10`
- `positive_mrr@10`
- `positive_ndcg@10`
- `auc`

낮을수록 좋은 지표:

- `dislike_hit_rate@10`
- `dislike_item_rate@10`
- `dislike_precision@10`
- `dislike_recall@10`
- `dislike_mrr@10`
- `dislike_ndcg@10`

## 로컬에서 Colab 업로드 bundle 생성

`apps/ai-server`에서 실행합니다.

```bash
cd /c/book-curation/apps/ai-server

wc -l data/lightfm/nemotron_rule_based_synthetic_events_1000x63.jsonl

rm -rf colab_lightfm_hybrid_bundle
mkdir -p colab_lightfm_hybrid_bundle/script
mkdir -p colab_lightfm_hybrid_bundle/data/lightfm
mkdir -p colab_lightfm_hybrid_bundle/artifacts/lightfm

cp script/train_evaluate_lightfm_701_hybrid.py colab_lightfm_hybrid_bundle/script/
cp data/lightfm/nemotron_rule_based_synthetic_events_1000x63.jsonl \
  colab_lightfm_hybrid_bundle/data/lightfm/

tar -czf colab_lightfm_hybrid_bundle.tar.gz colab_lightfm_hybrid_bundle
ls -lh colab_lightfm_hybrid_bundle.tar.gz
```

## Colab 새 노트북에서 실행

CPU 런타임을 사용합니다.

### 1. 업로드

```python
from google.colab import files
uploaded = files.upload()
```

`colab_lightfm_hybrid_bundle.tar.gz`를 업로드합니다.

```python
!tar -xzf colab_lightfm_hybrid_bundle.tar.gz
%cd colab_lightfm_hybrid_bundle
!wc -l data/lightfm/nemotron_rule_based_synthetic_events_1000x63.jsonl
```

### 2. conda 환경 구성

```python
!pip install -q condacolab
import condacolab
condacolab.install()
```

런타임이 재시작되면 다시 아래부터 실행합니다.

```python
%cd /content/colab_lightfm_hybrid_bundle
!mamba create -y -n lightfm311 -c conda-forge python=3.11 lightfm numpy scipy scikit-learn joblib
!mamba run -n lightfm311 python -c "from lightfm import LightFM; print('LightFM env OK')"
```

### 3. Hybrid LightFM 학습/평가

```python
!mamba run -n lightfm311 python script/train_evaluate_lightfm_701_hybrid.py \
  --events-path data/lightfm/nemotron_rule_based_synthetic_events_1000x63.jsonl \
  --output-dir artifacts/lightfm/nemotron_rule_based_1000x63_701_hybrid \
  --feature-mode hybrid \
  --loss warp \
  --epochs 60 \
  --components 64 \
  --learning-rate 0.03 \
  --item-alpha 1e-6 \
  --user-alpha 1e-6 \
  --num-threads 2 \
  --k 10 \
  --train-ratio 0.7 \
  --validation-ratio 0.2 \
  --test-ratio 0.1 \
  --excluded-event-types DISLIKE_ADD,DISLIKE_REMOVE,DISLIKED,NOT_INTERESTED,UNLIKE,BLOCK,NEGATIVE \
  --dislike-event-types DISLIKE_ADD,DISLIKED,NOT_INTERESTED,NEGATIVE
```

### 4. 결과 확인

```python
!cat artifacts/lightfm/nemotron_rule_based_1000x63_701_hybrid/metrics.json
!find artifacts/lightfm/nemotron_rule_based_1000x63_701_hybrid -maxdepth 1 -type f -print
```

생성되는 주요 파일:

```text
model.joblib
mappings.json
metadata.json
metrics.json
user_features.npz
item_features.npz
feature_sources.json
```

### 5. 비교용 identity-only 학습

하이브리드가 실제로 개선됐는지 비교하려면 같은 스크립트에서 `--feature-mode identity`도 실행합니다.

```python
!mamba run -n lightfm311 python script/train_evaluate_lightfm_701_hybrid.py \
  --events-path data/lightfm/nemotron_rule_based_synthetic_events_1000x63.jsonl \
  --output-dir artifacts/lightfm/nemotron_rule_based_1000x63_701_identity \
  --feature-mode identity \
  --loss warp \
  --epochs 60 \
  --components 64 \
  --learning-rate 0.03 \
  --num-threads 2 \
  --k 10 \
  --train-ratio 0.7 \
  --validation-ratio 0.2 \
  --test-ratio 0.1 \
  --excluded-event-types DISLIKE_ADD,DISLIKE_REMOVE,DISLIKED,NOT_INTERESTED,UNLIKE,BLOCK,NEGATIVE \
  --dislike-event-types DISLIKE_ADD,DISLIKED,NOT_INTERESTED,NEGATIVE
```

## 결과 다운로드

```python
!tar -czf nemotron_rule_based_1000x63_701_hybrid_artifact.tar.gz artifacts/lightfm/nemotron_rule_based_1000x63_701_hybrid
from google.colab import files
files.download("nemotron_rule_based_1000x63_701_hybrid_artifact.tar.gz")
```

## 주의사항

현재 artifact는 하이브리드 feature matrix를 함께 저장합니다. 운영 추천 코드에서 이 모델을 바로 사용하려면 `model.predict(..., user_features=..., item_features=...)` 형태로 호출하도록 서빙 로직도 맞춰야 합니다. 기존 identity-only LightFM artifact와는 serving 방식이 다를 수 있습니다.
