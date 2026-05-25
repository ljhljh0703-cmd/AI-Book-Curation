package com.taeo.bookcuration.chat.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.taeo.bookcuration.chat.client.AiRecommendationClient;
import com.taeo.bookcuration.chat.client.AiRecommendationClient.AiRecommendationResponse;
import com.taeo.bookcuration.chat.client.AiRecommendationClient.ChatHistoryItem;
import com.taeo.bookcuration.chat.dto.ChatDtos.*;
import com.taeo.bookcuration.recommendation.audience.BookAudienceLabelQueryService;
import com.taeo.bookcuration.recommendation.event.service.RecommendationEventLoggingService;
import com.taeo.bookcuration.recommendation.service.RecommendationModelSettingService;
import com.taeo.bookcuration.recommendation.service.RecommendationModelSettingService.RecommendationModelSetting;
import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Duration;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@Service
@RequiredArgsConstructor
public class ChatService {
    private static final int MAX_ACTIVE_CHAT_COUNT = 8;
    private static final int MAX_USER_MESSAGE_COUNT = 10;
    private static final int AI_HISTORY_MESSAGE_LIMIT = 6;
    private static final int AI_HISTORY_CONTENT_LIMIT = 1500;
    private static final List<String> AI_HISTORY_METADATA_KEYS = List.of(
            "intent",
            "intentSource",
            "requiresHistory",
            "detectedConsumptionContext",
            "detectedReadingMode",
            "consumptionContextType",
            "visualAttentionLimited",
            "handsFreePreferred",
            "requiresVisualReference",
            "topicQuery",
            "retrievalQuery",
            "rerankerQuery",
            "contextPolicyApplied",
            "multiTurnContextInherited",
            "multiTurnContextSource",
            "multiTurnContextReason",
            "inheritedReadingMode",
            "inheritedConsumptionContext",
            "inheritedRequestedAudienceGroup",
            "pipeline"
    );
    private final JdbcTemplate jdbcTemplate;
    private final AiRecommendationClient aiRecommendationClient;
    private final UserRecommendationProfileService userRecommendationProfileService;
    private final RecommendationModelSettingService recommendationModelSettingService;
    private final RecommendationEventLoggingService recommendationEventLoggingService;
    private final BookAudienceLabelQueryService bookAudienceLabelQueryService;
    private final ObjectMapper objectMapper;

    @Transactional(readOnly = true)
    public ChatSessionListResponse listSessions(UUID userId) {
        List<ChatSessionResponse> sessions = jdbcTemplate.query("""
                SELECT id, title, status, created_at, updated_at
                FROM book.chat_sessions
                WHERE user_id = ? AND status = 'ACTIVE'
                ORDER BY updated_at DESC
                LIMIT 8
                """, (rs, rowNum) -> toSession(rs), userId);
        return new ChatSessionListResponse(MAX_ACTIVE_CHAT_COUNT, MAX_USER_MESSAGE_COUNT, sessions);
    }

    @Transactional
    public ChatSessionResponse createSession(UUID userId, String title) {
        long activeCount = jdbcTemplate.queryForObject("""
                SELECT COUNT(*) FROM book.chat_sessions
                WHERE user_id = ? AND status = 'ACTIVE'
                """, Long.class, userId);
        if (activeCount >= MAX_ACTIVE_CHAT_COUNT) {
            throw new IllegalArgumentException("채팅방은 최대 " + MAX_ACTIVE_CHAT_COUNT + "개까지 생성할 수 있습니다. 기존 채팅방을 삭제한 뒤 다시 시도해주세요.");
        }
        return jdbcTemplate.queryForObject("""
                INSERT INTO book.chat_sessions (user_id, title, status)
                VALUES (?, ?, 'ACTIVE')
                RETURNING id, title, status, created_at, updated_at
                """, (rs, rowNum) -> toSession(rs), userId, normalizeTitle(title));
    }

