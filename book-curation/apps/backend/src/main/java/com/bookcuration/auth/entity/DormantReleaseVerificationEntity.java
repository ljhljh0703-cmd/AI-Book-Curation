package com.taeo.bookcuration.auth.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.OffsetDateTime;

@Getter
@Entity
@Table(name = "dormant_release_verifications", schema = "book")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class DormantReleaseVerificationEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false)
    private UserEntity user;

    @Column(nullable = false, length = 320)
    private String email;

    @Column(name = "code_hash", nullable = false, length = 255)
    private String codeHash;

    @Column(name = "expires_at", nullable = false)
    private OffsetDateTime expiresAt;

    @Column(name = "consumed_at")
    private OffsetDateTime consumedAt;

    @Column(name = "attempt_count", nullable = false)
    private int attemptCount;

    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;

    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt;

    public static DormantReleaseVerificationEntity create(
            UserEntity user,
            String email,
            String codeHash,
            OffsetDateTime expiresAt
    ) {
        DormantReleaseVerificationEntity verification = new DormantReleaseVerificationEntity();
        verification.user = user;
        verification.email = email.trim().toLowerCase();
        verification.codeHash = codeHash;
        verification.expiresAt = expiresAt;
        verification.attemptCount = 0;
        return verification;
    }

    public boolean isExpired() {
        return expiresAt != null && expiresAt.isBefore(OffsetDateTime.now());
    }

    public void increaseAttemptCount() {
        this.attemptCount++;
    }

    public boolean isMaxAttemptsReached(int maxAttempts) {
        return this.attemptCount >= maxAttempts;
    }

    public void consume() {
        this.consumedAt = OffsetDateTime.now();
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
