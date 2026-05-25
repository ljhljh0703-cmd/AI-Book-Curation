# LightFM shared-pool + real user hybrid-lite 학습 가이드

## 목적

이 문서는 `shared-pool synthetic dataset`에 현재 PostgreSQL DB의 실사용자 데이터를 함께 섞어 `hybrid-lite LightFM`을 학습하는 절차를 설명합니다.

이번 구조의 핵심은 다음입니다.

- Colab은 PostgreSQL에 직접 접속하지 않습니다.
- 로컬 또는 NAS에서 DB 데이터를 먼저 `JSONL`로 export합니다.
- 실사용자는 synthetic persona처럼 사용자당 63개 행동이 보장되지 않으므로, 가짜 행동을 만들지 않습니다.
- 부족한 interaction은 `real_user_features.jsonl`, `real_item_features.jsonl`로 보강합니다.
- 학습은 `shared-pool synthetic events + real user events + real user features + real item features` 조합으로 수행합니다.
- 최종 목표는 LightFM을 최종 추천기가 아니라 `50개 후보 -> 20개 후보 압축기`로 쓰는 것입니다.

---

## 1. 로컬/NAS에서 실사용자 데이터 export

DB에 접근 가능한 환경에서 실행합니다. Windows Git Bash 기준 예시입니다.

```bash
cd /c/book-curation/apps/ai-server
source .venv/Scripts/activate
python -m pip install python-dotenv sqlalchemy "psycopg[binary]" pydantic pydantic-settings
```

`.env.local`에는 URL 한 줄 방식 또는 분리 변수 방식을 사용할 수 있습니다. 비밀번호에 `!`, `@`, `#` 같은 특수문자가 있으면 분리 변수 방식이 더 안전합니다.

분리 변수 방식 예시:

```env
DB_HOST=192.168.0.10
DB_PORT=31432
DB_NAME=book_curation
DB_ID=book_user
DB_PASSWORD=BookCuration_2026!
DB_SCHEMA=book
```

URL 방식도 지원합니다.

```env
DB_URL=postgresql://book_user:URL_ENCODED_PASSWORD@192.168.0.10:31432/book_curation
DB_SCHEMA=book
```

스크립트는 `.env`, `.env.local`을 자동으로 읽습니다.

```bash
python script/export_real_lightfm_events.py \
  --output-events-path data/lightfm/real_user_events.jsonl \
  --output-user-features-path data/lightfm/real_user_features.jsonl \
  --output-item-features-path data/lightfm/real_item_features.jsonl \
  --summary-path data/lightfm/real_lightfm_export.summary.json \
  --schema book \
  --real-weight-multiplier 2.0
```

생성 파일 확인:

```bash
wc -l data/lightfm/real_user_events.jsonl
wc -l data/lightfm/real_user_features.jsonl
wc -l data/lightfm/real_item_features.jsonl
cat data/lightfm/real_lightfm_export.summary.json
```

생성되는 파일 역할:

| 파일 | 역할 |
|---|---|
| `real_user_events.jsonl` | 실제 사용자 행동 이벤트 |
| `real_user_features.jsonl` | 실사용자 온보딩/프로필/관심 카테고리/행동 count bucket feature |
| `real_item_features.jsonl` | DB 도서 category/source/year feature |
| `real_lightfm_export.summary.json` | export 결과 요약 |

주의: 위 파일들은 실제 사용자 데이터이므로 Git에 올리면 안 됩니다.

---

## 2. Colab 업로드용 tar.gz 생성

`apps/ai-server`에서 실행합니다.

```bash
rm -rf colab_lightfm_shared_real_hybrid_bundle

mkdir -p colab_lightfm_shared_real_hybrid_bundle/script
mkdir -p colab_lightfm_shared_real_hybrid_bundle/data/lightfm
mkdir -p colab_lightfm_shared_real_hybrid_bundle/artifacts/lightfm

cp script/train_evaluate_lightfm_701_hybrid.py \
  colab_lightfm_shared_real_hybrid_bundle/script/

cp script/train_evaluate_lightfm_701_hybrid_lite.py \
  colab_lightfm_shared_real_hybrid_bundle/script/

cp data/lightfm/nemotron_rule_based_shared_synthetic_events_1000x63.jsonl \
  colab_lightfm_shared_real_hybrid_bundle/data/lightfm/

cp data/lightfm/real_user_events.jsonl \
  colab_lightfm_shared_real_hybrid_bundle/data/lightfm/

cp data/lightfm/real_user_features.jsonl \
  colab_lightfm_shared_real_hybrid_bundle/data/lightfm/

cp data/lightfm/real_item_features.jsonl \
  colab_lightfm_shared_real_hybrid_bundle/data/lightfm/

cp data/lightfm/real_lightfm_export.summary.json \
  colab_lightfm_shared_real_hybrid_bundle/data/lightfm/ 2>/dev/null || true

tar -czf colab_lightfm_shared_real_hybrid_bundle.tar.gz \
  colab_lightfm_shared_real_hybrid_bundle

ls -lh colab_lightfm_shared_real_hybrid_bundle.tar.gz
```

