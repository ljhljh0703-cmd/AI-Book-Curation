package com.taeo.bookcuration.chat.client;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.taeo.bookcuration.config.AiServerProperties;
import com.taeo.bookcuration.recommendation.service.RecommendationModelSettingService.RecommendationModelSetting;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

import java.io.IOException;
import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@Slf4j
@Component
public class AiRecommendationClient {

    private static final String AI_INTERNAL_HEADER_NAME = "X-AI-Internal-Key";
    private static final String DEFAULT_EMBEDDING_MODEL = "CLOVA";
    private static final String DEFAULT_RANKING_MODEL = "LIGHTFM";

    private final RestClient restClient;
    private final RestClient longRunningRestClient;
    private final ObjectMapper objectMapper;
    private final String internalApiKey;

    public AiRecommendationClient(AiServerProperties properties) {
        SimpleClientHttpRequestFactory requestFactory = new SimpleClientHttpRequestFactory();
        requestFactory.setConnectTimeout(toMillis(properties.connectTimeout()));
        requestFactory.setReadTimeout(toMillis(properties.readTimeout()));

        SimpleClientHttpRequestFactory longRunningRequestFactory = new SimpleClientHttpRequestFactory();
        longRunningRequestFactory.setConnectTimeout(toMillis(properties.connectTimeout()));
        longRunningRequestFactory.setReadTimeout(toMillis(properties.lightfmTrainingReadTimeout()));

        this.internalApiKey = properties.internalApiKey();
        this.objectMapper = new ObjectMapper()
                .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);
        this.restClient = RestClient.builder()
                .baseUrl(properties.baseUrl())
                .requestFactory(requestFactory)
                .build();
        this.longRunningRestClient = RestClient.builder()
                .baseUrl(properties.baseUrl())
                .requestFactory(longRunningRequestFactory)
                .build();
    }

    public ReviewPreferenceAnalysisResponse analyzeReviewPreference(ReviewPreferenceAnalysisRequest request) {
        return restClient.post()
                .uri("/api/v1/reviews/analyze")
                .headers(this::applyInternalApiKey)
                .body(request)
                .retrieve()
                .onStatus(HttpStatusCode::isError, (req, res) -> {
                    log.warn("AI review preference analysis API failed. status={}", res.getStatusCode());
                    throw new IllegalStateException("AI 리뷰 분석 서버 응답이 올바르지 않습니다.");
                })
                .body(ReviewPreferenceAnalysisResponse.class);
    }

    public UserPreferenceProfileVectorizeResponse vectorizeUserPreferenceProfile(UserPreferenceProfileVectorizeRequest request) {
        return restClient.post()
                .uri("/api/v1/user-preference-profiles/vectorize")
                .headers(this::applyInternalApiKey)
                .body(request)
                .retrieve()
                .onStatus(HttpStatusCode::isError, (req, res) -> {
                    log.warn("AI user preference profile vectorize API failed. status={}", res.getStatusCode());
                    throw new IllegalStateException("AI 사용자 프로필 벡터화 서버 응답이 올바르지 않습니다.");
                })
                .body(UserPreferenceProfileVectorizeResponse.class);
    }

    public AiRecommendationResponse recommend(UUID userId, String query, List<ChatHistoryItem> history) {
        return recommend(UUID.randomUUID(), userId, query, history, Map.of(), null);
    }

    public AiRecommendationResponse recommend(
            UUID userId,
            String query,
            List<ChatHistoryItem> history,
            Map<String, Object> userProfile
    ) {
        return recommend(UUID.randomUUID(), userId, query, history, userProfile, null);
    }

    public AiRecommendationResponse recommend(
            UUID requestId,
            UUID userId,
            String query,
            List<ChatHistoryItem> history,
            Map<String, Object> userProfile,
            RecommendationModelSetting modelSetting
    ) {
        return recommend(requestId, userId, query, history, userProfile, modelSetting, Map.of());
    }

    public AiRecommendationResponse recommend(
            UUID requestId,
            UUID userId,
            String query,
            List<ChatHistoryItem> history,
            Map<String, Object> userProfile,
            RecommendationModelSetting modelSetting,
            Map<String, Map<String, Object>> audienceLabelMap
    ) {
        Map<String, Object> safeUserProfile = userProfile == null ? Map.of() : userProfile;
        Map<String, Map<String, Object>> safeAudienceLabelMap = audienceLabelMap == null ? Map.of() : audienceLabelMap;
        AiRecommendationRequest request = new AiRecommendationRequest(
                requestId == null ? null : requestId.toString(),
                userId.toString(),
                query,
                isPersonalizedProfile(safeUserProfile),
                false,
                null,
                null,
                history == null ? List.of() : history,
                Map.of(),
                safeUserProfile,
                safeAudienceLabelMap,
                resolveEmbeddingModel(modelSetting),
                resolveRankingModel(modelSetting),
                resolveRecommendationStrategy(modelSetting),
                resolvePersonalizationModel(modelSetting),
                resolveRerankerProvider(modelSetting),
                resolveBm25Enabled(modelSetting)
        );

        return postRecommend(request, "AI recommendation API failed. status={}");
    }

    public AiRecommendationResponse recommendGuest(
            String guestSessionId,
            String guestRoomId,
            String query,
            List<ChatHistoryItem> history,
            Map<String, Object> guestProfile
    ) {
        return recommendGuest(UUID.randomUUID(), guestSessionId, guestRoomId, query, history, guestProfile, null);
    }

    public AiRecommendationResponse recommendGuest(
            UUID requestId,
            String guestSessionId,
            String guestRoomId,
            String query,
            List<ChatHistoryItem> history,
            Map<String, Object> guestProfile,
            RecommendationModelSetting modelSetting
    ) {
        return recommendGuest(requestId, guestSessionId, guestRoomId, query, history, guestProfile, modelSetting, Map.of());
    }

    public AiRecommendationResponse recommendGuest(
            UUID requestId,
            String guestSessionId,
            String guestRoomId,
            String query,
            List<ChatHistoryItem> history,
            Map<String, Object> guestProfile,
            RecommendationModelSetting modelSetting,
            Map<String, Map<String, Object>> audienceLabelMap
    ) {
        AiRecommendationRequest request = new AiRecommendationRequest(
                requestId == null ? null : requestId.toString(),
                null,
                query,
                false,
                true,
                guestSessionId,
                guestRoomId,
                history == null ? List.of() : history,
                guestProfile == null ? Map.of() : guestProfile,
                Map.of(),
                audienceLabelMap == null ? Map.of() : audienceLabelMap,
                resolveEmbeddingModel(modelSetting),
                resolveRankingModel(modelSetting),
                resolveRecommendationStrategy(modelSetting),
                resolvePersonalizationModel(modelSetting),
                resolveRerankerProvider(modelSetting),
                resolveBm25Enabled(modelSetting)
        );

        return postRecommend(request, "Guest AI recommendation API failed. status={}");
    }

    private AiRecommendationResponse postRecommend(AiRecommendationRequest request, String errorLogMessage) {
        byte[] responseBody = restClient.post()
                .uri("/api/v1/chat/recommend")
                .headers(this::applyInternalApiKey)
                .body(request)
                .retrieve()
                .onStatus(HttpStatusCode::isError, (req, res) -> {
                    log.warn(errorLogMessage, res.getStatusCode());
                    throw new IllegalStateException("AI 추천 서버 응답이 올바르지 않습니다. 잠시 후 다시 시도해주세요.");
                })
                .body(byte[].class);
        if (responseBody == null || responseBody.length == 0) {
            throw new IllegalStateException("AI 추천 서버 응답이 비어 있습니다. 잠시 후 다시 시도해주세요.");
        }
        try {
            return objectMapper.readValue(responseBody, AiRecommendationResponse.class);
        } catch (IOException ex) {
            log.warn("AI recommendation JSON parse failed. responseBytes={}", responseBody.length, ex);
            throw new IllegalStateException("AI 추천 서버 응답 형식을 해석할 수 없습니다. 잠시 후 다시 시도해주세요.");
        }
    }



    public LightFmArtifactSummaryClientResponse getLightFmArtifactSummary() {
        return restClient.get()
                .uri("/api/v1/admin/lightfm/artifact-summary")
                .headers(this::applyInternalApiKey)
                .retrieve()
                .onStatus(HttpStatusCode::isError, (req, res) -> {
                    log.warn("AI LightFM artifact summary API failed. status={}", res.getStatusCode());
                    throw new IllegalStateException("AI LightFM artifact summary 서버 응답이 올바르지 않습니다.");
                })
                .body(LightFmArtifactSummaryClientResponse.class);
    }

    public LightFmTrainingResponse trainLightFm(LightFmTrainingRequest request) {
        return longRunningRestClient.post()
                .uri("/api/v1/admin/lightfm/train")
                .headers(this::applyInternalApiKey)
                .body(request)
                .retrieve()
                .onStatus(HttpStatusCode::isError, (req, res) -> {
                    log.warn("AI LightFM training API failed. status={}", res.getStatusCode());
                    throw new IllegalStateException("AI LightFM training 서버 응답이 올바르지 않습니다.");
                })
                .body(LightFmTrainingResponse.class);
    }

    public AudienceLabelBatchResponse classifyAudienceLabels(AudienceLabelBatchRequest request) {
        return restClient.post()
                .uri("/api/v1/admin/audience-labels/classify")
                .headers(this::applyInternalApiKey)
                .body(request)
                .retrieve()
                .onStatus(HttpStatusCode::isError, (req, res) -> {
                    log.warn("AI audience label classify API failed. status={}", res.getStatusCode());
                    throw new IllegalStateException("AI audience label 서버 응답이 올바르지 않습니다.");
                })
                .body(AudienceLabelBatchResponse.class);
    }

    private boolean isPersonalizedProfile(Map<String, Object> userProfile) {
        if (userProfile == null || userProfile.isEmpty()) {
            return false;
        }
        Object profileAvailable = userProfile.get("profileAvailable");
        if (profileAvailable instanceof Boolean value) {
            return value;
        }
        return true;
    }

    private String resolveEmbeddingModel(RecommendationModelSetting modelSetting) {
        if (modelSetting == null || modelSetting.embeddingModel() == null || modelSetting.embeddingModel().isBlank()) {
            return DEFAULT_EMBEDDING_MODEL;
        }
        return modelSetting.embeddingModel();
    }

    private String resolveRankingModel(RecommendationModelSetting modelSetting) {
        if (modelSetting == null || modelSetting.rankingModel() == null || modelSetting.rankingModel().isBlank()) {
            return DEFAULT_RANKING_MODEL;
        }
        return modelSetting.rankingModel();
    }

    private String resolveRecommendationStrategy(RecommendationModelSetting modelSetting) {
        if (modelSetting == null || modelSetting.recommendationStrategy() == null || modelSetting.recommendationStrategy().isBlank()) {
            return "AUTO_HYBRID";
        }
        return modelSetting.recommendationStrategy();
    }

    private String resolvePersonalizationModel(RecommendationModelSetting modelSetting) {
        if (modelSetting == null || modelSetting.personalizationModel() == null || modelSetting.personalizationModel().isBlank()) {
            return resolveRankingModel(modelSetting);
        }
        return modelSetting.personalizationModel();
    }

    private String resolveRerankerProvider(RecommendationModelSetting modelSetting) {
        if (modelSetting == null || modelSetting.rerankerProvider() == null || modelSetting.rerankerProvider().isBlank()) {
            return "NONE";
        }
        return modelSetting.rerankerProvider();
    }

    private Boolean resolveBm25Enabled(RecommendationModelSetting modelSetting) {
        // 수정 포인트: BM25는 관리자 설정에서 명시적으로 켜진 경우에만 ai-server에 전달합니다.
        return modelSetting != null && Boolean.TRUE.equals(modelSetting.bm25Enabled());
    }

    private void applyInternalApiKey(HttpHeaders headers) {
        if (internalApiKey != null && !internalApiKey.isBlank()) {
            headers.set(AI_INTERNAL_HEADER_NAME, internalApiKey);
        }
    }

    private int toMillis(Duration duration) {
        return Math.toIntExact(duration.toMillis());
    }

    public RecommendationReasonStatusResponse fetchRecommendationReasons(UUID requestId) {
        if (requestId == null) {
            throw new IllegalArgumentException("requestId is required");
        }
        return restClient.get()
                .uri("/api/v1/chat/recommendation-reasons/{requestId}", requestId.toString())
                .headers(this::applyInternalApiKey)
                .retrieve()
                .onStatus(HttpStatusCode::isError, (req, res) -> {
                    log.warn("AI recommendation reason status API failed. status={}", res.getStatusCode());
                    throw new IllegalStateException("AI 추천 이유 생성 상태를 확인할 수 없습니다.");
                })
                .body(RecommendationReasonStatusResponse.class);
    }


    @JsonIgnoreProperties(ignoreUnknown = true)
    public record LightFmArtifactSummaryClientResponse(
            Boolean available,
            @JsonProperty("artifact_version") String artifactVersion,
            @JsonProperty("artifact_dir") String artifactDir,
            @JsonProperty("user_count") Integer userCount,
            @JsonProperty("item_count") Integer itemCount,
            @JsonProperty("positive_event_count") Integer positiveEventCount,
            @JsonProperty("trained_at") String trainedAt,
            @JsonProperty("error_message") String errorMessage
    ) {}

    public record LightFmTrainingRequest(
            @JsonProperty("job_id") String jobId,
            @JsonProperty("dataset_manifest_path") String datasetManifestPath,
            @JsonProperty("event_paths") List<String> eventPaths,
            @JsonProperty("work_dir") String workDir,
            @JsonProperty("versions_dir") String versionsDir,
            @JsonProperty("current_dir") String currentDir,
            @JsonProperty("training_mode") String trainingMode,
            @JsonProperty("num_threads") Integer numThreads,
            Integer epochs,
            @JsonProperty("no_components") Integer noComponents,
            @JsonProperty("max_sampled") Integer maxSampled,
            @JsonProperty("learning_rate") BigDecimal learningRate,
            String loss,
            @JsonProperty("timeout_seconds") Integer timeoutSeconds,
            @JsonProperty("retention_count") Integer retentionCount,
            @JsonProperty("synthetic_max_ratio") BigDecimal syntheticMaxRatio,
            @JsonProperty("real_weight_multiplier") BigDecimal realWeightMultiplier,
            @JsonProperty("max_rows_per_source") Integer maxRowsPerSource
    ) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record LightFmTrainingResponse(
            String status,
            @JsonProperty("artifact_version") String artifactVersion,
            @JsonProperty("artifact_dir") String artifactDir,
            @JsonProperty("exit_code") Integer exitCode,
            @JsonProperty("error_message") String errorMessage,
            Map<String, Object> metrics
    ) {}

    public record AudienceLabelBatchRequest(
            List<AudienceLabelBook> books
    ) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record AudienceLabelBook(
            String isbn,
            String title,
            String author,
            String publisher,
            @JsonProperty("publish_date") String publishDate,
            Integer page,
            String description,
            @JsonProperty("simple_intro") String simpleIntro,
            @JsonProperty("book_intro") String bookIntro,
            List<String> categories,
            @JsonProperty("cate_depth1") List<String> cateDepth1,
            List<String> kcid,
            @JsonProperty("author_intro") String authorIntro,
            @JsonProperty("book_index") String bookIndex,
            @JsonProperty("pub_review") String pubReview
    ) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record AudienceLabelBatchResponse(
            List<AudienceLabelResult> items
    ) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record AudienceLabelResult(
            String isbn,
            String status,
            @JsonProperty("audience_group") String audienceGroup,
            @JsonProperty("audience_min_age") Integer audienceMinAge,
            @JsonProperty("audience_max_age") Integer audienceMaxAge,
            @JsonProperty("difficulty_level") String difficultyLevel,
            BigDecimal confidence,
            String reason,
            @JsonProperty("error_message") String errorMessage
    ) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record RecommendationReasonStatusResponse(
            @JsonProperty("request_id") String requestId,
            String status,
            String answer,
            List<BookCandidate> candidates,
            @JsonProperty("error_message") String errorMessage,
            @JsonProperty("created_at") String createdAt,
            @JsonProperty("updated_at") String updatedAt
    ) {}

    public record ReviewPreferenceAnalysisRequest(
            @JsonProperty("user_id") String userId,
            @JsonProperty("book_id") Long bookId,
            @JsonProperty("review_id") String reviewId,
            BigDecimal rating,
            @JsonProperty("review_content") String reviewContent,
            @JsonProperty("book_metadata") Map<String, Object> bookMetadata
    ) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record ReviewPreferenceAnalysisResponse(
            @JsonProperty("overall_sentiment") String overallSentiment,
            @JsonProperty("sentiment_score") Double sentimentScore,
            Double confidence,
            @JsonProperty("liked_aspects") List<String> likedAspects,
            @JsonProperty("disliked_aspects") List<String> dislikedAspects,
            @JsonProperty("preference_terms") List<String> preferenceTerms,
            @JsonProperty("avoid_terms") List<String> avoidTerms,
            @JsonProperty("preferred_mood") List<String> preferredMood,
            @JsonProperty("avoid_mood") List<String> avoidMood,
            String summary,
            @JsonProperty("analysis_status") String analysisStatus,
            @JsonProperty("analysis_error_message") String analysisErrorMessage
    ) {}

    public record UserPreferenceProfileVectorizeRequest(
            @JsonProperty("user_id") String userId,
            @JsonProperty("profile_version") Integer profileVersion,
            @JsonProperty("profile_text") String profileText,
            @JsonProperty("embedding_model") String embeddingModel
    ) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record UserPreferenceProfileVectorizeResponse(
            @JsonProperty("user_id") String userId,
            @JsonProperty("profile_version") Integer profileVersion,
            @JsonProperty("collection_name") String collectionName,
            @JsonProperty("point_id") String pointId,
            @JsonProperty("embedding_model") String embeddingModel,
            @JsonProperty("embedding_dimension") Integer embeddingDimension,
            @JsonProperty("build_status") String buildStatus,
            @JsonProperty("error_message") String errorMessage
    ) {}

    public record AiRecommendationRequest(
            @JsonProperty("request_id") String requestId,
            @JsonProperty("user_id") String userId,
            String query,
            Boolean personalized,
            Boolean guest,
            @JsonProperty("guest_session_id") String guestSessionId,
            @JsonProperty("guest_room_id") String guestRoomId,
            List<ChatHistoryItem> history,
            @JsonProperty("guest_profile") Map<String, Object> guestProfile,
            @JsonProperty("user_profile") Map<String, Object> userProfile,
            @JsonProperty("audience_label_map") Map<String, Map<String, Object>> audienceLabelMap,
            @JsonProperty("embedding_model") String embeddingModel,
            @JsonProperty("ranking_model") String rankingModel,
            @JsonProperty("recommendation_strategy") String recommendationStrategy,
            @JsonProperty("personalization_model") String personalizationModel,
            @JsonProperty("reranker_provider") String rerankerProvider,
            @JsonProperty("bm25_enabled") Boolean bm25Enabled
    ) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record ChatHistoryItem(
            String role,
            String content,
            @JsonProperty("created_at") String createdAt,
            List<BookCandidate> candidates,
            // 수정 포인트: 이전 assistant 응답의 최소 구조화 metadata만 ai-server history로 되돌려
            // 멀티턴 소비 상황/reading_mode 승계에 사용합니다. user_profile 원문은 포함하지 않습니다.
            Map<String, Object> metadata
    ) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record AiRecommendationResponse(
            @JsonProperty("request_id") String requestId,
            String query,
            String answer,
            String cover,
            Boolean guest,
            Boolean personalized,
            @JsonProperty("profile_applied") Boolean profileApplied,
            String intent,
            @JsonProperty("intent_source") String intentSource,
            @JsonProperty("requires_history") Boolean requiresHistory,
            @JsonProperty("embedding_model") String embeddingModel,
            @JsonProperty("ranking_model") String rankingModel,
            @JsonProperty("recommendation_strategy") String recommendationStrategy,
            @JsonProperty("personalization_model") String personalizationModel,
            @JsonProperty("personalization_provider") String personalizationProvider,
            @JsonProperty("sequence_provider") String sequenceProvider,
            @JsonProperty("reranker_provider") String rerankerProvider,
            @JsonProperty("bm25_enabled") Boolean bm25Enabled,
            @JsonProperty("retrieval_strategy") String retrievalStrategy,
            @JsonProperty("retrieval_fallback") Boolean retrievalFallback,
            @JsonProperty("retrieval_fallback_reason") String retrievalFallbackReason,
            @JsonProperty("ranking_model_applied") Boolean rankingModelApplied,
            @JsonProperty("ranking_model_fallback") Boolean rankingModelFallback,
            @JsonProperty("ranking_model_fallback_reason") String rankingModelFallbackReason,
            @JsonProperty("ranking_model_applied_model") String rankingModelAppliedModel,
            @JsonProperty("ranking_artifact_version") String rankingArtifactVersion,
            @JsonProperty("recommendation_reason_status") String recommendationReasonStatus,
            @JsonProperty("recommendation_reason_error_message") String recommendationReasonErrorMessage,
            @JsonProperty("final_recommendation_limit") Integer finalRecommendationLimit,
            @JsonProperty("detected_consumption_context") String detectedConsumptionContext,
            @JsonProperty("detected_reading_mode") String detectedReadingMode,
            @JsonProperty("consumption_context_type") String consumptionContextType,
            @JsonProperty("visual_attention_limited") Boolean visualAttentionLimited,
            @JsonProperty("hands_free_preferred") Boolean handsFreePreferred,
            @JsonProperty("requires_visual_reference") Boolean requiresVisualReference,
            @JsonProperty("topic_query") String topicQuery,
            @JsonProperty("retrieval_query") String retrievalQuery,
            @JsonProperty("reranker_query") String rerankerQuery,
            @JsonProperty("context_policy_applied") Boolean contextPolicyApplied,
            @JsonProperty("multi_turn_context_inherited") Boolean multiTurnContextInherited,
            @JsonProperty("multi_turn_context_source") String multiTurnContextSource,
            @JsonProperty("multi_turn_context_reason") String multiTurnContextReason,
            @JsonProperty("inherited_reading_mode") String inheritedReadingMode,
            @JsonProperty("inherited_consumption_context") String inheritedConsumptionContext,
            @JsonProperty("inherited_requested_audience_group") String inheritedRequestedAudienceGroup,
            Map<String, Object> pipeline,
            List<BookCandidate> candidates
    ) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record BookCandidate(
            String isbn,
            String title,
            String author,
            String publisher,
            @JsonProperty("publish_date") String publishDate,
            Integer page,
            Integer price,
            @JsonProperty("simple_intro") String simpleIntro,
            @JsonProperty("book_intro") String bookIntro,
            String description,
            List<String> categories,
            @JsonProperty("cate_depth1") List<String> cateDepth1,
            List<String> kcid,
            @JsonProperty("book_index") String bookIndex,
            @JsonProperty("pub_review") String pubReview,
            @JsonProperty("ori_cover_s") String oriCoverS,
            @JsonProperty("cover_url") String coverUrl,
            String cover,
            @JsonProperty("author_intro") String authorIntro,
            Double score,
            Integer rank,
            @JsonProperty("recommended_at") String recommendedAt,
            Double candidateRelevanceScore,
            Double qdrantScore,
            Double ruleScore,
            Double profileVectorScore,
            Double lightfmScore,
            Double sasrecScore,
            Double rerankerScore,
            Double preScore,
            Double finalScore,
            @JsonProperty("rerank_score") Double rerankScore,
            @JsonProperty("rerank_reason") String rerankReason,
            @JsonProperty("recommendation_reason") String recommendationReason,
            @JsonProperty("recommendation_reason_source") String recommendationReasonSource,
            @JsonProperty("recommendation_reason_status") String recommendationReasonStatus,
            @JsonProperty("audience_profile") Map<String, Object> audienceProfile,
            @JsonProperty("score_detail") Map<String, Object> scoreDetail
    ) {}
}
