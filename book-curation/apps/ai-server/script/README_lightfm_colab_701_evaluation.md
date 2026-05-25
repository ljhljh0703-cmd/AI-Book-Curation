# LightFM 7:2:1 학습/검증/테스트 평가 가이드

이 문서는 `nemotron_rule_based_synthetic_events_1000x63.jsonl`을 사용해서 Colab conda 환경에서 LightFM을 학습하고, 7:2:1 분할 평가와 DISLIKE 회피 지표를 확인하는 절차입니다.

## 핵심 구조

```text
positive event:
- FAVORITE_ADD
- READING_ADD
- READ_ADD

negative evaluation event:
- DISLIKE_ADD
```

수정 포인트:
`DISLIKE_ADD`는 LightFM positive interaction으로 학습하지 않습니다. 대신 평가 단계에서 negative label로만 사용하여 Top-K 추천 결과에 비선호 책이 섞이는지 확인합니다.

평가 분할은 사용자별 positive interaction 기준입니다.

```text
train       70%
validation  20%
test        10%
```

평가 방식은 다음과 같습니다.

```text
validation:
- train 70%로 모델 학습
- validation 20% positive hit/recall/auc 평가
- DISLIKE_ADD 회피 지표 평가

test:
- train 70% + validation 20%로 모델 재학습
- test 10% positive hit/recall/auc 평가
- DISLIKE_ADD 회피 지표 평가

final artifact:
- 전체 positive event 100%로 최종 모델 학습 후 저장
- DISLIKE_ADD는 최종 모델 학습에도 사용하지 않음
```

## 1. 로컬에서 Colab 업로드용 bundle 만들기

`apps/ai-server`에서 실행합니다.

```bash
cd /c/book-curation/apps/ai-server

wc -l data/lightfm/nemotron_rule_based_synthetic_events_1000x63.jsonl

rm -rf colab_lightfm_701_bundle
mkdir -p colab_lightfm_701_bundle/script
mkdir -p colab_lightfm_701_bundle/data/lightfm
mkdir -p colab_lightfm_701_bundle/artifacts/lightfm

cp script/train_evaluate_lightfm_701.py colab_lightfm_701_bundle/script/
cp data/lightfm/nemotron_rule_based_synthetic_events_1000x63.jsonl \
  colab_lightfm_701_bundle/data/lightfm/

tar -czf colab_lightfm_701_bundle.tar.gz colab_lightfm_701_bundle
ls -lh colab_lightfm_701_bundle.tar.gz
```

## 2. Colab에 bundle 업로드

Colab에서 CPU 런타임을 사용합니다.

```text
런타임 > 런타임 유형 변경 > 하드웨어 가속기: 없음
```

업로드 셀:

```python
from google.colab import files
uploaded = files.upload()
```

`colab_lightfm_701_bundle.tar.gz`를 업로드합니다.

압축 해제:

```python
!tar -xzf colab_lightfm_701_bundle.tar.gz
%cd colab_lightfm_701_bundle
!find . -maxdepth 3 -type f
!wc -l data/lightfm/nemotron_rule_based_synthetic_events_1000x63.jsonl
```

## 3. Colab conda 환경 구성

기존 pip 설치가 실패했다면 새 런타임에서 아래 순서로 진행하는 것을 권장합니다.

```python
!pip install -q condacolab
import condacolab
condacolab.install()
```

런타임이 재시작되면 다시 bundle 위치로 이동합니다.

```python
%cd /content/colab_lightfm_701_bundle
```

conda 환경 생성:

```python
!mamba create -y -n lightfm311 -c conda-forge python=3.11 lightfm numpy scipy scikit-learn joblib
```

설치 확인:

```python
!mamba run -n lightfm311 python -c "from lightfm import LightFM; import numpy; import scipy; import sklearn; import joblib; print('LightFM env OK')"
```

## 4. 7:2:1 평가 + 최종 모델 학습

```python
!mamba run -n lightfm311 python script/train_evaluate_lightfm_701.py \
  --events-path data/lightfm/nemotron_rule_based_synthetic_events_1000x63.jsonl \
  --output-dir artifacts/lightfm/nemotron_rule_based_1000x63_701 \
  --loss warp \
  --epochs 30 \
  --components 64 \
  --learning-rate 0.05 \
  --num-threads 2 \
  --k 10 \
  --train-ratio 0.7 \
  --validation-ratio 0.2 \
  --test-ratio 0.1 \
  --excluded-event-types DISLIKE_ADD,DISLIKE_REMOVE,DISLIKED,NOT_INTERESTED,UNLIKE,BLOCK,NEGATIVE \
  --dislike-event-types DISLIKE_ADD,DISLIKED,NOT_INTERESTED,NEGATIVE
```

## 5. 결과 확인

```python
!find artifacts/lightfm/nemotron_rule_based_1000x63_701 -maxdepth 2 -type f -print
!cat artifacts/lightfm/nemotron_rule_based_1000x63_701/metrics.json
```

주요 지표 해석:

```text
positive_hit_rate@10      높을수록 좋음
positive_precision@10     높을수록 좋음
positive_recall@10        높을수록 좋음
auc                       높을수록 좋음

dislike_hit_rate@10       낮을수록 좋음
dislike_item_rate@10      낮을수록 좋음
dislike_mrr@10            낮을수록 좋음
dislike_ndcg@10           낮을수록 좋음
```

## 6. 결과 다운로드

```python
!tar -czf nemotron_rule_based_1000x63_701_artifact.tar.gz artifacts/lightfm/nemotron_rule_based_1000x63_701
from google.colab import files
files.download('nemotron_rule_based_1000x63_701_artifact.tar.gz')
```

로컬 `apps/ai-server`에 다운로드한 압축파일을 넣고 압축을 해제합니다.

```bash
cd /c/book-curation/apps/ai-server
tar -xzf nemotron_rule_based_1000x63_701_artifact.tar.gz
ls -lh artifacts/lightfm/nemotron_rule_based_1000x63_701
```
