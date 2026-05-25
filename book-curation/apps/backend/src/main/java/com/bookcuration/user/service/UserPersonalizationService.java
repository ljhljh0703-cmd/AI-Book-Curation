package com.taeo.bookcuration.user.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.taeo.bookcuration.admin.character.entity.CharacterDefinitionEntity;
import com.taeo.bookcuration.admin.character.repository.CharacterDefinitionRepository;
import com.taeo.bookcuration.admin.onboarding.repository.OnboardingOptionRepository;
import com.taeo.bookcuration.auth.entity.UserEntity;
import com.taeo.bookcuration.auth.repository.UserRepository;
import com.taeo.bookcuration.library.dto.LibraryDtos.LibraryPageResponse;
import com.taeo.bookcuration.library.dto.LibraryDtos.NearbyLibraryResponse;
import com.taeo.bookcuration.library.repository.LibraryJdbcRepository;
import com.taeo.bookcuration.library.service.BookAvailabilityClient;
import com.taeo.bookcuration.recommendation.event.dto.RecommendationEventDtos.UserBehaviorEventType;
import com.taeo.bookcuration.recommendation.event.service.RecommendationEventLoggingService;
import com.taeo.bookcuration.recommendation.profile.service.UserPreferenceProfileBuildService;
import com.taeo.bookcuration.review.service.ReviewPolicyService;
import com.taeo.bookcuration.review.service.ReviewPolicyService.ReviewPolicy;
import com.taeo.bookcuration.user.dto.UserDtos.BookActionRequest;
import com.taeo.bookcuration.user.dto.UserDtos.BookActionResponse;
import com.taeo.bookcuration.user.dto.UserDtos.BookAvailabilityLibraryResult;
import com.taeo.bookcuration.user.dto.UserDtos.BookAvailabilityRequest;
import com.taeo.bookcuration.user.dto.UserDtos.BookAvailabilityResponse;
import com.taeo.bookcuration.user.dto.UserDtos.BookShelfRequest;
import com.taeo.bookcuration.user.dto.UserDtos.BookShelfResponse;
import com.taeo.bookcuration.user.dto.UserDtos.BookShelfReviewRequest;
import com.taeo.bookcuration.user.dto.UserDtos.BookShelfReviewResponse;
import com.taeo.bookcuration.user.dto.UserDtos.CharacterLevelUpEventResponse;
import com.taeo.bookcuration.user.dto.UserDtos.BookShelfSummaryResponse;
import com.taeo.bookcuration.user.dto.UserDtos.BookShelfStateResponse;
import com.taeo.bookcuration.user.dto.UserDtos.BookSnapshotRequest;
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
import com.taeo.bookcuration.user.entity.UserBookActionEntity;
import com.taeo.bookcuration.user.entity.UserBookShelfEntity;
import com.taeo.bookcuration.user.entity.UserCharacterEntity;
import com.taeo.bookcuration.user.entity.UserInterestCategoryEntity;
import com.taeo.bookcuration.user.entity.UserInterestKeywordEntity;
import com.taeo.bookcuration.user.entity.UserPreferredLibraryEntity;
import com.taeo.bookcuration.user.entity.UserProfileEntity;
import com.taeo.bookcuration.user.repository.UserBookActionRepository;
import com.taeo.bookcuration.user.repository.UserBookShelfRepository;
import com.taeo.bookcuration.user.repository.UserCharacterRepository;
import com.taeo.bookcuration.user.repository.UserInterestCategoryRepository;
import com.taeo.bookcuration.user.repository.UserInterestKeywordRepository;
import com.taeo.bookcuration.user.repository.UserPreferredLibraryRepository;
import com.taeo.bookcuration.user.repository.UserProfileRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import java.math.BigDecimal;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;

@Service
@RequiredArgsConstructor
public class UserPersonalizationService {

    private static final List<String> ALLOWED_ACTION_TYPES = List.of(
            "VIEW", "CLICK", "LIKE", "DISLIKE", "NOT_INTERESTED", "RATING",
            "BORROW_CLICK", "SEARCH_CLICK", "READ_START", "READ_FINISH"
    );
    private static final List<String> ALLOWED_SHELF_TYPES = List.of("WANT_TO_READ", "READING", "READ", "FAVORITE", "INTERESTED", "NOT_INTERESTED");
    private static final DateTimeFormatter RESIDENT_FRONT_FORMATTER = DateTimeFormatter.ofPattern("yyMMdd");
    private static final int MAX_PREFERRED_LIBRARY_COUNT = 3;
    private static final int MAX_READING_BOOK_COUNT = 3;
    private static final int MAX_INTERESTED_BOOK_COUNT = 20;
    private static final int MAX_NOT_INTERESTED_BOOK_COUNT = 20;
    private static final int MAX_INTEREST_CATEGORY_COUNT = 3;
    private static final int NEARBY_AVAILABILITY_LIMIT = 10;
    private static final BigDecimal MIN_RATING = new BigDecimal("0.5");
    private static final BigDecimal MAX_RATING = new BigDecimal("5.0");
    private static final BigDecimal RATING_STEP = new BigDecimal("0.5");
    private static final BigDecimal DEFAULT_RADIUS_KM = new BigDecimal("5.00");
    private static final BigDecimal MIN_RADIUS_KM = new BigDecimal("1.00");
    private static final BigDecimal MAX_RADIUS_KM = new BigDecimal("50.00");
    private static final List<BigDecimal> ALLOWED_RADIUS_OPTIONS = List.of(
            new BigDecimal("1.00"), new BigDecimal("2.00"), new BigDecimal("3.00"), new BigDecimal("4.00"), new BigDecimal("5.00"),
            new BigDecimal("6.00"), new BigDecimal("7.00"), new BigDecimal("8.00"), new BigDecimal("9.00"), new BigDecimal("10.00"),
            new BigDecimal("50.00")
    );
    private static final String DEFAULT_CHARACTER_KEY = "DEFAULT_BOOKEMON";
    private static final int MAX_CHARACTER_LEVEL = 4;

    private final UserRepository userRepository;
    private final UserProfileRepository userProfileRepository;
    private final UserCharacterRepository userCharacterRepository;
    private final OnboardingOptionRepository onboardingOptionRepository;
    private final CharacterDefinitionRepository characterDefinitionRepository;
    private final UserInterestCategoryRepository userInterestCategoryRepository;
    private final UserInterestKeywordRepository userInterestKeywordRepository;
    private final UserPreferredLibraryRepository userPreferredLibraryRepository;
    private final UserBookActionRepository userBookActionRepository;
    private final UserBookShelfRepository userBookShelfRepository;
    private final LibraryJdbcRepository libraryJdbcRepository;
    private final BookAvailabilityClient bookAvailabilityClient;
    private final ReviewPolicyService reviewPolicyService;
    private final JdbcTemplate jdbcTemplate;
    private final ObjectMapper objectMapper;
    private final RecommendationEventLoggingService recommendationEventLoggingService;
    private final UserPreferenceProfileBuildService userPreferenceProfileBuildService;

    @Transactional
    public UserProfileResponse getProfile(UUID userId) {
        UserEntity user = userRepository.findById(userId)
                .orElseThrow(() -> new IllegalArgumentException("사용자를 찾을 수 없습니다."));

        UserProfileEntity profile = userProfileRepository.findById(userId)
                .orElseGet(() -> userProfileRepository.save(UserProfileEntity.createEmpty(user)));

        return toProfileResponse(profile);
    }

