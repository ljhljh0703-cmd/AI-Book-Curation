package com.taeo.bookcuration.recommendation.audience;

import lombok.RequiredArgsConstructor;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.util.LinkedHashMap;
import java.util.Map;

@Service
@RequiredArgsConstructor
public class BookAudienceLabelQueryService {

    private final JdbcTemplate jdbcTemplate;

    @Transactional(readOnly = true)
    public Map<String, Map<String, Object>> findReadyAudienceLabelMap() {
        if (!hasAudienceLabelColumns()) {
            return Map.of();
        }

        Map<String, Map<String, Object>> labels = new LinkedHashMap<>();
        jdbcTemplate.query(
                """
                SELECT isbn13,
                       audience_group,
                       audience_min_age,
                       audience_max_age,
                       difficulty_level,
                       audience_label_confidence,
                       audience_label_reason,
                       audience_labeled_at
                FROM book.books
                WHERE audience_label_status = 'READY'
                  AND audience_group IS NOT NULL
                  AND isbn13 IS NOT NULL
                """,
                rs -> {
                    String isbn13 = rs.getString("isbn13");
                    String audienceGroup = rs.getString("audience_group");
                    if (isbn13 == null || isbn13.isBlank() || audienceGroup == null || audienceGroup.isBlank()) {
                        return;
                    }
                    Map<String, Object> profile = new LinkedHashMap<>();
                    profile.put("target_age_group", audienceGroup);
                    profile.put("audience_group", audienceGroup);
                    profile.put("audience_min_age", (Integer) rs.getObject("audience_min_age"));
                    profile.put("audience_max_age", (Integer) rs.getObject("audience_max_age"));
                    profile.put("difficulty_level", rs.getString("difficulty_level"));
                    BigDecimal confidence = rs.getBigDecimal("audience_label_confidence");
                    profile.put("confidence", confidence == null ? null : confidence.doubleValue());
                    profile.put("reason", rs.getString("audience_label_reason"));
                    profile.put("source", "POSTGRES");
                    labels.put(isbn13.trim(), profile);
                }
        );
        return labels;
    }

    private boolean hasAudienceLabelColumns() {
        try {
            Boolean exists = jdbcTemplate.queryForObject(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_schema = 'book'
                          AND table_name = 'books'
                          AND column_name = 'audience_label_status'
                    )
                    """,
                    Boolean.class
            );
            return Boolean.TRUE.equals(exists);
        } catch (DataAccessException ex) {
            return false;
        }
    }
}
