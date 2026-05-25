package com.taeo.bookcuration.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.time.Duration;

@ConfigurationProperties(prefix = "app.ai-server")
public record AiServerProperties(
        String baseUrl,
        Duration connectTimeout,
        Duration readTimeout,
        String internalApiKey,
        Duration lightfmTrainingReadTimeout
) {
    public AiServerProperties {
        // 수정 포인트: K3s 내부 Service DNS를 기본값으로 사용해 backend → ai-server 내부 호출을 보수적으로 연결합니다.
        baseUrl = (baseUrl == null || baseUrl.isBlank()) ? "http://book-curation-ai:8001" : trimTrailingSlash(baseUrl);
        connectTimeout = connectTimeout == null ? Duration.ofSeconds(3) : connectTimeout;
        readTimeout = readTimeout == null ? Duration.ofSeconds(75) : readTimeout;
        // 수정 포인트: ai-server가 내부 공유키 검증을 켰을 때 backend가 같은 키를 헤더로 전달할 수 있게 합니다.
        internalApiKey = internalApiKey == null ? "" : internalApiKey.trim();
        lightfmTrainingReadTimeout = lightfmTrainingReadTimeout == null ? Duration.ofSeconds(7260) : lightfmTrainingReadTimeout;
    }

    private static String trimTrailingSlash(String value) {
        String trimmed = value.trim();
        while (trimmed.endsWith("/")) {
            trimmed = trimmed.substring(0, trimmed.length() - 1);
        }
        return trimmed;
    }
}