    @Transactional
    public UserProfileResponse updateProfile(UUID userId, UserProfileRequest request) {
        UserEntity user = findUser(userId);
        UserProfileEntity profile = getOrCreateProfile(user);

        // 수정 포인트: 기존 전체 저장 API는 레거시 호환용입니다. 신규 마이페이지 화면은 섹션별 API를 사용합니다.
        Long readerTypeOptionId = profile.getReaderTypeOptionId();
        LocalDate birthDate = resolveBirthDateForProfile(profile, request.residentNumberFront(), request.residentGenderDigit());
        String residentGenderDigit = blankToNull(request.residentGenderDigit()) == null
                ? profile.getResidentGenderDigit()
                : request.residentGenderDigit().trim();

        profile.updateFromMyPage(
                birthDate,
                residentGenderDigit,
                readerTypeOptionId,
                blankToNull(request.readingPurpose()),
                null,
                null,
                null,
                normalizePreferredRadius(request.preferredRadiusKm())
        );
        UserProfileEntity savedProfile = userProfileRepository.save(profile);
        replaceInterestCategories(userId, request.categoryCodes());
        replaceInterestKeywords(userId, request.keywords());
        rebuildPreferenceProfileSafely(userId);

        return toProfileResponse(savedProfile);
    }

    @Transactional
    public UserProfileResponse updateProfileIdentity(UUID userId, UserProfileIdentityRequest request) {
        UserEntity user = findUser(userId);
        UserProfileEntity profile = getOrCreateProfile(user);

        LocalDate birthDate = resolveBirthDateForProfile(profile, request.residentNumberFront(), request.residentGenderDigit());
        String residentGenderDigit = blankToNull(request.residentGenderDigit()) == null
                ? profile.getResidentGenderDigit()
                : request.residentGenderDigit().trim();

        // 수정 포인트: 기본 정보 저장은 user_profiles의 생년월일/성별 식별값만 갱신합니다.
        profile.updateIdentityFromMyPage(birthDate, residentGenderDigit);
        return toProfileResponse(userProfileRepository.save(profile));
    }

    @Transactional
    public UserProfileResponse updateProfileCategories(UUID userId, UserProfileCategoriesRequest request) {
        UserEntity user = findUser(userId);
        UserProfileEntity profile = getOrCreateProfile(user);

        // 수정 포인트: 희망 장르 저장은 user_interest_categories만 교체하고 독서 목적/기본정보/반경은 건드리지 않습니다.
        replaceInterestCategories(userId, request.categoryCodes());
        profile.markUpdatedFromMyPage();
        UserProfileEntity savedProfile = userProfileRepository.save(profile);
        rebuildPreferenceProfileSafely(userId);

        return toProfileResponse(savedProfile);
    }

    @Transactional
    public UserProfileResponse updateProfileReadingPurpose(UUID userId, UserProfileReadingPurposeRequest request) {
        UserEntity user = findUser(userId);
        UserProfileEntity profile = getOrCreateProfile(user);

        // 수정 포인트: 독서 목적 저장은 user_profiles.reading_purpose만 갱신합니다.
        profile.updateReadingPurposeFromMyPage(blankToNull(request.readingPurpose()));
        UserProfileEntity savedProfile = userProfileRepository.save(profile);
        rebuildPreferenceProfileSafely(userId);

        return toProfileResponse(savedProfile);
    }

    @Transactional
    public UserProfileResponse updateProfilePreferredRadius(UUID userId, UserProfilePreferredRadiusRequest request) {
        UserEntity user = findUser(userId);
        UserProfileEntity profile = getOrCreateProfile(user);

        // 수정 포인트: 선호 반경 저장은 도서관 검색 기본 반경만 갱신합니다.
        profile.updatePreferredRadiusFromMyPage(normalizePreferredRadius(request.preferredRadiusKm()));
        return toProfileResponse(userProfileRepository.save(profile));
    }

    private UserEntity findUser(UUID userId) {
        return userRepository.findById(userId)
                .orElseThrow(() -> new IllegalArgumentException("사용자를 찾을 수 없습니다."));
    }

    private UserProfileEntity getOrCreateProfile(UserEntity user) {
        return userProfileRepository.findById(user.getId())
                .orElseGet(() -> userProfileRepository.save(UserProfileEntity.createEmpty(user)));
    }

    private void replaceInterestCategories(UUID userId, List<String> requestedCategoryCodes) {
        userInterestCategoryRepository.deleteByUserId(userId);

        List<String> categoryCodes = safeList(requestedCategoryCodes).stream()
                .map(String::trim)
                .filter(value -> !value.isBlank())
                .distinct()
                .limit(MAX_INTEREST_CATEGORY_COUNT)
                .toList();

        categoryCodes.stream()
                .map(categoryCode -> UserInterestCategoryEntity.create(userId, categoryCode, "MYPAGE"))
                .forEach(userInterestCategoryRepository::save);
    }

    private void replaceInterestKeywords(UUID userId, List<String> requestedKeywords) {
        userInterestKeywordRepository.deleteByUserId(userId);
        safeList(requestedKeywords).stream()
                .map(String::trim)
                .filter(value -> !value.isBlank())
                .distinct()
                .map(keyword -> UserInterestKeywordEntity.create(userId, keyword, "MYPAGE"))
                .forEach(userInterestKeywordRepository::save);
    }

    @Transactional
    public UserCharacterResponse getCharacter(UUID userId) {
        UserCharacterEntity character = getOrIssueFallbackCharacter(userId);
        // 수정 포인트: 기존 데이터의 review_growth_count와 current_image_url/stage가 어긋난 경우
        // 마이페이지 조회 시점에도 현재 레벨 이미지로 동기화합니다.
        if (syncCharacterImageWithReviewGrowth(character)) {
            character = userCharacterRepository.save(character);
        }
        return toCharacterResponse(character);
    }

    @Transactional
    public UserCharacterResponse updateCharacterNickname(UUID userId, UserCharacterNicknameRequest request) {
        UserCharacterEntity character = getOrIssueFallbackCharacter(userId);
        character.changeCharacterNickname(request.characterNickname().trim());
        return toCharacterResponse(character);
    }

    @Transactional(readOnly = true)
    public List<PreferredLibraryResponse> getPreferredLibraries(UUID userId) {
        return userPreferredLibraryRepository.findByUserIdOrderByPriorityAscCreatedAtAsc(userId).stream()
                .map(this::toPreferredLibraryResponse)
                .toList();
    }

    @Transactional
    public PreferredLibraryResponse savePreferredLibrary(UUID userId, PreferredLibraryRequest request) {
        String libCode = request.libCode().trim();
        int priority = request.priority() == null ? 1 : Math.min(Math.max(request.priority(), 1), MAX_PREFERRED_LIBRARY_COUNT);

        if (!libraryJdbcRepository.existsByLibCode(libCode)) {
            throw new IllegalArgumentException("존재하지 않는 도서관 코드입니다.");
        }

        Optional<UserPreferredLibraryEntity> existing = userPreferredLibraryRepository.findByUserIdAndLibCode(userId, libCode);
        if (existing.isEmpty() && userPreferredLibraryRepository.countByUserId(userId) >= MAX_PREFERRED_LIBRARY_COUNT) {
            throw new IllegalArgumentException("나만의 도서관은 최대 " + MAX_PREFERRED_LIBRARY_COUNT + "개까지 등록할 수 있습니다.");
        }

        UserPreferredLibraryEntity entity = existing
                .orElseGet(() -> UserPreferredLibraryEntity.create(userId, libCode, priority));
        entity.updatePriority(priority);

        UserPreferredLibraryEntity saved = userPreferredLibraryRepository.save(entity);
        return toPreferredLibraryResponse(saved);
    }

    @Transactional
    public void deletePreferredLibrary(UUID userId, String libCode) {
        userPreferredLibraryRepository.deleteByUserIdAndLibCode(userId, libCode.trim());
    }

