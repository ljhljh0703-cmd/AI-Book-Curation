# syntax=docker/dockerfile:1.7
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 수정 포인트: 빌드가 무거운 numpy/scipy/lightfm 계열을 별도 레이어로 분리합니다.
# requirements-runtime.txt만 바뀌는 경우 이 레이어를 재사용할 수 있습니다.
COPY requirements-heavy.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    apt-get update \
    && apt-get install -y --no-install-recommends build-essential gcc g++ libgomp1 \
    && pip install --prefer-binary -r requirements-heavy.txt \
    && apt-get purge -y --auto-remove build-essential gcc g++ \
    && rm -rf /var/lib/apt/lists/*

# 수정 포인트: Redis/Qdrant/FastAPI 같은 런타임 의존성은 가벼운 별도 레이어로 설치합니다.
COPY requirements-runtime.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --prefer-binary -r requirements-runtime.txt

COPY requirements.txt ./
COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
