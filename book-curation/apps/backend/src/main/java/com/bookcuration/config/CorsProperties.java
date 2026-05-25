package com.taeo.bookcuration.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.util.List;

@ConfigurationProperties(prefix = "app.cors")
public record CorsProperties(
        List<String> allowedOrigins
) {
    public List<String> safeAllowedOrigins() {
        if (allowedOrigins == null || allowedOrigins.isEmpty()) {
            return List.of("http://localhost:5173", "http://localhost:3000");
        }
        return allowedOrigins;
    }
}
