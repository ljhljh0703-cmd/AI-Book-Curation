package com.taeo.bookcuration.admin.recommendationmodel.dto;

import jakarta.validation.constraints.NotBlank;

import java.time.OffsetDateTime;
import java.util.List;

public final class AdminRecommendationModelDtos {

    private AdminRecommendationModelDtos() {
    }

    public record RecommendationModelSettingResponse(
            String embeddingModel,
            String recommendationStrategy,
            String personalizationModel,
            String rerankerProvider,
            Boolean bm25Enabled,
            // 수정 포인트: 기존 frontend/backend 소비 코드가 남아 있어도 깨지지 않도록 rankingModel alias를 유지합니다.
            String rankingModel,
            List<String> embeddingModelOptions,
            List<String> recommendationStrategyOptions,
            List<String> personalizationModelOptions,
            List<String> rerankerProviderOptions,
            List<String> rankingModelOptions,
            OffsetDateTime updatedAt
    ) {
    }

    public record RecommendationModelSettingUpdateRequest(
            @NotBlank(message = "embeddingModel은 필수입니다.")
            String embeddingModel,
            @NotBlank(message = "recommendationStrategy는 필수입니다.")
            String recommendationStrategy,
            @NotBlank(message = "personalizationModel은 필수입니다.")
            String personalizationModel,
            @NotBlank(message = "rerankerProvider는 필수입니다.")
            String rerankerProvider,
            // 수정 포인트: null이면 service에서 기본 false로 처리해 기존 추천 품질을 유지합니다.
            Boolean bm25Enabled
    ) {
    }
}