    @Transactional
    public BookActionResponse saveBookAction(UUID userId, BookActionRequest request) {
        String actionType = normalizeNullableUpper(request.actionType());
        if (actionType == null || !ALLOWED_ACTION_TYPES.contains(actionType)) {
            throw new IllegalArgumentException("지원하지 않는 actionType입니다.");
        }
        BigDecimal rating = normalizeOptionalRating(request.rating());

        UserBookActionEntity saved = userBookActionRepository.save(
                UserBookActionEntity.create(
                        userId,
                        request.bookId(),
                        actionType,
                        rating,
                        blankToNull(request.source()),
                        request.metadata()
                )
        );

        // 수정 포인트: 기존 user_book_actions 저장은 유지하고, 학습/분석용 공통 행동 이벤트도 제한 없이 별도 누적합니다.
        logBookActionBehavior(userId, request.bookId(), actionType, rating, blankToNull(request.source()), request.metadata());

        return new BookActionResponse(
                saved.getId(),
                saved.getBookId(),
                saved.getActionType(),
                saved.getRating(),
                saved.getCreatedAt()
        );
    }

    @Transactional(readOnly = true)
    public List<BookShelfResponse> getBookShelves(UUID userId, String shelfType) {
        String normalizedShelfType = normalizeNullableUpper(shelfType);
        List<UserBookShelfEntity> rows = normalizedShelfType == null
                ? userBookShelfRepository.findByUserIdOrderByUpdatedAtDesc(userId)
                : userBookShelfRepository.findByUserIdAndShelfTypeOrderByUpdatedAtDesc(userId, normalizedShelfType);
        return rows.stream().map(this::toBookShelfResponse).toList();
    }

    @Transactional(readOnly = true)
    public BookShelfSummaryResponse getBookShelfSummary(UUID userId) {
        Map<String, Integer> counts = new LinkedHashMap<>();
        counts.put("READING", toInt(userBookShelfRepository.countByUserIdAndShelfType(userId, "READING")));
        counts.put("READ", toInt(userBookShelfRepository.countByUserIdAndShelfType(userId, "READ")));
        counts.put("INTERESTED", toInt(userBookShelfRepository.countByUserIdAndShelfType(userId, "INTERESTED")));
        counts.put("NOT_INTERESTED", toInt(userBookShelfRepository.countByUserIdAndShelfType(userId, "NOT_INTERESTED")));

        Map<String, Integer> remaining = new LinkedHashMap<>();
        remaining.put("READING", Math.max(0, MAX_READING_BOOK_COUNT - counts.get("READING")));
        remaining.put("INTERESTED", Math.max(0, MAX_INTERESTED_BOOK_COUNT - counts.get("INTERESTED")));
        remaining.put("NOT_INTERESTED", Math.max(0, MAX_NOT_INTERESTED_BOOK_COUNT - counts.get("NOT_INTERESTED")));

        return new BookShelfSummaryResponse(MAX_READING_BOOK_COUNT, MAX_INTERESTED_BOOK_COUNT, MAX_NOT_INTERESTED_BOOK_COUNT, counts, remaining);
    }

    @Transactional(readOnly = true)
    public List<BookShelfStateResponse> getBookShelfStates(UUID userId, String isbn13s) {
        // 수정 포인트: 채팅 추천 카드가 다시 렌더링될 때 기존 관심/비관심/읽는 중 상태를 ISBN 기준으로 복원합니다.
        List<String> normalizedIsbns = parseIsbn13s(isbn13s);
        if (normalizedIsbns.isEmpty()) {
            return List.of();
        }

        String placeholders = String.join(",", normalizedIsbns.stream().map(value -> "?").toList());
        List<Object> params = new ArrayList<>();
        params.add(userId);
        params.addAll(normalizedIsbns);

        return jdbcTemplate.query("""
                SELECT
                    b.isbn13,
                    b.id AS book_id,
                    COALESCE(BOOL_OR(ubs.shelf_type = 'INTERESTED'), FALSE) AS interested,
                    COALESCE(BOOL_OR(ubs.shelf_type = 'NOT_INTERESTED'), FALSE) AS not_interested,
                    COALESCE(BOOL_OR(ubs.shelf_type = 'READING'), FALSE) AS reading
                FROM book.books b
                LEFT JOIN book.user_book_shelves ubs
                    ON ubs.book_id = b.id
                   AND ubs.user_id = ?
                   AND ubs.shelf_type IN ('INTERESTED', 'NOT_INTERESTED', 'READING')
                WHERE b.isbn13 IN (""" + placeholders + """
                )
                GROUP BY b.isbn13, b.id
                """, (rs, rowNum) -> new BookShelfStateResponse(
                        rs.getString("isbn13"),
                        rs.getLong("book_id"),
                        rs.getBoolean("interested"),
                        rs.getBoolean("not_interested"),
                        rs.getBoolean("reading")
                ), params.toArray());
    }

    @Transactional
    public BookShelfResponse saveBookShelf(UUID userId, BookShelfRequest request) {
        String shelfType = normalizeShelfType(request.shelfType());
        Long bookId = resolveBookId(request.bookId(), request.book());

        String oppositeShelfType = switch (shelfType) {
            case "INTERESTED" -> "NOT_INTERESTED";
            case "NOT_INTERESTED" -> "INTERESTED";
            default -> null;
        };
        if (oppositeShelfType != null) {
            userBookShelfRepository.deleteByUserIdAndBookIdAndShelfType(userId, bookId, oppositeShelfType);
        }

        Optional<UserBookShelfEntity> existing = userBookShelfRepository.findByUserIdAndBookIdAndShelfType(userId, bookId, shelfType);
        if (existing.isEmpty()) {
            enforceShelfLimit(userId, shelfType);
        }

        UserBookShelfEntity entity = existing
                .orElseGet(() -> UserBookShelfEntity.create(userId, bookId, shelfType, request.note()));
        entity.updateNote(request.note());
        UserBookShelfEntity saved = userBookShelfRepository.save(entity);

        if ("READING".equals(shelfType)) {
            userBookActionRepository.save(UserBookActionEntity.create(userId, bookId, "READ_START", null, "BOOKSTAND", Map.of("shelfType", shelfType)));
        } else if ("INTERESTED".equals(shelfType)) {
            userBookActionRepository.save(UserBookActionEntity.create(userId, bookId, "LIKE", null, "CHAT_RECOMMENDATION", Map.of("shelfType", shelfType)));
        } else if ("NOT_INTERESTED".equals(shelfType)) {
            userBookActionRepository.save(UserBookActionEntity.create(userId, bookId, "DISLIKE", null, "CHAT_RECOMMENDATION", Map.of("shelfType", shelfType)));
        }
        // 수정 포인트: 관심/비선호 20개 제한은 shelf 상태에만 적용하고, 행동 로그는 별도 테이블에 계속 누적합니다.
        logShelfAddBehavior(userId, bookId, shelfType);
        // 수정 포인트: 관심/읽는 중/비선호 상태 변화는 사용자 취향 프로필 재집계 대상입니다.
        rebuildPreferenceProfileSafely(userId);

        return toBookShelfResponse(saved);
    }

