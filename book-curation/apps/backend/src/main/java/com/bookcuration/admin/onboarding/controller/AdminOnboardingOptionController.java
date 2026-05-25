package com.taeo.bookcuration.admin.onboarding.controller;

import com.taeo.bookcuration.admin.onboarding.dto.AdminOnboardingOptionDtos.OnboardingOptionGroup;
import com.taeo.bookcuration.admin.onboarding.dto.AdminOnboardingOptionDtos.OnboardingOptionReorderRequest;
import com.taeo.bookcuration.admin.onboarding.dto.AdminOnboardingOptionDtos.OnboardingOptionRequest;
import com.taeo.bookcuration.admin.onboarding.dto.AdminOnboardingOptionDtos.OnboardingOptionResponse;
import com.taeo.bookcuration.admin.onboarding.service.AdminOnboardingOptionService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/admin/onboarding-options")
@RequiredArgsConstructor
@PreAuthorize("hasRole('ADMIN')")
public class AdminOnboardingOptionController {

    private final AdminOnboardingOptionService adminOnboardingOptionService;

    @GetMapping
    public List<OnboardingOptionResponse> getOptions(@RequestParam OnboardingOptionGroup optionGroup) {
        // 수정 포인트: 관리자 화면 탭별로 독자 유형/선호 카테고리 선택지를 조회합니다.
        return adminOnboardingOptionService.getOptions(optionGroup);
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public OnboardingOptionResponse createOption(@Valid @RequestBody OnboardingOptionRequest request) {
        return adminOnboardingOptionService.createOption(request);
    }

    @PutMapping("/{id}")
    public OnboardingOptionResponse updateOption(
            @PathVariable Long id,
            @Valid @RequestBody OnboardingOptionRequest request
    ) {
        return adminOnboardingOptionService.updateOption(id, request);
    }

    @PatchMapping("/display-order")
    public List<OnboardingOptionResponse> reorderOptions(@Valid @RequestBody OnboardingOptionReorderRequest request) {
        // 수정 포인트: 정렬은 숫자 직접 입력 대신 드래그앤드랍 결과를 한 번에 저장합니다.
        return adminOnboardingOptionService.reorderOptions(request);
    }

    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void deleteOption(@PathVariable Long id) {
        adminOnboardingOptionService.deleteOption(id);
    }
}
