package com.taeo.bookcuration.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.time.Duration;

@ConfigurationProperties(prefix = "app.query-evaluation-runner")
public record QueryEvaluationRunnerProperties(
        Boolean enabled,
        String baseUrl,
        String apiKey,
        Duration connectTimeout,
        Duration readTimeout
) {
    public QueryEvaluationRunnerProperties {
        // 수정 포인트: 관리자 성능평가의 무거운 실행은 NAS ai-server pod가 아니라 외부 local runner로 우회할 수 있게 분리합니다.
        enabled = enabled != null && enabled;
        baseUrl = (baseUrl == null || baseUrl.isBlank()) ? "" : trimTrailingSlash(baseUrl);
        apiKey = apiKey == null ? "" : apiKey.trim();
        connectTimeout = connectTimeout == null ? Duration.ofSeconds(3) : connectTimeout;
        readTimeout = readTimeout == null ? Duration.ofSeconds(30) : readTimeout;
    }

    public boolean configured() {
        return Boolean.TRUE.equals(enabled) && baseUrl != null && !baseUrl.isBlank();
    }

    private static String trimTrailingSlash(String value) {
        String trimmed = value.trim();
        while (trimmed.endsWith("/")) {
            trimmed = trimmed.substring(0, trimmed.length() - 1);
        }
        return trimmed;
    }
}