    @Transactional
    public BookShelfReviewResponse completeBookShelfReview(UUID userId, Long shelfId, BookShelfReviewRequest request) {
        UserBookShelfEntity readingShelf = userBookShelfRepository.findByIdAndUserId(shelfId, userId)
                .orElseThrow(() -> new IllegalArgumentException("독서대 항목을 찾을 수 없습니다."));

        if (!"READING".equals(readingShelf.getShelfType())) {
            throw new IllegalArgumentException("읽는 중인 책만 리뷰를 작성할 수 있습니다.");
        }

        ReviewPolicy reviewPolicy = reviewPolicyService.getReviewPolicy();
        OffsetDateTime reviewAvailableAt = readingShelf.getCreatedAt().plus(reviewPolicy.waitDuration());
        if (OffsetDateTime.now().isBefore(reviewAvailableAt)) {
            throw new IllegalArgumentException("책 등록 후 " + reviewPolicy.reviewWaitLabel() + "이 지나야 리뷰를 작성할 수 있습니다.");
        }

        userBookShelfRepository.findByUserIdAndBookIdAndShelfType(userId, readingShelf.getBookId(), "READ")
                .filter(existing -> !existing.getId().equals(readingShelf.getId()))
                .ifPresent(userBookShelfRepository::delete);

        // 수정 포인트: 별점은 0.5 단위만 허용해 DB 제약조건 위반 전에 명확한 검증 오류를 반환합니다.
        BigDecimal reviewRating = normalizeRequiredRating(request.rating());

        readingShelf.completeReading(request.reviewContent().trim(), reviewRating);
        UserBookShelfEntity saved = userBookShelfRepository.save(readingShelf);
        int reviewLength = request.reviewContent().trim().length();
        userBookActionRepository.save(UserBookActionEntity.create(
                userId,
                saved.getBookId(),
                "READ_FINISH",
                reviewRating,
                "BOOKSTAND",
                Map.of("reviewLength", reviewLength)
        ));
        // 수정 포인트: 읽은 책/평점/리뷰를 각각 모델 학습용 행동 이벤트로 분리해 나중에 weight를 다르게 줄 수 있게 합니다.
        logReviewCompletionBehavior(userId, saved.getBookId(), saved.getId(), reviewRating, reviewLength);
        // 수정 포인트: 리뷰/평점은 한 묶음이므로 리뷰 완료 시점에 감성 신호를 저장하고 사용자 프로필 벡터를 갱신합니다.
        analyzeReviewAndRebuildProfileSafely(userId, saved);

        // 수정 포인트: 사용자+도서 기준으로 리뷰 성장 보상은 최초 1회만 지급합니다.
        // 책장 데이터를 삭제하고 같은 책을 다시 등록해도 중복 경험치가 지급되지 않습니다.
        boolean reviewRewardGranted = grantReviewRewardIfFirst(userId, saved.getBookId(), saved.getId());

        UserCharacterEntity character = getOrIssueFallbackCharacter(userId);
        CharacterGrowth beforeGrowth = calculateCharacterGrowth(character.getReviewGrowthCount());
        UserCharacterEntity savedCharacter = character;
        CharacterGrowth afterGrowth = beforeGrowth;
        CharacterLevelUpEventResponse levelUpEvent = null;

        if (reviewRewardGranted) {
            character.increaseReviewGrowthCount();
            applyReviewGrowth(character);
            savedCharacter = userCharacterRepository.save(character);
            afterGrowth = calculateCharacterGrowth(savedCharacter.getReviewGrowthCount());
            levelUpEvent = toLevelUpEvent(savedCharacter, beforeGrowth, afterGrowth);
        }

        return new BookShelfReviewResponse(
                toBookShelfResponse(saved, reviewPolicy),
                toCharacterResponse(savedCharacter),
                levelUpEvent,
                reviewRewardGranted,
                reviewRewardGranted
                        ? "리뷰 보상이 지급되었습니다."
                        : "이미 리뷰 보상을 받은 책입니다. 리뷰는 저장됐지만 경험치는 추가되지 않았습니다."
        );
    }

    private boolean grantReviewRewardIfFirst(UUID userId, Long bookId, Long shelfId) {
        int insertedRows = jdbcTemplate.update("""
                INSERT INTO book.user_review_reward_logs (user_id, book_id, shelf_id)
                VALUES (?, ?, ?)
                ON CONFLICT (user_id, book_id) DO NOTHING
                """, userId, bookId, shelfId);
        return insertedRows > 0;
    }

    @Transactional
    public void deleteBookShelf(UUID userId, Long bookId, String shelfType) {
        String normalizedShelfType = normalizeShelfType(shelfType);
        userBookShelfRepository.deleteByUserIdAndBookIdAndShelfType(userId, bookId, normalizedShelfType);
        // 수정 포인트: 상태 삭제와 별도로 FAVORITE_REMOVE/DISLIKE_REMOVE 이벤트를 누적해 취향 변경 이력을 보존합니다.
        logShelfRemoveBehavior(userId, bookId, normalizedShelfType);
        deactivateReviewSignalAndRebuildProfileSafely(userId, bookId);
    }

    @Transactional
    public void deleteBookShelfByIsbn(UUID userId, String isbn13, String shelfType) {
        // 수정 포인트: 추천 카드에서 잘못 누른 관심/비관심/책읽기 버튼을 다시 눌러 취소할 수 있게 합니다.
        String normalizedShelfType = normalizeShelfType(shelfType);
        findBookIdByIsbn13(isbn13).ifPresent(bookId -> {
            userBookShelfRepository.deleteByUserIdAndBookIdAndShelfType(userId, bookId, normalizedShelfType);
            logShelfRemoveBehavior(userId, bookId, normalizedShelfType);
            deactivateReviewSignalAndRebuildProfileSafely(userId, bookId);
        });
    }

    @Transactional
    public void deleteBookShelfById(UUID userId, Long shelfId) {
        UserBookShelfEntity shelf = userBookShelfRepository.findByIdAndUserId(shelfId, userId)
                .orElseThrow(() -> new IllegalArgumentException("독서대 항목을 찾을 수 없습니다."));
        userBookShelfRepository.delete(shelf);
        logShelfRemoveBehavior(userId, shelf.getBookId(), shelf.getShelfType());
        deactivateReviewSignalAndRebuildProfileSafely(userId, shelf.getBookId());
    }

    private void analyzeReviewAndRebuildProfileSafely(UUID userId, UserBookShelfEntity shelf) {
        runAfterCommit(() -> {
            try {
                userPreferenceProfileBuildService.analyzeReviewAndRebuildProfile(userId, shelf);
            } catch (Exception ex) {
                // 수정 포인트: 리뷰 분석/프로필 벡터 생성 실패가 리뷰 저장 성공을 롤백하지 않도록 방어합니다.
            }
        });
    }

    private void rebuildPreferenceProfileSafely(UUID userId) {
        runAfterCommit(() -> {
            try {
                userPreferenceProfileBuildService.rebuildUserProfileSafely(userId);
            } catch (Exception ex) {
                // 수정 포인트: 취향 프로필 갱신 실패는 추천 fallback으로 처리합니다.
            }
        });
    }

    private void deactivateReviewSignalAndRebuildProfileSafely(UUID userId, Long bookId) {
        runAfterCommit(() -> {
            try {
                userPreferenceProfileBuildService.deactivateReviewSignalAndRebuild(userId, bookId);
            } catch (Exception ex) {
                // 수정 포인트: 삭제 흐름에서 분석 신호 정리 실패가 사용자 요청 실패로 이어지지 않게 합니다.
            }
        });
    }

