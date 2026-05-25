from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatHistoryItem(BaseModel):
    # 수정 포인트: 이전 ai-server 응답의 top-level debug metadata나 backend metadata wrapper를
    # 멀티턴 intent 승계에 사용할 수 있도록 extra 필드를 보존합니다.
    model_config = ConfigDict(extra="allow")

    role: str
    content: str
    created_at: Optional[str] = None
    createdAt: Optional[str] = None
    candidates: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BookCandidate(BaseModel):
    isbn: Optional[str] = None
    title: Optional[str] = None
    author: Optional[str] = None
    publisher: Optional[str] = None
    publish_date: Optional[str] = None
    page: Optional[int] = None
    price: Optional[int] = None
    format: Optional[str] = None
    book_format: Optional[str] = None
    media_type: Optional[str] = None
    content_format: Optional[str] = None
    is_audio_book: Optional[bool] = None
    is_ebook: Optional[bool] = None
    simple_intro: Optional[str] = None
    book_intro: Optional[str] = None
    description: Optional[str] = None
    categories: List[str] = Field(default_factory=list)
    cate_depth1: List[str] = Field(default_factory=list)
    kcid: List[str] = Field(default_factory=list)
    cate_depth2: List[str] = Field(default_factory=list)
    cate_depth3: List[str] = Field(default_factory=list)
    genre: Optional[str] = None
    genres: List[str] = Field(default_factory=list)
    categoryName: Optional[str] = None
    category_name: Optional[str] = None
    category_full_name: Optional[str] = None
    category_path: Optional[str] = None
    audience_profile: Dict[str, Any] = Field(default_factory=dict)
    book_index: Optional[str] = None
    pub_review: Optional[str] = None
    ori_cover_s: Optional[str] = None
    cover_url: Optional[str] = None
    cover: Optional[str] = None
    author_intro: Optional[str] = None
    score: float = 0.0
    # 수정 포인트: 이후 LightFM/SASRec/Cross-Encoder 점수를 붙일 수 있도록 단계별 점수 필드를 미리 열어둡니다.
    rank: Optional[int] = None
    recommended_at: Optional[str] = None
    candidateRelevanceScore: Optional[float] = None
    qdrantScore: Optional[float] = None
    ruleScore: Optional[float] = None
    profileVectorScore: Optional[float] = None
    lightfmScore: Optional[float] = None
    sasrecScore: Optional[float] = None
    rerankerScore: Optional[float] = None
    preScore: Optional[float] = None
    finalScore: Optional[float] = None
    
    rerank_score: Optional[float] = None
    rerank_reason: Optional[str] = None
    recommendation_reason: Optional[str] = None
    recommendation_reason_source: Optional[str] = None
    recommendation_reason_status: Optional[str] = None
    # 수정 포인트: 개인화 리랭킹 디버깅용 세부 점수입니다. 프론트 사용자 UI에는 노출하지 않아도 됩니다.
    score_detail: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("categories", "cate_depth1", "kcid", "cate_depth2", "cate_depth3", "genres", mode="before")
    @classmethod
    def _coerce_list_fields(cls, value: Any) -> List[Any]:
        # 수정 포인트: Qdrant payload 또는 비동기 reason job 결과에서 list 필드가 None으로 들어와도
        # 응답 검증이 500으로 깨지지 않도록 빈 list로 정규화합니다.
        return value if isinstance(value, list) else []

    @field_validator("audience_profile", "score_detail", mode="before")
    @classmethod
    def _coerce_dict_fields(cls, value: Any) -> Dict[str, Any]:
        # 수정 포인트: audience_profile=None 때문에 recommendation-reasons 조회가 500이 되는 문제를 방지합니다.
        return value if isinstance(value, dict) else {}


class ChatRequest(BaseModel):
    # 수정 포인트: backend가 생성한 추천 요청 식별자를 ai-server까지 전달해 노출/클릭 로그를 묶습니다.
    request_id: Optional[str] = None
    user_id: Optional[str] = None
    query: str
    personalized: bool = False

    # 수정 포인트: 비로그인 추천 요청인지 구분하기 위한 플래그입니다.
    # guest=true이면 user_id 없이 guest_profile 기반으로 추천 흐름을 보강합니다.
    guest: bool = False

    # 수정 포인트: 비로그인 브라우저/채팅방 식별값입니다.
    # ai-server는 저장하지 않고, rate-limit/debug/logging 용도로만 사용할 수 있습니다.
    guest_session_id: Optional[str] = None
    guest_room_id: Optional[str] = None

    # 수정 포인트: 로그인 사용자의 온보딩/서재/리뷰/평점/비선호 정보를 backend가 모아서 전달합니다.
    # 실제 리랭킹 구현 전에도 검색어 보강과 답변 프롬프트에 사용합니다.
    user_profile: Dict[str, Any] = Field(default_factory=dict)

    # 수정 포인트: 비로그인 사용자의 채팅방별 임시 프로필입니다.
    # frontend localStorage에서 유지한 값을 backend가 그대로 전달합니다.
    guest_profile: Dict[str, Any] = Field(default_factory=dict)

    # 수정 포인트: PostgreSQL book.books READY audience label을 ISBN key로 전달받아 후보 soft reranking에 사용합니다.
    audience_label_map: Dict[str, Dict[str, Any]] = Field(default_factory=dict)

    # 수정 포인트: backend 관리자 설정값을 recommend 요청마다 전달받아 검색/랭킹 전략을 선택합니다.
    embedding_model: Optional[str] = "CLOVA"
    # 수정 포인트: ranking_model은 기존 backend/로그 호환 필드이고, 신규 설정은 아래 세 필드로 분리합니다.
    ranking_model: Optional[str] = "LIGHTFM"
    recommendation_strategy: Optional[str] = "AUTO_HYBRID"
    personalization_model: Optional[str] = "LIGHTFM"
    reranker_provider: Optional[str] = "NONE"
    # 수정 포인트: 기본값 false라서 관리자에서 켜지 않는 한 기존 books/books_kure dense lookup 흐름과 동일하게 동작합니다.
    bm25_enabled: bool = False

    history: List[ChatHistoryItem] = Field(default_factory=list)


