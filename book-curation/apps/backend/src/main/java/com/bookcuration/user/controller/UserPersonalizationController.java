package com.taeo.bookcuration.user.controller;

import com.taeo.bookcuration.auth.service.AuthUser;
import com.taeo.bookcuration.user.dto.UserDtos.BookActionRequest;
import com.taeo.bookcuration.user.dto.UserDtos.BookActionResponse;
import com.taeo.bookcuration.user.dto.UserDtos.BookAvailabilityRequest;
import com.taeo.bookcuration.user.dto.UserDtos.BookAvailabilityResponse;
import com.taeo.bookcuration.user.dto.UserDtos.BookShelfRequest;
import com.taeo.bookcuration.user.dto.UserDtos.BookShelfResponse;
import com.taeo.bookcuration.user.dto.UserDtos.BookShelfReviewRequest;
import com.taeo.bookcuration.user.dto.UserDtos.BookShelfReviewResponse;
import com.taeo.bookcuration.user.dto.UserDtos.BookShelfSummaryResponse;
import com.taeo.bookcuration.user.dto.UserDtos.BookShelfStateResponse;
import com.taeo.bookcuration.user.dto.UserDtos.PreferredLibraryRequest;
import com.taeo.bookcuration.user.dto.UserDtos.PreferredLibraryResponse;
import com.taeo.bookcuration.user.dto.UserDtos.UserCharacterNicknameRequest;
import com.taeo.bookcuration.user.dto.UserDtos.UserCharacterResponse;
import com.taeo.bookcuration.user.dto.UserDtos.UserProfileCategoriesRequest;
import com.taeo.bookcuration.user.dto.UserDtos.UserProfileIdentityRequest;
import com.taeo.bookcuration.user.dto.UserDtos.UserProfilePreferredRadiusRequest;
import com.taeo.bookcuration.user.dto.UserDtos.UserProfileReadingPurposeRequest;
import com.taeo.bookcuration.user.dto.UserDtos.UserProfileRequest;
import com.taeo.bookcuration.user.dto.UserDtos.UserProfileResponse;
import com.taeo.bookcuration.user.service.UserPersonalizationService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
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
@RequestMapping("/api/users/me")
@RequiredArgsConstructor
public class UserPersonalizationController {

    private final UserPersonalizationService userPersonalizationService;

    @GetMapping("/profile")
    public UserProfileResponse getProfile(@AuthenticationPrincipal AuthUser authUser) {
        return userPersonalizationService.getProfile(authUser.id());
    }

    @PutMapping("/profile")
    public UserProfileResponse updateProfile(
            @AuthenticationPrincipal AuthUser authUser,
            @Valid @RequestBody UserProfileRequest request
    ) {
        // 수정 포인트: 기존 전체 저장 API는 온보딩/레거시 클라이언트 호환용으로 유지합니다.
        // 마이페이지 화면에서는 아래 섹션별 API를 호출해 불필요한 장르/키워드 재저장을 막습니다.
        return userPersonalizationService.updateProfile(authUser.id(), request);
    }

    @PatchMapping("/profile/identity")
    public UserProfileResponse updateProfileIdentity(
            @AuthenticationPrincipal AuthUser authUser,
            @Valid @RequestBody UserProfileIdentityRequest request
    ) {
        return userPersonalizationService.updateProfileIdentity(authUser.id(), request);
    }

    @PutMapping("/profile/categories")
    public UserProfileResponse updateProfileCategories(
            @AuthenticationPrincipal AuthUser authUser,
            @Valid @RequestBody UserProfileCategoriesRequest request
    ) {
        return userPersonalizationService.updateProfileCategories(authUser.id(), request);
    }

    @PatchMapping("/profile/reading-purpose")
    public UserProfileResponse updateProfileReadingPurpose(
            @AuthenticationPrincipal AuthUser authUser,
            @Valid @RequestBody UserProfileReadingPurposeRequest request
    ) {
        return userPersonalizationService.updateProfileReadingPurpose(authUser.id(), request);
    }

    @PatchMapping("/profile/preferred-radius")
    public UserProfileResponse updateProfilePreferredRadius(
            @AuthenticationPrincipal AuthUser authUser,
            @Valid @RequestBody UserProfilePreferredRadiusRequest request
    ) {
        return userPersonalizationService.updateProfilePreferredRadius(authUser.id(), request);
    }

    @GetMapping("/character")
    public UserCharacterResponse getCharacter(@AuthenticationPrincipal AuthUser authUser) {
        return userPersonalizationService.getCharacter(authUser.id());
    }

