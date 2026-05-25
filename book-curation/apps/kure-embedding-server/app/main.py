from __future__ import annotations

import secrets

from fastapi import Depends, FastAPI, HTTPException, Request, status

from app.core.config import settings
from app.schemas.embedding import EmbedRequest, EmbedResponse, HealthResponse, WarmupResponse
from app.services.kure_embedding_service import KureEmbeddingService

app = FastAPI(title="Book Curation KURE Embedding Server", version="0.1.0")
embedding_service = KureEmbeddingService()


def verify_internal_api_key(request: Request) -> None:
    expected_key = settings.KURE_INTERNAL_API_KEY.strip()
    if not expected_key:
        return

    header_name = settings.KURE_INTERNAL_HEADER_NAME.strip() or "X-KURE-Internal-Key"
    provided_key = request.headers.get(header_name, "").strip()
    # 수정 포인트: ai-server가 보내는 내부 인증 헤더 값을 안전하게 비교합니다.
    if not provided_key or not secrets.compare_digest(provided_key, expected_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized KURE embedding server request",
        )


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        loaded=KureEmbeddingService.is_loaded(),
        model_name=KureEmbeddingService.loaded_model_name() or settings.KURE_MODEL_PATH or settings.KURE_MODEL_NAME,
    )


@app.post("/warmup", response_model=WarmupResponse, dependencies=[Depends(verify_internal_api_key)])
def warmup() -> WarmupResponse:
    dimension = embedding_service.warmup()
    return WarmupResponse(status="ok", dimension=dimension, loaded=True)


@app.post("/embed", response_model=EmbedResponse, dependencies=[Depends(verify_internal_api_key)])
def embed(request: EmbedRequest) -> EmbedResponse:
    try:
        vector = embedding_service.embed(request.text)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        print(f"[KURE EMBED ERROR] error={exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="KURE embedding 생성에 실패했습니다.",
        ) from exc

    return EmbedResponse(dimension=len(vector), vector=vector)
