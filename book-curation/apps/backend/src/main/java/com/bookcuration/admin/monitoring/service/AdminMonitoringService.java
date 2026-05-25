package com.taeo.bookcuration.admin.monitoring.service;

import com.taeo.bookcuration.admin.monitoring.dto.AdminMonitoringDtos.MonitoringMetricResponse;
import com.taeo.bookcuration.admin.monitoring.dto.AdminMonitoringDtos.MonitoringResponse;
import com.taeo.bookcuration.admin.monitoring.dto.AdminMonitoringDtos.MonitoringSeriesPoint;
import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.sql.Date;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

@Service
@RequiredArgsConstructor
public class AdminMonitoringService {

    private static final ZoneId SERVICE_ZONE = ZoneId.of("Asia/Seoul");
    private static final int MAX_CUSTOM_RANGE_DAYS = 366;

    private final JdbcTemplate jdbcTemplate;

    @Transactional(readOnly = true)
    public MonitoringResponse getMonitoring(String rawRangeType, LocalDate requestStartDate, LocalDate requestEndDate) {
        DateRange dateRange = resolveDateRange(rawRangeType, requestStartDate, requestEndDate);

        List<MonitoringMetricResponse> metrics = List.of(
                metric(
                        "SIGNUPS",
                        "회원가입 수",
                        "해당 일자에 가입한 일반 회원 수입니다.",
                        signupSeries(dateRange.startDate(), dateRange.endDate())
                ),
                metric(
                        "ACTIVE_USERS",
                        "접속회원 수",
                        "로그인 이벤트 기준 일자별 순 접속 회원 수입니다.",
                        activeUserSeries(dateRange.startDate(), dateRange.endDate())
                ),
                metric(
                        "CHAT_MESSAGES",
                        "채팅 발신 수",
                        "사용자가 발신한 채팅 메시지 수입니다.",
                        chatMessageSeries(dateRange.startDate(), dateRange.endDate())
                ),
                metric(
                        "CHAT_SESSIONS",
                        "채팅방 생성 수",
                        "생성된 채팅방 수입니다.",
                        chatSessionSeries(dateRange.startDate(), dateRange.endDate())
                ),
                metric(
                        "LIKES",
                        "좋아요 수",
                        "현재 유지 중인 관심 도서 수입니다. 취소된 좋아요는 집계에서 제외됩니다.",
                        shelfSeries(dateRange.startDate(), dateRange.endDate(), "INTERESTED")
                ),
                metric(
                        "DISLIKES",
                        "싫어요 수",
                        "현재 유지 중인 비관심 도서 수입니다. 취소된 싫어요는 집계에서 제외됩니다.",
                        shelfSeries(dateRange.startDate(), dateRange.endDate(), "NOT_INTERESTED")
                ),
                metric(
                        "READING_BUTTONS",
                        "책읽기 버튼 수",
                        "현재 읽는 중 상태로 유지 중인 도서 수입니다. 취소되거나 읽은 책으로 전환된 항목은 제외됩니다.",
                        shelfSeries(dateRange.startDate(), dateRange.endDate(), "READING")
                )
        );

        return new MonitoringResponse(
                dateRange.rangeType(),
                dateRange.startDate(),
                dateRange.endDate(),
                metrics,
                OffsetDateTime.now(SERVICE_ZONE)
        );
    }

    private MonitoringMetricResponse metric(
            String key,
            String label,
            String description,
            List<MonitoringSeriesPoint> series
    ) {
        long total = series.stream().mapToLong(MonitoringSeriesPoint::count).sum();
        return new MonitoringMetricResponse(key, label, description, total, series);
    }

    private List<MonitoringSeriesPoint> signupSeries(LocalDate startDate, LocalDate endDate) {
        return dailySeries("""
                SELECT (created_at AT TIME ZONE 'Asia/Seoul')::date AS metric_date,
                       COUNT(*)::bigint AS metric_count
                FROM book.users
                WHERE role = 'USER'
                  AND created_at >= ?
                  AND created_at < ?
                GROUP BY metric_date
                ORDER BY metric_date
                """, startDate, endDate);
    }

    private List<MonitoringSeriesPoint> activeUserSeries(LocalDate startDate, LocalDate endDate) {
        if (!tableExists("user_login_events")) {
            return emptyDailySeries(startDate, endDate);
        }

        return dailySeries("""
                SELECT (event.login_at AT TIME ZONE 'Asia/Seoul')::date AS metric_date,
                       COUNT(DISTINCT event.user_id)::bigint AS metric_count
                FROM book.user_login_events event
                JOIN book.users users ON users.id = event.user_id
                WHERE users.role = 'USER'
                  AND event.login_at >= ?
                  AND event.login_at < ?
                GROUP BY metric_date
                ORDER BY metric_date
                """, startDate, endDate);
    }

