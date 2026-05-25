package com.taeo.bookcuration.chat.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.taeo.bookcuration.chat.client.AiRecommendationClient;
import com.taeo.bookcuration.chat.client.AiRecommendationClient.AiRecommendationResponse;
import com.taeo.bookcuration.chat.client.AiRecommendationClient.ChatHistoryItem;
import com.taeo.bookcuration.chat.dto.GuestChatDtos.GuestAssistantMessage;
import com.taeo.bookcuration.chat.dto.GuestChatDtos.GuestChatHistoryItem;
import com.taeo.bookcuration.chat.dto.GuestChatDtos.GuestChatMessagesResponse;
import com.taeo.bookcuration.chat.dto.GuestChatDtos.GuestProfileSnapshot;
import com.taeo.bookcuration.chat.dto.GuestChatDtos.GuestRecommendRequest;
import com.taeo.bookcuration.chat.dto.GuestChatDtos.GuestRecommendResponse;
import com.taeo.bookcuration.cache.GuestChatStateService;
import com.taeo.bookcuration.cache.GuestRecommendationCacheService;
import com.taeo.bookcuration.cache.RedisKeyService;
import com.taeo.bookcuration.cache.RedisLockService;
import com.taeo.bookcuration.config.RedisProperties;
import com.taeo.bookcuration.recommendation.service.RecommendationModelSettingService;
import com.taeo.bookcuration.recommendation.service.RecommendationModelSettingService.RecommendationModelSetting;
import lombok.RequiredArgsConstructor;
import org.springframework.context.MessageSource;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import java.time.Duration;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;

@Service
@RequiredArgsConstructor
public class PublicChatService {
    private static final int MAX_GUEST_CHAT_COUNT = 3;
    private static final int MAX_GUEST_USER_MESSAGE_COUNT = 15;
    private static final int AI_GUEST_HISTORY_MESSAGE_LIMIT = 6;
    private static final int GUEST_RESTORE_MESSAGE_LIMIT = 40;
    private static final int AI_GUEST_HISTORY_CONTENT_LIMIT = 1200;
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
    private static final String LOGIN_PROMPT_MESSAGE_CODE = "guest.chat.loginPrompt";
    private static final String EMPTY_ANSWER_MESSAGE_CODE = "guest.chat.emptyAnswer";
    private static final String PENDING_ANSWER_MESSAGE_CODE = "guest.chat.pendingAnswer";

    private final AiRecommendationClient aiRecommendationClient;
    private final RecommendationModelSettingService recommendationModelSettingService;
    private final ObjectMapper objectMapper;
    private final MessageSource messageSource;
    private final RedisProperties redisProperties;
    private final RedisKeyService redisKeyService;
    private final RedisLockService redisLockService;
    private final GuestChatStateService guestChatStateService;
    private final GuestRecommendationCacheService guestRecommendationCacheService;

