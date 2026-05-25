package com.taeo.bookcuration.admin.onboarding.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.time.OffsetDateTime;
import java.util.List;

public final class AdminOnboardingOptionDtos {

    private AdminOnboardingOptionDtos() {
    }

    public enum OnboardingOptionGroup {
        READER_TYPE,
        BOOK_CATEGORY
    }

    public record OnboardingOptionRequest(
            @NotNull
            OnboardingOptionGroup optionGroup,
            @NotBlank
            @Size(max = 100)
            String label,
            @Size(max = 300)
            String description,
            @Size(max = 50)
            String characterGroupCode,
            Boolean active
    ) {
    }

    public record OnboardingOptionReorderRequest(
            @NotNull
            OnboardingOptionGroup optionGroup,
            @NotEmpty
            List<Long> orderedIds
    ) {
    }

    public record OnboardingOptionResponse(
            Long id,
            String optionGroup,
            String label,
            String description,
            String characterGroupCode,
            Integer displayOrder,
            Boolean active,
            OffsetDateTime createdAt,
            OffsetDateTime updatedAt
    ) {
    }
}
