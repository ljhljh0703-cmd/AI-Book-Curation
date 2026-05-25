package com.taeo.bookcuration.user.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;

public final class UserDtos {

    private UserDtos() {
    }

    public record UserProfileRequest(
            @Pattern(regexp = "\\d{6}", message = "residentNumberFront는 YYMMDD 6자리 숫자여야 합니다.")
            String residentNumberFront,
            // 수정 포인트: DB 제약조건과 동일하게 1~4만 허용해 5~9 입력 시 DB 오류 전에 검증 오류를 반환합니다.
            @Pattern(regexp = "[1-4]", message = "residentGenderDigit은 주민등록번호 뒷자리 첫 숫자 1~4 중 하나여야 합니다.")
            String residentGenderDigit,
            Long readerTypeOptionId,
            @Size(max = 300)
            String readingPurpose,
            @Size(max = 100)
            String regionName,
            BigDecimal latitude,
            BigDecimal longitude,
            // 수정 포인트: 도서관 검색 반경은 1~10km 단위 선택지와 10~50km 광역 선택지(값 50)만 허용합니다.
            @DecimalMin("1.0")
            @DecimalMax("50.0")
            BigDecimal preferredRadiusKm,
            List<String> categoryCodes,
            List<String> keywords
    ) {
    }

    public record UserProfileIdentityRequest(
            @Pattern(regexp = "\\d{6}", message = "residentNumberFront는 YYMMDD 6자리 숫자여야 합니다.")
            String residentNumberFront,
            @Pattern(regexp = "[1-4]", message = "residentGenderDigit은 주민등록번호 뒷자리 첫 숫자 1~4 중 하나여야 합니다.")
            String residentGenderDigit
    ) {
    }

    public record UserProfileCategoriesRequest(
            @Size(max = 3, message = "희망 장르는 최대 3개까지 선택할 수 있습니다.")
            List<@NotBlank String> categoryCodes
    ) {
    }

    public record UserProfileReadingPurposeRequest(
            @Size(max = 300, message = "독서 목적은 300자 이하로 입력해 주세요.")
            String readingPurpose
    ) {
    }

    public record UserProfilePreferredRadiusRequest(
            @NotNull(message = "preferredRadiusKm는 필수입니다.")
            @DecimalMin("1.0")
            @DecimalMax("50.0")
            BigDecimal preferredRadiusKm
    ) {
    }

    public record UserProfileResponse(
            UUID userId,
            LocalDate birthDate,
            String residentGenderDigit,
            Long readerTypeOptionId,
            String readerTypeLabel,
            String readingPurpose,
            String regionName,
            BigDecimal latitude,
            BigDecimal longitude,
            BigDecimal preferredRadiusKm,
            boolean onboardingCompleted,
            List<String> categoryCodes,
            List<String> keywords
    ) {
    }

    public record UserCharacterResponse(
            UUID userId,
            String characterKey,
            String stage,
            String characterNickname,
            int reviewGrowthCount,
            String currentImageUrl,
            int characterLevel,
            int experience,
            int experienceToNextLevel,
            int experiencePercent,
            int maxLevel
    ) {
    }

    public record UserCharacterNicknameRequest(
            @NotBlank
            @Size(min = 1, max = 30)
            String characterNickname
    ) {
    }

    public record PreferredLibraryRequest(
            @NotBlank
            String libCode,
            @Positive
            Integer priority
    ) {
    }

    public record PreferredLibraryResponse(
            Long id,
            String libCode,
            String libName,
            String address,
            BigDecimal latitude,
            BigDecimal longitude,
            int priority
    ) {
    }

    public record BookActionRequest(
            @NotNull
            Long bookId,
            @NotBlank
            String actionType,
            // 수정 포인트: 리뷰 평점과 동일하게 0.5 단위 평점을 저장할 수 있도록 BigDecimal을 사용합니다.
            @DecimalMin("0.5")
            @DecimalMax("5.0")
            BigDecimal rating,
            String source,
            Map<String, Object> metadata
    ) {
    }

    public record BookActionResponse(
            Long id,
            Long bookId,
            String actionType,
            BigDecimal rating,
            OffsetDateTime createdAt
    ) {
    }

    public record BookSnapshotRequest(
            Long bookId,
            @Pattern(regexp = "\\d{13}", message = "isbn13은 13자리 숫자여야 합니다.")
            String isbn13,
            @Size(max = 500)
            String title,
            @Size(max = 500)
            String author,
            @Size(max = 255)
            String publisher,
            String coverUrl,
            String categoryCode,
            Map<String, Object> metadata
    ) {
    }

    public record BookShelfRequest(
            Long bookId,
            @Valid
            BookSnapshotRequest book,
            @NotBlank
            String shelfType,
            String note
    ) {
    }

    public record BookShelfResponse(
            Long id,
            Long bookId,
            String isbn13,
            String title,
            String author,
            String publisher,
            String coverUrl,
            String shelfType,
            String note,
            String reviewContent,
            BigDecimal reviewRating,
            OffsetDateTime reviewAvailableAt,
            boolean reviewAvailable,
            int reviewWaitMinutes,
            String reviewWaitLabel,
            OffsetDateTime completedAt,
            OffsetDateTime createdAt,
            OffsetDateTime updatedAt
    ) {
    }

    public record BookShelfSummaryResponse(
            int maxReadingCount,
            int maxInterestedCount,
            int maxNotInterestedCount,
            Map<String, Integer> counts,
            Map<String, Integer> remaining
    ) {
    }

    public record BookShelfStateResponse(
            String isbn13,
            Long bookId,
            boolean interested,
            boolean notInterested,
            boolean reading
    ) {
    }

    public record BookShelfReviewRequest(
            @NotBlank
            @Size(max = 2000)
            String reviewContent,
            // 수정 포인트: 별점 UI가 0.5점 단위로 동작하므로 리뷰 저장 요청도 0.5~5.0 범위의 소수 평점을 받습니다.
            @NotNull
            @DecimalMin("0.5")
            @DecimalMax("5.0")
            BigDecimal rating
    ) {
    }

    public record CharacterLevelUpEventResponse(
            int previousLevel,
            int newLevel,
            String characterNickname,
            String characterImageUrl,
            int experience,
            int experienceToNextLevel,
            int maxLevel,
            String message
    ) {
    }

    public record BookShelfReviewResponse(
            BookShelfResponse shelf,
            UserCharacterResponse character,
            CharacterLevelUpEventResponse levelUpEvent,
            boolean reviewRewardGranted,
            String reviewRewardMessage
    ) {
    }

    public record BookAvailabilityRequest(
            @Valid
            BookSnapshotRequest book,
            @Pattern(regexp = "\\d{13}", message = "isbn13은 13자리 숫자여야 합니다.")
            String isbn13,
            BigDecimal latitude,
            BigDecimal longitude,
            BigDecimal radiusKm
    ) {
    }

    public record BookAvailabilityLibraryResult(
            String source,
            String libCode,
            String libName,
            String address,
            BigDecimal distanceMeters,
            Boolean hasBook,
            Boolean loanAvailable,
            String message,
            boolean success
    ) {
    }

    public record BookAvailabilityResponse(
            String isbn13,
            int preferredLibraryCount,
            int nearbyLibraryCount,
            List<BookAvailabilityLibraryResult> libraries
    ) {
    }
}