package com.taeo.bookcuration.user.entity;

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

import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.UUID;

@Getter
@Entity
@Table(name = "user_interest_keywords", schema = "book")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class UserInterestKeywordEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "user_id", nullable = false, columnDefinition = "uuid")
    private UUID userId;

    @Column(nullable = false, length = 100)
    private String keyword;

    @Column(nullable = false, precision = 5, scale = 2)
    private BigDecimal weight;

    @Column(nullable = false, length = 30)
    private String source;

    @Column(name = "last_observed_at", nullable = false)
    private OffsetDateTime lastObservedAt;

    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;

    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt;

    public static UserInterestKeywordEntity create(UUID userId, String keyword, String source) {
        UserInterestKeywordEntity entity = new UserInterestKeywordEntity();
        entity.userId = userId;
        entity.keyword = keyword.trim();
        entity.weight = BigDecimal.ONE;
        entity.source = source;
        entity.lastObservedAt = OffsetDateTime.now();
        return entity;
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
