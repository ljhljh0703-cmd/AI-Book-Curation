# LightFM 환경 구축 및 실행 가이드라인 (macOS Apple Silicon 대응)

본 문서는 macOS(Apple Silicon) 환경에서 발생하는 `lightfm` 설치 및 컴파일 오류를 우회하고, Ubuntu 가상 환경을 통해 안정적으로 모델을 훈련 및 서빙하기 위한 절차를 정의합니다.

## 1. 핵심 원칙
- **로컬 직접 설치 금지**: macOS 및 Python 3.12+ 환경에서 `lightfm`은 C-API 호환성 문제로 설치가 거의 불가능합니다.
- **Python 3.11 고정**: `lightfm` 라이브러리의 안정성을 위해 반드시 **Python 3.11** 환경을 사용합니다.
- **Ubuntu 가상화 기반**: Multipass 또는 Docker를 통한 Ubuntu(Linux) 환경에서만 실행합니다.

## 2. 환경 구축 절차 (Ubuntu/Multipass)

### 2.1 Multipass 설치 및 인스턴스 생성
```bash
# Mac 터미널에서 실행
brew install --cask multipass
multipass launch --name ai-env --cpus 2 --memory 4G --disk 20G
multipass shell ai-env
```

### 2.2 Python 3.11 및 필수 라이브러리 설치
Ubuntu 내부에서 `pip install` 시 발생하는 `AttributeError`를 방지하기 위해 반드시 소스 패치 과정을 거칩니다.

```bash
# Ubuntu 내부 실행
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev build-essential git

# 가상환경 생성 및 활성화
python3.11 -m venv ~/venv311
source ~/venv311/bin/activate

# LightFM 소스 패치 및 강제 빌드 (핵심 단계)
cd ~
git clone https://github.com/lyst/lightfm.git
cd lightfm
sed -i 's/builtins.__LIGHTFM_SETUP__ = True/pass/g' setup.py  # setup.py 버그 패치
pip install cython setuptools
pip install .

# 기타 의존성 설치
pip install pandas datasets tqdm joblib scipy pydantic-settings
```

## 3. 개발 워크플로우 (Mac ↔ Ubuntu)

### 3.1 프로젝트 폴더 연결
Mac에서 수정한 코드를 Ubuntu에서 바로 테스트하기 위해 마운트를 활용합니다.
```bash
# Mac 터미널에서 실행
multipass mount "/Users/godju/Downloads/AI AGENT/AI Book Curation" ai-env:/home/ubuntu/project
```

### 3.2 랭킹 모델 테스트 실행
Ubuntu 인스턴스 접속 후 프로젝트 경로에서 실행합니다.
```bash
# Ubuntu 내부 실행
cd /home/ubuntu/project/book-curation/apps/ai-server
source ~/venv311/bin/activate
export PYTHONPATH=\$PYTHONPATH:\$(pwd)

# 검증 스크립트 실행
python3 app/test_lightfm_final.py
```

## 4. 트러블슈팅
- **`total 0` (마운트 오류)**: Mac의 `시스템 설정 -> 개인정보 보호 및 보안 -> 전체 디스크 접근 권한`에서 Multipass를 허용했는지 확인하세요.
- **`ModuleNotFoundError`**: `PYTHONPATH`가 설정되지 않았거나 가상환경이 활성화되지 않은 상태입니다.
- **`AttributeError: 'dict' object has no attribute '__LIGHTFM_SETUP__'`**: `pip install lightfm`을 직접 시도하지 말고, 반드시 위 2.2절의 **소스 패치 및 강제 빌드** 방식을 따르세요.

---
**작성일**: 2026-05-13
**담당**: GitHub Copilot (Gemini 3 Flash)
