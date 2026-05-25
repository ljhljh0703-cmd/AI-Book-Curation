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
@Table(name = "user_book_shelves", schema = "book")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class UserBookShelfEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "user_id", nullable = false, columnDefinition = "uuid")
    private UUID userId;

    @Column(name = "book_id", nullable = false)
    private Long bookId;

    @Column(name = "shelf_type", nullable = false, length = 30)
    private String shelfType;

    private String note;

    @Column(name = "review_content")
    private String reviewContent;

    @Column(name = "review_rating", precision = 2, scale = 1)
    // 수정 포인트: 리뷰 평점을 0.5 단위로 저장하기 위해 numeric(2,1)에 매핑합니다.
    private BigDecimal reviewRating;

    @Column(name = "completed_at")
    private OffsetDateTime completedAt;

    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;

    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt;

    public static UserBookShelfEntity create(UUID userId, Long bookId, String shelfType, String note) {
        UserBookShelfEntity entity = new UserBookShelfEntity();
        entity.userId = userId;
        entity.bookId = bookId;
        entity.shelfType = shelfType;
        entity.note = note;
        return entity;
    }

    public void updateNote(String note) {
        this.note = note;
    }

    public void changeShelfType(String shelfType) {
        this.shelfType = shelfType;
    }

    public void completeReading(String reviewContent, BigDecimal reviewRating) {
        // 수정 포인트: 리뷰 작성 완료 시 읽는 중 상태를 읽은 책 상태로 전환합니다.
        this.shelfType = "READ";
        this.reviewContent = reviewContent;
        this.reviewRating = reviewRating;
        this.completedAt = OffsetDateTime.now();
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
