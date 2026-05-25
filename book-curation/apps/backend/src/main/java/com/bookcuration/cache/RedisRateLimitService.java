package com.taeo.bookcuration.cache;

import com.taeo.bookcuration.config.RedisProperties;
import com.taeo.bookcuration.security.ratelimit.RateLimitProperties;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.util.Optional;

@Slf4j
@Service
@RequiredArgsConstructor
public class RedisRateLimitService {

    private final RedisProperties redisProperties;
    private final StringRedisTemplate redisTemplate;

    public Optional<Decision> consume(String key, RateLimitProperties.EndpointLimit limit) {
        if (!redisProperties.enabled()) {
            return Optional.empty();
        }
        try {
            long count = redisTemplate.opsForValue().increment(key);
            if (count == 1L) {
                redisTemplate.expire(key, Duration.ofMillis(limit.windowMillis()));
            }
            long ttlSeconds = Optional.ofNullable(redisTemplate.getExpire(key))
                    .filter(value -> value > 0)
                    .orElse(Math.max(1L, limit.windowMillis() / 1000L));
            boolean allowed = count <= limit.getCapacity();
            return Optional.of(new Decision(allowed, ttlSeconds, Math.max(0L, limit.getCapacity() - count)));
        } catch (Exception e) {
            log.warn("Redis rate limit is unavailable. key={}, reason={}", key, e.getMessage());
            return Optional.empty();
        }
    }

    public record Decision(boolean allowed, long retryAfterSeconds, long remaining) {
    }
}
