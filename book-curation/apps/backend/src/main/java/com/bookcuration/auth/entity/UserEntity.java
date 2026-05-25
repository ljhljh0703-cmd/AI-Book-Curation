package com.taeo.bookcuration.auth.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.OffsetDateTime;
import java.util.UUID;

@Getter
@Entity
@Table(name = "users", schema = "book")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class UserEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    @Column(columnDefinition = "uuid")
    private UUID id;

    // 수정 포인트: 자체 로그인/소셜 로그인을 모두 지원하기 위해 users에는 대표 이메일만 둡니다.
    @Column(name = "primary_email", length = 320)
    private String primaryEmail;

    @Column(nullable = false, length = 50)
    private String nickname;

    // 수정 포인트: 관리자 API 권한 제어를 위해 role은 users에 유지합니다.
    @Column(nullable = false, length = 20)
    private String role;

    @Column(nullable = false, length = 20)
    private String status;

    @Column(name = "last_login_at")
    private OffsetDateTime lastLoginAt;

    @Column(name = "dormant_at")
    private OffsetDateTime dormantAt;

    @Column(name = "dormant_released_at")
    private OffsetDateTime dormantReleasedAt;

    @Column(name = "withdrawn_at")
    private OffsetDateTime withdrawnAt;

    @Column(name = "withdrawn_reason_code", length = 50)
    private String withdrawnReasonCode;

    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;

    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt;

    public static UserEntity createLocalUser(String email, String nickname) {
        UserEntity user = new UserEntity();
        user.primaryEmail = normalizeEmail(email);
        user.nickname = nickname;
        user.role = "USER";
        user.status = "ACTIVE";
        return user;
    }

    public static UserEntity createSocialUser(String email, String nickname) {
        UserEntity user = new UserEntity();
        user.primaryEmail = normalizeEmail(email);
        user.nickname = nickname;
        user.role = "USER";
        user.status = "ACTIVE";
        return user;
    }

    public void changeNickname(String nickname) {
        // 수정 포인트: 이메일은 로그인 식별값으로 유지하고, 화면 표시용 닉네임만 마이페이지에서 변경할 수 있게 합니다.
        this.nickname = nickname;
    }

    public void markLoggedIn() {
        this.lastLoginAt = OffsetDateTime.now();
        if ("INACTIVE".equals(this.status)) {
            this.status = "ACTIVE";
            this.dormantReleasedAt = OffsetDateTime.now();
        }
    }

    public void markDormant() {
        if (!"ACTIVE".equals(this.status)) {
            return;
        }
        this.status = "INACTIVE";
        this.dormantAt = OffsetDateTime.now();
    }

    public void releaseDormant() {
        this.status = "ACTIVE";
        this.lastLoginAt = OffsetDateTime.now();
        this.dormantReleasedAt = OffsetDateTime.now();
    }

    public void markWithdrawn(String reasonCode) {
        this.status = "DELETED";
        // 수정 포인트: 탈퇴 회원은 재가입을 막지 않도록 대표 이메일을 제거합니다.
        // 연관 인증/소셜/프로필 데이터 삭제는 AuthService.withdraw() 트랜잭션에서 함께 처리합니다.
        this.primaryEmail = null;
        this.withdrawnAt = OffsetDateTime.now();
        this.withdrawnReasonCode = reasonCode;
    }

    private static String normalizeEmail(String email) {
        if (email == null || email.isBlank()) {
            return null;
        }
        return email.trim().toLowerCase();
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
