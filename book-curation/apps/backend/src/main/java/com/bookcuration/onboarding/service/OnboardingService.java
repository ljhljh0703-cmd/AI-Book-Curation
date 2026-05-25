package com.taeo.bookcuration.onboarding.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.taeo.bookcuration.admin.character.entity.CharacterDefinitionEntity;
import com.taeo.bookcuration.admin.character.repository.CharacterDefinitionRepository;
import com.taeo.bookcuration.admin.onboarding.entity.OnboardingOptionEntity;
import com.taeo.bookcuration.admin.onboarding.repository.OnboardingOptionRepository;
import com.taeo.bookcuration.auth.entity.UserEntity;
import com.taeo.bookcuration.auth.repository.UserRepository;
import com.taeo.bookcuration.library.repository.LibraryJdbcRepository;
import com.taeo.bookcuration.onboarding.dto.OnboardingDtos.CharacterSummary;
import com.taeo.bookcuration.onboarding.dto.OnboardingDtos.OnboardingOptionResponse;
import com.taeo.bookcuration.onboarding.dto.OnboardingDtos.OnboardingSubmitRequest;
import com.taeo.bookcuration.onboarding.dto.OnboardingDtos.OnboardingSubmitResponse;
import com.taeo.bookcuration.onboarding.dto.OnboardingDtos.ProfileSummary;
import com.taeo.bookcuration.onboarding.dto.OnboardingDtos.SavedBookShelfSummary;
import com.taeo.bookcuration.onboarding.dto.OnboardingDtos.SelectedBookRequest;
import com.taeo.bookcuration.user.dto.UserDtos.BookSnapshotRequest;
import com.taeo.bookcuration.user.entity.UserBookActionEntity;
import com.taeo.bookcuration.user.entity.UserBookShelfEntity;
import com.taeo.bookcuration.user.entity.UserCharacterEntity;
import com.taeo.bookcuration.user.entity.UserInterestCategoryEntity;
import com.taeo.bookcuration.user.entity.UserPreferredLibraryEntity;
import com.taeo.bookcuration.user.entity.UserProfileEntity;
import com.taeo.bookcuration.user.repository.UserBookActionRepository;
import com.taeo.bookcuration.user.repository.UserBookShelfRepository;
import com.taeo.bookcuration.user.repository.UserCharacterRepository;
import com.taeo.bookcuration.user.repository.UserInterestCategoryRepository;
import com.taeo.bookcuration.user.repository.UserPreferredLibraryRepository;
import com.taeo.bookcuration.user.repository.UserProfileRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
public class OnboardingService {

    private static final String GROUP_READER_TYPE = "READER_TYPE";
    private static final String GROUP_BOOK_CATEGORY = "BOOK_CATEGORY";
    private static final List<String> ALLOWED_SHELF_TYPES = List.of("WANT_TO_READ", "READING", "READ", "FAVORITE");
    private static final DateTimeFormatter RESIDENT_FRONT_FORMATTER = DateTimeFormatter.ofPattern("yyMMdd");
    private static final BigDecimal DEFAULT_RADIUS_KM = new BigDecimal("5.00");
    private static final BigDecimal MIN_RADIUS_KM = new BigDecimal("1.00");
    private static final BigDecimal MAX_RADIUS_KM = new BigDecimal("50.00");
    private static final List<BigDecimal> ALLOWED_RADIUS_OPTIONS = List.of(
            new BigDecimal("1.00"), new BigDecimal("2.00"), new BigDecimal("3.00"), new BigDecimal("4.00"), new BigDecimal("5.00"),
            new BigDecimal("6.00"), new BigDecimal("7.00"), new BigDecimal("8.00"), new BigDecimal("9.00"), new BigDecimal("10.00"),
            new BigDecimal("50.00")
    );

    private final OnboardingOptionRepository onboardingOptionRepository;
    private final CharacterDefinitionRepository characterDefinitionRepository;
    private final UserRepository userRepository;
    private final UserProfileRepository userProfileRepository;
    private final UserCharacterRepository userCharacterRepository;
    private final UserInterestCategoryRepository userInterestCategoryRepository;
    private final UserPreferredLibraryRepository userPreferredLibraryRepository;
    private final UserBookShelfRepository userBookShelfRepository;
    private final UserBookActionRepository userBookActionRepository;
    private final LibraryJdbcRepository libraryJdbcRepository;
    private final JdbcTemplate jdbcTemplate;
    private final ObjectMapper objectMapper;

