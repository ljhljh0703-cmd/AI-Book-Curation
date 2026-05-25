package com.taeo.bookcuration.recommendation.event.controller;

import com.taeo.bookcuration.auth.service.AuthUser;
import com.taeo.bookcuration.recommendation.event.dto.RecommendationEventDtos.RecommendationEventRequest;
import com.taeo.bookcuration.recommendation.event.dto.RecommendationEventDtos.RecommendationEventResponse;
import com.taeo.bookcuration.recommendation.event.service.RecommendationEventLoggingService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/recommendation-events")
@RequiredArgsConstructor
public class RecommendationEventController {

    private final RecommendationEventLoggingService recommendationEventLoggingService;

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public RecommendationEventResponse logEvent(
            @AuthenticationPrincipal AuthUser authUser,
            @Valid @RequestBody RecommendationEventRequest request
    ) {
        // 수정 포인트: 추천 카드 클릭/상세보기 이벤트를 알라딘 API 재호출 없이 프론트가 가진 후보 snapshot만으로 저장합니다.
        return recommendationEventLoggingService.logRecommendationEvent(authUser.id(), request);
    }
}
