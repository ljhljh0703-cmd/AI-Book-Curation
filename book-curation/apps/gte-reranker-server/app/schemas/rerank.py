from typing import Any

from pydantic import BaseModel, Field, model_validator


class RerankRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    texts: list[str] = Field(default_factory=list)
    documents: list[str] = Field(default_factory=list)
    return_documents: bool = False

    @model_validator(mode="after")
    def normalize_documents(self) -> "RerankRequest":
        if not self.texts and self.documents:
            self.texts = self.documents
        if not self.texts:
            raise ValueError("texts 또는 documents는 최소 1개 이상이어야 합니다.")
        return self


class RerankItem(BaseModel):
    index: int
    score: float
    document: str | None = None


class RerankResponse(BaseModel):
    model: str
    results: list[RerankItem]


class HealthResponse(BaseModel):
    status: str
    reranker_model: str
    loaded: bool
    model_name: str


class WarmupResponse(BaseModel):
    status: str
    reranker_model: str = "GTE_MULTILINGUAL"
    loaded: bool
    sample_score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
