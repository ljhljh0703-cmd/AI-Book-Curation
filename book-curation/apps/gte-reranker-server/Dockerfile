FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/models \
    SENTENCE_TRANSFORMERS_HOME=/models \
    TRANSFORMERS_CACHE=/models \
    GTE_RERANKER_MODEL_CACHE_DIR=/models \
    GTE_RERANKER_DEVICE=cpu

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /models

COPY requirements-torch-cpu.txt requirements.txt ./
RUN pip install --no-cache-dir -r requirements-torch-cpu.txt \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
