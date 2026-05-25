export interface ChatSession {
  id: string;
  title: string;
  status: string;
  createdAt: string;
  updatedAt: string;
}

export interface ChatSessionListResponse {
  maxActiveChatCount: number;
  maxUserMessageCount: number;
  sessions: ChatSession[];
}

export interface RecommendedBookCandidate {
  isbn?: string | null;
  title?: string | null;
  author?: string | null;
  publisher?: string | null;
  publish_date?: string | null;
  publishDate?: string | null;
  simple_intro?: string | null;
  simpleIntro?: string | null;
  book_intro?: string | null;
  bookIntro?: string | null;
  book_index?: string | null;
  bookIndex?: string | null;
  pub_review?: string | null;
  pubReview?: string | null;
  description?: string | null;
  page?: number | null;
  price?: number | null;
  ori_cover_s?: string | null;
  oriCoverS?: string | null;
  cover_url?: string | null;
  coverUrl?: string | null;
  cover?: string | null;
  categories?: string[];
  cate_depth1?: string[];
  cateDepth1?: string[];
  kcid?: string[];
  score?: number | null;
  // 수정 포인트: 추천 파이프라인 단계별 score를 프론트 타입에 열어두어 향후 LightFM/SASRec/Reranker 점수 표시/로그에 재사용합니다.
  rank?: number | null;
  recommended_at?: string | null;
  recommendedAt?: string | null;
  candidateRelevanceScore?: number | null;
  qdrantScore?: number | null;
  ruleScore?: number | null;
  profileVectorScore?: number | null;
  lightfmScore?: number | null;
  sasrecScore?: number | null;
  rerankerScore?: number | null;
  preScore?: number | null;
  finalScore?: number | null;
  rerank_score?: number | null;
  rerankScore?: number | null;
  rerank_reason?: string | null;
  rerankReason?: string | null;
  recommendation_reason?: string | null;
  recommendationReason?: string | null;
  recommendation_reason_source?: string | null;
  recommendationReasonSource?: string | null;
  recommendation_reason_status?: string | null;
  recommendationReasonStatus?: string | null;
  audience_profile?: Record<string, unknown>;
  audienceProfile?: Record<string, unknown>;
  score_detail?: Record<string, unknown>;
  scoreDetail?: Record<string, unknown>;
}

export interface ChatMessageMetadata {
  source?: "AI_SERVER" | string;
  latencyMs?: number;
  cover?: string | null;
  // 수정 포인트: 추천 요청 단위 requestId와 provider 정보를 카드 클릭/상세보기 로그에 그대로 전달합니다.
  requestId?: string | null;
  query?: string | null;
  embeddingModel?: string | null;
  rankingModel?: string | null;
  personalizationProvider?: string | null;
  sequenceProvider?: string | null;
  rerankerProvider?: string | null;
  pipeline?: Record<string, unknown>;
  candidates?: RecommendedBookCandidate[];
  recommendationReasonStatus?: string | null;
  recommendationReasonErrorMessage?: string | null;
  [key: string]: unknown;
}

export interface ChatMessage {
  id: number;
  sessionId: string;
  role: "USER" | "ASSISTANT" | "SYSTEM" | "TOOL";
  content: string;
  // 수정 포인트: backend가 AI 추천 후보 도서와 표지 정보를 metadata JSONB로 내려주면 프론트에서 카드 형태로 표시합니다.
  metadata?: ChatMessageMetadata;
  createdAt: string;
}

export interface SendChatMessageResponse {
  session: ChatSession;
  userMessage: ChatMessage;
  assistantMessage: ChatMessage;
  maxUserMessageCount: number;
}

export interface GuestChatHistoryItem {
  role: "user" | "assistant";
  content: string;
  createdAt?: string | null;
  candidates?: RecommendedBookCandidate[];
  // 수정 포인트: 비로그인 후속 질문에서 이전 응답의 reading_mode/consumption_context를
  // ai-server가 복원할 수 있도록 최소 metadata subset만 전달합니다.
  metadata?: Record<string, unknown>;
}

export interface GuestProfileSnapshot {
  preferredGenres: string[];
  dislikedGenres: string[];
  preferredMoods: string[];
  dislikedMoods: string[];
  readingLevel: string | null;
  summary: string;
}

export interface GuestRecommendRequest {
  guestSessionId: string;
  guestRoomId: string;
  content: string;
  history: GuestChatHistoryItem[];
  guestProfile: GuestProfileSnapshot;
}

export interface GuestAssistantMessage {
  role: "ASSISTANT";
  content: string;
  metadata?: ChatMessageMetadata;
  createdAt: string;
}

export interface GuestRecommendResponse {
  guest: true;
  personalized: false;
  maxGuestChatCount: number;
  maxGuestUserMessageCount: number;
  loginPrompt: string;
  assistantMessage: GuestAssistantMessage;
}

export interface GuestStoredMessage {
  role: "USER" | "ASSISTANT";
  content: string;
  metadata?: ChatMessageMetadata;
  createdAt: string;
}

export interface GuestChatMessagesResponse {
  guestSessionId: string;
  guestRoomId: string;
  messages: GuestStoredMessage[];
}

export interface RecommendationReasonStatusResponse {
  requestId?: string | null;
  request_id?: string | null;
  status: string;
  answer?: string | null;
  candidates?: RecommendedBookCandidate[];
  errorMessage?: string | null;
  error_message?: string | null;
  assistantMessage?: ChatMessage | null;
}