class ChatResponse(BaseModel):
    request_id: Optional[str] = None
    query: str
    answer: str
    cover: Optional[str] = None
    cover_url: Optional[str] = None
    ori_cover_s: Optional[str] = None
    candidates: List[BookCandidate] = Field(default_factory=list)

    # 수정 포인트: 호출자가 현재 추천이 어떤 모드로 생성됐는지 확인할 수 있게 합니다.
    guest: bool = False
    personalized: bool = False
    profile_applied: bool = False

    # 수정 포인트: 비로그인 멀티턴 디버깅용 메타 정보입니다.
    # 프론트/백엔드가 사용하지 않아도 무해하며, 로그로 intent 분류 결과를 확인할 수 있습니다.
    intent: Optional[str] = None
    intent_source: Optional[str] = None
    requires_history: bool = False

    # 수정 포인트: 관리자 추천 모델 설정이 실제 ai-server 응답까지 전달됐는지 확인하기 위한 메타데이터입니다.
    embedding_model: str = "CLOVA"
    ranking_model: str = "LIGHTFM"
    recommendation_strategy: str = "AUTO_HYBRID"
    personalization_model: str = "LIGHTFM"
    personalization_provider: str = "PROFILE_VECTOR"
    sequence_provider: str = "NONE"
    reranker_provider: str = "NONE"
    bm25_enabled: bool = False
    retrieval_strategy: Optional[str] = None
    retrieval_fallback: bool = False
    retrieval_fallback_reason: Optional[str] = None
    pipeline: Dict[str, Any] = Field(default_factory=dict)
    # 수정 포인트: ai-server 내부 stage별 소요 시간을 응답에 포함해 추천모델/리랭커 적용 전후 병목을 비교합니다.
    timings: Dict[str, Any] = Field(default_factory=dict)

    # 수정 포인트: 관리자 rankingModel 값이 실제 모델 stage에 적용됐는지 확인하기 위한 메타데이터입니다.
    ranking_model_applied: bool = False
    ranking_model_fallback: bool = False
    ranking_model_fallback_reason: Optional[str] = None
    ranking_model_applied_model: Optional[str] = None
    ranking_artifact_version: Optional[str] = None

    recommendation_reason_status: Optional[str] = None
    recommendation_reason_error_message: Optional[str] = None

    # 수정 포인트: 소비 상황/도서 주제 분리와 검색·리랭킹 정규화 결과를 운영 응답에서 확인합니다.
    detected_consumption_context: Optional[str] = None
    detected_reading_mode: Optional[str] = None
    consumption_context_type: Optional[str] = None
    visual_attention_limited: Optional[bool] = None
    hands_free_preferred: Optional[bool] = None
    requires_visual_reference: Optional[bool] = None
    topic_query: Optional[str] = None
    retrieval_query: Optional[str] = None
    reranker_query: Optional[str] = None
    context_policy_applied: bool = False
    excluded_by_context_policy: Optional[int] = None
    personalization_mode_before: Optional[str] = None
    personalization_mode_after: Optional[str] = None
    final_limit: Optional[int] = None

    # 수정 포인트: 사용자 질의/온보딩 중 어느 전략이 적용됐는지 디버깅하기 위한 메타데이터입니다.
    personalization_mode: Optional[str] = None
    personalization_query_score: float = 0.0
    personalization_profile_score: float = 0.0
    personalization_reason: Optional[str] = None
    personalization_core_terms: List[str] = Field(default_factory=list)

    # 수정 포인트: 사용자가 "한 권만/두 권만"처럼 추천 개수를 명시한 경우
    # ai-server의 final stage가 실제 몇 권을 반환했는지 backend/frontend 로그에서 확인할 수 있게 합니다.
    final_recommendation_limit: Optional[int] = None

    # 수정 포인트: 후속 질문에서 이전 소비 상황/청취 모드가 실제로 승계됐는지 운영 응답에서 확인합니다.
    multi_turn_context_inherited: bool = False
    multi_turn_context_source: Optional[str] = None
    multi_turn_context_reason: Optional[str] = None
    inherited_reading_mode: Optional[str] = None
    inherited_consumption_context: Optional[str] = None
    inherited_requested_audience_group: Optional[str] = None


class RecommendationReasonStatusResponse(BaseModel):
    request_id: str
    status: str
    answer: Optional[str] = None
    candidates: List[BookCandidate] = Field(default_factory=list)
    error_message: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
