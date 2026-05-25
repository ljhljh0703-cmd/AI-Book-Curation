package com.taeo.bookcuration.auth.entity;

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

import java.time.OffsetDateTime;
import java.util.UUID;

@Getter
@Entity
@Table(name = "user_credentials", schema = "book")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class UserCredentialEntity {

    @Id
    @Column(name = "user_id", columnDefinition = "uuid")
    private UUID userId;

    @OneToOne(fetch = FetchType.EAGER, optional = false)
    @MapsId
    @JoinColumn(name = "user_id", nullable = false)
    private UserEntity user;

    @Column(nullable = false, length = 320)
    private String email;

    @Column(name = "password_hash", nullable = false, length = 255)
    private String passwordHash;

    @Column(name = "password_changed_at")
    private OffsetDateTime passwordChangedAt;

    @Column(name = "failed_login_count", nullable = false)
    private int failedLoginCount;

    @Column(name = "locked_until")
    private OffsetDateTime lockedUntil;

    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;

    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt;

    public static UserCredentialEntity create(UserEntity user, String email, String passwordHash) {
        UserCredentialEntity credential = new UserCredentialEntity();
        credential.user = user;
        credential.email = email.trim().toLowerCase();
        credential.passwordHash = passwordHash;
        credential.passwordChangedAt = OffsetDateTime.now();
        credential.failedLoginCount = 0;
        return credential;
    }

    public void increaseFailedLoginCount() {
        this.failedLoginCount++;
    }

    public void resetFailedLoginCount() {
        this.failedLoginCount = 0;
        this.lockedUntil = null;
    }

    public void changePassword(String passwordHash) {
        this.passwordHash = passwordHash;
        this.passwordChangedAt = OffsetDateTime.now();
        resetFailedLoginCount();
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
