package com.taeo.bookcuration.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.time.Duration;

@ConfigurationProperties(prefix = "app.redis")
public record RedisProperties(
        boolean enabled,
        String keyPrefix,
        Duration guestChatTtl,
        Duration guestDuplicateLockTtl,
        Duration recommendationCacheTtl,
        Duration qdrantSearchCacheTtl,
        Duration gteRerankCacheTtl,
        Duration adminJobLockTtl
) {
    public RedisProperties {
        keyPrefix = normalizePrefix(keyPrefix);
        guestChatTtl = positiveOrDefault(guestChatTtl, Duration.ofHours(24));
        guestDuplicateLockTtl = positiveOrDefault(guestDuplicateLockTtl, Duration.ofSeconds(20));
        recommendationCacheTtl = positiveOrDefault(recommendationCacheTtl, Duration.ofMinutes(10));
        qdrantSearchCacheTtl = positiveOrDefault(qdrantSearchCacheTtl, Duration.ofMinutes(10));
        gteRerankCacheTtl = positiveOrDefault(gteRerankCacheTtl, Duration.ofMinutes(10));
        adminJobLockTtl = positiveOrDefault(adminJobLockTtl, Duration.ofHours(6));
    }

    private static String normalizePrefix(String value) {
        String normalized = value == null || value.isBlank() ? "book-curation" : value.trim();
        while (normalized.endsWith(":")) {
            normalized = normalized.substring(0, normalized.length() - 1);
        }
        return normalized;
    }

    private static Duration positiveOrDefault(Duration value, Duration fallback) {
        return value == null || value.isZero() || value.isNegative() ? fallback : value;
    }
}
