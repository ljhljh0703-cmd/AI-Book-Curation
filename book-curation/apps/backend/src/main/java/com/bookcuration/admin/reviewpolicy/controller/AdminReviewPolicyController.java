package com.taeo.bookcuration.admin.reviewpolicy.controller;

import com.taeo.bookcuration.admin.reviewpolicy.dto.AdminReviewPolicyDtos.ReviewPolicyResponse;
import com.taeo.bookcuration.admin.reviewpolicy.dto.AdminReviewPolicyDtos.ReviewPolicyUpdateRequest;
import com.taeo.bookcuration.review.service.ReviewPolicyService;
import com.taeo.bookcuration.review.service.ReviewPolicyService.ReviewPolicy;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/admin/review-policy")
@PreAuthorize("hasRole('ADMIN')")
@RequiredArgsConstructor
public class AdminReviewPolicyController {

    private final ReviewPolicyService reviewPolicyService;

    @GetMapping
    public ReviewPolicyResponse getReviewPolicy() {
        return toResponse(reviewPolicyService.getReviewPolicy());
    }

    @PutMapping
    public ReviewPolicyResponse updateReviewPolicy(@Valid @RequestBody ReviewPolicyUpdateRequest request) {
        ReviewPolicy policy = reviewPolicyService.updateReviewWaitMinutes(request.reviewWaitMinutes());
        return toResponse(policy);
    }

    private ReviewPolicyResponse toResponse(ReviewPolicy policy) {
        return new ReviewPolicyResponse(
                policy.reviewWaitMinutes(),
                policy.reviewWaitLabel(),
                policy.updatedAt()
        );
    }
}
