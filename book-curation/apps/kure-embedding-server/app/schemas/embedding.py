from pydantic import BaseModel, Field


class EmbedRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class EmbedResponse(BaseModel):
    embedding_model: str = "KURE"
    dimension: int
    vector: list[float]


class WarmupResponse(BaseModel):
    status: str
    embedding_model: str = "KURE"
    dimension: int
    loaded: bool


class HealthResponse(BaseModel):
    status: str
    embedding_model: str = "KURE"
    loaded: bool
    model_name: str
