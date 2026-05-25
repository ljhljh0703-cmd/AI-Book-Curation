package com.taeo.bookcuration.admin.recommendationmodel.dto;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;

import java.time.OffsetDateTime;
import java.util.UUID;

public final class AdminAudienceLabelDtos {

    private AdminAudienceLabelDtos() {
    }

    public record AudienceLabelBatchStartRequest(
            @Min(value = 1, message = "limit은 1 이상이어야 합니다.")
            @Max(value = 500, message = "limit은 500 이하로 지정해 주세요.")
            Integer limit,
            Boolean force
    ) {
    }

    public record AudienceLabelBatchJobResponse(
            UUID jobId,
            String status,
            Integer requestedLimit,
            Boolean force,
            Integer totalTargetCount,
            Integer processedCount,
            Integer successCount,
            Integer failedCount,
            Integer skippedCount,
            String message,
            String errorMessage,
            OffsetDateTime startedAt,
            OffsetDateTime finishedAt
    ) {
    }

    public record AudienceLabelSummaryResponse(
            Boolean schemaReady,
            Long totalBookCount,
            Long defaultTargetCount,
            Long forceTargetCount,
            Long pendingCount,
            Long failedCount,
            Long readyCount,
            Long skippedCount,
            Long unknownStatusCount,
            String message
    ) {
    }
}
