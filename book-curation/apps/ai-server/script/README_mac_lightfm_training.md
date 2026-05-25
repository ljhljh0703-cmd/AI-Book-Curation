# 맥북(Apple Silicon / Intel) 로컬 LightFM 학습 가이드

이 문서는 구글 코랩(Colab)을 거치지 않고, **macOS 로컬 터미널에서 직접 LightFM을 설치하고 훈련하는 방법**을 다룹니다.

C++ 기반의 `lightfm` 패키지는 최신 파이썬 버전의 `pip` 환경(특히 Apple Silicon의 `arm64` 아키텍처)에서 빌드 에러가 자주 발생합니다. 이를 우회하기 위한 가장 확실하고 검증된 핵심 조합은 다음과 같습니다:

> 🔑 **핵심 조합: Miniforge + conda-forge (Pre-compiled Binary) + Python 3.11**

---

## 0. 맥북 칩셋(아키텍처) 확인
터미널을 열고 아래 명령어를 입력합니다.
```bash
uname -m
```
* **결과가 `arm64`인 경우**: M1/M2/M3/M4 계열의 **Apple Silicon Mac**입니다.
* **결과가 `x86_64`인 경우**: **Intel Mac**입니다.

---

## 1. Xcode Command Line Tools 설치
운영체제 기본 빌드 도구가 필요합니다.
```bash
xcode-select --install
```
> *이미 설치되어 있다는 메시지가 나오면 무시하고 다음으로 넘어갑니다.*

---

## 2. Miniforge 설치
칩셋 아키텍처에 맞는 버전을 다운로드하고 설치합니다.

### Apple Silicon Mac (M1/M2/M3/M4)
```bash
cd ~
curl -L -O https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-MacOSX-arm64.sh
bash Miniforge3-MacOSX-arm64.sh
```

### Intel Mac
```bash
cd ~
curl -L -O https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-MacOSX-x86_64.sh
bash Miniforge3-MacOSX-x86_64.sh
```

**[설치 중 주의사항]**
1. `Do you accept the license terms? [yes|no]` -> `yes` 입력
2. 설치 경로 지정 -> 기본값 그대로 `Enter`
3. `Do you wish to update your shell profile to automatically initialize conda?` -> `yes` 입력
4. **설치가 완료되면 반드시 현재 터미널 창을 닫고 완전히 새 터미널을 열어주세요.**

---

## 3. Conda 초기화 확인
새 터미널에서 아래 명령어로 conda가 정상 인식되는지 확인합니다.
```bash
conda --version
```
> 명령어를 찾을 수 없다고 나온다면 다음을 순차적으로 실행한 뒤 터미널을 다시 껐다 켭니다.
> ```bash
> source ~/.zshrc
> # 그래도 안 되면:
> source ~/miniforge3/bin/activate
> conda init zsh
> ```

---

## 4. 전용 Conda 환경 생성 (Python 3.11)
독립된 훈련용 파이썬 환경을 생성하고 활성화합니다.
```bash
conda create -n book-curation python=3.11 -y
conda activate book-curation
```
> 성공 시 터미널 프롬프트 앞에 `(book-curation)`이 표시됩니다.

---

## 5. LightFM 및 필수 라이브러리 설치 (conda-forge)
`pip` 대신 `conda-forge` 채널에서 미리 빌드된 안전한 바이너리를 다운로드합니다.
```bash
conda install -c conda-forge lightfm pandas numpy scipy scikit-learn joblib tqdm -y
```

**[설치 검증]**
```bash
python -c "import lightfm; print('✅ LightFM 정상 로드 완료!')"
```
> `✅ LightFM 정상 로드 완료!`가 출력되면 로컬 환경 구축 성공입니다.

---

## 6. 로컬 훈련 실행하기 (Train)

### 저장소 이동
```bash
# 본인의 프로젝트 경로에 맞게 이동하세요
cd ~/Book_curation/book-curation-dev/apps/ai-server
```

### 데이터 가공 (Flattening)
중첩된 페르소나 JSON 파일이 있다면 먼저 평탄화 작업을 거칩니다.
```bash
python script/flatten_persona_events.py \
  --input-file "$HOME/Downloads/persona_full_result.json" \
  --output-file "data/persona_events.jsonl"
```

### 3 Epoch 테스트 훈련
```bash
python script/train_lightfm.py \
  --events-path "data/persona_events.jsonl" \
  --output-dir "artifacts/lightfm/latest_mac" \
  --epochs 3 \
  --loss warp
```

### 30 Epoch 본 학습
테스트가 성공적으로 완료되면 30회 학습을 돌려 최종 가중치(`weights.joblib`)를 추출합니다.
```bash
python script/train_lightfm.py \
  --events-path "data/persona_events.jsonl" \
  --output-dir "artifacts/lightfm/latest_mac" \
  --epochs 30 \
  --loss warp
```

### 검증 (Validation)
추출된 `weights.joblib`가 정상 작동하는지 검증합니다.
```bash
python script/validate_lightfm_artifact.py \
  --artifact-dir "artifacts/lightfm/latest_mac" \
  --user-id "<테스트할_USER_ID>" \
  --item-id "<테스트할_ISBN>"
```

---

## 💡 아키텍처 참고 사항 (서빙)
이 가이드를 통해 **로컬(Conda) 환경에서 성공적으로 모델 훈련**을 마칠 수 있습니다. 

훈련을 마친 뒤 생성된 `weights.joblib` 가중치 파일은 우리 프로젝트에 도입된 **Zero-Dependency Pure NumPy Serving** 아키텍처 덕분에, 무거운 Conda 환경 밖의 일반 `pip` 환경이나 도커(Docker) 컨테이너 서버에서도 `lightfm` 패키지 없이 가볍고 초고속으로 서빙(Inference)될 수 있습니다!