---

## 3. Colab에서 압축 해제

```python
from google.colab import files
uploaded = files.upload()
```

`colab_lightfm_shared_real_hybrid_bundle.tar.gz` 업로드 후:

```python
!tar -xzf colab_lightfm_shared_real_hybrid_bundle.tar.gz
%cd colab_lightfm_shared_real_hybrid_bundle
!ls data/lightfm
!wc -l data/lightfm/*.jsonl
```

---

## 4. Colab LightFM 환경 준비

이미 `lightfm311` 환경이 있으면 확인만 합니다.

```python
!mamba run -n lightfm311 python -c "from lightfm import LightFM; print('LightFM OK')"
```

환경이 없거나 깨졌으면 재설치합니다.

```python
!pip install -q condacolab
import condacolab
condacolab.install()
```

런타임 재시작 후:

```python
%cd /content/colab_lightfm_shared_real_hybrid_bundle

!mamba env remove -n lightfm311 -y || true
!rm -rf /usr/local/envs/lightfm311

!mamba create -y -n lightfm311 -c conda-forge \
  python=3.11 \
  lightfm \
  numpy \
  scipy \
  scikit-learn \
  joblib \
  python-dotenv \
  pydantic \
  pydantic-settings

!mamba run -n lightfm311 python -c "from lightfm import LightFM; print('LightFM OK')"
```

---

## 5. shared-pool + real user + hybrid-lite 50→20 학습/평가

```python
!mamba run -n lightfm311 python -u script/train_evaluate_lightfm_701_hybrid_lite.py \
  --events-path data/lightfm/nemotron_rule_based_shared_synthetic_events_1000x63.jsonl \
  --events-path data/lightfm/real_user_events.jsonl \
  --user-features-path data/lightfm/real_user_features.jsonl \
  --item-features-path data/lightfm/real_item_features.jsonl \
  --output-dir artifacts/lightfm/shared_real_hybrid_lite_50to20_final \
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

결과 확인:

```python
!cat artifacts/lightfm/shared_real_hybrid_lite_50to20_final/metrics.json
```

중요하게 볼 지표:

| 지표 | 의미 |
|---|---|
| `test.positive_candidate@20_in_50_recall` | 후보 50개 안의 positive를 20개 안에 얼마나 남겼는지 |
| `test.positive_candidate@20_in_50_hit_rate` | 사용자별 Top-20 안에 positive가 하나 이상 남았는지 |
| `test.dislike_candidate@20_in_50_recall` | 후보 50개 안의 dislike가 20개 안에 얼마나 남았는지. 낮을수록 좋음 |
| `test.auc` | 전체 ranking 구분 능력 |

---

## 6. 결과 artifact 다운로드

```python
!tar -czf shared_real_hybrid_lite_50to20_final.tar.gz \
  artifacts/lightfm/shared_real_hybrid_lite_50to20_final

from google.colab import files
files.download("shared_real_hybrid_lite_50to20_final.tar.gz")
```

---

## 7. 운영 해석

이 artifact에 포함되는 실사용자는 export 시점에 DB에 존재한 사용자입니다.

- artifact 생성 시점에 존재하고 feature 또는 event가 있는 사용자: mapping 포함 가능
- artifact 생성 이후 신규 가입한 사용자: 다음 재학습 전까지 LightFM mapping에 없음
- mapping에 없는 사용자: 기존 Qdrant/룰베이스 fallback 사용

운영에서는 다음 흐름이 권장됩니다.

1. 신규/로그 부족 사용자: Qdrant + 룰베이스 fallback
2. 로그가 누적된 사용자: 다음 batch 학습 때 LightFM artifact에 포함
3. 추천 시: Qdrant/룰베이스 후보 50개 생성
4. LightFM hybrid-lite로 20개 압축
5. 최종 리랭커가 20개를 다시 정렬

---

## 8. Git ignore 주의

아래 파일은 Git에 올리면 안 됩니다.

```text
data/lightfm/*.jsonl
data/lightfm/*.summary.json
artifacts/lightfm/**
*.tar.gz
```
