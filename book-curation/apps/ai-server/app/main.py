import secrets

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.schemas.audience_label import AudienceLabelBatchRequest, AudienceLabelBatchResponse
from app.schemas.chat import ChatRequest, ChatResponse, RecommendationReasonStatusResponse
from app.schemas.lightfm_training import LightFmArtifactSummaryResponse, LightFmTrainingRequest, LightFmTrainingResponse
from app.schemas.query_evaluation import (
    QueryEvaluationCommandResponse,
    QueryEvaluationJobListResponse,
    QueryEvaluationLabelSaveRequest,
    QueryEvaluationRowsResponse,
    QueryEvaluationRunRequest,
    QueryEvaluationSummaryRequest,
)
from app.schemas.preference import (
    ReviewPreferenceAnalysisRequest,
    ReviewPreferenceAnalysisResponse,
    UserPreferenceProfileVectorizeRequest,
    UserPreferenceProfileVectorizeResponse,
)
from app.services.chat.chat_service import BookChatService
from app.services.common.rate_limiter import FixedWindowRateLimiter, RateLimitDecision
from app.services.profiling.review_preference_analyzer import ReviewPreferenceAnalyzer
from app.services.profiling.user_profile_vector_service import UserProfileVectorService
from app.services.recommendation.audience_label_batch import AudienceLabelBatchClassifier
from app.services.recommendation.recommendation_reason_jobs import recommendation_reason_jobs
from app.services.ranking.lightfm_training_service import LightFmTrainingService
from app.services.evaluation.query_payload_rule_evaluation_service import QueryPayloadRuleEvaluationService

app = FastAPI(title="Book Curation AI Server", version="0.2.0")

chat_service = BookChatService()
review_preference_analyzer = ReviewPreferenceAnalyzer()
user_profile_vector_service = UserProfileVectorService()
audience_label_batch_classifier = AudienceLabelBatchClassifier()
lightfm_training_service = LightFmTrainingService()
query_evaluation_service = QueryPayloadRuleEvaluationService()
_user_rate_limiter = FixedWindowRateLimiter()
_global_rate_limiter = FixedWindowRateLimiter()


@app.get("/health")
def health_check():
    return {"status": "ok"}


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        first_ip = forwarded_for.split(",")[0].strip()
        if first_ip:
            return first_ip

    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()

    if request.client and request.client.host:
        return request.client.host

    return "unknown"


def _verify_internal_api_key(request: Request) -> None:
    expected_key = settings.AI_INTERNAL_API_KEY.strip()
    if not expected_key:
        return

    provided_key = request.headers.get(settings.AI_INTERNAL_HEADER_NAME, "").strip()
    if not provided_key or not secrets.compare_digest(provided_key, expected_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized AI server request",
        )


def _busy_response(query: str, decision: RateLimitDecision, rule_name: str, chat_request: ChatRequest) -> JSONResponse:
    retry_after = max(1, decision.retry_after_seconds)
    answer = (
        "현재 AI 추천 요청이 많아 외부 모델 호출을 잠시 제한하고 있습니다. "
        f"약 {retry_after}초 후 다시 질문해 주세요. "
        "이 응답은 CLOVA 429를 더 키우지 않기 위해 ai-server에서 조기 차단한 안내입니다."
    )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        headers={
            "Retry-After": str(retry_after),
            "X-AI-RateLimit-Rule": rule_name,
            "X-AI-RateLimit-Limit-Remaining": str(max(0, decision.remaining)),
        },
        content={
            "query": query,
            "answer": answer,
            "ori_cover_s": None,
            "cover_url": None,
            "cover": None,
            "candidates": [],
            "guest": chat_request.guest,
            "personalized": bool(chat_request.personalized and not chat_request.guest),
            "profile_applied": False,
            "intent": None,
            "intent_source": None,
            "requires_history": False,
            "embedding_model": chat_request.embedding_model or "CLOVA",
            "ranking_model": chat_request.ranking_model or "RULE_BASED",
        },
    )