    @Transactional(readOnly = true)
    public List<ChatMessageResponse> listMessages(UUID userId, UUID sessionId) {
        ensureActiveSessionOwner(userId, sessionId);
        return jdbcTemplate.query("""
                SELECT id, session_id, role, content, metadata::text AS metadata, created_at
                FROM book.chat_messages
                WHERE session_id = ?
                ORDER BY created_at ASC, id ASC
                """, (rs, rowNum) -> toMessage(rs), sessionId);
    }

    @Transactional
    public SendChatMessageResponse sendMessageToNewSession(UUID userId, String content) {
        // 수정 포인트: 새 채팅 버튼 클릭만으로는 DB 채팅방을 만들지 않고, 첫 메시지 전송 시점에만 채팅방을 생성합니다.
        ChatSessionResponse createdSession = createSession(userId, content);
        return sendMessage(userId, UUID.fromString(createdSession.id()), content);
    }

    @Transactional
    public SendChatMessageResponse sendMessage(UUID userId, UUID sessionId, String content) {
        ensureActiveSessionOwner(userId, sessionId);
        long userMessageCount = countUserMessages(sessionId);
        if (userMessageCount >= MAX_USER_MESSAGE_COUNT) {
            throw new IllegalArgumentException("이 채팅방에서는 질문을 최대 " + MAX_USER_MESSAGE_COUNT + "개까지만 보낼 수 있습니다. 새 채팅으로 이어서 질문해 주세요.");
        }

        ChatMessageResponse userMessage = insertMessage(sessionId, "USER", content, null);

        // 수정 포인트: 첫 질문을 채팅방 제목으로 자동 반영한다.
        jdbcTemplate.update("""
                UPDATE book.chat_sessions
                SET title = CASE WHEN title IS NULL OR title = '새 채팅' THEN ? ELSE title END,
                    updated_at = NOW()
                WHERE id = ? AND user_id = ? AND status = 'ACTIVE'
                """, normalizeTitle(content), sessionId, userId);

        // 수정 포인트: ai-server가 user_id만으로 백엔드 DB의 채팅 내역을 직접 알 수 없으므로,
        // 현재 채팅방의 최근 이전 메시지를 backend가 history로 구성해 함께 전달합니다.
        List<ChatHistoryItem> history = findRecentAiHistory(sessionId, userMessage.id());

        Instant startedAt = Instant.now();
        // 수정 포인트: 로그인 추천도 온보딩/서재/리뷰 기반 사용자 프로필을 ai-server에 전달해 리랭킹할 수 있게 합니다.
        Map<String, Object> userProfile = userRecommendationProfileService.buildProfile(userId);
        boolean personalized = Boolean.TRUE.equals(userProfile.get("profileAvailable"));
        // 수정 포인트: 추천 요청 단위 requestId를 먼저 만들고, 검색 질의는 낮은 weight의 행동 로그로 별도 누적합니다.
        UUID requestId = UUID.randomUUID();
        // 수정 포인트: 관리자 페이지의 추천 모델 설정값을 로그인 추천 요청마다 읽어 ai-server로 전달합니다.
        RecommendationModelSetting modelSetting = recommendationModelSettingService.getSetting();
        recommendationEventLoggingService.startRecommendationRequestSafely(requestId, userId, content, modelSetting);
        recommendationEventLoggingService.logSearchQuerySafely(userId, requestId, content);
        Map<String, Map<String, Object>> audienceLabelMap = bookAudienceLabelQueryService.findReadyAudienceLabelMap();
        AiRecommendationResponse aiResponse = aiRecommendationClient.recommend(requestId, userId, content, history, userProfile, modelSetting, audienceLabelMap);
        long latencyMs = Duration.between(startedAt, Instant.now()).toMillis();
        recommendationEventLoggingService.logRecommendationResponseSafely(requestId, userId, content, aiResponse);

        // 수정 포인트: FastAPI 응답 answer는 채팅 본문에 저장하고, 후보 도서/표지/지연시간은 metadata JSONB에 함께 저장합니다.
        ChatMessageResponse assistantMessage = insertMessage(
                sessionId,
                "ASSISTANT",
                normalizeAnswer(aiResponse),
                buildAssistantMetadata(aiResponse, latencyMs, personalized)
        );

        return new SendChatMessageResponse(findSession(userId, sessionId), userMessage, assistantMessage, MAX_USER_MESSAGE_COUNT);
    }