    @Transactional(readOnly = true)
    public List<OnboardingOptionResponse> getActiveOptions(String optionGroup) {
        List<OnboardingOptionEntity> options = optionGroup == null || optionGroup.isBlank()
                ? onboardingOptionRepository.findByActiveTrueOrderByOptionGroupAscDisplayOrderAscIdAsc()
                : onboardingOptionRepository.findByOptionGroupAndActiveTrueOrderByDisplayOrderAscIdAsc(optionGroup.trim().toUpperCase(Locale.ROOT));

        Map<String, CharacterDefinitionEntity> charactersByKey = characterDefinitionRepository.findAllByOrderByIdAsc().stream()
                .collect(Collectors.toMap(CharacterDefinitionEntity::getCharacterKey, Function.identity(), (left, right) -> left));

        return options.stream()
                .map(option -> toOptionResponse(option, charactersByKey.get(option.getCharacterGroupCode())))
                .toList();
    }

    @Transactional
    public OnboardingSubmitResponse complete(UUID userId, OnboardingSubmitRequest request) {
        UserEntity user = userRepository.findById(userId)
                .orElseThrow(() -> new IllegalArgumentException("사용자를 찾을 수 없습니다."));

        OnboardingOptionEntity readerType = findActiveOption(request.readerTypeOptionId(), GROUP_READER_TYPE);

        // 수정 포인트: 대표 장르 컬럼(book_category_option_id)을 제거했으므로
        // 온보딩 희망 장르는 최대 3개의 선택지 목록만 저장합니다.
        List<OnboardingOptionEntity> bookCategories = findActiveBookCategoryOptions(request.bookCategoryOptionIds());

        LocalDate birthDate = parseBirthDate(request.residentNumberFront(), request.residentGenderDigit());

        UserProfileEntity profile = userProfileRepository.findById(userId)
                .orElseGet(() -> UserProfileEntity.createEmpty(user));

        BigDecimal radius = normalizePreferredRadius(request.preferredRadiusKm());

        profile.completeOnboarding(
                birthDate,
                request.residentGenderDigit().trim(),
                readerType.getId(),
                blankToNull(request.readingPurpose()),
                blankToNull(request.regionName()),
                request.latitude(),
                request.longitude(),
                radius
        );

        UserProfileEntity savedProfile = userProfileRepository.save(profile);

        // 수정 포인트: 선택한 희망 장르 최대 3개를 기존 user_interest_categories 구조에 저장해 추천 조건으로 활용합니다.
        // category_code에는 KDC 코드가 아니라 onboarding_options.option_key 값을 저장합니다.
        userInterestCategoryRepository.deleteByUserId(userId);
        bookCategories.stream()
                .map(OnboardingOptionEntity::getOptionKey)
                .map(categoryCode -> UserInterestCategoryEntity.create(userId, categoryCode, "ONBOARDING"))
                .forEach(userInterestCategoryRepository::save);

        UserCharacterEntity savedCharacter = issueCharacterByReaderType(user, readerType);

        List<SavedBookShelfSummary> savedBookShelves = saveSelectedBooks(userId, request.selectedBooks());
        String savedLibraryCode = savePreferredLibraryIfPresent(userId, request.preferredLibraryCode());

        return new OnboardingSubmitResponse(
                savedProfile.isOnboardingCompleted(),
                new ProfileSummary(
                        savedProfile.getBirthDate(),
                        savedProfile.getResidentGenderDigit(),
                        savedProfile.getReaderTypeOptionId(),
                        bookCategories.stream().map(OnboardingOptionEntity::getId).toList(),
                        savedProfile.getReadingPurpose(),
                        savedProfile.getRegionName(),
                        savedProfile.getLatitude(),
                        savedProfile.getLongitude(),
                        savedProfile.getPreferredRadiusKm()
                ),
                new CharacterSummary(
                        savedCharacter.getCharacterKey(),
                        savedCharacter.getCharacterNickname(),
                        savedCharacter.getCurrentImageUrl()
                ),
                savedBookShelves,
                savedLibraryCode
        );
    }



    @Transactional
    public void skip(UUID userId) {
        UserEntity user = userRepository.findById(userId)
                .orElseThrow(() -> new IllegalArgumentException("사용자를 찾을 수 없습니다."));

        UserProfileEntity profile = userProfileRepository.findById(userId)
                .orElseGet(() -> UserProfileEntity.createEmpty(user));

        profile.skipOnboarding();
        userProfileRepository.save(profile);

        if (!userCharacterRepository.existsById(userId)) {
            userCharacterRepository.save(UserCharacterEntity.createDefault(user));
        }
    }
    private List<OnboardingOptionEntity> findActiveBookCategoryOptions(List<Long> optionIds) {
        List<Long> requestedIds = safeOptionIds(optionIds);

        if (requestedIds.isEmpty()) {
            throw new IllegalArgumentException("희망 장르는 최소 1개 이상 선택해 주세요.");
        }

        if (requestedIds.size() > 3) {
            throw new IllegalArgumentException("희망 장르는 최대 3개까지 선택할 수 있습니다.");
        }

        return requestedIds.stream()
                .map(optionId -> findActiveOption(optionId, GROUP_BOOK_CATEGORY))
                .toList();
    }

