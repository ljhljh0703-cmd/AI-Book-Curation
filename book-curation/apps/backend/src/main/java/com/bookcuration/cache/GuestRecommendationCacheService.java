package com.taeo.bookcuration.cache;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.taeo.bookcuration.chat.client.AiRecommendationClient;
import com.taeo.bookcuration.chat.dto.GuestChatDtos.GuestRecommendResponse;
import com.taeo.bookcuration.config.RedisProperties;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Map;
import java.util.Optional;

@Slf4j
@Service
@RequiredArgsConstructor
public class GuestRecommendationCacheService {

    private final RedisProperties properties;
    private final RedisKeyService keyService;
    private final StringRedisTemplate redisTemplate;
    private final ObjectMapper objectMapper;

    public String key(
            String guestSessionId,
            String guestRoomId,
            String content,
            List<AiRecommendationClient.ChatHistoryItem> history,
            Map<String, Object> guestProfile
    ) {
        // 수정 포인트: stale cache 방지를 위해 query/history/profile hash를 모두 cache key에 포함합니다.
        return keyService.key(
                "guest",
                "recommendation-result",
                guestSessionId,
                guestRoomId,
                keyService.hash(content).substring(0, 32),
                keyService.hash(toJson(history)).substring(0, 32),
                keyService.hash(toJson(guestProfile)).substring(0, 32)
        );
    }

    public Optional<GuestRecommendResponse> get(String key) {
        if (!properties.enabled()) {
            return Optional.empty();
        }
        try {
            String raw = redisTemplate.opsForValue().get(key);
            if (raw == null || raw.isBlank()) {
                return Optional.empty();
            }
            return Optional.of(objectMapper.readValue(raw, GuestRecommendResponse.class));
        } catch (Exception e) {
            log.warn("Guest recommendation cache read failed. key={}, reason={}", key, e.getMessage());
            return Optional.empty();
        }
    }

    public void put(String key, GuestRecommendResponse response) {
        if (!properties.enabled() || response == null) {
            return;
        }
        try {
            redisTemplate.opsForValue().set(key, objectMapper.writeValueAsString(response), properties.recommendationCacheTtl());
        } catch (Exception e) {
            log.warn("Guest recommendation cache write failed. key={}, reason={}", key, e.getMessage());
        }
    }

    private String toJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (Exception e) {
            return String.valueOf(value);
        }
    }
}