    public GuestRecommendResponse recommend(GuestRecommendRequest request) {
        Instant startedAt = Instant.now();
        String queryHash = redisKeyService.hash(request.content());
        String duplicateLockKey = redisKeyService.key(
                "guest",
                "duplicate-message-lock",
                request.guestSessionId(),
                request.guestRoomId(),
                queryHash.substring(0, 32)
        );
        RedisLockService.LockToken duplicateLock = redisLockService.tryLock(duplicateLockKey, redisProperties.guestDuplicateLockTtl());
        if (duplicateLock.available() && !duplicateLock.acquired()) {
            // 수정 포인트: 같은 guestId/room/message의 중복 전송은 Redis TTL lock으로 ai-server 중복 호출 전에 차단합니다.
            throw new ResponseStatusException(HttpStatus.CONFLICT, "같은 메시지가 이미 처리 중입니다. 잠시 후 다시 시도해 주세요.");
        }

        List<ChatHistoryItem> history = normalizeHistory(request.history());
        if (history.isEmpty()) {
            // 수정 포인트: 프론트 localStorage가 비어 있어도 Valkey TTL 저장소에 남은 비로그인 대화는 새로고침 후 재사용합니다.
            history = guestChatStateService.loadHistory(request.guestSessionId(), request.guestRoomId(), AI_GUEST_HISTORY_MESSAGE_LIMIT);
        }
        Map<String, Object> guestProfile = normalizeGuestProfile(request.guestProfile());

        String recommendationCacheKey = guestRecommendationCacheService.key(
                request.guestSessionId(),
                request.guestRoomId(),
                request.content(),
                history,
                guestProfile
        );
        GuestRecommendResponse cachedResponse = guestRecommendationCacheService.get(recommendationCacheKey)
                .map(response -> resolveCachedGuestRecommendation(response, recommendationCacheKey))
                .orElse(null);
        if (cachedResponse != null) {
            Map<String, Object> cachedMetadata = cachedResponse.assistantMessage() == null
                    ? Map.of()
                    : cachedResponse.assistantMessage().metadata();
            String cachedAnswer = cachedResponse.assistantMessage() == null ? "" : cachedResponse.assistantMessage().content();
            guestChatStateService.appendUserAndAssistantMessages(
                    request.guestSessionId(),
                    request.guestRoomId(),
                    request.content(),
                    cachedAnswer,
                    cachedMetadata
            );
            return cachedResponse;
        }

        UUID requestId = UUID.randomUUID();
        RecommendationModelSetting modelSetting = recommendationModelSettingService.getSetting();
        AiRecommendationResponse aiResponse = aiRecommendationClient.recommendGuest(
                requestId,
                request.guestSessionId(),
                request.guestRoomId(),
                request.content(),
                history,
                guestProfile,
                modelSetting
        );
        long latencyMs = Duration.between(startedAt, Instant.now()).toMillis();

        String answer = normalizeGuestAnswer(aiResponse);
        String loginPrompt = loginPrompt();
        Map<String, Object> metadata = buildAssistantMetadata(aiResponse, latencyMs, guestProfile, loginPrompt);
        guestChatStateService.appendUserAndAssistantMessages(
                request.guestSessionId(),
                request.guestRoomId(),
                request.content(),
                answer,
                metadata
        );

        GuestRecommendResponse response = new GuestRecommendResponse(
                true,
                false,
                MAX_GUEST_CHAT_COUNT,
                MAX_GUEST_USER_MESSAGE_COUNT,
                loginPrompt,
                new GuestAssistantMessage("ASSISTANT", answer, metadata, OffsetDateTime.now())
        );
        // 수정 포인트: guest 추천 cache를 후보 snapshot과 reason 상태 검증으로 분리합니다.
        // PENDING snapshot도 저장하되, cache hit 시 기존 requestId의 reason job이 terminal 상태일 때만 재사용합니다.
        // 아직 PENDING이면 stale requestId를 사용자에게 돌려주지 않고 ai-server를 다시 호출합니다.
        guestRecommendationCacheService.put(recommendationCacheKey, response);
        return response;
    }


    private GuestRecommendResponse resolveCachedGuestRecommendation(GuestRecommendResponse cachedResponse, String cacheKey) {
        if (cachedResponse == null || cachedResponse.assistantMessage() == null) {
            return null;
        }
        Map<String, Object> metadata = cachedResponse.assistantMessage().metadata() == null
                ? Map.of()
                : cachedResponse.assistantMessage().metadata();
        if (!isReasonPending(metadata)) {
            return cachedResponse;
        }
        String requestId = String.valueOf(metadata.getOrDefault("requestId", "")).trim();
        if (requestId.isBlank()) {
            return null;
        }
        try {
            AiRecommendationClient.RecommendationReasonStatusResponse reasonStatus = aiRecommendationClient.fetchRecommendationReasons(UUID.fromString(requestId));
            if (reasonStatus == null || !isTerminalReasonStatus(reasonStatus.status())) {
                return null;
            }
            GuestRecommendResponse resolvedResponse = mergeReasonStatus(cachedResponse, reasonStatus);
            guestRecommendationCacheService.put(cacheKey, resolvedResponse);
            return resolvedResponse;
        } catch (Exception e) {
            return null;
        }
    }

