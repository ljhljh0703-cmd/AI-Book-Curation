package com.taeo.bookcuration.onboarding.dto;

import com.taeo.bookcuration.user.dto.UserDtos.BookSnapshotRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;

public final class OnboardingDtos {

    private OnboardingDtos() {
    }

    public record OnboardingOptionResponse(
            Long id,
            String optionGroup,
            String optionKey,
            String label,
            String description,
            String characterKey,
            String characterDefaultName,
            String characterImageUrl,
            Integer displayOrder
    ) {
    }

    public record OnboardingSubmitRequest(
            @NotBlank
            @Pattern(regexp = "\\d{6}", message = "residentNumberFront는 YYMMDD 6자리 숫자여야 합니다.")
            String residentNumberFront,

            @NotBlank
            // 수정 포인트: DB 제약조건과 동일하게 1~4만 허용해 잘못된 값이 저장 단계까지 내려가지 않게 합니다.
            @Pattern(regexp = "[1-4]", message = "residentGenderDigit은 주민등록번호 뒷자리 첫 숫자 1~4 중 하나여야 합니다.")
            String residentGenderDigit,

            @NotNull
            Long readerTypeOptionId,

            @Size(max = 3)
            List<@NotNull Long> bookCategoryOptionIds,

            @Size(max = 300)
            String readingPurpose,

            @Size(max = 100)
            String regionName,

            BigDecimal latitude,

            BigDecimal longitude,

            @DecimalMin("1.0")
            @DecimalMax("50.0")
            BigDecimal preferredRadiusKm,

            @Size(max = 50)
            String preferredLibraryCode,

            @Size(max = 3)
            List<@Valid SelectedBookRequest> selectedBooks
    ) {
    }

    public record SelectedBookRequest(
            Long bookId,

            @Valid
            BookSnapshotRequest book,

            @Size(max = 30)
            String shelfType,

            @Size(max = 500)
            String note
    ) {
    }

    public record OnboardingSubmitResponse(
            boolean onboardingCompleted,
            ProfileSummary profile,
            CharacterSummary character,
            List<SavedBookShelfSummary> savedBookShelves,
            String preferredLibraryCode
    ) {
    }

    public record ProfileSummary(
            LocalDate birthDate,
            String residentGenderDigit,
            Long readerTypeOptionId,
            List<Long> bookCategoryOptionIds,
            String readingPurpose,
            String regionName,
            BigDecimal latitude,
            BigDecimal longitude,
            BigDecimal preferredRadiusKm
    ) {
    }

    public record CharacterSummary(
            String characterKey,
            String characterNickname,
            String currentImageUrl
    ) {
    }

    public record SavedBookShelfSummary(
            Long bookId,
            String shelfType
    ) {
    }
}