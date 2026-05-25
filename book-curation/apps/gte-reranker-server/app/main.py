from __future__ import annotations

import secrets

from fastapi import Depends, FastAPI, HTTPException, Request, status

from app.core.config import settings
from app.schemas.rerank import HealthResponse, RerankItem, RerankRequest, RerankResponse, WarmupResponse
from app.services.gte_reranker_service import GteRerankerService

app = FastAPI(title="Book Curation GTE Reranker Server", version="0.1.0")
reranker_service = GteRerankerService()


def verify_internal_api_key(request: Request) -> None:
    expected_key = settings.GTE_RERANKER_API_KEY.strip()
    if not expected_key:
        return
    header_name = settings.GTE_RERANKER_HEADER_NAME.strip() or "X-GTE-Reranker-Key"
    provided_key = request.headers.get(header_name, "").strip()
    if not provided_key or not secrets.compare_digest(provided_key, expected_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized GTE reranker server request",
        )


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        reranker_model="GTE_MULTILINGUAL",
        loaded=GteRerankerService.is_loaded(),
        model_name=GteRerankerService.loaded_model_name() or settings.GTE_RERANKER_MODEL_PATH or settings.GTE_RERANKER_MODEL_NAME,
    )


@app.post("/warmup", response_model=WarmupResponse, dependencies=[Depends(verify_internal_api_key)])
def warmup() -> WarmupResponse:
    score = reranker_service.warmup()
    return WarmupResponse(status="ok", loaded=True, sample_score=score)


@app.post("/rerank", response_model=RerankResponse, dependencies=[Depends(verify_internal_api_key)])
def rerank(request: RerankRequest) -> RerankResponse:
    try:
        scores = reranker_service.rerank(request.query, request.texts)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        print(f"[GTE RERANK ERROR] error={exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GTE reranker 추론에 실패했습니다.",
        ) from exc

    ranked = sorted(enumerate(scores), key=lambda row: row[1], reverse=True)
    results = [
        RerankItem(
            index=index,
            score=float(score),
            document=request.texts[index] if request.return_documents and index < len(request.texts) else None,
        )
        for index, score in ranked
    ]
    return RerankResponse(model=settings.GTE_RERANKER_MODEL_PATH or settings.GTE_RERANKER_MODEL_NAME, results=results)
