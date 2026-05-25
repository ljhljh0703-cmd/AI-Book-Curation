package com.taeo.bookcuration.user.entity;

import com.taeo.bookcuration.auth.entity.UserEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.MapsId;
import jakarta.persistence.OneToOne;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.UUID;

@Getter
@Entity
@Table(name = "user_profiles", schema = "book")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class UserProfileEntity {

    @Id
    @Column(name = "user_id", columnDefinition = "uuid")
    private UUID userId;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @MapsId
    @JoinColumn(name = "user_id", nullable = false)
    private UserEntity user;

    @Column(name = "birth_date")
    private LocalDate birthDate;

    @Column(name = "resident_gender_digit", length = 1)
    private String residentGenderDigit;

    @Column(name = "reader_type_option_id")
    private Long readerTypeOptionId;

    @Column(name = "reading_purpose", length = 300)
    private String readingPurpose;

    @Column(name = "region_name", length = 100)
    private String regionName;

    @Column(precision = 9, scale = 6)
    private BigDecimal latitude;

    @Column(precision = 9, scale = 6)
    private BigDecimal longitude;

    @Column(name = "preferred_radius_km", nullable = false, precision = 5, scale = 2)
    private BigDecimal preferredRadiusKm;

    @Column(name = "profile_summary")
    private String profileSummary;

    @Column(name = "onboarding_completed", nullable = false)
    private boolean onboardingCompleted;

    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;

    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt;

    public static UserProfileEntity createEmpty(UserEntity user) {
        UserProfileEntity profile = new UserProfileEntity();
        profile.user = user;
        profile.preferredRadiusKm = new BigDecimal("5.00");
        profile.onboardingCompleted = false;
        return profile;
    }

    public void update(
            String readingPurpose,
            String regionName,
            BigDecimal latitude,
            BigDecimal longitude,
            BigDecimal preferredRadiusKm,
            String profileSummary
    ) {
        // 수정 포인트: reading_level 컬럼은 제거되었으므로 독서 목적만 자유 텍스트로 관리합니다.
        this.readingPurpose = readingPurpose;
        // 수정 포인트: 위치/지역명은 DB에 저장하지 않고 검색 시점의 브라우저 위치만 사용합니다.
        this.regionName = null;
        this.latitude = null;
        this.longitude = null;
        this.preferredRadiusKm = preferredRadiusKm == null ? new BigDecimal("5.00") : preferredRadiusKm;
        this.profileSummary = profileSummary;
        this.onboardingCompleted = true;
    }

    public void updateFromMyPage(
            LocalDate birthDate,
            String residentGenderDigit,
            Long readerTypeOptionId,
            String readingPurpose,
            String regionName,
            BigDecimal latitude,
            BigDecimal longitude,
            BigDecimal preferredRadiusKm
    ) {
        // 수정 포인트: 이름은 수집하지 않고, 생년월일/독자유형/희망장르 등 추천에 필요한 값만 저장합니다.
        if (birthDate != null) {
            this.birthDate = birthDate;
        }
        if (residentGenderDigit != null) {
            this.residentGenderDigit = residentGenderDigit;
        }
        this.readerTypeOptionId = readerTypeOptionId;
        // 수정 포인트: 대표 장르 컬럼(book_category_option_id)은 제거하고,
        // 희망 장르는 user_interest_categories에 optionKey 목록으로만 저장합니다.
        this.readingPurpose = readingPurpose;
        // 수정 포인트: 위치/지역명은 DB에 저장하지 않고 검색 시점의 브라우저 위치만 사용합니다.
        this.regionName = null;
        this.latitude = null;
        this.longitude = null;
        this.preferredRadiusKm = preferredRadiusKm == null ? new BigDecimal("5.00") : preferredRadiusKm;
        this.onboardingCompleted = true;
    }
    public void updateIdentityFromMyPage(LocalDate birthDate, String residentGenderDigit) {
        // 수정 포인트: 기본 정보 탭 저장은 생년월일/성별 식별값만 갱신하고 장르/독서목적/반경은 건드리지 않습니다.
        if (birthDate != null) {
            this.birthDate = birthDate;
        }
        if (residentGenderDigit != null) {
            this.residentGenderDigit = residentGenderDigit;
        }
        this.onboardingCompleted = true;
    }

    public void updateReadingPurposeFromMyPage(String readingPurpose) {
        // 수정 포인트: 독서 목적 탭 저장은 reading_purpose만 갱신합니다.
        this.readingPurpose = readingPurpose;
        this.onboardingCompleted = true;
    }

    public void updatePreferredRadiusFromMyPage(BigDecimal preferredRadiusKm) {
        // 수정 포인트: 선호 반경 탭 저장은 도서관 검색 기본 반경만 갱신합니다.
        this.preferredRadiusKm = preferredRadiusKm == null ? new BigDecimal("5.00") : preferredRadiusKm;
        this.onboardingCompleted = true;
    }

    public void markUpdatedFromMyPage() {
        // 수정 포인트: 희망 장르처럼 별도 테이블만 바뀌는 탭도 마이페이지 수정 완료 상태를 유지합니다.
        this.onboardingCompleted = true;
    }


    public void skipOnboarding() {
        this.regionName = null;
        this.latitude = null;
        this.longitude = null;
        this.preferredRadiusKm = this.preferredRadiusKm == null ? new BigDecimal("5.00") : this.preferredRadiusKm;
        // 수정 포인트: 온보딩 건너뛰기는 완료가 아니므로 다음 로그인 때 다시 안내될 수 있게 false를 유지합니다.
        this.onboardingCompleted = false;
    }
    public void completeOnboarding(
            LocalDate birthDate,
            String residentGenderDigit,
            Long readerTypeOptionId,
            String readingPurpose,
            String regionName,
            BigDecimal latitude,
            BigDecimal longitude,
            BigDecimal preferredRadiusKm
    ) {
        // 수정 포인트: 주민등록번호 원문은 저장하지 않고 생년월일과 뒷자리 첫 글자만 저장합니다. 이름은 수집하지 않습니다.
        this.birthDate = birthDate;
        this.residentGenderDigit = residentGenderDigit;
        this.readerTypeOptionId = readerTypeOptionId;
        // 수정 포인트: 대표 장르 컬럼(book_category_option_id)은 제거하고,
        // 희망 장르는 user_interest_categories에 optionKey 목록으로만 저장합니다.
        this.readingPurpose = readingPurpose;
        // 수정 포인트: 위치/지역명은 DB에 저장하지 않고 검색 시점의 브라우저 위치만 사용합니다.
        this.regionName = null;
        this.latitude = null;
        this.longitude = null;
        this.preferredRadiusKm = preferredRadiusKm == null ? new BigDecimal("5.00") : preferredRadiusKm;
        this.onboardingCompleted = true;
    }

    @PrePersist
    void prePersist() {
        OffsetDateTime now = OffsetDateTime.now();
        this.createdAt = now;
        this.updatedAt = now;
    }

    @PreUpdate
    void preUpdate() {
        this.updatedAt = OffsetDateTime.now();
    }
}