    @PutMapping("/character/nickname")
    public UserCharacterResponse updateCharacterNickname(
            @AuthenticationPrincipal AuthUser authUser,
            @Valid @RequestBody UserCharacterNicknameRequest request
    ) {
        return userPersonalizationService.updateCharacterNickname(authUser.id(), request);
    }

    @GetMapping("/preferred-libraries")
    public List<PreferredLibraryResponse> getPreferredLibraries(@AuthenticationPrincipal AuthUser authUser) {
        return userPersonalizationService.getPreferredLibraries(authUser.id());
    }

    @PostMapping("/preferred-libraries")
    @ResponseStatus(HttpStatus.CREATED)
    public PreferredLibraryResponse savePreferredLibrary(
            @AuthenticationPrincipal AuthUser authUser,
            @Valid @RequestBody PreferredLibraryRequest request
    ) {
        return userPersonalizationService.savePreferredLibrary(authUser.id(), request);
    }

    @DeleteMapping("/preferred-libraries/{libCode}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void deletePreferredLibrary(
            @AuthenticationPrincipal AuthUser authUser,
            @PathVariable String libCode
    ) {
        userPersonalizationService.deletePreferredLibrary(authUser.id(), libCode);
    }

    @PostMapping("/book-actions")
    @ResponseStatus(HttpStatus.CREATED)
    public BookActionResponse saveBookAction(
            @AuthenticationPrincipal AuthUser authUser,
            @Valid @RequestBody BookActionRequest request
    ) {
        return userPersonalizationService.saveBookAction(authUser.id(), request);
    }

    @GetMapping("/book-shelves")
    public List<BookShelfResponse> getBookShelves(
            @AuthenticationPrincipal AuthUser authUser,
            @RequestParam(required = false) String shelfType
    ) {
        return userPersonalizationService.getBookShelves(authUser.id(), shelfType);
    }

    @GetMapping("/book-shelves/summary")
    public BookShelfSummaryResponse getBookShelfSummary(@AuthenticationPrincipal AuthUser authUser) {
        return userPersonalizationService.getBookShelfSummary(authUser.id());
    }

    @GetMapping("/book-shelves/states")
    public List<BookShelfStateResponse> getBookShelfStates(
            @AuthenticationPrincipal AuthUser authUser,
            @RequestParam String isbn13s
    ) {
        // 수정 포인트: 채팅방 재진입 시 추천 도서 버튼의 기존 활성 상태를 ISBN 기준으로 복원합니다.
        return userPersonalizationService.getBookShelfStates(authUser.id(), isbn13s);
    }

    @PostMapping("/book-shelves")
    @ResponseStatus(HttpStatus.CREATED)
    public BookShelfResponse saveBookShelf(
            @AuthenticationPrincipal AuthUser authUser,
            @Valid @RequestBody BookShelfRequest request
    ) {
        return userPersonalizationService.saveBookShelf(authUser.id(), request);
    }

    @PostMapping("/book-shelves/{shelfId}/review")
    public BookShelfReviewResponse completeBookShelfReview(
            @AuthenticationPrincipal AuthUser authUser,
            @PathVariable Long shelfId,
            @Valid @RequestBody BookShelfReviewRequest request
    ) {
        return userPersonalizationService.completeBookShelfReview(authUser.id(), shelfId, request);
    }

    @DeleteMapping("/book-shelves/{shelfId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void deleteBookShelfById(
            @AuthenticationPrincipal AuthUser authUser,
            @PathVariable Long shelfId
    ) {
        userPersonalizationService.deleteBookShelfById(authUser.id(), shelfId);
    }

    @DeleteMapping("/book-shelves/by-isbn/{isbn13}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void deleteBookShelfByIsbn(
            @AuthenticationPrincipal AuthUser authUser,
            @PathVariable String isbn13,
            @RequestParam String shelfType
    ) {
        // 수정 포인트: 추천 카드에서 다시 누른 버튼을 취소할 수 있도록 ISBN 기준 삭제 API를 제공합니다.
        userPersonalizationService.deleteBookShelfByIsbn(authUser.id(), isbn13, shelfType);
    }

    @DeleteMapping("/book-shelves")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void deleteBookShelf(
            @AuthenticationPrincipal AuthUser authUser,
            @RequestParam Long bookId,
            @RequestParam String shelfType
    ) {
        userPersonalizationService.deleteBookShelf(authUser.id(), bookId, shelfType);
    }

    @PostMapping("/book-availability")
    public BookAvailabilityResponse checkBookAvailability(
            @AuthenticationPrincipal AuthUser authUser,
            @Valid @RequestBody BookAvailabilityRequest request
    ) {
        return userPersonalizationService.checkBookAvailability(authUser.id(), request);
    }
}