    private boolean isTerminalReasonStatus(String status) {
        return "COMPLETED".equalsIgnoreCase(status) || "FAILED".equalsIgnoreCase(status) || "SKIPPED".equalsIgnoreCase(status);
    }

    private GuestRecommendResponse mergeReasonStatus(
            GuestRecommendResponse cachedResponse,
            AiRecommendationClient.RecommendationReasonStatusResponse reasonStatus
    ) {
        GuestAssistantMessage cachedMessage = cachedResponse.assistantMessage();
        Map<String, Object> nextMetadata = new LinkedHashMap<>(cachedMessage.metadata() == null ? Map.of() : cachedMessage.metadata());
        nextMetadata.put("recommendationReasonStatus", reasonStatus.status());
        nextMetadata.put("recommendationReasonErrorMessage", reasonStatus.errorMessage());
        if (reasonStatus.candidates() != null && !reasonStatus.candidates().isEmpty()) {
            nextMetadata.put("candidates", objectMapper.convertValue(reasonStatus.candidates(), new TypeReference<List<Map<String, Object>>>() {}));
        }
        String answer = reasonStatus.answer() == null || reasonStatus.answer().isBlank()
                ? cachedMessage.content()
                : reasonStatus.answer().trim();
        nextMetadata.put("answer", answer);
        return new GuestRecommendResponse(
                cachedResponse.guest(),
                cachedResponse.personalized(),
                cachedResponse.maxGuestChatCount(),
                cachedResponse.maxGuestUserMessageCount(),
                cachedResponse.loginPrompt(),
                new GuestAssistantMessage(cachedMessage.role(), answer, nextMetadata, cachedMessage.createdAt())
        );
    }

    private List<ChatHistoryItem> normalizeHistory(List<GuestChatHistoryItem> history) {
        if (history == null || history.isEmpty()) {
            return List.of();
        }

        int fromIndex = Math.max(0, history.size() - AI_GUEST_HISTORY_MESSAGE_LIMIT);
        return history.subList(fromIndex, history.size()).stream()
                .filter(item -> item != null && item.content() != null && !item.content().isBlank())
                .map(item -> new ChatHistoryItem(
                        "assistant".equalsIgnoreCase(item.role()) ? "assistant" : "user",
                        truncate(item.content(), AI_GUEST_HISTORY_CONTENT_LIMIT),
                        item.createdAt() == null ? null : item.createdAt().toString(),
                        normalizeHistoryCandidates(item.candidates()),
                        sanitizeHistoryMetadata(item.metadata())
                ))
                .toList();
    }

    private List<AiRecommendationClient.BookCandidate> normalizeHistoryCandidates(List<AiRecommendationClient.BookCandidate> candidates) {
        if (candidates == null || candidates.isEmpty()) {
            return List.of();
        }
        return candidates.stream()
                .filter(candidate -> candidate != null && (candidate.title() != null || candidate.isbn() != null))
                .limit(5)
                .toList();
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
        // 수정 포인트: localStorage/Valkey에서 복원한 비로그인 history에는 profile 원문을 넣지 않고,
        // intent/context 승계용 metadata subset만 ai-server로 전달합니다.
        return result;
    }

