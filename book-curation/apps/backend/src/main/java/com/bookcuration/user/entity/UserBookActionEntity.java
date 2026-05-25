package com.taeo.bookcuration.user.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.Map;
import java.util.UUID;

@Getter
@Entity
@Table(name = "user_book_actions", schema = "book")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class UserBookActionEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "user_id", nullable = false, columnDefinition = "uuid")
    private UUID userId;

    @Column(name = "book_id", nullable = false)
    private Long bookId;

    @Column(name = "action_type", nullable = false, length = 30)
    private String actionType;

    // 수정 포인트: 리뷰 평점이 0.5 단위까지 저장될 수 있도록 정수 Short 대신 BigDecimal을 사용합니다.
    private BigDecimal rating;

    @Column(length = 30)
    private String source;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private Map<String, Object> metadata;

    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;

    public static UserBookActionEntity create(
            UUID userId,
            Long bookId,
            String actionType,
            BigDecimal rating,
            String source,
            Map<String, Object> metadata
    ) {
        UserBookActionEntity entity = new UserBookActionEntity();
        entity.userId = userId;
        entity.bookId = bookId;
        entity.actionType = actionType;
        entity.rating = rating;
        entity.source = source;
        entity.metadata = metadata;
        return entity;
    }

    @PrePersist
    void prePersist() {
        this.createdAt = OffsetDateTime.now();
    }
}
