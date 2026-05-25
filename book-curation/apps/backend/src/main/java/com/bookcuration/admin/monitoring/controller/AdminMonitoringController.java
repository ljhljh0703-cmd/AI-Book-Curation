package com.taeo.bookcuration.admin.monitoring.controller;

import com.taeo.bookcuration.admin.monitoring.dto.AdminMonitoringDtos.MonitoringResponse;
import com.taeo.bookcuration.admin.monitoring.service.AdminMonitoringService;
import lombok.RequiredArgsConstructor;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDate;

@RestController
@RequestMapping("/api/admin/monitoring")
@PreAuthorize("hasRole('ADMIN')")
@RequiredArgsConstructor
public class AdminMonitoringController {

    private final AdminMonitoringService adminMonitoringService;

    @GetMapping
    public MonitoringResponse getMonitoring(
            @RequestParam(defaultValue = "DAILY") String rangeType,
            @RequestParam(required = false) LocalDate startDate,
            @RequestParam(required = false) LocalDate endDate
    ) {
        // 수정 포인트: 관리자 모니터링은 사용자별 상세가 아니라 서비스 전체 일자별 집계만 반환합니다.
        return adminMonitoringService.getMonitoring(rangeType, startDate, endDate);
    }
}
