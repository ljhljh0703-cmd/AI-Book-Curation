package com.taeo.bookcuration.auth.service;

import com.taeo.bookcuration.auth.repository.UserRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.time.OffsetDateTime;

@Slf4j
@Component
@RequiredArgsConstructor
public class DormantAccountScheduler {

    private final UserRepository userRepository;

    @Value("${app.auth.dormant.days:180}")
    private long dormantDays;

    @Scheduled(cron = "${app.auth.dormant.cron:0 0 3 * * *}", zone = "${APP_TZ:Asia/Seoul}")
    @Transactional
    public void markDormantAccounts() {
        OffsetDateTime threshold = OffsetDateTime.now().minusDays(dormantDays);
        int updatedCount = userRepository.markDormantUsers(threshold);
        if (updatedCount > 0) {
            log.info("Dormant account scheduler updated {} user(s). threshold={}", updatedCount, threshold);
        } else {
            log.debug("Dormant account scheduler found no eligible users. threshold={}", threshold);
        }
    }
}
