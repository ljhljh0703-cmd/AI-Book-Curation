package com.taeo.bookcuration.cache;

import com.taeo.bookcuration.config.RedisProperties;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Locale;
import java.util.stream.Collectors;
import java.util.stream.Stream;

@Component
@RequiredArgsConstructor
public class RedisKeyService {

    private final RedisProperties properties;

    public String key(String domain, String purpose, String... parts) {
        String suffix = Stream.concat(Stream.of(domain, purpose), Stream.of(parts == null ? new String[0] : parts))
                .map(this::safePart)
                .filter(value -> !value.isBlank())
                .collect(Collectors.joining(":"));
        return properties.keyPrefix() + ":" + suffix;
    }

    public String hash(String value) {
        String normalized = value == null ? "" : value.trim();
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(digest.digest(normalized.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 digest is not available", e);
        }
    }

    private String safePart(String value) {
        if (value == null || value.isBlank()) {
            return "";
        }
        String safe = value.trim().toLowerCase(Locale.ROOT)
                .replaceAll("[^a-z0-9._-]+", "-")
                .replaceAll("-+", "-");
        return safe.length() > 120 ? hash(safe).substring(0, 32) : safe;
    }
}