def _rate_limit(request: Request, chat_request: ChatRequest) -> JSONResponse | None:
    if not settings.AI_REQUEST_RATE_LIMIT_ENABLED:
        return None

    global_decision = _global_rate_limiter.consume(
        key="ai-chat:global",
        capacity=settings.AI_REQUEST_GLOBAL_CAPACITY,
        window_seconds=settings.AI_REQUEST_GLOBAL_WINDOW_SECONDS,
    )
    if not global_decision.allowed:
        return _busy_response(chat_request.query, global_decision, "global", chat_request)

    if chat_request.guest:
        guest_global_decision = _global_rate_limiter.consume(
            key="ai-chat:guest:global",
            capacity=settings.AI_GUEST_REQUEST_GLOBAL_CAPACITY,
            window_seconds=settings.AI_GUEST_REQUEST_GLOBAL_WINDOW_SECONDS,
        )
        if not guest_global_decision.allowed:
            return _busy_response(chat_request.query, guest_global_decision, "guest-global", chat_request)

        # 수정 포인트: 비로그인은 user_id가 없으므로 guestSessionId를 우선 쓰고 없으면 IP 기준으로 제한합니다.
        user_or_ip = chat_request.guest_session_id or f"guest-ip:{_client_ip(request)}"
        rate_limit_key = f"ai-chat:guest:{user_or_ip}"
        user_capacity = settings.AI_GUEST_REQUEST_PER_SESSION_CAPACITY
        user_window_seconds = settings.AI_GUEST_REQUEST_PER_SESSION_WINDOW_SECONDS
    else:
        user_or_ip = chat_request.user_id or f"ip:{_client_ip(request)}"
        rate_limit_key = f"ai-chat:user:{user_or_ip}"
        user_capacity = settings.AI_REQUEST_PER_USER_CAPACITY
        user_window_seconds = settings.AI_REQUEST_PER_USER_WINDOW_SECONDS

    user_decision = _user_rate_limiter.consume(
        key=rate_limit_key,
        capacity=user_capacity,
        window_seconds=user_window_seconds,
    )
    if not user_decision.allowed:
        return _busy_response(chat_request.query, user_decision, "guest-session" if chat_request.guest else "user", chat_request)

    return None


@app.post("/api/v1/admin/audience-labels/classify", response_model=AudienceLabelBatchResponse)
def classify_audience_labels(request: Request, label_request: AudienceLabelBatchRequest):
    _verify_internal_api_key(request)
    return audience_label_batch_classifier.classify(label_request)


@app.get("/api/v1/admin/lightfm/artifact-summary", response_model=LightFmArtifactSummaryResponse)
def lightfm_artifact_summary(request: Request):
    _verify_internal_api_key(request)
    return lightfm_training_service.artifact_summary()


@app.post("/api/v1/admin/lightfm/train", response_model=LightFmTrainingResponse)
def train_lightfm_artifact(request: Request, training_request: LightFmTrainingRequest):
    _verify_internal_api_key(request)
    return lightfm_training_service.train_and_promote(training_request)




@app.post("/api/v1/admin/evaluation/query-payload-rules/run", response_model=QueryEvaluationCommandResponse)
def run_query_payload_rule_evaluation(request: Request, eval_request: QueryEvaluationRunRequest):
    _verify_internal_api_key(request)
    return query_evaluation_service.run(eval_request)


@app.get("/api/v1/admin/evaluation/query-payload-rules/jobs", response_model=QueryEvaluationJobListResponse)
def query_payload_rule_jobs(request: Request, limit: int = 50):
    _verify_internal_api_key(request)
    return query_evaluation_service.list_jobs(limit=limit)


@app.get("/api/v1/admin/evaluation/query-payload-rules/labels", response_model=QueryEvaluationRowsResponse)
def query_payload_rule_label_rows(
    request: Request,
    out_dir: str | None = None,
    offset: int = 0,
    limit: int = 200,
):
    _verify_internal_api_key(request)
    return query_evaluation_service.read_labels(out_dir=out_dir, offset=offset, limit=limit)