    private void runAfterCommit(Runnable task) {
        // 수정 포인트: 취향 프로필 벡터 재집계/리뷰 분석은 사용자 저장 응답을 붙잡지 않도록 커밋 이후 별도 스레드에서 실행합니다.
        if (!TransactionSynchronizationManager.isSynchronizationActive()) {
            CompletableFuture.runAsync(task);
            return;
        }
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                CompletableFuture.runAsync(task);
            }
        });
    }

    private void logBookActionBehavior(UUID userId, Long bookId, String actionType, BigDecimal rating, String source, Map<String, Object> metadata) {
        UserBehaviorEventType eventType = toBehaviorEventTypeForAction(actionType);
        if (eventType == null) {
            return;
        }
        Map<String, Object> behaviorMetadata = copyMetadata(metadata);
        behaviorMetadata.put("legacyActionType", actionType);
        recommendationEventLoggingService.logBehaviorEventSafely(
                userId,
                bookId,
                eventType,
                source == null ? "USER_ACTION" : source,
                null,
                null,
                null,
                "RATING".equals(actionType) ? rating : null,
                behaviorMetadata
        );
    }

    private void logShelfAddBehavior(UUID userId, Long bookId, String shelfType) {
        UserBehaviorEventType eventType = toBehaviorEventTypeForShelfAdd(shelfType);
        if (eventType == null) {
            return;
        }
        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("shelfType", shelfType);
        recommendationEventLoggingService.logBehaviorEventSafely(userId, bookId, eventType, "BOOKSTAND", null, null, null, null, metadata);
    }

    private void logShelfRemoveBehavior(UUID userId, Long bookId, String shelfType) {
        UserBehaviorEventType eventType = toBehaviorEventTypeForShelfRemove(shelfType);
        if (eventType == null) {
            return;
        }
        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("shelfType", shelfType);
        recommendationEventLoggingService.logBehaviorEventSafely(userId, bookId, eventType, "BOOKSTAND", null, null, null, null, metadata);
    }

    private void logReviewCompletionBehavior(UUID userId, Long bookId, Long shelfId, BigDecimal rating, int reviewLength) {
        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("shelfId", shelfId);
        metadata.put("reviewLength", reviewLength);
        recommendationEventLoggingService.logBehaviorEventSafely(userId, bookId, UserBehaviorEventType.READ_ADD, "BOOKSTAND", null, null, null, null, metadata);
        recommendationEventLoggingService.logBehaviorEventSafely(userId, bookId, UserBehaviorEventType.RATING_ADD, "BOOKSTAND", null, null, null, rating, metadata);
        recommendationEventLoggingService.logBehaviorEventSafely(userId, bookId, UserBehaviorEventType.REVIEW_ADD, "BOOKSTAND", null, null, null, null, metadata);
    }

    private UserBehaviorEventType toBehaviorEventTypeForAction(String actionType) {
        return switch (actionType) {
            case "VIEW" -> UserBehaviorEventType.DETAIL_VIEW;
            case "CLICK", "SEARCH_CLICK", "BORROW_CLICK" -> UserBehaviorEventType.BOOK_CLICK;
            case "LIKE" -> UserBehaviorEventType.FAVORITE_ADD;
            case "DISLIKE", "NOT_INTERESTED" -> UserBehaviorEventType.DISLIKE_ADD;
            case "RATING" -> UserBehaviorEventType.RATING_ADD;
            case "READ_START" -> UserBehaviorEventType.READING_ADD;
            case "READ_FINISH" -> UserBehaviorEventType.READ_ADD;
            default -> null;
        };
    }

    private UserBehaviorEventType toBehaviorEventTypeForShelfAdd(String shelfType) {
        return switch (shelfType) {
            case "READING" -> UserBehaviorEventType.READING_ADD;
            case "READ" -> UserBehaviorEventType.READ_ADD;
            case "INTERESTED", "FAVORITE", "WANT_TO_READ" -> UserBehaviorEventType.FAVORITE_ADD;
            case "NOT_INTERESTED" -> UserBehaviorEventType.DISLIKE_ADD;
            default -> null;
        };
    }

    private UserBehaviorEventType toBehaviorEventTypeForShelfRemove(String shelfType) {
        return switch (shelfType) {
            case "INTERESTED", "FAVORITE", "WANT_TO_READ" -> UserBehaviorEventType.FAVORITE_REMOVE;
            case "NOT_INTERESTED" -> UserBehaviorEventType.DISLIKE_REMOVE;
            default -> null;
        };
    }

    private Map<String, Object> copyMetadata(Map<String, Object> metadata) {
        Map<String, Object> copied = new LinkedHashMap<>();
        if (metadata != null) {
            copied.putAll(metadata);
        }
        return copied;
    }

    @Transactional(readOnly = true)
    public BookAvailabilityResponse checkBookAvailability(UUID userId, BookAvailabilityRequest request) {
        String isbn13 = resolveIsbn13(request);
        UserProfileEntity profile = userProfileRepository.findById(userId).orElse(null);

        List<BookAvailabilityLibraryResult> results = new ArrayList<>();
        Map<String, Boolean> seenLibCodes = new LinkedHashMap<>();

        List<UserPreferredLibraryEntity> preferredLibraries = userPreferredLibraryRepository.findByUserIdOrderByPriorityAscCreatedAtAsc(userId);
        for (UserPreferredLibraryEntity preferredLibrary : preferredLibraries) {
            addAvailabilityResult(results, seenLibCodes, "PREFERRED", preferredLibrary.getLibCode(), null, isbn13);
        }

        BigDecimal latitude = request.latitude();
        BigDecimal longitude = request.longitude();
        BigDecimal radiusKm = request.radiusKm() != null ? request.radiusKm() : profile == null ? null : profile.getPreferredRadiusKm();

        if (latitude != null && longitude != null) {
            int radiusMeters = Math.min(Math.max(toRadiusMeters(radiusKm), 100), 50_000);
            // 수정 포인트: 도서관 검색 API가 page/size 기반으로 변경되어 내부 도서 소장 확인은 첫 페이지 10건만 조회합니다.
            LibraryPageResponse<NearbyLibraryResponse> nearbyLibraryPage = libraryJdbcRepository.findNearby(
                    latitude.doubleValue(),
                    longitude.doubleValue(),
                    radiusMeters,
                    0,
                    NEARBY_AVAILABILITY_LIMIT
            );
            for (NearbyLibraryResponse nearbyLibrary : nearbyLibraryPage.content()) {
                addAvailabilityResult(results, seenLibCodes, "NEARBY", nearbyLibrary.libCode(), nearbyLibrary.distanceMeters(), isbn13);
            }
        }

        return new BookAvailabilityResponse(isbn13, preferredLibraries.size(), Math.max(0, results.size() - preferredLibraries.size()), results);
    }

    private void addAvailabilityResult(
            List<BookAvailabilityLibraryResult> results,
            Map<String, Boolean> seenLibCodes,
            String source,
            String libCode,
            BigDecimal distanceMeters,
            String isbn13
    ) {
        if (libCode == null || seenLibCodes.containsKey(libCode)) {
            return;
        }
        seenLibCodes.put(libCode, true);
        LibraryJdbcRepository.LibrarySummary library = libraryJdbcRepository.findSummaryByLibCode(libCode).orElse(null);
        BookAvailabilityClient.AvailabilityResult availability = bookAvailabilityClient.check(libCode, isbn13);
        results.add(new BookAvailabilityLibraryResult(
                source,
                libCode,
                library == null ? null : library.libName(),
                library == null ? null : library.address(),
                distanceMeters,
                availability.hasBook(),
                availability.loanAvailable(),
                availability.message(),
                availability.success()
        ));
    }

    private Long resolveBookId(Long bookId, BookSnapshotRequest book) {
        if (bookId != null && existsBookId(bookId)) {
            return bookId;
        }
        if (book == null || blankToNull(book.isbn13()) == null) {
            throw new IllegalArgumentException("도서 ISBN 정보가 필요합니다.");
        }
        return upsertBook(book);
    }

    private Optional<Long> findBookIdByIsbn13(String isbn13) {
        String normalizedIsbn = blankToNull(isbn13);
        if (normalizedIsbn == null || !normalizedIsbn.matches("\\d{13}")) {
            return Optional.empty();
        }

        List<Long> rows = jdbcTemplate.query(
                "SELECT id FROM book.books WHERE isbn13 = ?",
                (rs, rowNum) -> rs.getLong("id"),
                normalizedIsbn
        );
        return rows.stream().findFirst();
    }

    private boolean existsBookId(Long bookId) {
        Boolean exists = jdbcTemplate.queryForObject("SELECT EXISTS (SELECT 1 FROM book.books WHERE id = ?)", Boolean.class, bookId);
        return Boolean.TRUE.equals(exists);
    }

    private Long upsertBook(BookSnapshotRequest book) {
        String isbn13 = book.isbn13().trim();
        String title = blankToNull(book.title()) == null ? "제목 정보 없음" : book.title().trim();
        String categoryCode = resolveValidBookCategoryCode(book);

        return jdbcTemplate.queryForObject("""
                WITH incoming AS (
                    SELECT
                        CAST(? AS varchar(13)) AS isbn13,
                        CAST(? AS varchar(500)) AS title,
                        CAST(? AS varchar(500)) AS author,
                        CAST(? AS varchar(255)) AS publisher,
                        CAST(? AS text) AS cover_url,
                        CAST(? AS varchar(50)) AS requested_category_code,
                        CAST(? AS jsonb) AS raw_json
                ),
                resolved AS (
                    SELECT
                        incoming.isbn13,
                        incoming.title,
                        incoming.author,
                        incoming.publisher,
                        incoming.cover_url,
                        CASE
                            WHEN incoming.requested_category_code IS NOT NULL
                             AND EXISTS (
                                 SELECT 1
                                 FROM book.book_categories category
                                 WHERE category.category_code = incoming.requested_category_code
                             )
                            THEN incoming.requested_category_code
                            ELSE NULL
                        END AS category_code,
                        incoming.raw_json
                    FROM incoming
                )
                INSERT INTO book.books (isbn13, title, author, publisher, cover_url, category_code, source, raw_json)
                SELECT
                    isbn13,
                    title,
                    author,
                    publisher,
                    cover_url,
                    category_code,
                    'CHAT_RECOMMENDATION',
                    raw_json
                FROM resolved
                ON CONFLICT (isbn13) DO UPDATE SET
                    title = COALESCE(NULLIF(EXCLUDED.title, ''), books.title),
                    author = COALESCE(EXCLUDED.author, books.author),
                    publisher = COALESCE(EXCLUDED.publisher, books.publisher),
                    cover_url = COALESCE(EXCLUDED.cover_url, books.cover_url),
                    -- 수정 포인트: 새 추천 카드에 유효 category_code가 없으면 기존 값을 보존합니다.
                    category_code = COALESCE(EXCLUDED.category_code, books.category_code),
                    raw_json = COALESCE(EXCLUDED.raw_json, books.raw_json),
                    updated_at = NOW()
                RETURNING id
                """, Long.class,
                isbn13,
                title,
                blankToNull(book.author()),
                blankToNull(book.publisher()),
                blankToNull(book.coverUrl()),
                // 수정 포인트: category_code는 book.book_categories에 실제 존재하는 경우에만 저장합니다.
                // null/미등록 값이면 SQL에서 NULL 처리되어 사용자 액션은 실패하지 않습니다.
                categoryCode,
                toJson(book.metadata())
        );
    }

    private String resolveValidBookCategoryCode(BookSnapshotRequest book) {
        List<String> candidates = new ArrayList<>();
        addCategoryCandidate(candidates, book.categoryCode());

        Map<String, Object> metadata = book.metadata();
        if (metadata != null) {
            addCategoryCandidate(candidates, metadata.get("categoryCode"));
            addCategoryCandidate(candidates, metadata.get("category_code"));
            addCategoryCandidate(candidates, metadata.get("categoryId"));
            addCategoryCandidate(candidates, metadata.get("category"));
            addCategoryCandidate(candidates, metadata.get("categories"));
            addCategoryCandidate(candidates, metadata.get("cate_depth1"));
            addCategoryCandidate(candidates, metadata.get("kcid"));
        }

        for (String candidate : candidates) {
            if (existsBookCategoryCode(candidate)) {
                return candidate;
            }
        }
        return null;
    }

    private void addCategoryCandidate(List<String> candidates, Object value) {
        if (value == null) {
            return;
        }

        if (value instanceof Map<?, ?> mapValue) {
            addCategoryCandidate(candidates, mapValue.get("categoryCode"));
            addCategoryCandidate(candidates, mapValue.get("category_code"));
            addCategoryCandidate(candidates, mapValue.get("code"));
            addCategoryCandidate(candidates, mapValue.get("categoryId"));
            addCategoryCandidate(candidates, mapValue.get("id"));
            addCategoryCandidate(candidates, mapValue.get("name"));
            addCategoryCandidate(candidates, mapValue.get("label"));
            return;
        }

        if (value instanceof Iterable<?> iterable) {
            for (Object item : iterable) {
                addCategoryCandidate(candidates, item);
            }
            return;
        }

        if (value.getClass().isArray()) {
            int length = java.lang.reflect.Array.getLength(value);
            for (int index = 0; index < length; index++) {
                addCategoryCandidate(candidates, java.lang.reflect.Array.get(value, index));
            }
            return;
        }

        String candidate = blankToNull(String.valueOf(value));
        if (candidate == null || candidates.contains(candidate)) {
            return;
        }
        candidates.add(candidate);
    }

    private boolean existsBookCategoryCode(String categoryCode) {
        String normalizedCategoryCode = blankToNull(categoryCode);
        if (normalizedCategoryCode == null) {
            return false;
        }

        try {
            Boolean exists = jdbcTemplate.queryForObject(
                    "SELECT EXISTS (SELECT 1 FROM book.book_categories WHERE category_code = CAST(? AS varchar(50)))",
                    Boolean.class,
                    normalizedCategoryCode
            );
            return Boolean.TRUE.equals(exists);
        } catch (RuntimeException e) {
            // 수정 포인트: 장르 코드 검증 중 DB/스키마 문제가 있어도 추천 카드 액션 자체는 실패시키지 않습니다.
            return false;
        }
    }

    private void enforceShelfLimit(UUID userId, String shelfType) {
        long count = userBookShelfRepository.countByUserIdAndShelfType(userId, shelfType);
        if ("READING".equals(shelfType) && count >= MAX_READING_BOOK_COUNT) {
            throw new IllegalArgumentException("읽는 중인 책은 최대 " + MAX_READING_BOOK_COUNT + "권까지 등록할 수 있습니다.");
        }
        if ("INTERESTED".equals(shelfType) && count >= MAX_INTERESTED_BOOK_COUNT) {
            throw new IllegalArgumentException("관심있는 책은 최대 " + MAX_INTERESTED_BOOK_COUNT + "권까지 등록할 수 있습니다.");
        }
        if ("NOT_INTERESTED".equals(shelfType) && count >= MAX_NOT_INTERESTED_BOOK_COUNT) {
            throw new IllegalArgumentException("관심없는 책은 최대 " + MAX_NOT_INTERESTED_BOOK_COUNT + "권까지 등록할 수 있습니다.");
        }
    }

    private String resolveIsbn13(BookAvailabilityRequest request) {
        String directIsbn = blankToNull(request.isbn13());
        if (directIsbn != null) {
            return directIsbn;
        }
        if (request.book() != null && blankToNull(request.book().isbn13()) != null) {
            return request.book().isbn13().trim();
        }
        throw new IllegalArgumentException("대출 가능 여부 조회에는 ISBN13이 필요합니다.");
    }

    private int toRadiusMeters(BigDecimal radiusKm) {
        BigDecimal safeRadius = radiusKm == null ? new BigDecimal("5") : radiusKm;
        return safeRadius.multiply(new BigDecimal("1000")).intValue();
    }

    private UserCharacterEntity getOrIssueFallbackCharacter(UUID userId) {
        UserEntity user = userRepository.findById(userId)
                .orElseThrow(() -> new IllegalArgumentException("사용자를 찾을 수 없습니다."));

        UserCharacterEntity character = userCharacterRepository.findById(userId)
                .orElseGet(() -> UserCharacterEntity.createDefault(user));

        if (isLegacyOrIncompleteCharacter(character)) {
            // 수정 포인트: 온보딩을 건너뛴 사용자는 1/2/3 독자유형 캐릭터가 아니라 DEFAULT_BOOKEMON을 받아야 합니다.
            // DEFAULT_BOOKEMON이 없을 때만 관리자 캐릭터 마스터의 첫 번째 항목을 fallback으로 사용합니다.
            Optional<CharacterDefinitionEntity> fallbackCharacter = characterDefinitionRepository.findByCharacterKey(DEFAULT_CHARACTER_KEY)
                    .or(() -> characterDefinitionRepository.findAllByOrderByIdAsc().stream().findFirst());

            fallbackCharacter.ifPresent(definition ->
                    character.issueInitialCharacter(
                            definition.getCharacterKey(),
                            definition.getDefaultName(),
                            definition.getLevel1ImageUrl()
                    )
            );
        } else {
            syncDefaultCharacterNicknameIfNeeded(character);
        }

        return userCharacterRepository.save(character);
    }

    private void syncDefaultCharacterNicknameIfNeeded(UserCharacterEntity character) {
        if (DEFAULT_CHARACTER_KEY.equals(character.getCharacterKey())) {
            return;
        }

        String nickname = character.getCharacterNickname();
        if (nickname != null
                && !nickname.isBlank()
                && !"북케몬".equals(nickname)
                && !"북케몬 알".equals(nickname)) {
            return;
        }

        characterDefinitionRepository.findByCharacterKey(character.getCharacterKey())
                .ifPresent(definition ->
                        character.issueInitialCharacter(
                                definition.getCharacterKey(),
                                definition.getDefaultName(),
                                character.getCurrentImageUrl() == null || character.getCurrentImageUrl().isBlank()
                                        ? definition.getLevel1ImageUrl()
                                        : character.getCurrentImageUrl()
                        )
                );
    }

    private static boolean isLegacyOrIncompleteCharacter(UserCharacterEntity character) {
        return character.getCharacterKey() == null
                || character.getCharacterKey().isBlank()
                || "BOOKEMON_EGG".equals(character.getCharacterKey())
                || character.getCurrentImageUrl() == null
                || character.getCurrentImageUrl().isBlank();
    }

    private UserProfileResponse toProfileResponse(UserProfileEntity profile) {
        UUID userId = profile.getUserId();
        List<String> categoryCodes = userInterestCategoryRepository.findByUserIdOrderByCategoryCodeAsc(userId).stream()
                .map(UserInterestCategoryEntity::getCategoryCode)
                .toList();
        List<String> keywords = userInterestKeywordRepository.findByUserIdOrderByKeywordAsc(userId).stream()
                .map(UserInterestKeywordEntity::getKeyword)
                .toList();

        OptionSummary readerType = findOptionSummary(profile.getReaderTypeOptionId());

        return new UserProfileResponse(
                userId,
                profile.getBirthDate(),
                profile.getResidentGenderDigit(),
                profile.getReaderTypeOptionId(),
                readerType.label(),
                profile.getReadingPurpose(),
                profile.getRegionName(),
                profile.getLatitude(),
                profile.getLongitude(),
                profile.getPreferredRadiusKm(),
                profile.isOnboardingCompleted(),
                categoryCodes,
                keywords
        );
    }

    private PreferredLibraryResponse toPreferredLibraryResponse(UserPreferredLibraryEntity entity) {
        LibraryJdbcRepository.LibrarySummary library = libraryJdbcRepository.findSummaryByLibCode(entity.getLibCode()).orElse(null);
        return new PreferredLibraryResponse(
                entity.getId(),
                entity.getLibCode(),
                library == null ? null : library.libName(),
                library == null ? null : library.address(),
                library == null ? null : library.latitude(),
                library == null ? null : library.longitude(),
                entity.getPriority()
        );
    }

    private static BigDecimal normalizePreferredRadius(BigDecimal preferredRadiusKm) {
        BigDecimal radius = preferredRadiusKm == null ? DEFAULT_RADIUS_KM : preferredRadiusKm;

        return ALLOWED_RADIUS_OPTIONS.stream()
                .filter(option -> option.compareTo(radius) == 0)
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("선호 반경은 1~10km 또는 10~50km 중 하나로 선택해 주세요."));
    }

    private static BigDecimal normalizeOptionalRating(BigDecimal rating) {
        if (rating == null) {
            return null;
        }
        return normalizeRating(rating);
    }

    private static BigDecimal normalizeRequiredRating(BigDecimal rating) {
        if (rating == null) {
            throw new IllegalArgumentException("rating은 필수입니다.");
        }
        return normalizeRating(rating);
    }

    private static BigDecimal normalizeRating(BigDecimal rating) {
        if (rating.compareTo(MIN_RATING) < 0 || rating.compareTo(MAX_RATING) > 0
                || rating.remainder(RATING_STEP).compareTo(BigDecimal.ZERO) != 0) {
            throw new IllegalArgumentException("rating은 0.5 단위로 0.5에서 5.0 사이여야 합니다.");
        }

        // 수정 포인트: DB numeric(2,1) 컬럼과 응답 포맷을 맞추기 위해 1자리 소수로 정규화합니다.
        return rating.setScale(1);
    }

    private OptionSummary findOptionSummary(Long optionId) {
        if (optionId == null) {
            return new OptionSummary(null);
        }
        return onboardingOptionRepository.findById(optionId)
                .map(option -> new OptionSummary(option.getLabel()))
                .orElseGet(() -> new OptionSummary(null));
    }

    private void applyReviewGrowth(UserCharacterEntity character) {
        CharacterGrowth growth = calculateCharacterGrowth(character.getReviewGrowthCount());
        String levelImageUrl = resolveCharacterImageUrl(
                character.getCharacterKey(),
                growth.characterLevel(),
                character.getCurrentImageUrl()
        );
        character.changeStage(growth.stage(), character.getCharacterKey(), levelImageUrl);
    }

    private boolean syncCharacterImageWithReviewGrowth(UserCharacterEntity character) {
        CharacterGrowth growth = calculateCharacterGrowth(character.getReviewGrowthCount());
        String levelImageUrl = resolveCharacterImageUrl(
                character.getCharacterKey(),
                growth.characterLevel(),
                character.getCurrentImageUrl()
        );

        if (levelImageUrl == null || levelImageUrl.isBlank()) {
            return false;
        }

        boolean stageChanged = !growth.stage().equals(character.getStage());
        boolean imageChanged = !levelImageUrl.equals(character.getCurrentImageUrl());
        if (!stageChanged && !imageChanged) {
            return false;
        }

        character.changeStage(growth.stage(), character.getCharacterKey(), levelImageUrl);
        return true;
    }

    private static CharacterGrowth calculateCharacterGrowth(int reviewGrowthCount) {
        if (reviewGrowthCount <= 0) {
            return new CharacterGrowth(1, "EGG", 0, 100, 0, MAX_CHARACTER_LEVEL);
        }

        int level2ReviewCount = reviewGrowthCount - 1;
        if (level2ReviewCount < 5) {
            int experience = level2ReviewCount * 20;
            return new CharacterGrowth(2, "BABY", experience, 100, experience, MAX_CHARACTER_LEVEL);
        }

        int level3ReviewCount = level2ReviewCount - 5;
        if (level3ReviewCount < 10) {
            int experience = level3ReviewCount * 10;
            return new CharacterGrowth(3, "GROWTH", experience, 100, experience, MAX_CHARACTER_LEVEL);
        }

        return new CharacterGrowth(MAX_CHARACTER_LEVEL, "FINAL", 100, 100, 100, MAX_CHARACTER_LEVEL);
    }

    private CharacterLevelUpEventResponse toLevelUpEvent(
            UserCharacterEntity character,
            CharacterGrowth beforeGrowth,
            CharacterGrowth afterGrowth
    ) {
        if (afterGrowth.characterLevel() <= beforeGrowth.characterLevel()) {
            return null;
        }

        String nickname = blankToNull(character.getCharacterNickname()) == null ? "북케몬" : character.getCharacterNickname();
        String message = afterGrowth.characterLevel() >= afterGrowth.maxLevel()
                ? nickname + "이(가) 최대 레벨에 도달했어요!"
                : nickname + "이(가) Lv." + afterGrowth.characterLevel() + "로 성장했어요!";

        String levelImageUrl = resolveCharacterImageUrl(
                character.getCharacterKey(),
                afterGrowth.characterLevel(),
                character.getCurrentImageUrl()
        );

        return new CharacterLevelUpEventResponse(
                beforeGrowth.characterLevel(),
                afterGrowth.characterLevel(),
                nickname,
                levelImageUrl,
                afterGrowth.experience(),
                afterGrowth.experienceToNextLevel(),
                afterGrowth.maxLevel(),
                message
        );
    }

    private UserCharacterResponse toCharacterResponse(UserCharacterEntity character) {
        CharacterGrowth growth = calculateCharacterGrowth(character.getReviewGrowthCount());
        String displayImageUrl = resolveCharacterImageUrl(
                character.getCharacterKey(),
                growth.characterLevel(),
                character.getCurrentImageUrl()
        );

        return new UserCharacterResponse(
                character.getUserId(),
                character.getCharacterKey(),
                character.getStage(),
                character.getCharacterNickname(),
                character.getReviewGrowthCount(),
                displayImageUrl,
                growth.characterLevel(),
                growth.experience(),
                growth.experienceToNextLevel(),
                growth.experiencePercent(),
                growth.maxLevel()
        );
    }

    private String resolveCharacterImageUrl(String characterKey, int characterLevel, String fallbackImageUrl) {
        return characterDefinitionRepository.findByCharacterKey(characterKey)
                .map(definition -> switch (characterLevel) {
                    case 1 -> firstNotBlank(definition.getLevel1ImageUrl(), definition.getImageUrl(), fallbackImageUrl);
                    case 2 -> firstNotBlank(definition.getLevel2ImageUrl(), definition.getLevel1ImageUrl(), definition.getImageUrl(), fallbackImageUrl);
                    case 3 -> firstNotBlank(definition.getLevel3ImageUrl(), definition.getLevel2ImageUrl(), definition.getLevel1ImageUrl(), fallbackImageUrl);
                    case 4 -> firstNotBlank(definition.getLevel4ImageUrl(), definition.getLevel3ImageUrl(), definition.getLevel2ImageUrl(), definition.getLevel1ImageUrl(), fallbackImageUrl);
                    default -> firstNotBlank(definition.getLevel1ImageUrl(), definition.getImageUrl(), fallbackImageUrl);
                })
                .orElse(fallbackImageUrl);
    }

    private static String firstNotBlank(String... values) {
        if (values == null) {
            return null;
        }
        for (String value : values) {
            if (value != null && !value.isBlank()) {
                return value;
            }
        }
        return null;
    }

    private BookShelfResponse toBookShelfResponse(UserBookShelfEntity entity) {
        return toBookShelfResponse(entity, reviewPolicyService.getReviewPolicy());
    }

    private BookShelfResponse toBookShelfResponse(UserBookShelfEntity entity, ReviewPolicy reviewPolicy) {
        BookSummary book = findBookSummary(entity.getBookId()).orElse(BookSummary.empty(entity.getBookId()));
        OffsetDateTime reviewAvailableAt = entity.getCreatedAt().plus(reviewPolicy.waitDuration());
        boolean reviewAvailable = "READING".equals(entity.getShelfType()) && !OffsetDateTime.now().isBefore(reviewAvailableAt);

        return new BookShelfResponse(
                entity.getId(),
                entity.getBookId(),
                book.isbn13(),
                book.title(),
                book.author(),
                book.publisher(),
                book.coverUrl(),
                entity.getShelfType(),
                entity.getNote(),
                entity.getReviewContent(),
                entity.getReviewRating(),
                reviewAvailableAt,
                reviewAvailable,
                reviewPolicy.reviewWaitMinutes(),
                reviewPolicy.reviewWaitLabel(),
                entity.getCompletedAt(),
                entity.getCreatedAt(),
                entity.getUpdatedAt()
        );
    }

    private record CharacterGrowth(
            int characterLevel,
            String stage,
            int experience,
            int experienceToNextLevel,
            int experiencePercent,
            int maxLevel
    ) {
    }

    private Optional<BookSummary> findBookSummary(Long bookId) {
        List<BookSummary> rows = jdbcTemplate.query("""
                SELECT id, isbn13, title, author, publisher, cover_url
                FROM book.books
                WHERE id = ?
                """, (rs, rowNum) -> toBookSummary(rs), bookId);
        return rows.stream().findFirst();
    }

    private BookSummary toBookSummary(ResultSet rs) throws SQLException {
        return new BookSummary(
                rs.getLong("id"),
                rs.getString("isbn13"),
                rs.getString("title"),
                rs.getString("author"),
                rs.getString("publisher"),
                rs.getString("cover_url")
        );
    }

    private LocalDate resolveBirthDateForProfile(UserProfileEntity profile, String residentNumberFront, String residentGenderDigit) {
        String front = blankToNull(residentNumberFront);
        if (front == null) {
            return profile.getBirthDate();
        }

        String digit = blankToNull(residentGenderDigit);
        if (digit == null) {
            // 수정 포인트: 기존 birthDate를 표시용 YYMMDD로 다시 보낸 요청은 생년월일 수정이 아니므로 그대로 유지합니다.
            // 일부 기존/소셜 회원 데이터는 resident_gender_digit이 비어 있을 수 있어 다른 탭 저장까지 막지 않게 합니다.
            if (matchesExistingResidentFront(profile.getBirthDate(), front)) {
                return profile.getBirthDate();
            }
            throw new IllegalArgumentException("주민등록번호 앞자리를 수정할 때는 뒷자리 첫 숫자도 필요합니다.");
        }
        return parseBirthDate(front, digit);
    }

    private static boolean matchesExistingResidentFront(LocalDate birthDate, String residentNumberFront) {
        if (birthDate == null || residentNumberFront == null || residentNumberFront.isBlank()) {
            return false;
        }
        return birthDate.format(RESIDENT_FRONT_FORMATTER).equals(residentNumberFront.trim());
    }

    private static LocalDate parseBirthDate(String residentNumberFront, String residentGenderDigit) {
        try {
            LocalDate parsed = LocalDate.parse(residentNumberFront, RESIDENT_FRONT_FORMATTER);
            int yy = parsed.getYear() % 100;
            int century = resolveCentury(residentGenderDigit);
            return LocalDate.of(century + yy, parsed.getMonth(), parsed.getDayOfMonth());
        } catch (DateTimeParseException ex) {
            throw new IllegalArgumentException("주민등록번호 앞자리는 올바른 YYMMDD 형식이어야 합니다.");
        }
    }

    private static int resolveCentury(String residentGenderDigit) {
        return switch (residentGenderDigit) {
            case "1", "2" -> 1900;
            case "3", "4" -> 2000;
            default -> {
                // 수정 포인트: DTO 검증을 우회한 잘못된 값도 DB 저장 전에 명확한 400 오류로 차단합니다.
                throw new IllegalArgumentException("주민등록번호 뒷자리 첫 숫자는 1~4 중 하나여야 합니다.");
            }
        };
    }

    private static List<String> parseIsbn13s(String isbn13s) {
        if (isbn13s == null || isbn13s.isBlank()) {
            return List.of();
        }
        return List.of(isbn13s.split(",")).stream()
                .map(String::trim)
                .filter(value -> value.matches("\\d{13}"))
                .distinct()
                .limit(50)
                .toList();
    }

    private static String normalizeNullableUpper(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        return value.trim().toUpperCase(Locale.ROOT);
    }

    private static String normalizeShelfType(String value) {
        String shelfType = normalizeNullableUpper(value);
        if (shelfType == null || !ALLOWED_SHELF_TYPES.contains(shelfType)) {
            throw new IllegalArgumentException("지원하지 않는 책장 구분값입니다.");
        }
        return shelfType;
    }

    private static String blankToNull(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        return value.trim();
    }

    private static List<String> safeList(List<String> values) {
        return values == null ? List.of() : values;
    }

    private static int toInt(long value) {
        return Math.toIntExact(value);
    }

    private String toJson(Map<String, Object> metadata) {
        try {
            return objectMapper.writeValueAsString(metadata == null ? Map.of() : metadata);
        } catch (JsonProcessingException e) {
            throw new IllegalArgumentException("도서 메타데이터를 JSON으로 변환하지 못했습니다.", e);
        }
    }

    private record OptionSummary(String label) {
    }

    private record BookSummary(Long id, String isbn13, String title, String author, String publisher, String coverUrl) {
        static BookSummary empty(Long bookId) {
            return new BookSummary(bookId, null, "도서 정보 없음", null, null, null);
        }
    }
}