    @Transactional
    public RecommendationReasonPollResponse pollRecommendationReasons(UUID userId, UUID requestId) {
        AiRecommendationClient.RecommendationReasonStatusResponse reasonResponse = aiRecommendationClient.fetchRecommendationReasons(requestId);
        String status = reasonResponse == null || reasonResponse.status() == null ? "MISSING" : reasonResponse.status().trim().toUpperCase();
        if ("PENDING".equals(status) || "MISSING".equals(status)) {
            return new RecommendationReasonPollResponse(status, null, reasonResponse == null ? null : reasonResponse.errorMessage());
        }

        List<Map<String, Object>> candidates = reasonResponse == null || reasonResponse.candidates() == null
                ? List.of()
                : objectMapper.convertValue(reasonResponse.candidates(), new TypeReference<List<Map<String, Object>>>() {});
        String answer = reasonResponse == null ? null : reasonResponse.answer();
        boolean hasReasonPayload = (answer != null && !answer.isBlank()) || !candidates.isEmpty();
        if (("PARTIAL".equals(status) || "COMPLETED".equals(status)) && !hasReasonPayload) {
            return new RecommendationReasonPollResponse("FAILED", null, "추천 이유 응답이 비어 있습니다.");
        }

        // 수정 포인트: PARTIAL 상태도 DB 메시지 metadata에 반영해 카드별 추천 이유가 완성되는 즉시 화면에 표시되게 합니다.
        if ("PARTIAL".equals(status) || "COMPLETED".equals(status)) {
            ChatMessageResponse existing = findAssistantMessageByRequestId(userId, requestId);
            Map<String, Object> metadata = new LinkedHashMap<>(existing.metadata() == null ? Map.of() : existing.metadata());
            metadata.put("answer", answer == null || answer.isBlank() ? existing.content() : answer.trim());
            metadata.put("recommendationReasonStatus", status);
            metadata.put("recommendationReasonErrorMessage", null);
            metadata.put("candidates", candidates);

            ChatMessageResponse updated = jdbcTemplate.queryForObject("""
                    UPDATE book.chat_messages
                    SET content = ?, metadata = ?::jsonb
                    WHERE id = ?
                    RETURNING id, session_id, role, content, metadata::text AS metadata, created_at
                    """, (rs, rowNum) -> toMessage(rs), answer == null || answer.isBlank() ? existing.content() : answer.trim(), toJson(metadata), existing.id());
            return new RecommendationReasonPollResponse(status, updated, null);
        }

        return new RecommendationReasonPollResponse(status, null, reasonResponse == null ? null : reasonResponse.errorMessage());
    }

    private ChatMessageResponse findAssistantMessageByRequestId(UUID userId, UUID requestId) {
        List<ChatMessageResponse> messages = jdbcTemplate.query("""
                SELECT cm.id, cm.session_id, cm.role, cm.content, cm.metadata::text AS metadata, cm.created_at
                FROM book.chat_messages cm
                JOIN book.chat_sessions cs ON cs.id = cm.session_id
                WHERE cs.user_id = ?
                  AND cs.status = 'ACTIVE'
                  AND cm.role = 'ASSISTANT'
                  AND cm.metadata ->> 'requestId' = ?
                ORDER BY cm.created_at DESC
                LIMIT 1
                """, (rs, rowNum) -> toMessage(rs), userId, requestId.toString());
        if (messages.isEmpty()) {
            throw new IllegalArgumentException("추천 이유를 갱신할 채팅 메시지를 찾을 수 없습니다.");
        }
        return messages.get(0);
    }

