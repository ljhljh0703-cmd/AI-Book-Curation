from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8001
    APP_ENV: str = "local"

    # 평가 original/dense 경로는 CLOVA를 쓰지 않으므로 API key가 없어도 settings import가 실패하지 않게 합니다.
    # 실제 CLOVA 호출은 ClovaClient 사용 시점에만 이루어지며, LLM 평가 variant는 실패 시 original query로 fallback합니다.
    CLOVA_API_KEY: str = ""

    # 수정 포인트: CLOVA Studio v3 네이티브 Chat Completions는 /v3/chat-completions/{modelName} 경로를 사용합니다.
    # 환경변수에 모델명이 빠져 있어도 clova_client에서 CLOVA_CHAT_MODEL을 붙여 호출합니다.
    CLOVA_CHAT_URL: str = "https://clovastudio.stream.ntruss.com/v3/chat-completions"
    CLOVA_EMBED_URL: str = "https://clovastudio.stream.ntruss.com/v1/api-tools/embedding/v2"
    CLOVA_CHAT_MODEL: str = "HCX-007"
    CLOVA_EMBED_MODEL: str = "embedding-v2"

    # 수정 포인트: CLOVA 429는 완전히 없앨 수 없으므로, ai-server 내부에서 요청 간격/재시도/쿨다운을 환경변수로 조절합니다.
    CLOVA_MAX_RETRIES: int = 4
    CLOVA_RETRY_INITIAL_DELAY_SECONDS: float = 1.0
    CLOVA_RETRY_MAX_DELAY_SECONDS: float = 30.0
    CLOVA_429_COOLDOWN_SECONDS: float = 30.0
    CLOVA_CHAT_MIN_INTERVAL_SECONDS: float = 1.2
    CLOVA_EMBED_MIN_INTERVAL_SECONDS: float = 1.2
    CLOVA_CHAT_TIMEOUT_SECONDS: float = 60.0
    CLOVA_EMBED_TIMEOUT_SECONDS: float = 30.0
    CLOVA_EMBEDDING_CACHE_SIZE: int = 2048

    QDRANT_URL: str = "http://127.0.0.1:6333"
    QDRANT_API_KEY: str = ""
    QDRANT_COLLECTION: str = "books"
    # 수정 포인트: BM25는 관리자 설정이 켜진 요청에서만 hybrid collection을 사용합니다.
    # 기본값은 OFF이므로 기존 books/books_kure dense lookup 흐름은 그대로 유지됩니다.
    QDRANT_HYBRID_COLLECTION: str = "books_hybrid"
    QDRANT_HYBRID_DENSE_VECTOR_NAME: str = "dense"
    QDRANT_HYBRID_SPARSE_VECTOR_NAME: str = "bm25_text"
    QDRANT_BM25_HASH_METHOD: str = "blake2b_64_mod_2000000000"
    QDRANT_BM25_HASH_MOD: int = 2_000_000_000
    QDRANT_RRF_K: float = 60.0
    # 수정 포인트: BM25 ON 상태의 dense/sparse 검색은 결과 품질을 바꾸지 않고 지연시간만 줄이기 위해 병렬 실행합니다.
    # Qdrant 클라이언트/네트워크 이슈가 있으면 운영 env에서 false로 즉시 되돌릴 수 있습니다.
    QDRANT_HYBRID_PARALLEL_SEARCH_ENABLED: bool = True

    # Valkey/Redis TTL cache settings. PostgreSQL remains the source of truth for logged-in user data.
    REDIS_ENABLED: bool = False
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_USERNAME: str = ""
    REDIS_PASSWORD: str = ""
    REDIS_DATABASE: int = 0
    REDIS_KEY_PREFIX: str = "book-curation"
    REDIS_SOCKET_TIMEOUT_SECONDS: float = 1.0
    GUEST_CHAT_TTL_SECONDS: int = 86400
    GUEST_RATE_LIMIT_PER_MINUTE: int = 8
    GUEST_RATE_LIMIT_PER_DAY: int = 40
    RECOMMENDATION_CACHE_TTL_SECONDS: int = 600
    QDRANT_SEARCH_CACHE_TTL_SECONDS: int = 600
    GTE_RERANK_CACHE_TTL_SECONDS: int = 600
    QDRANT_CACHE_ENABLED: bool = True
    QDRANT_SEARCH_TIMEOUT_SECONDS: float = 5.0
    QDRANT_SEARCH_LIMIT: int = 80
    QDRANT_PREFETCH_LIMIT: int = 100
    GTE_RERANK_TOP_K: int = 20
    RECOMMENDATION_CANDIDATE_LIMIT: int = 80
    # 운영 추천 요청 경로에서는 Qdrant에 write/upsert를 하지 않습니다.
    # payload index 생성이 필요한 경우 별도 관리 작업에서만 true로 켜세요.
    QDRANT_ENSURE_PAYLOAD_INDEXES: bool = False

    # 수정 포인트: KURE는 ai-server 프로세스에 직접 로드하지 않고 별도 FastAPI 서비스로 호출합니다.
    # CLOVA/KURE 벡터 공간이 다르므로 Qdrant 컬렉션도 반드시 분리합니다.
    QDRANT_KURE_COLLECTION: str = "books_kure"
    QDRANT_KURE_HYBRID_COLLECTION: str = "books_kure_hybrid"
    # 수정 포인트: 도서 벡터 컬렉션과 사용자 프로필 벡터 컬렉션을 분리합니다.
    QDRANT_USER_PROFILE_COLLECTION: str = "user_preference_profiles_kure"
    KURE_EMBEDDING_BASE_URL: str = "http://kure-embedding-server:8002"
    KURE_INTERNAL_API_KEY: str = ""
    KURE_INTERNAL_HEADER_NAME: str = "X-KURE-Internal-Key"
    KURE_REQUEST_TIMEOUT_SECONDS: float = 10.0
    KURE_MAX_RETRIES: int = 2
    KURE_RETRY_INITIAL_DELAY_SECONDS: float = 0.3
    KURE_RETRY_MAX_DELAY_SECONDS: float = 2.0
    KURE_EXPECTED_DIMENSION: int = 1024
    KURE_FALLBACK_TO_CLOVA: bool = False

    TOP_K: int = 10
    # 수정 포인트: 개인화 추천 파이프라인의 단계별 limit을 환경변수로 분리합니다.
    # 현재 목표 흐름은 Qdrant 100 → Rule 50 → Profile Vector 20 → Final 5 입니다.
    QDRANT_CANDIDATE_LIMIT: int = 100
    RULE_CANDIDATE_LIMIT: int = 50
    PERSONALIZATION_CANDIDATE_LIMIT: int = 20
    FINAL_RECOMMEND_COUNT: int = 5

    # 수정 포인트: 추천 이유는 후보 선정 이후 1회 LLM으로 자연어만 생성하고,
    # 후보 추가/삭제/순위 변경은 서버 검증 단계에서 차단합니다.
    RECOMMENDATION_REASON_PROVIDER: str = "LLM"
    RECOMMENDATION_REASON_MAX_CHARS: int = 220
    # 추천 카드 선응답을 위해 LLM 추천이유 생성은 기본적으로 비동기 후처리로 실행합니다.
    RECOMMENDATION_REASON_ASYNC_ENABLED: bool = True
    RECOMMENDATION_REASON_ASYNC_WORKERS: int = 2
    RECOMMENDATION_REASON_ASYNC_TTL_SECONDS: int = 900


    # Audience labels are enum-only signals used by deterministic reranking.
    AUDIENCE_LABEL_PROVIDER: str = "PAYLOAD_ONLY"
    AUDIENCE_LABEL_CANDIDATE_LIMIT: int = 12
    AUDIENCE_LABEL_CACHE_SIZE: int = 2048
    # 사용자 프로필 리랭킹마다 후보 대상 독자 라벨을 LLM으로 만들면 지연이 커져 기본값은 비활성화합니다.
    # 어린이/청소년/성인 대상처럼 현재 질문이 독자 대상을 직접 요구한 경우에는 audience stage가 실행됩니다.
    AUDIENCE_LABEL_ENABLE_FOR_PROFILE_RERANK: bool = False


    PERSONALIZATION_PROVIDER: str = "PROFILE_VECTOR"
    SEQUENCE_PROVIDER: str = "NONE"
    RERANKER_PROVIDER: str = "NONE"

    # 수정 포인트: 관리자 DB 설정은 추천 전략/개인화 모델/reranker provider로 분리하고,
    # 인프라 endpoint와 timeout은 k8s ConfigMap/Secret으로 주입합니다.
    RERANKER_ENABLED: bool = False
    GTE_RERANKER_PRIMARY_URL: str = "http://192.168.0.9:7997/rerank"
    GTE_RERANKER_FALLBACK_URL: str = "http://gte-reranker-server:8080/rerank"
    GTE_RERANKER_API_KEY: str = ""
    GTE_RERANKER_HEADER_NAME: str = "X-GTE-Reranker-Key"
    GTE_RERANKER_MODEL_NAME: str = "Alibaba-NLP/gte-multilingual-reranker-base"
    GTE_RERANKER_MAX_DOCUMENTS: int = 20
    GTE_RERANKER_MAX_DOC_CHARS: int = 600
    GTE_RERANKER_PRIMARY_TIMEOUT_SECONDS: float = 3.0
    GTE_RERANKER_FALLBACK_TIMEOUT_SECONDS: float = 8.0
    GTE_RERANKER_FAIL_OPEN: bool = True
    GTE_RERANKER_RETRY_COUNT: int = 0

    # 수정 포인트: 관리자 Reranker=HCX_RERANKER 선택 시 CLOVA Studio Reranker API를 호출합니다.
    # API key는 live secret의 HCX_RERANKER_API_KEY를 우선 사용하고, 없으면 기존 CLOVA_API_KEY로 fallback합니다.
    HCX_RERANKER_URL: str = "https://clovastudio.stream.ntruss.com/v1/api-tools/reranker"
    HCX_RERANKER_API_KEY: str = ""
    HCX_RERANKER_MAX_DOCUMENTS: int = 20
    HCX_RERANKER_MAX_DOC_CHARS: int = 900
    HCX_RERANKER_MAX_TOKENS: int = 1024
    HCX_RERANKER_TIMEOUT_SECONDS: float = 12.0
    HCX_RERANK_CACHE_TTL_SECONDS: int = 600

    # 수정 포인트: 관리자 rankingModel=LIGHTFM 선택 시 사용할 LightFM artifact/runtime 설정입니다.
    # artifact가 없거나 user/item mapping이 맞지 않으면 추천 실패 대신 RULE_BASED로 fallback합니다.
    LIGHTFM_ENABLED: bool = True
    LIGHTFM_ARTIFACT_DIR: str = "artifacts/lightfm/latest"
    # 기존 배포 호환용 alias입니다. 신규 배포에서는 LIGHTFM_ARTIFACT_DIR를 사용합니다.
    LIGHTFM_ARTIFACT_PATH: str = ""
    LIGHTFM_TOP_N: int = 20
    LIGHTFM_CANDIDATE_LIMIT: int = 50
    LIGHTFM_ITEM_ID_FIELDS: str = "isbn,isbn13,book_id,bookId,itemId"
    LIGHTFM_NUM_THREADS: int = 2
    LIGHTFM_SCORE_MODEL_WEIGHT: float = 0.8
    LIGHTFM_SCORE_RULE_WEIGHT: float = 0.2
    LIGHTFM_FALLBACK_TO_RULE_BASED: bool = True
    LIGHTFM_MIN_KNOWN_ITEMS: int = 5

    # NAS 운영 학습 설정입니다. backend가 export/job 상태를 관리하고 ai-server는 subprocess 학습/promote만 수행합니다.
    LIGHTFM_ARTIFACT_ROOT: str = "/app/artifacts/lightfm"
    LIGHTFM_DATASET_DIR: str = "/app/artifacts/lightfm/datasets"
    LIGHTFM_WORK_DIR: str = "/app/artifacts/lightfm/work"
    LIGHTFM_ARTIFACT_VERSIONS_DIR: str = "/app/artifacts/lightfm/versions"
    LIGHTFM_TRAINING_LOG_DIR: str = "/app/artifacts/lightfm/logs"
    LIGHTFM_TRAINING_NUM_THREADS: int = 1
    LIGHTFM_TRAINING_EPOCHS: int = 10
    LIGHTFM_TRAINING_NO_COMPONENTS: int = 32
    LIGHTFM_TRAINING_MAX_SAMPLED: int = 10
    LIGHTFM_TRAINING_LEARNING_RATE: float = 0.03
    LIGHTFM_TRAINING_LOSS: str = "warp"
    LIGHTFM_TRAINING_TIMEOUT_SECONDS: int = 7200
    LIGHTFM_ARTIFACT_RETENTION_COUNT: int = 3
    LIGHTFM_TRAINING_SYNTHETIC_MAX_RATIO: float = 0.5
    LIGHTFM_TRAINING_REAL_WEIGHT_MULTIPLIER: float = 2.0
    LIGHTFM_TRAINING_MAX_ROWS_PER_SOURCE: int = 50000
    LIGHTFM_TRAINING_MODE: str = "HYBRID_LITE"

    # 수정 포인트: 현재 메인 추천 pipeline은 app/prompts/*.md를 load_text_resource로 읽습니다.
    # 이 값은 과거 shared prompt 호환/문서 용도로 유지하되, 이번 변경에서는 삭제하지 않습니다.
    SYSTEM_PROMPT_PATH: str = "../../packages/prompts/book_chat_system_prompt.txt"

    # 수정 포인트: ai-server가 외부로 노출되었거나 개발용 포트가 열린 경우를 대비해 내부 호출용 공유키를 지원합니다.
    # 값이 비어 있으면 기존 배포 호환성을 위해 검증을 비활성화합니다.
    AI_INTERNAL_API_KEY: str = ""
    AI_INTERNAL_HEADER_NAME: str = "X-AI-Internal-Key"

    # 수정 포인트: Java backend rate-limit을 통과한 요청이라도 ai-server에서 한 번 더 유입량을 제한해 외부 LLM API 429를 줄입니다.
    # 제한 초과 시 CLOVA를 호출하지 않고 사용자에게 잠시 후 재시도 안내 응답을 반환합니다.
    AI_REQUEST_RATE_LIMIT_ENABLED: bool = True
    AI_REQUEST_PER_USER_CAPACITY: int = 6
    AI_REQUEST_PER_USER_WINDOW_SECONDS: int = 60
    AI_REQUEST_GLOBAL_CAPACITY: int = 20
    AI_REQUEST_GLOBAL_WINDOW_SECONDS: int = 60
    # 수정 포인트: 비로그인 추천은 user_id가 없으므로 guest session/IP 기준으로 더 보수적인 제한과 낮은 top_k를 사용합니다.
    AI_GUEST_REQUEST_PER_SESSION_CAPACITY: int = 8
    AI_GUEST_REQUEST_PER_SESSION_WINDOW_SECONDS: int = 60
    AI_GUEST_REQUEST_GLOBAL_CAPACITY: int = 15
    AI_GUEST_REQUEST_GLOBAL_WINDOW_SECONDS: int = 60
    AI_GUEST_HISTORY_LIMIT: int = 16
    GUEST_TOP_K: int = 6

    model_config = SettingsConfigDict(
        # 로컬 테스트 설정 추가: 기존 .env를 유지하면서 .env.local이 있으면 마지막에 읽어 localhost 설정으로 덮어씁니다.
        # Docker 배포에서는 .env.local을 포함하지 않으므로 기존 NAS/K3s 설정에는 영향을 주지 않습니다.
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