    private static List<Long> safeOptionIds(List<Long> optionIds) {
        return optionIds == null
                ? List.of()
                : optionIds.stream()
                        .filter(Objects::nonNull)
                        .distinct()
                        .toList();
    }

    private OnboardingOptionEntity findActiveOption(Long optionId, String expectedGroup) {
        OnboardingOptionEntity option = onboardingOptionRepository.findById(optionId)
                .orElseThrow(() -> new IllegalArgumentException("존재하지 않는 온보딩 선택지입니다."));

        if (!expectedGroup.equals(option.getOptionGroup()) || !Boolean.TRUE.equals(option.getActive())) {
            throw new IllegalArgumentException("사용할 수 없는 온보딩 선택지입니다.");
        }

        return option;
    }

    private UserCharacterEntity issueCharacterByReaderType(UserEntity user, OnboardingOptionEntity readerType) {
        UserCharacterEntity character = userCharacterRepository.findById(user.getId())
                .orElseGet(() -> UserCharacterEntity.createDefault(user));

        String characterKey = blankToNull(readerType.getCharacterGroupCode());
        if (characterKey == null) {
            throw new IllegalArgumentException("선택한 독자 유형에 연결된 캐릭터가 없습니다. 관리자에게 문의해 주세요.");
        }

        CharacterDefinitionEntity definition = characterDefinitionRepository.findByCharacterKey(characterKey)
                .orElseThrow(() -> new IllegalArgumentException("독자 유형에 연결된 캐릭터 정보를 찾을 수 없습니다."));

        // 수정 포인트: 온보딩 완료 시 독자 유형의 character_group_code로 캐릭터를 찾고, 성장형 1단계 이미지를 최초 발급 이미지로 사용합니다.
        // 사용자가 이미 캐릭터 이름을 직접 바꾼 상태에서 온보딩을 재저장하는 경우에는 기존 이름을 보존합니다.
        character.issueInitialCharacter(definition.getCharacterKey(), definition.getDefaultName(), definition.getLevel1ImageUrl());

        return userCharacterRepository.save(character);
    }

    private List<SavedBookShelfSummary> saveSelectedBooks(UUID userId, List<SelectedBookRequest> selectedBooks) {
        List<SelectedBookRequest> safeBooks = selectedBooks == null ? List.of() : selectedBooks;

        if (safeBooks.size() > 3) {
            throw new IllegalArgumentException("온보딩에서 선택할 수 있는 도서는 최대 3권입니다.");
        }

        return safeBooks.stream()
                .filter(Objects::nonNull)
                .map(selectedBook -> {
                    Long bookId = resolveBookId(selectedBook.bookId(), selectedBook.book());
                    String shelfType = normalizeShelfType(selectedBook.shelfType());

                    Optional<UserBookShelfEntity> existing = userBookShelfRepository.findByUserIdAndBookIdAndShelfType(
                            userId,
                            bookId,
                            shelfType
                    );

                    UserBookShelfEntity entity = existing
                            .orElseGet(() -> UserBookShelfEntity.create(
                                    userId,
                                    bookId,
                                    shelfType,
                                    selectedBook.note()
                            ));

                    entity.updateNote(selectedBook.note());

                    UserBookShelfEntity saved = userBookShelfRepository.save(entity);
                    saveOnboardingBookActionIfNew(userId, bookId, shelfType, existing.isEmpty());
                    return new SavedBookShelfSummary(saved.getBookId(), saved.getShelfType());
                })
                .toList();
    }

    private Long resolveBookId(Long bookId, BookSnapshotRequest book) {
        if (bookId != null) {
            if (!existsBookId(bookId)) {
                throw new IllegalArgumentException("존재하지 않는 도서 ID입니다.");
            }
            return bookId;
        }

        if (book == null || blankToNull(book.isbn13()) == null) {
            throw new IllegalArgumentException("온보딩 선택 도서는 bookId 또는 ISBN13이 포함된 book 정보가 필요합니다.");
        }

        // 수정 포인트: 알라딘 검색 결과처럼 내부 bookId가 아직 없는 도서는 온보딩 완료 시 book.books에 먼저 upsert합니다.
        return upsertBookFromOnboarding(book);
    }

    private boolean existsBookId(Long bookId) {
        Boolean exists = jdbcTemplate.queryForObject("SELECT EXISTS (SELECT 1 FROM book.books WHERE id = ?)", Boolean.class, bookId);
        return Boolean.TRUE.equals(exists);
    }

