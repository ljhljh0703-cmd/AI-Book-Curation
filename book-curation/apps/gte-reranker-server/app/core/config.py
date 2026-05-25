from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8080
    APP_ENV: str = "local"

    GTE_RERANKER_MODEL_NAME: str = "Alibaba-NLP/gte-multilingual-reranker-base"
    GTE_RERANKER_MODEL_PATH: str = ""
    GTE_RERANKER_MODEL_CACHE_DIR: str = "/models"
    GTE_RERANKER_DEVICE: str = "cpu"
    GTE_RERANKER_BATCH_SIZE: int = 4
    GTE_RERANKER_TORCH_NUM_THREADS: int = 2
    GTE_RERANKER_TRUST_REMOTE_CODE: bool = True
    GTE_RERANKER_MAX_TEXT_CHARS: int = 1200

    GTE_RERANKER_API_KEY: str = ""
    GTE_RERANKER_HEADER_NAME: str = "X-GTE-Reranker-Key"

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
