package com.taeo.bookcuration.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "data4library")
public record Data4LibraryProperties(
        String baseUrl,
        String authKey,
        Integer pageSize
) {
    public int safePageSize() {
        return pageSize == null || pageSize <= 0 ? 100 : pageSize;
    }

    public boolean hasAuthKey() {
        // 수정 포인트: 관리자 화면에서 Library API 토큰 설정 여부만 판단할 수 있게 헬퍼를 제공합니다.
        return authKey != null && !authKey.isBlank();
    }
}
