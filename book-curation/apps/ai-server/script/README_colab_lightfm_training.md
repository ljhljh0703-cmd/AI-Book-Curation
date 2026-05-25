# Colab에서 dev 브랜치 기준 LightFM 학습 실행 가이드

이 문서는 `dev` 브랜치에 반영된 ai-server LightFM 학습 스크립트를 Google Colab에서 실행하기 위한 명령어 모음입니다.

전제:
- 팀원별 synthetic subset 파일은 이미 만들어져 있음
- 입력 파일 형식은 `.jsonl`, `.json`, `.csv` 중 하나
- 학습 스크립트 위치는 `apps/ai-server/script/train_lightfm.py`
- artifact 출력 구조는 `model.joblib`, `mappings.json`, `metadata.json`
- LightFM 학습은 CPU로도 가능하지만, 데이터가 커지면 Colab High-RAM 런타임을 권장

---

## 0. Colab 런타임 준비

Colab 상단 메뉴에서 아래처럼 설정합니다.

```text
런타임 → 런타임 유형 변경 → 하드웨어 가속기: CPU 또는 T4
```

LightFM 자체는 CPU 기반 학습으로도 충분합니다. GPU는 필수는 아닙니다.

---

## 1. Google Drive 마운트

subset과 학습 artifact를 Drive에 보관하려면 먼저 Drive를 마운트합니다.

```python
from google.colab import drive
drive.mount("/content/drive")
```

권장 Drive 경로 예시:

```text
/content/drive/MyDrive/book-curation/lightfm-subsets/
/content/drive/MyDrive/book-curation/lightfm-artifacts/latest/
```

---

## 2. dev 브랜치 clone

아래의 `<YOUR_REPOSITORY_URL>`은 실제 저장소 URL로 바꿔주세요.

예시:
- GitHub: `https://github.com/<ORG>/<REPO>.git`
- GitLab: `https://gitlab.com/<GROUP>/<REPO>.git`

```bash
cd /content

REPO_URL="<YOUR_REPOSITORY_URL>"
BRANCH="dev"

rm -rf /content/book-curation
git clone --branch "${BRANCH}" --single-branch "${REPO_URL}" /content/book-curation

cd /content/book-curation
git status
git rev-parse --abbrev-ref HEAD
```

정상이라면 마지막 명령어 결과가 아래처럼 나와야 합니다.

```text
dev
```

---

## 2-1. 저장소가 private인 경우

### GitLab Personal Access Token 사용 예시

토큰을 코드에 직접 적지 말고 Colab 입력창에서 받는 방식을 권장합니다.

```python
from getpass import getpass

GITLAB_TOKEN = getpass("GitLab Personal Access Token: ")
GITLAB_GROUP = "<GROUP>"
GITLAB_REPO = "<REPO>"
```

```python
!rm -rf /content/book-curation
!git clone --branch dev --single-branch https://oauth2:{GITLAB_TOKEN}@gitlab.com/{GITLAB_GROUP}/{GITLAB_REPO}.git /content/book-curation
```

### GitHub Personal Access Token 사용 예시

```python
from getpass import getpass

GITHUB_TOKEN = getpass("GitHub Personal Access Token: ")
GITHUB_OWNER = "<ORG_OR_USER>"
GITHUB_REPO = "<REPO>"
```

```python
!rm -rf /content/book-curation
!git clone --branch dev --single-branch https://{GITHUB_TOKEN}@github.com/{GITHUB_OWNER}/{GITHUB_REPO}.git /content/book-curation
```

주의:
- 토큰을 노트북에 평문으로 저장하지 마세요.
- 노트북 공유 전에는 출력 로그에 토큰이 남지 않았는지 확인하세요.

---

## 3. ai-server 의존성 설치

```bash
cd /content/book-curation/apps/ai-server

sudo apt-get update -y
sudo apt-get install -y build-essential gcc g++ python3-dev

python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

설치 확인:

```bash
python - <<'PY'
import numpy
import scipy
import joblib
from lightfm import LightFM

print("numpy:", numpy.__version__)
print("scipy:", scipy.__version__)
print("LightFM import OK")
PY
```

---

## 4. subset 파일 경로 확인

팀원별 subset 파일을 Drive에 올렸다고 가정합니다.

예시 구조:

```text
/content/drive/MyDrive/book-curation/lightfm-subsets/
  team-a/
    synthetic_events.jsonl
  team-b/
    synthetic_events.jsonl
  team-c/
    synthetic_events.csv
```

파일 확인:

```bash
SUBSET_ROOT="/content/drive/MyDrive/book-curation/lightfm-subsets"

find "${SUBSET_ROOT}" -maxdepth 3 -type f \( -name "*.jsonl" -o -name "*.json" -o -name "*.csv" \) | sort
```

---

## 5. 단일 subset으로 학습 실행

```bash
cd /content/book-curation/apps/ai-server

EVENT_PATH="/content/drive/MyDrive/book-curation/lightfm-subsets/team-a/synthetic_events.jsonl"
OUTPUT_DIR="/content/drive/MyDrive/book-curation/lightfm-artifacts/latest"