@app.put("/api/v1/admin/evaluation/query-payload-rules/labels", response_model=QueryEvaluationCommandResponse)
def save_query_payload_rule_labels(request: Request, label_request: QueryEvaluationLabelSaveRequest):
    _verify_internal_api_key(request)
    return query_evaluation_service.save_labels(label_request)


@app.post("/api/v1/admin/evaluation/query-payload-rules/summarize", response_model=QueryEvaluationCommandResponse)
def summarize_query_payload_rule_labels(request: Request, summary_request: QueryEvaluationSummaryRequest):
    _verify_internal_api_key(request)
    return query_evaluation_service.summarize(summary_request)


@app.get("/api/v1/admin/evaluation/query-payload-rules/summary", response_model=QueryEvaluationRowsResponse)
def query_payload_rule_summary_rows(
    request: Request,
    out_dir: str | None = None,
    summary_type: str = "labeled",
    offset: int = 0,
    limit: int = 200,
):
    _verify_internal_api_key(request)
    return query_evaluation_service.read_summary(out_dir=out_dir, summary_type=summary_type, offset=offset, limit=limit)

@app.post("/api/v1/reviews/analyze", response_model=ReviewPreferenceAnalysisResponse)
def analyze_review_preference(request: Request, analysis_request: ReviewPreferenceAnalysisRequest):
    _verify_internal_api_key(request)
    return review_preference_analyzer.analyze(analysis_request)


@app.post("/api/v1/user-preference-profiles/vectorize", response_model=UserPreferenceProfileVectorizeResponse)
def vectorize_user_preference_profile(request: Request, vectorize_request: UserPreferenceProfileVectorizeRequest):
    _verify_internal_api_key(request)
    return user_profile_vector_service.vectorize(vectorize_request)


@app.get("/api/v1/chat/recommendation-reasons/{request_id}", response_model=RecommendationReasonStatusResponse)
def recommendation_reasons(request: Request, request_id: str):
    _verify_internal_api_key(request)
    return recommendation_reason_jobs.get(request_id)


@app.post("/api/v1/chat/recommend", response_model=ChatResponse)
def recommend_books(request: Request, chat_request: ChatRequest):
    _verify_internal_api_key(request)

    limited_response = _rate_limit(request, chat_request)
    if limited_response is not None:
        return limited_response

    history = chat_request.history or []

    # 로그인 사용자 프로필만 리랭킹에 사용합니다.
    # guest=True인 경우 guest_profile은 리랭킹에 사용하지 않고 빈 dict를 전달합니다.
    active_user_profile = chat_request.user_profile if not chat_request.guest else {}

    result = chat_service.recommend(
        query=chat_request.query,
        personalized=chat_request.personalized,
        history=[item.model_dump() for item in history],
        user_id=chat_request.user_id,
        guest=chat_request.guest,
        guest_session_id=chat_request.guest_session_id,
        guest_room_id=chat_request.guest_room_id,
        user_profile=active_user_profile,
        guest_profile={},
        embedding_model=chat_request.embedding_model,
        ranking_model=chat_request.ranking_model,
        # 수정 포인트: backend가 전달한 관리자 추천 설정을 누락하지 않고 ai-server service layer까지 전달합니다.
        # 기존에는 ranking_model만 전달되어 RERANKER_PROVIDER=GTE_MULTILINGUAL이어도
        # service 기본값(NONE)으로 덮여 GTE/Alibaba reranker가 실행되지 않았습니다.
        recommendation_strategy=chat_request.recommendation_strategy,
        personalization_model=chat_request.personalization_model,
        reranker_provider=chat_request.reranker_provider,
        bm25_enabled=chat_request.bm25_enabled,
        request_id=chat_request.request_id,
        audience_label_map=chat_request.audience_label_map,
    )

    return JSONResponse(content=result)