    @Transactional
    public void deleteSession(UUID userId, UUID sessionId) {
        int updated = jdbcTemplate.update("""
                UPDATE book.chat_sessions
                SET status = 'DELETED', ended_at = NOW(), updated_at = NOW()
                WHERE id = ? AND user_id = ? AND status = 'ACTIVE'
                """, sessionId, userId);
        if (updated == 0) throw new IllegalArgumentException("채팅방을 찾을 수 없습니다.");
    }

    private void ensureActiveSessionOwner(UUID userId, UUID sessionId) {
        Boolean exists = jdbcTemplate.queryForObject("""
                SELECT EXISTS (SELECT 1 FROM book.chat_sessions WHERE id = ? AND user_id = ? AND status = 'ACTIVE')
                """, Boolean.class, sessionId, userId);
        if (!Boolean.TRUE.equals(exists)) throw new IllegalArgumentException("채팅방을 찾을 수 없습니다.");
    }

    private long countUserMessages(UUID sessionId) {
        Long count = jdbcTemplate.queryForObject("""
                SELECT COUNT(*)
                FROM book.chat_messages
                WHERE session_id = ? AND role = 'USER'
                """, Long.class, sessionId);
        return count == null ? 0 : count;
    }


    private List<ChatHistoryItem> findRecentAiHistory(UUID sessionId, Long currentUserMessageId) {
        return jdbcTemplate.query("""
                SELECT role, content, metadata, created_at
                FROM (
                    SELECT id, role, content, metadata::text AS metadata, created_at
                    FROM book.chat_messages
                    WHERE session_id = ?
                      AND id <> ?
                      AND role IN ('USER', 'ASSISTANT')
                    ORDER BY created_at DESC, id DESC
                    LIMIT ?
                ) recent_messages
                ORDER BY created_at ASC, id ASC
                """, (rs, rowNum) -> new ChatHistoryItem(
                toAiHistoryRole(rs.getString("role")),
                truncateForAiHistory(rs.getString("content")),
                toIsoString(rs.getObject("created_at", OffsetDateTime.class)),
                extractHistoryCandidates(rs.getString("metadata")),
                extractHistoryMetadata(rs.getString("metadata"))
        ), sessionId, currentUserMessageId, AI_HISTORY_MESSAGE_LIMIT);
    }

    private List<AiRecommendationClient.BookCandidate> extractHistoryCandidates(String metadataJson) {
        if (metadataJson == null || metadataJson.isBlank()) {
            return List.of();
        }
        try {
            Map<String, Object> metadata = objectMapper.readValue(metadataJson, new TypeReference<Map<String, Object>>() {});
            Object candidates = metadata.get("candidates");
            if (candidates == null) {
                return List.of();
            }
            List<AiRecommendationClient.BookCandidate> parsed = objectMapper.convertValue(
                    candidates,
                    new TypeReference<List<AiRecommendationClient.BookCandidate>>() {}
            );
            return parsed == null ? List.of() : parsed;
        } catch (IllegalArgumentException | JsonProcessingException ex) {
            return List.of();
        }
    }

    private Map<String, Object> extractHistoryMetadata(String metadataJson) {
        if (metadataJson == null || metadataJson.isBlank()) {
            return Map.of();
        }
        try {
            Map<String, Object> metadata = objectMapper.readValue(metadataJson, new TypeReference<Map<String, Object>>() {});
            return sanitizeHistoryMetadata(metadata);
        } catch (IllegalArgumentException | JsonProcessingException ex) {
            return Map.of();
        }
    }

    private Map<String, Object> sanitizeHistoryMetadata(Map<String, Object> metadata) {
        if (metadata == null || metadata.isEmpty()) {
            return Map.of();
        }
        Map<String, Object> result = new LinkedHashMap<>();
        for (String key : AI_HISTORY_METADATA_KEYS) {
            Object value = metadata.get(key);
            if (value != null) {
                result.put(key, value);
            }
        }
        // 수정 포인트: 멀티턴 승계에 필요한 intent/query/debug subset만 history로 재전달합니다.
        // candidates는 별도 필드로 전달하고, raw user_profile 원문은 metadata에 포함하지 않습니다.
        return result;
    }

    private String toIsoString(OffsetDateTime value) {
        return value == null ? null : value.toString();
    }

