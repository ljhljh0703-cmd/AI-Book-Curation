package com.taeo.bookcuration.admin.monitoring.dto;

import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.List;

public final class AdminMonitoringDtos {

    private AdminMonitoringDtos() {
    }

    public record MonitoringResponse(
            String rangeType,
            LocalDate startDate,
            LocalDate endDate,
            List<MonitoringMetricResponse> metrics,
            OffsetDateTime generatedAt
    ) {
    }

    public record MonitoringMetricResponse(
            String key,
            String label,
            String description,
            long total,
            List<MonitoringSeriesPoint> series
    ) {
    }

    public record MonitoringSeriesPoint(
            LocalDate date,
            long count
    ) {
    }
}
