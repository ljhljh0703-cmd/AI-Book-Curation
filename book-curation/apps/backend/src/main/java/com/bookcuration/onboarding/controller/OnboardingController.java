package com.taeo.bookcuration.onboarding.controller;

import com.taeo.bookcuration.auth.dto.AuthDtos.MeResponse;
import com.taeo.bookcuration.auth.service.AuthService;
import com.taeo.bookcuration.auth.service.AuthUser;
import com.taeo.bookcuration.onboarding.dto.AladinBookDtos.AladinBookSearchResponse;
import com.taeo.bookcuration.onboarding.dto.OnboardingDtos.OnboardingOptionResponse;
import com.taeo.bookcuration.onboarding.dto.OnboardingDtos.OnboardingSubmitRequest;
import com.taeo.bookcuration.onboarding.dto.OnboardingDtos.OnboardingSubmitResponse;
import com.taeo.bookcuration.onboarding.service.AladinBookSearchService;
import com.taeo.bookcuration.onboarding.service.OnboardingService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/onboarding")
@RequiredArgsConstructor
public class OnboardingController {

    private final OnboardingService onboardingService;
    private final AuthService authService;
    private final AladinBookSearchService aladinBookSearchService;

    @GetMapping("/options")
    public List<OnboardingOptionResponse> getOptions(@RequestParam(required = false) String optionGroup) {
        // 수정 포인트: 프론트 온보딩 화면은 관리자 API가 아니라 사용자용 active 옵션 조회 API만 사용합니다.
        return onboardingService.getActiveOptions(optionGroup);
    }


    @GetMapping("/books/search")
    public AladinBookSearchResponse searchBooks(
            @RequestParam String keyword,
            @RequestParam(required = false, defaultValue = "10") Integer limit,
            @RequestParam(required = false, defaultValue = "1") Integer start
    ) {
        // 수정 포인트: 온보딩 프론트가 TTBKey를 직접 보관하지 않도록 backend에서 알라딘 검색 API를 호출합니다.
        return aladinBookSearchService.search(keyword, limit, start);
    }

    @PostMapping("/complete")
    public OnboardingSubmitResponse complete(
            @AuthenticationPrincipal AuthUser authUser,
            @Valid @RequestBody OnboardingSubmitRequest request
    ) {
        return onboardingService.complete(authUser.id(), request);
    }

    @PostMapping("/skip")
    public MeResponse skip(@AuthenticationPrincipal AuthUser authUser) {
        onboardingService.skip(authUser.id());
        return authService.toMeResponse(authUser);
    }
}