python script/train_lightfm.py \
  --events-path "${EVENT_PATH}" \
  --output-dir "${OUTPUT_DIR}" \
  --loss warp \
  --epochs 30 \
  --components 64 \
  --learning-rate 0.05 \
  --num-threads 2
```

학습이 끝나면 아래 파일이 생성됩니다.

```text
/content/drive/MyDrive/book-curation/lightfm-artifacts/latest/
  model.joblib
  mappings.json
  metadata.json
```

---

## 6. 여러 팀원 subset을 합쳐서 학습 실행

디렉터리 경로를 넣으면 해당 디렉터리 바로 아래의 `.jsonl`, `.json`, `.csv` 파일을 읽습니다.

```bash
cd /content/book-curation/apps/ai-server

TEAM_A="/content/drive/MyDrive/book-curation/lightfm-subsets/team-a"
TEAM_B="/content/drive/MyDrive/book-curation/lightfm-subsets/team-b"
TEAM_C="/content/drive/MyDrive/book-curation/lightfm-subsets/team-c"
OUTPUT_DIR="/content/drive/MyDrive/book-curation/lightfm-artifacts/latest"

python script/train_lightfm.py \
  --events-path "${TEAM_A}" \
  --events-path "${TEAM_B}" \
  --events-path "${TEAM_C}" \
  --output-dir "${OUTPUT_DIR}" \
  --loss warp \
  --epochs 30 \
  --components 64 \
  --learning-rate 0.05 \
  --num-threads 2
```

---

## 7. 환경변수로 여러 subset 경로 지정

반복 실행할 때는 환경변수 방식이 편합니다.

```bash
cd /content/book-curation/apps/ai-server

export LIGHTFM_TRAIN_EVENTS_PATH="/content/drive/MyDrive/book-curation/lightfm-subsets/team-a/synthetic_events.jsonl,/content/drive/MyDrive/book-curation/lightfm-subsets/team-b/synthetic_events.jsonl"
export LIGHTFM_OUTPUT_DIR="/content/drive/MyDrive/book-curation/lightfm-artifacts/latest"
export LIGHTFM_EPOCHS="30"
export LIGHTFM_NO_COMPONENTS="64"
export LIGHTFM_LEARNING_RATE="0.05"
export LIGHTFM_NUM_THREADS="2"

python script/train_lightfm.py
```

---

## 8. subset 필드명이 다른 경우

기본적으로 학습 스크립트는 아래 필드명을 자동으로 찾습니다.

| 의미 | 기본 후보 필드 |
|---|---|
| 사용자 | `user_key,user_id,persona_id` |
| 도서 | `isbn13,isbn,book_key,book_id,item_id` |
| 이벤트 타입 | `event_type,type,action` |
| 가중치 | `final_weight,weight,base_weight` |
| 출처 | `user_source,source` |

필드명이 다르면 실행 시 직접 지정합니다.

```bash
cd /content/book-curation/apps/ai-server

python script/train_lightfm.py \
  --events-path "/content/drive/MyDrive/book-curation/lightfm-subsets/team-a/events.jsonl" \
  --output-dir "/content/drive/MyDrive/book-curation/lightfm-artifacts/latest" \
  --user-field "persona_user_id" \
  --item-field "isbn" \
  --event-type-field "behavior_type" \
  --weight-field "event_weight" \
  --source-field "source"
```

여러 후보 필드명을 줄 수도 있습니다.

```bash
python script/train_lightfm.py \
  --events-path "/content/drive/MyDrive/book-curation/lightfm-subsets/team-a/events.jsonl" \
  --output-dir "/content/drive/MyDrive/book-curation/lightfm-artifacts/latest" \
  --user-field "user_key,user_id,persona_id" \
  --item-field "isbn13,isbn,book_key"
```

---

## 9. DISLIKED 제외 확인

기본적으로 아래 이벤트 타입은 WARP positive 학습에서 제외됩니다.

```text
DISLIKED
NOT_INTERESTED
UNLIKE
BLOCK
NEGATIVE
```

필요하면 직접 지정할 수 있습니다.

```bash
python script/train_lightfm.py \
  --events-path "/content/drive/MyDrive/book-curation/lightfm-subsets/team-a" \
  --output-dir "/content/drive/MyDrive/book-curation/lightfm-artifacts/latest" \
  --excluded-event-types "DISLIKED,NOT_INTERESTED,UNLIKE,BLOCK,NEGATIVE"
```

---

## 10. 생성된 artifact 검증

```bash
cd /content/book-curation/apps/ai-server

ARTIFACT_DIR="/content/drive/MyDrive/book-curation/lightfm-artifacts/latest"

python script/validate_lightfm_artifact.py \
  --artifact-dir "${ARTIFACT_DIR}"
```

정상이라면 아래와 비슷하게 출력됩니다.

```text
[LIGHTFM ARTIFACT] path=... users=100 items=5000 version=lightfm_...
```

특정 사용자/도서 score까지 확인하려면 아래처럼 실행합니다.

```bash
python script/validate_lightfm_artifact.py \
  --artifact-dir "${ARTIFACT_DIR}" \
  --user-id "persona:sample-user-001" \
  --item-id "9780000000001" \
  --item-id "9780000000002"
