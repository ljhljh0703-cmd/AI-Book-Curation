package com.taeo.bookcuration.recommendation.profile.controller;

import com.taeo.bookcuration.recommendation.profile.service.UserPreferenceProfileBuildService;
import lombok.RequiredArgsConstructor;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;
import java.util.UUID;

@RestController
@RequestMapping("/api/admin/preference-profiles")
@PreAuthorize("hasRole('ADMIN')")
@RequiredArgsConstructor
public class AdminPreferenceProfileController {

    private final UserPreferenceProfileBuildService profileBuildService;

    @PostMapping("/users/{userId}/rebuild")
    public Map<String, Object> rebuildUserProfile(@PathVariable UUID userId) {
        return profileBuildService.rebuildUserProfile(userId);
    }

    @PostMapping("/reviews/backfill")
    public Map<String, Object> backfillReviewSignals(@RequestParam(defaultValue = "20") int limit) {
        return profileBuildService.backfillReviewSignals(limit);
    }

    @PostMapping("/reviews/retry-failed")
    public Map<String, Object> retryFailedReviewSignals(@RequestParam(defaultValue = "20") int limit) {
        return profileBuildService.retryFailedReviewSignals(limit);
    }
}