    private Long upsertBookFromOnboarding(BookSnapshotRequest book) {
        String isbn13 = blankToNull(book.isbn13());
        if (isbn13 == null || !isbn13.matches("\\d{13}")) {
            throw new IllegalArgumentException("온보딩 선택 도서는 13자리 ISBN13이 필요합니다.");
        }

        String title = blankToNull(book.title()) == null ? "제목 정보 없음" : book.title().trim();

        return jdbcTemplate.queryForObject("""
                INSERT INTO book.books (isbn13, title, author, publisher, cover_url, source, raw_json)
                VALUES (?, ?, ?, ?, ?, 'ALADIN_ONBOARDING', CAST(? AS jsonb))
                ON CONFLICT (isbn13) DO UPDATE SET
                    title = COALESCE(NULLIF(EXCLUDED.title, ''), books.title),
                    author = COALESCE(EXCLUDED.author, books.author),
                    publisher = COALESCE(EXCLUDED.publisher, books.publisher),
                    cover_url = COALESCE(EXCLUDED.cover_url, books.cover_url),
                    raw_json = COALESCE(EXCLUDED.raw_json, books.raw_json),
                    updated_at = NOW()
                RETURNING id
                """, Long.class,
                isbn13,
                title,
                blankToNull(book.author()),
                blankToNull(book.publisher()),
                blankToNull(book.coverUrl()),
                toJson(book.metadata())
        );
    }

    private void saveOnboardingBookActionIfNew(UUID userId, Long bookId, String shelfType, boolean created) {
        if (!created) {
            return;
        }

        String actionType = switch (shelfType) {
            case "READ" -> "READ_FINISH";
            case "READING" -> "READ_START";
            case "FAVORITE" -> "LIKE";
            default -> null;
        };

        if (actionType == null) {
            return;
        }

        // 수정 포인트: 온보딩에서 선택한 읽은 책도 개인화 학습용 행동 로그에 남길 수 있도록 source를 ONBOARDING으로 기록합니다.
        userBookActionRepository.save(UserBookActionEntity.create(
                userId,
                bookId,
                actionType,
                null,
                "ONBOARDING",
                Map.of("shelfType", shelfType)
        ));
    }

    private String toJson(Map<String, Object> metadata) {
        try {
            return objectMapper.writeValueAsString(metadata == null ? Map.of() : metadata);
        } catch (JsonProcessingException e) {
            throw new IllegalArgumentException("도서 메타데이터를 JSON으로 변환할 수 없습니다.");
        }
    }

    private String savePreferredLibraryIfPresent(UUID userId, String preferredLibraryCode) {
        String libCode = blankToNull(preferredLibraryCode);

        if (libCode == null) {
            return null;
        }

        if (!libraryJdbcRepository.existsByLibCode(libCode)) {
            throw new IllegalArgumentException("존재하지 않는 도서관 코드입니다.");
        }

        UserPreferredLibraryEntity entity = userPreferredLibraryRepository.findByUserIdAndLibCode(userId, libCode)
                .orElseGet(() -> UserPreferredLibraryEntity.create(userId, libCode, 1));

        entity.updatePriority(1);

        return userPreferredLibraryRepository.save(entity).getLibCode();
    }

    private OnboardingOptionResponse toOptionResponse(OnboardingOptionEntity option, CharacterDefinitionEntity character) {
        return new OnboardingOptionResponse(
                option.getId(),
                option.getOptionGroup(),
                option.getOptionKey(),
                option.getLabel(),
                option.getDescription(),
                option.getCharacterGroupCode(),
                character == null ? null : character.getDefaultName(),
                character == null ? null : character.getLevel1ImageUrl(),
                option.getDisplayOrder()
        );
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
                // 수정 포인트: 프론트/DTO 검증을 우회한 잘못된 값도 저장 전에 명확한 400 오류로 차단합니다.
                throw new IllegalArgumentException("주민등록번호 뒷자리 첫 숫자는 1~4 중 하나여야 합니다.");
            }
        };
    }

    private static BigDecimal normalizePreferredRadius(BigDecimal preferredRadiusKm) {
        BigDecimal radius = preferredRadiusKm == null ? DEFAULT_RADIUS_KM : preferredRadiusKm;

        return ALLOWED_RADIUS_OPTIONS.stream()
                .filter(option -> option.compareTo(radius) == 0)
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("선호 반경은 1~10km 또는 10~50km 중 하나로 선택해 주세요."));
    }

    private static String normalizeShelfType(String shelfType) {
        String normalized = shelfType == null || shelfType.isBlank()
                ? "READ"
                : shelfType.trim().toUpperCase(Locale.ROOT);

        if (!ALLOWED_SHELF_TYPES.contains(normalized)) {
            throw new IllegalArgumentException("지원하지 않는 책장 상태입니다.");
        }

        return normalized;
    }

    private static String blankToNull(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }

        return value.trim();
    }
}