package com.taeo.bookcuration.review.service;

import lombok.RequiredArgsConstructor;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.List;

@Service
@RequiredArgsConstructor
public class ReviewPolicyService {

    private static final String REVIEW_WAIT_MINUTES_KEY = "REVIEW_WAIT_MINUTES";
    private static final String REVIEW_WAIT_MINUTES_DESCRIPTION = "읽는 중 도서 등록 후 리뷰 작성이 가능해지는 대기시간(분)";
    private static final int DEFAULT_REVIEW_WAIT_MINUTES = 60 * 24 * 3;
    private static final int MAX_REVIEW_WAIT_MINUTES = 60 * 24 * 30;

    private final JdbcTemplate jdbcTemplate;

    @Transactional(readOnly = true)
    public ReviewPolicy getReviewPolicy() {
        if (!serviceSettingsTableExists()) {
            return defaultPolicy();
        }

        List<ReviewPolicy> rows = jdbcTemplate.query(
                """
                SELECT setting_value, updated_at
                FROM book.service_settings
                WHERE setting_key = ?
                """,
                (rs, rowNum) -> {
                    int minutes = parseReviewWaitMinutes(rs.getString("setting_value"));
                    OffsetDateTime updatedAt = rs.getObject("updated_at", OffsetDateTime.class);
                    return toPolicy(minutes, updatedAt);
                },
                REVIEW_WAIT_MINUTES_KEY
        );

        return rows.stream().findFirst().orElseGet(this::defaultPolicy);
    }

    @Transactional
    public ReviewPolicy updateReviewWaitMinutes(int reviewWaitMinutes) {
        validateReviewWaitMinutes(reviewWaitMinutes);
        if (!serviceSettingsTableExists()) {
            throw new IllegalStateException("book.service_settings 테이블이 없습니다. docs/sql/31-service-review-policy.sql을 먼저 실행해 주세요.");
        }

        return jdbcTemplate.queryForObject(
                """
                INSERT INTO book.service_settings (setting_key, setting_value, description)
                VALUES (?, ?, ?)
                ON CONFLICT (setting_key)
                DO UPDATE SET
                    setting_value = EXCLUDED.setting_value,
                    description = EXCLUDED.description,
                    updated_at = NOW()
                RETURNING setting_value, updated_at
                """,
                (rs, rowNum) -> toPolicy(
                        parseReviewWaitMinutes(rs.getString("setting_value")),
                        rs.getObject("updated_at", OffsetDateTime.class)
                ),
                REVIEW_WAIT_MINUTES_KEY,
                String.valueOf(reviewWaitMinutes),
                REVIEW_WAIT_MINUTES_DESCRIPTION
        );
    }

    public static String formatReviewWaitLabel(int reviewWaitMinutes) {
        if (reviewWaitMinutes <= 0) {
            return "즉시";
        }

        int days = reviewWaitMinutes / (60 * 24);
        int remainderAfterDays = reviewWaitMinutes % (60 * 24);
        int hours = remainderAfterDays / 60;
        int minutes = remainderAfterDays % 60;

        StringBuilder label = new StringBuilder();
        if (days > 0) {
            label.append(days).append("일");
        }
        if (hours > 0) {
            if (label.length() > 0) {
                label.append(" ");
            }
            label.append(hours).append("시간");
        }
        if (minutes > 0) {
            if (label.length() > 0) {
                label.append(" ");
            }
            label.append(minutes).append("분");
        }

        return label.toString();
    }

    private ReviewPolicy defaultPolicy() {
        return toPolicy(DEFAULT_REVIEW_WAIT_MINUTES, null);
    }

    private ReviewPolicy toPolicy(int reviewWaitMinutes, OffsetDateTime updatedAt) {
        int safeMinutes = normalizeReviewWaitMinutes(reviewWaitMinutes);
        return new ReviewPolicy(
                safeMinutes,
                formatReviewWaitLabel(safeMinutes),
                updatedAt
        );
    }

    private int parseReviewWaitMinutes(String value) {
        try {
            return normalizeReviewWaitMinutes(Integer.parseInt(value));
        } catch (RuntimeException ex) {
            return DEFAULT_REVIEW_WAIT_MINUTES;
        }
    }

    private int normalizeReviewWaitMinutes(int reviewWaitMinutes) {
        if (reviewWaitMinutes < 0) {
            return DEFAULT_REVIEW_WAIT_MINUTES;
        }
        return Math.min(reviewWaitMinutes, MAX_REVIEW_WAIT_MINUTES);
    }

    private void validateReviewWaitMinutes(int reviewWaitMinutes) {
        if (reviewWaitMinutes < 0 || reviewWaitMinutes > MAX_REVIEW_WAIT_MINUTES) {
            throw new IllegalArgumentException("리뷰 작성 대기시간은 0분 이상 43200분(30일) 이하로 입력해 주세요.");
        }
    }

    private boolean serviceSettingsTableExists() {
        try {
            Boolean exists = jdbcTemplate.queryForObject(
                    "SELECT to_regclass(?) IS NOT NULL",
                    Boolean.class,
                    "book.service_settings"
            );
            return Boolean.TRUE.equals(exists);
        } catch (DataAccessException ex) {
            return false;
        }
    }

    public record ReviewPolicy(
            int reviewWaitMinutes,
            String reviewWaitLabel,
            OffsetDateTime updatedAt
    ) {
        public Duration waitDuration() {
            return Duration.ofMinutes(reviewWaitMinutes);
        }
    }
}
