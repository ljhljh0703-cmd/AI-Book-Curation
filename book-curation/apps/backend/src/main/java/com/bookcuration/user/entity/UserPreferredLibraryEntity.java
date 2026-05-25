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

import java.time.OffsetDateTime;
import java.util.UUID;

@Getter
@Entity
@Table(name = "user_preferred_libraries", schema = "book")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class UserPreferredLibraryEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "user_id", nullable = false, columnDefinition = "uuid")
    private UUID userId;

    @Column(name = "lib_code", nullable = false, length = 50)
    private String libCode;

    @Column(nullable = false)
    private int priority;

    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;

    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt;

    public static UserPreferredLibraryEntity create(UUID userId, String libCode, int priority) {
        UserPreferredLibraryEntity entity = new UserPreferredLibraryEntity();
        entity.userId = userId;
        entity.libCode = libCode;
        entity.priority = priority;
        return entity;
    }

    public void updatePriority(int priority) {
        this.priority = priority;
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