    private String toAiHistoryRole(String role) {
        if ("ASSISTANT".equalsIgnoreCase(role)) {
            return "assistant";
        }
        return "user";
    }

    private String truncateForAiHistory(String content) {
        if (content == null || content.isBlank()) {
            return "";
        }
        String normalized = content.trim();
        if (normalized.length() <= AI_HISTORY_CONTENT_LIMIT) {
            return normalized;
        }
        return normalized.substring(0, AI_HISTORY_CONTENT_LIMIT) + "...";
    }

    private ChatSessionResponse findSession(UUID userId, UUID sessionId) {
        return jdbcTemplate.queryForObject("""
                SELECT id, title, status, created_at, updated_at
                FROM book.chat_sessions
                WHERE id = ? AND user_id = ? AND status = 'ACTIVE'
                """, (rs, rowNum) -> toSession(rs), sessionId, userId);
    }

    private ChatMessageResponse insertMessage(UUID sessionId, String role, String content, Map<String, Object> metadata) {
        return jdbcTemplate.queryForObject("""
                INSERT INTO book.chat_messages (session_id, role, content, metadata)
                VALUES (?, ?, ?, CAST(? AS jsonb))
                RETURNING id, session_id, role, content, metadata::text AS metadata, created_at
                """, (rs, rowNum) -> toMessage(rs), sessionId, role, content.trim(), toJson(metadata));
    }

    private ChatSessionResponse toSession(ResultSet rs) throws SQLException {
        return new ChatSessionResponse(rs.getObject("id", UUID.class).toString(), rs.getString("title"), rs.getString("status"), rs.getObject("created_at", OffsetDateTime.class), rs.getObject("updated_at", OffsetDateTime.class));
    }

    private ChatMessageResponse toMessage(ResultSet rs) throws SQLException {
        return new ChatMessageResponse(
                rs.getLong("id"),
                rs.getObject("session_id", UUID.class).toString(),
                rs.getString("role"),
                rs.getString("content"),
                readMetadata(rs.getString("metadata")),
                rs.getObject("created_at", OffsetDateTime.class)
        );
    }

    private String normalizeTitle(String value) {
        if (value == null || value.isBlank()) return "새 채팅";
        String compact = value.trim().replaceAll("\\s+", " ");
        return compact.length() > 40 ? compact.substring(0, 40) + "..." : compact;
    }

    private String normalizeAnswer(AiRecommendationResponse response) {
        if (response == null) {
            return "추천 결과를 생성하지 못했습니다. 질문을 조금 더 구체적으로 입력해 주세요.";
        }
        if (response.answer() != null && !response.answer().isBlank()) {
            return response.answer().trim();
        }
        int candidateCount = response.candidates() == null ? 0 : response.candidates().size();
        if (candidateCount > 0) {
            // 수정 포인트: 후보 카드는 정상 생성됐는데 추천 이유만 비동기 생성 중인 경우,
            // 실패 문구를 저장하지 않고 카드 선표시 상태에 맞는 안내 문구를 저장합니다.
            return "추천 도서 " + candidateCount + "권을 먼저 찾았습니다. 추천 이유는 생성 중입니다.";
        }
        return "추천 결과를 생성하지 못했습니다. 질문을 조금 더 구체적으로 입력해 주세요.";
    }

