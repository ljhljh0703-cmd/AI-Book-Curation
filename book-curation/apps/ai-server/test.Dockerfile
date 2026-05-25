FROM python:3.11-slim
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
# 라이브러리 직접 설치로 컴파일 지옥 회피
RUN pip install --no-cache-dir lightfm pandas datasets tqdm joblib scipy
