package com.taeo.bookcuration.cache;

import com.taeo.bookcuration.config.RedisProperties;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.util.List;
import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class RedisLockService {

    private static final DefaultRedisScript<Long> RELEASE_SCRIPT = new DefaultRedisScript<>(
            "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",
            Long.class
    );

    private final RedisProperties properties;
    private final StringRedisTemplate redisTemplate;

    public LockToken tryLock(String key, Duration ttl) {
        if (!properties.enabled()) {
            return LockToken.notAvailable(key);
        }
        String token = UUID.randomUUID().toString();
        Duration safeTtl = ttl == null || ttl.isZero() || ttl.isNegative() ? Duration.ofSeconds(30) : ttl;
        try {
            Boolean acquired = redisTemplate.opsForValue().setIfAbsent(key, token, safeTtl);
            return Boolean.TRUE.equals(acquired) ? LockToken.acquired(key, token) : LockToken.contended(key);
        } catch (Exception e) {
            log.warn("Redis lock is unavailable. key={}, reason={}", key, e.getMessage());
            return LockToken.notAvailable(key);
        }
    }

    public void release(LockToken token) {
        if (token == null || !token.acquired()) {
            return;
        }
        try {
            redisTemplate.execute(RELEASE_SCRIPT, List.of(token.key()), token.token());
        } catch (Exception e) {
            log.warn("Redis lock release failed. key={}, reason={}", token.key(), e.getMessage());
        }
    }

    public record LockToken(String key, String token, boolean acquired, boolean available) {
        static LockToken acquired(String key, String token) {
            return new LockToken(key, token, true, true);
        }

        static LockToken contended(String key) {
            return new LockToken(key, "", false, true);
        }

        static LockToken notAvailable(String key) {
            return new LockToken(key, "", false, false);
        }
    }
}
