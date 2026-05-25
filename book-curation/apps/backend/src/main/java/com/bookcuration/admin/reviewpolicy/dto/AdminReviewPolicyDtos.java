package com.taeo.bookcuration.admin.reviewpolicy.dto;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import java.time.OffsetDateTime;

public final class AdminReviewPolicyDtos {

    private AdminReviewPolicyDtos() {
    }

    public record ReviewPolicyResponse(
            int reviewWaitMinutes,
            String reviewWaitLabel,
            OffsetDateTime updatedAt
    ) {
    }

    public record ReviewPolicyUpdateRequest(
            @NotNull(message = "reviewWaitMinutes는 필수입니다.")
            @Min(value = 0, message = "reviewWaitMinutes는 0 이상이어야 합니다.")
            @Max(value = 43200, message = "reviewWaitMinutes는 최대 43200분(30일)까지 허용됩니다.")
            Integer reviewWaitMinutes
    ) {
    }
}