    private Map<String, Object> normalizeGuestProfile(GuestProfileSnapshot profile) {
        if (profile == null) {
            return Map.of();
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("preferredGenres", safeList(profile.preferredGenres(), 12));
        result.put("dislikedGenres", safeList(profile.dislikedGenres(), 12));
        result.put("preferredMoods", safeList(profile.preferredMoods(), 12));
        result.put("dislikedMoods", safeList(profile.dislikedMoods(), 12));
        result.put("readingLevel", truncate(profile.readingLevel(), 40));
        result.put("summary", truncate(profile.summary(), 1000));
        return result;
    }

    private List<String> safeList(List<String> values, int maxSize) {
        if (values == null || values.isEmpty()) {
            return List.of();
        }
        return values.stream()
                .filter(value -> value != null && !value.isBlank())
                .map(value -> truncate(value, 40))
                .distinct()
                .limit(maxSize)
                .toList();
    }


    private String loginPrompt() {
        return guestMessage(LOGIN_PROMPT_MESSAGE_CODE);
    }

    private String normalizeGuestAnswer(AiRecommendationResponse response) {
        if (response == null) {
            return guestMessage(EMPTY_ANSWER_MESSAGE_CODE);
        }
        boolean hasCandidates = response.candidates() != null && !response.candidates().isEmpty();
        if (hasCandidates && (response.answer() == null || response.answer().isBlank())) {
            return guestMessage(PENDING_ANSWER_MESSAGE_CODE);
        }
        return response.answer() == null || response.answer().isBlank()
                ? guestMessage(EMPTY_ANSWER_MESSAGE_CODE)
                : response.answer().trim();
    }

    private boolean isReasonPending(Map<String, Object> metadata) {
        String status = String.valueOf(metadata.getOrDefault("recommendationReasonStatus", ""));
        return "PENDING".equalsIgnoreCase(status) || "PARTIAL".equalsIgnoreCase(status);
    }


    public GuestChatMessagesResponse loadMessages(String guestSessionId, String guestRoomId) {
        return new GuestChatMessagesResponse(
                guestSessionId,
                guestRoomId,
                guestChatStateService.loadMessages(guestSessionId, guestRoomId, GUEST_RESTORE_MESSAGE_LIMIT)
        );
    }

    public AiRecommendationClient.RecommendationReasonStatusResponse pollRecommendationReasons(String requestId) {
        if (requestId == null || requestId.isBlank()) {
            throw new IllegalArgumentException("requestId가 필요합니다.");
        }
        return aiRecommendationClient.fetchRecommendationReasons(java.util.UUID.fromString(requestId));
    }

    private String guestMessage(String code) {
        return messageSource.getMessage(code, null, code, Locale.KOREAN);
    }

    private Map<String, Object> buildAssistantMetadata(
            AiRecommendationResponse response,
            long latencyMs,
            Map<String, Object> guestProfile,
            String loginPrompt
    ) {
        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("source", "AI_SERVER");
        metadata.put("guest", true);
        metadata.put("personalized", false);
        metadata.put("latencyMs", latencyMs);
        metadata.put("loginPrompt", loginPrompt);
        metadata.put("loginPromptRequired", true);
        metadata.put("sessionContextApplied", guestProfile != null && !guestProfile.isEmpty());

        if (response == null) {
            metadata.put("candidates", List.of());
            return metadata;
        }

        metadata.put("query", response.query());
        metadata.put("answer", response.answer());
        metadata.put("cover", response.cover());
        metadata.put("profileApplied", Boolean.TRUE.equals(response.profileApplied()));
        metadata.put("intent", response.intent());
        metadata.put("intentSource", response.intentSource());
        metadata.put("requiresHistory", Boolean.TRUE.equals(response.requiresHistory()));
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
        // 수정 포인트: 비로그인 history도 raw guest_profile 대신 멀티턴 승계에 필요한 최소 metadata만 보존합니다.
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

    private String truncate(String value, int maxLength) {
        if (value == null || value.isBlank()) {
            return "";
        }
        String normalized = value.trim().replaceAll("\\s+", " ");
        if (normalized.length() <= maxLength) {
            return normalized;
        }
        return normalized.substring(0, maxLength) + "...";
    }
}
