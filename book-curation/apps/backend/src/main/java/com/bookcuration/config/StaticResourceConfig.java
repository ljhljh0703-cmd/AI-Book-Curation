package com.taeo.bookcuration.config;

import lombok.RequiredArgsConstructor;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
@RequiredArgsConstructor
public class StaticResourceConfig implements WebMvcConfigurer {

    private final FileStorageProperties fileStorageProperties;

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        String publicPrefix = normalizePublicPrefix(fileStorageProperties.getPublicUrlPrefix());
        String location = fileStorageProperties.getRootPath().toAbsolutePath().normalize().toUri().toString();

        // 수정 포인트: NAS/K3s에 저장된 업로드 이미지를 /uploads/** 공개 경로로 서빙합니다.
        registry.addResourceHandler(publicPrefix + "/**")
                .addResourceLocations(location);
    }

    private static String normalizePublicPrefix(String value) {
        if (value == null || value.isBlank()) {
            return "/uploads";
        }
        String normalized = value.trim();
        if (!normalized.startsWith("/")) {
            normalized = "/" + normalized;
        }
        return normalized.replaceAll("/+$", "");
    }
}
