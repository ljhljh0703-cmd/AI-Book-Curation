from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8002
    APP_ENV: str = "local"

    KURE_MODEL_NAME: str = "nlpai-lab/KURE-v1"
    KURE_MODEL_PATH: str = ""
    KURE_MODEL_CACHE_DIR: str = "/models"
    KURE_DEVICE: str = "cpu"
    KURE_EXPECTED_DIMENSION: int = 1024
    KURE_BATCH_SIZE: int = 16
    KURE_TORCH_NUM_THREADS: int = 2
    KURE_NORMALIZE_EMBEDDINGS: bool = True

    KURE_INTERNAL_API_KEY: str = ""
    KURE_INTERNAL_HEADER_NAME: str = "X-KURE-Internal-Key"

    model_config = SettingsConfigDict(
        # 수정 포인트: 운영용 .env를 유지하면서 로컬 PC 실행 시 .env.local로 포트/모델 캐시/내부키를 덮어쓸 수 있게 합니다.
        # Docker/K8s에서는 환경변수 주입이 우선하므로 기존 배포 설정에는 영향을 주지 않습니다.
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
