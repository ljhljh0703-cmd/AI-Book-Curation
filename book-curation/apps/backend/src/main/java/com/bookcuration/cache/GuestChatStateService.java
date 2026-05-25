package com.taeo.bookcuration.cache;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.taeo.bookcuration.chat.client.AiRecommendationClient;
import com.taeo.bookcuration.chat.dto.GuestChatDtos.GuestStoredMessage;
import com.taeo.bookcuration.config.RedisProperties;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Slf4j
@Service
@RequiredArgsConstructor
public class GuestChatStateService {

    private static final int MAX_STORED_MESSAGES_PER_ROOM = 40;
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

    private final RedisProperties properties;
    private final RedisKeyService keyService;
    private final StringRedisTemplate redisTemplate;
    private final ObjectMapper objectMapper;

    public void appendUserAndAssistantMessages(
            String guestSessionId,
            String guestRoomId,
            String userContent,
            String assistantContent,
            Map<String, Object> assistantMetadata
    ) {
        if (!properties.enabled()) {
            return;
        }
        String key = messageKey(guestSessionId, guestRoomId);
        try {
            List<String> values = List.of(
                    objectMapper.writeValueAsString(new GuestStoredMessage(
                            "USER",
                            userContent,
                            Map.of("guest", true),
                            OffsetDateTime.now()
                    )),
                    objectMapper.writeValueAsString(new GuestStoredMessage(
                            "ASSISTANT",
                            assistantContent,
                            assistantMetadata == null ? Map.of() : assistantMetadata,
                            OffsetDateTime.now()
                    ))
            );
            redisTemplate.opsForList().rightPushAll(key, values);
            redisTemplate.opsForList().trim(key, -MAX_STORED_MESSAGES_PER_ROOM, -1);
            redisTemplate.expire(key, properties.guestChatTtl());
        } catch (Exception e) {
            log.warn("Guest chat Redis append failed. guestSessionId={}, guestRoomId={}, reason={}", guestSessionId, guestRoomId, e.getMessage());
        }
    }

    public List<GuestStoredMessage> loadMessages(String guestSessionId, String guestRoomId, int limit) {
        if (!properties.enabled()) {
            return List.of();
        }
        String key = messageKey(guestSessionId, guestRoomId);
        int safeLimit = Math.max(1, Math.min(limit, MAX_STORED_MESSAGES_PER_ROOM));
        try {
            Long size = redisTemplate.opsForList().size(key);
            if (size == null || size <= 0) {
                return List.of();
            }
            long start = Math.max(0L, size - safeLimit);
            List<String> raw = redisTemplate.opsForList().range(key, start, -1);
            if (raw == null || raw.isEmpty()) {
                return List.of();
            }
            List<GuestStoredMessage> messages = new ArrayList<>();
            for (String value : raw) {
                try {
                    messages.add(objectMapper.readValue(value, GuestStoredMessage.class));
                } catch (Exception ignored) {
                    // 수정 포인트: TTL 임시 저장소의 일부 레코드가 깨져도 전체 복원을 실패시키지 않습니다.
                }
            }
            return Collections.unmodifiableList(messages);
        } catch (Exception e) {
            log.warn("Guest chat Redis load failed. guestSessionId={}, guestRoomId={}, reason={}", guestSessionId, guestRoomId, e.getMessage());
            return List.of();
        }
    }

    public List<AiRecommendationClient.ChatHistoryItem> loadHistory(String guestSessionId, String guestRoomId, int limit) {
        return loadMessages(guestSessionId, guestRoomId, limit).stream()
                .filter(message -> message.content() != null && !message.content().isBlank())
                .map(message -> new AiRecommendationClient.ChatHistoryItem(
                        "ASSISTANT".equalsIgnoreCase(message.role()) ? "assistant" : "user",
                        message.content(),
                        message.createdAt() == null ? null : message.createdAt().toString(),
                        extractHistoryCandidates(message),
                        sanitizeHistoryMetadata(message.metadata())
                ))
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
        // 수정 포인트: Valkey 복원 history에도 profile 원문이 아닌 멀티턴용 metadata subset만 포함합니다.
        return result;
    }

    private List<AiRecommendationClient.BookCandidate> extractHistoryCandidates(GuestStoredMessage message) {
        if (!"ASSISTANT".equalsIgnoreCase(message.role()) || message.metadata() == null) {
            return List.of();
        }
        Object rawCandidates = message.metadata().get("candidates");
        if (!(rawCandidates instanceof List<?> rawList) || rawList.isEmpty()) {
            return List.of();
        }
        try {
            List<AiRecommendationClient.BookCandidate> candidates = objectMapper.convertValue(
                    rawCandidates,
                    new TypeReference<List<AiRecommendationClient.BookCandidate>>() {
                    }
            );
            return candidates.stream()
                    .filter(candidate -> candidate != null && hasCandidateIdentity(candidate))
                    .limit(5)
                    .toList();
        } catch (IllegalArgumentException e) {
            log.warn("Guest chat Redis candidate metadata restore failed. reason={}", e.getMessage());
            return List.of();
        }
    }

    private boolean hasCandidateIdentity(AiRecommendationClient.BookCandidate candidate) {
        return hasText(candidate.title()) || hasText(candidate.isbn());
    }

    private boolean hasText(String value) {
        return value != null && !value.isBlank();
    }

    private String messageKey(String guestSessionId, String guestRoomId) {
        return keyService.key("guest", "chat-messages", guestSessionId, guestRoomId);
    }
}
