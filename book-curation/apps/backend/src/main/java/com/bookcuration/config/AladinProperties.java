package com.taeo.bookcuration.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "aladin")
public record AladinProperties(
        String baseUrl,
        String ttbKey,
        String searchTarget,
        String output,
        String version,
        Integer maxResults
) {
    public AladinProperties {
        // 수정 포인트: 알라딘 OpenAPI 호출 설정은 Git에 키를 저장하지 않고 환경변수로 주입합니다.
        baseUrl = (baseUrl == null || baseUrl.isBlank()) ? "http://www.aladin.co.kr" : trimTrailingSlash(baseUrl);
        searchTarget = (searchTarget == null || searchTarget.isBlank()) ? "Book" : searchTarget.trim();
        output = (output == null || output.isBlank()) ? "JS" : output.trim();
        version = (version == null || version.isBlank()) ? "20131101" : version.trim();
        maxResults = maxResults == null || maxResults <= 0 ? 10 : Math.min(maxResults, 50);
    }

    public boolean hasTtbKey() {
        return ttbKey != null && !ttbKey.isBlank();
    }

    public String safeTtbKey() {
        return ttbKey == null ? "" : ttbKey.trim();
    }

    public int clampLimit(int requestedLimit) {
        int safeLimit = requestedLimit <= 0 ? maxResults : requestedLimit;
        return Math.min(Math.max(safeLimit, 1), Math.min(maxResults, 50));
    }

    private static String trimTrailingSlash(String value) {
        String trimmed = value.trim();
        while (trimmed.endsWith("/")) {
            trimmed = trimmed.substring(0, trimmed.length() - 1);
        }
        return trimmed;
    }
}