```

---

## 11. artifact를 압축해서 내려받기

```bash
ARTIFACT_DIR="/content/drive/MyDrive/book-curation/lightfm-artifacts/latest"
ZIP_PATH="/content/lightfm_latest_artifact.zip"

cd "${ARTIFACT_DIR}"
zip -r "${ZIP_PATH}" model.joblib mappings.json metadata.json

ls -lh "${ZIP_PATH}"
```

Colab에서 직접 다운로드하려면:

```python
from google.colab import files
files.download("/content/lightfm_latest_artifact.zip")
```

---

## 12. ai-server에 artifact 반영할 때 필요한 경로

운영 ai-server에서는 `LIGHTFM_ARTIFACT_PATH`가 artifact 디렉터리를 바라봐야 합니다.

예시:

```bash
export LIGHTFM_ARTIFACT_PATH="/app/artifacts/lightfm/latest"
```

해당 디렉터리 안에는 반드시 아래 파일이 있어야 합니다.

```text
/app/artifacts/lightfm/latest/
  model.joblib
  mappings.json
  metadata.json
```

---

## 13. 자주 나는 오류와 확인 방법

### 13-1. `No training event paths were provided`

원인:
- `--events-path`를 안 넣었거나
- `LIGHTFM_TRAIN_EVENTS_PATH`가 비어 있음

확인:

```bash
echo "${LIGHTFM_TRAIN_EVENTS_PATH}"
```

---

### 13-2. `Training event path does not exist`

원인:
- Drive 마운트가 안 됨
- 경로 오타
- 파일이 실제로 없음

확인:

```bash
ls -al "/content/drive/MyDrive/book-curation/lightfm-subsets"
find "/content/drive/MyDrive/book-curation/lightfm-subsets" -type f | head
```

---

### 13-3. `No positive events remained after filtering`

원인:
- 사용자 필드 또는 도서 필드명이 스크립트 기본값과 다름
- 모든 이벤트가 `DISLIKED` 등 excluded event type으로 들어감
- weight가 0 이하로 들어감

확인:

```bash
python - <<'PY'
import json
from pathlib import Path

path = Path("/content/drive/MyDrive/book-curation/lightfm-subsets/team-a/synthetic_events.jsonl")
with path.open("r", encoding="utf-8") as f:
    for i, line in enumerate(f):
        print(json.loads(line))
        if i >= 2:
            break
PY
```

필드명이 다르면 `--user-field`, `--item-field`, `--event-type-field`, `--weight-field` 옵션을 지정하세요.

---

### 13-4. `Import error: No module named lightfm`

원인:
- `requirements.txt` 설치가 안 됨
- Colab 런타임이 재시작되어 설치 내역이 사라짐

해결:

```bash
cd /content/book-curation/apps/ai-server
python -m pip install -r requirements.txt
```

---

### 13-5. LightFM 설치 실패

Colab 환경에서 native build 관련 오류가 나면 아래를 다시 실행합니다.

```bash
sudo apt-get update -y
sudo apt-get install -y build-essential gcc g++ python3-dev
python -m pip install --upgrade pip setuptools wheel
python -m pip install lightfm==1.17
```

그 다음 다시 requirements를 설치합니다.

```bash
python -m pip install -r /content/book-curation/apps/ai-server/requirements.txt
```

---

## 14. 권장 실행 순서 요약

```bash
# 1. 저장소 clone
cd /content
git clone --branch dev --single-branch "<YOUR_REPOSITORY_URL>" /content/book-curation

# 2. 의존성 설치
cd /content/book-curation/apps/ai-server
sudo apt-get update -y
sudo apt-get install -y build-essential gcc g++ python3-dev
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt

# 3. subset 확인
find "/content/drive/MyDrive/book-curation/lightfm-subsets" -maxdepth 3 -type f | sort

# 4. 학습 실행
python script/train_lightfm.py \
  --events-path "/content/drive/MyDrive/book-curation/lightfm-subsets/team-a" \
  --events-path "/content/drive/MyDrive/book-curation/lightfm-subsets/team-b" \
  --output-dir "/content/drive/MyDrive/book-curation/lightfm-artifacts/latest" \
  --loss warp \
  --epochs 30 \
  --components 64 \
  --learning-rate 0.05 \
  --num-threads 2

# 5. artifact 검증
python script/validate_lightfm_artifact.py \
  --artifact-dir "/content/drive/MyDrive/book-curation/lightfm-artifacts/latest"
```

---

## 15. 학습 결과를 dev 브랜치에 커밋하지 않는 것을 권장

`model.joblib` 같은 모델 artifact는 용량이 크고 자주 바뀌므로 Git에 직접 커밋하지 않는 편이 좋습니다.

권장:
- Drive, NAS, S3, PVC 등에 artifact 보관
- 운영 배포 시 `LIGHTFM_ARTIFACT_PATH`로 mount
- Git에는 학습 스크립트와 설정만 관리

그래도 임시로 저장소 안에 넣어야 한다면 `.gitignore`를 먼저 확인하세요.

```bash
cd /content/book-curation
git status --short
```