    private Map<String, Object> buildAssistantMetadata(AiRecommendationResponse response, long latencyMs, boolean personalized) {
        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("source", "AI_SERVER");
        // 수정 포인트: 실제 user_profile 원문은 chat_messages.metadata에 저장하지 않고, 개인화 응답 여부만 남겨 과도한 개인정보 중복 저장을 피합니다.
        metadata.put("guest", false);
        metadata.put("personalized", personalized);
        metadata.put("latencyMs", latencyMs);


        if (response == null) {
            metadata.put("candidates", List.of());
            return metadata;
        }

        // 수정 포인트: FastAPI 원문 응답을 보존해 프론트 표시와 향후 추천 로그/개인화 학습에 재사용할 수 있게 합니다.
        metadata.put("query", response.query());
        metadata.put("answer", normalizeAnswer(response));
        metadata.put("cover", response.cover());
        metadata.put("requestId", response.requestId());
        metadata.put("embeddingModel", response.embeddingModel());
        metadata.put("rankingModel", response.rankingModel());
        metadata.put("personalizationProvider", response.personalizationProvider());
        metadata.put("sequenceProvider", response.sequenceProvider());
        metadata.put("rerankerProvider", response.rerankerProvider());
        metadata.put("rankingModelApplied", Boolean.TRUE.equals(response.rankingModelApplied()));
        metadata.put("rankingModelFallback", Boolean.TRUE.equals(response.rankingModelFallback()));
        metadata.put("rankingModelFallbackReason", response.rankingModelFallbackReason());
        metadata.put("rankingModelAppliedModel", response.rankingModelAppliedModel());
        metadata.put("rankingArtifactVersion", response.rankingArtifactVersion());
        metadata.put("recommendationReasonStatus", response.recommendationReasonStatus());
        metadata.put("recommendationReasonErrorMessage", response.recommendationReasonErrorMessage());
        metadata.put("finalRecommendationLimit", response.finalRecommendationLimit());
        // 수정 포인트: 다음 턴의 ai-server history에 필요한 구조화 query/context metadata만 저장합니다.
        // 개인정보성 user_profile 원문은 저장하지 않고, 멀티턴 승계에 필요한 최소 값만 보존합니다.
        metadata.put("intent", response.intent());
        metadata.put("intentSource", response.intentSource());
        metadata.put("requiresHistory", Boolean.TRUE.equals(response.requiresHistory()));
        metadata.put("detectedConsumptionContext", response.detectedConsumptionContext());
        metadata.put("detectedReadingMode", response.detectedReadingMode());
        metadata.put("consumptionContextType", response.consumptionContextType());
        metadata.put("visualAttentionLimited", response.visualAttentionLimited());
        metadata.put("handsFreePreferred", response.handsFreePreferred());
        metadata.put("requiresVisualReference", response.requiresVisualReference());
        metadata.put("topicQuery", response.topicQuery());
        metadata.put("retrievalQuery", response.retrievalQuery());
        metadata.put("rerankerQuery", response.rerankerQuery());
        metadata.put("contextPolicyApplied", Boolean.TRUE.equals(response.contextPolicyApplied()));
        metadata.put("multiTurnContextInherited", Boolean.TRUE.equals(response.multiTurnContextInherited()));
        metadata.put("multiTurnContextSource", response.multiTurnContextSource());
        metadata.put("multiTurnContextReason", response.multiTurnContextReason());
        metadata.put("inheritedReadingMode", response.inheritedReadingMode());
        metadata.put("inheritedConsumptionContext", response.inheritedConsumptionContext());
        metadata.put("inheritedRequestedAudienceGroup", response.inheritedRequestedAudienceGroup());
        metadata.put("pipeline", response.pipeline() == null ? Map.of() : response.pipeline());
        metadata.put("candidates", response.candidates() == null ? List.of() : objectMapper.convertValue(response.candidates(), new TypeReference<List<Map<String, Object>>>() {}));
        return metadata;
    }

    private String toJson(Map<String, Object> metadata) {
        if (metadata == null) {
            return null;
        }
        try {
            return objectMapper.writeValueAsString(metadata);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("채팅 메타데이터를 JSON으로 변환하지 못했습니다.", e);
        }
    }

    private Map<String, Object> readMetadata(String metadataJson) {
        if (metadataJson == null || metadataJson.isBlank()) {
            return Map.of();
        }
        try {
            return objectMapper.readValue(metadataJson, new TypeReference<Map<String, Object>>() {});
        } catch (JsonProcessingException e) {
            // 수정 포인트: 과거 데이터에 잘못된 metadata가 있어도 채팅 목록/메시지 조회 자체는 깨지지 않도록 비워서 내려줍니다.
            return Map.of();
        }
    }
}