    private List<MonitoringSeriesPoint> chatMessageSeries(LocalDate startDate, LocalDate endDate) {
        return dailySeries("""
                SELECT (created_at AT TIME ZONE 'Asia/Seoul')::date AS metric_date,
                       COUNT(*)::bigint AS metric_count
                FROM book.chat_messages
                WHERE role = 'USER'
                  AND created_at >= ?
                  AND created_at < ?
                GROUP BY metric_date
                ORDER BY metric_date
                """, startDate, endDate);
    }

    private List<MonitoringSeriesPoint> chatSessionSeries(LocalDate startDate, LocalDate endDate) {
        return dailySeries("""
                SELECT (created_at AT TIME ZONE 'Asia/Seoul')::date AS metric_date,
                       COUNT(*)::bigint AS metric_count
                FROM book.chat_sessions
                WHERE created_at >= ?
                  AND created_at < ?
                GROUP BY metric_date
                ORDER BY metric_date
                """, startDate, endDate);
    }

    private List<MonitoringSeriesPoint> shelfSeries(LocalDate startDate, LocalDate endDate, String shelfType) {
        return dailySeries("""
                SELECT (created_at AT TIME ZONE 'Asia/Seoul')::date AS metric_date,
                       COUNT(*)::bigint AS metric_count
                FROM book.user_book_shelves
                WHERE shelf_type = ?
                  AND created_at >= ?
                  AND created_at < ?
                GROUP BY metric_date
                ORDER BY metric_date
                """, startDate, endDate, shelfType);
    }

    private List<MonitoringSeriesPoint> dailySeries(
            String sql,
            LocalDate startDate,
            LocalDate endDate,
            Object... leadingParameters
    ) {
        Map<LocalDate, Long> counts = new LinkedHashMap<>();
        for (LocalDate date = startDate; !date.isAfter(endDate); date = date.plusDays(1)) {
            counts.put(date, 0L);
        }

        List<Object> parameters = new ArrayList<>();
        parameters.addAll(List.of(leadingParameters));
        parameters.add(startDate.atStartOfDay(SERVICE_ZONE).toOffsetDateTime());
        parameters.add(endDate.plusDays(1).atStartOfDay(SERVICE_ZONE).toOffsetDateTime());

        jdbcTemplate.query(sql, rs -> {
            LocalDate metricDate = toLocalDate(rs.getObject("metric_date"));
            if (metricDate != null && counts.containsKey(metricDate)) {
                counts.put(metricDate, rs.getLong("metric_count"));
            }
        }, parameters.toArray());

        return counts.entrySet().stream()
                .map(entry -> new MonitoringSeriesPoint(entry.getKey(), entry.getValue()))
                .toList();
    }

    private List<MonitoringSeriesPoint> emptyDailySeries(LocalDate startDate, LocalDate endDate) {
        List<MonitoringSeriesPoint> series = new ArrayList<>();
        for (LocalDate date = startDate; !date.isAfter(endDate); date = date.plusDays(1)) {
            series.add(new MonitoringSeriesPoint(date, 0));
        }
        return series;
    }

    private boolean tableExists(String tableName) {
        Boolean exists = jdbcTemplate.queryForObject(
                "SELECT to_regclass(?) IS NOT NULL",
                Boolean.class,
                "book." + tableName
        );
        return Boolean.TRUE.equals(exists);
    }

    private DateRange resolveDateRange(String rawRangeType, LocalDate requestStartDate, LocalDate requestEndDate) {
        String rangeType = rawRangeType == null || rawRangeType.isBlank()
                ? "DAILY"
                : rawRangeType.trim().toUpperCase(Locale.ROOT);

        LocalDate today = LocalDate.now(SERVICE_ZONE);
        LocalDate startDate;
        LocalDate endDate;

        switch (rangeType) {
            case "DAILY" -> {
                startDate = today;
                endDate = today;
            }
            case "WEEKLY" -> {
                startDate = today.minusDays(6);
                endDate = today;
            }
            case "MONTHLY" -> {
                startDate = today.minusDays(29);
                endDate = today;
            }
            case "CUSTOM" -> {
                if (requestStartDate == null || requestEndDate == null) {
                    throw new IllegalArgumentException("기간별 검색은 시작일과 종료일을 모두 입력해 주세요.");
                }
                startDate = requestStartDate;
                endDate = requestEndDate;
            }
            default -> throw new IllegalArgumentException("지원하지 않는 모니터링 기간입니다.");
        }

        if (startDate.isAfter(endDate)) {
            throw new IllegalArgumentException("시작일은 종료일보다 늦을 수 없습니다.");
        }

        if (startDate.plusDays(MAX_CUSTOM_RANGE_DAYS - 1L).isBefore(endDate)) {
            throw new IllegalArgumentException("모니터링 조회 기간은 최대 366일까지 가능합니다.");
        }

        return new DateRange(rangeType, startDate, endDate);
    }

    private LocalDate toLocalDate(Object value) {
        if (value instanceof LocalDate localDate) {
            return localDate;
        }
        if (value instanceof Date date) {
            return date.toLocalDate();
        }
        if (value != null) {
            return LocalDate.parse(value.toString());
        }
        return null;
    }

    private record DateRange(
            String rangeType,
            LocalDate startDate,
            LocalDate endDate
    ) {
    }
}
