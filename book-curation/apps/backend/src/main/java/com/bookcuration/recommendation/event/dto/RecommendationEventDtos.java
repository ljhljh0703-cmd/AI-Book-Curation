package com.taeo.bookcuration.recommendation.event.dto;

import com.taeo.bookcuration.user.dto.UserDtos.BookSnapshotRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.Map;
import java.util.UUID;

public final class RecommendationEventDtos {

    private RecommendationEventDtos() {
    }

    public enum UserBehaviorEventType {
        RECOMMENDATION_IMPRESSION,
        BOOK_CLICK,
        DETAIL_VIEW,
        FAVORITE_ADD,
        FAVORITE_REMOVE,
        READING_ADD,
        READ_ADD,
        RATING_ADD,
        REVIEW_ADD,
        DISLIKE_ADD,
        DISLIKE_REMOVE,
        SEARCH_QUERY
    }

    public record RecommendationEventRequest(
            UUID requestId,
            Long bookId,
            @Valid
            BookSnapshotRequest book,
            @NotNull
            UserBehaviorEventType eventType,
            @Size(max = 50)
            String source,
            @Size(max = 4000)
            String query,
            @Min(1)
            Integer rank,
            @DecimalMin("0.0")
            BigDecimal score,
            Map<String, Object> metadata
    ) {
    }

    public record RecommendationEventResponse(
            Long id,
            UUID requestId,
            Long bookId,
            UserBehaviorEventType eventType,
            OffsetDateTime createdAt
    ) {
    }
}
