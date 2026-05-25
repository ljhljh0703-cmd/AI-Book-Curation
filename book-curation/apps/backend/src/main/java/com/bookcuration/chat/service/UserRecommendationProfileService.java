package com.taeo.bookcuration.chat.service;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.Period;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class UserRecommendationProfileService {

    private static final int MAX_INTEREST_CATEGORIES = 20;
    private static final int MAX_INTEREST_KEYWORDS = 20;
    private static final int MAX_SHELF_BOOKS = 30;
    private static final int MAX_REVIEW_BOOKS = 20;
    private static final int MAX_PREFERRED_LIBRARIES = 5;
    private static final int MAX_REVIEW_PREFERENCE_SIGNALS = 20;
    private static final int TEXT_LIMIT = 800;

    private final JdbcTemplate jdbcTemplate;

    @Transactional(readOnly = true)
    public Map<String, Object> buildProfile(UUID userId) {
        Map<String, Object> profile = new LinkedHashMap<>();
        profile.put("profileType", "LOGIN_USER");
        profile.put("userId", userId.toString());

        Map<String, Object> onboardingProfile = findOnboardingProfile(userId);
        Map<String, Object> demographicProfile = findDemographicProfile(userId);
        List<Map<String, Object>> interestCategories = findInterestCategories(userId);
        List<Map<String, Object>> interestKeywords = findInterestKeywords(userId);
        List<Map<String, Object>> shelfBooks = findShelfBooks(userId);
        List<Map<String, Object>> reviewedBooks = findReviewedBooks(userId);
        // 수정 포인트: 실시간 추천 프로필은 현재 서재/프로필 상태만 사용합니다.
        // user_book_actions 같은 raw 행동 로그는 삭제된 서재 항목의 READ/READING 이력을 남길 수 있으므로
        // 추천 이유/GTE query/profile reranking의 positive 근거로 전달하지 않습니다.
        List<Map<String, Object>> recommendationActions = List.of();
        List<Map<String, Object>> preferredLibraries = findPreferredLibraries(userId);
        List<Map<String, Object>> reviewPreferenceSignals = findReviewPreferenceSignals(userId);
        // 수정 포인트: 저장된 user_preference_profiles 벡터/요약은 비동기 재집계 전까지 삭제된 책을 포함할 수 있습니다.
        // 이번 실시간 추천 요청에서는 현재 서재와 현재 리뷰 감성 신호만 사용해 stale positive profile을 차단합니다.
        Map<String, Object> recommendationPreferenceProfile = Map.of();

        boolean profileAvailable = !onboardingProfile.isEmpty()
                || !interestCategories.isEmpty()
                || !interestKeywords.isEmpty()
                || !shelfBooks.isEmpty()
                || !reviewedBooks.isEmpty()
                || !recommendationActions.isEmpty()
                || !reviewPreferenceSignals.isEmpty()
                || !recommendationPreferenceProfile.isEmpty()
                || !demographicProfile.isEmpty();
        boolean profileSearchSignalAvailable = hasProfileSearchSignals(
                interestCategories,
                interestKeywords,
                shelfBooks,
                reviewedBooks,
                reviewPreferenceSignals,
                recommendationPreferenceProfile
        );

        profile.put("profileAvailable", profileAvailable);
        profile.put("profileSearchSignalAvailable", profileSearchSignalAvailable);
        profile.put("positiveProfileSignalAvailable", profileSearchSignalAvailable);
        profile.put("onboarding", onboardingProfile);
        profile.put("demographicProfile", demographicProfile);
        profile.put("demographic_profile", demographicProfile);
        profile.put("ageGroup", demographicProfile.get("ageGroup"));
        profile.put("age_group", demographicProfile.get("ageGroup"));
        profile.put("userAgeGroup", demographicProfile.get("ageGroup"));
        profile.put("user_age_group", demographicProfile.get("ageGroup"));
        profile.put("ageGroupSource", demographicProfile.get("ageGroupSource"));
        profile.put("age_group_source", demographicProfile.get("age_group_source"));
        profile.put("interestCategories", interestCategories);
        profile.put("interestKeywords", interestKeywords);
        profile.put("shelfBooks", shelfBooks);
        profile.put("reviewedBooks", reviewedBooks);
        profile.put("recentActions", recommendationActions);
        profile.put("preferredLibraries", preferredLibraries);
        profile.put("reviewPreferenceSignals", reviewPreferenceSignals);
        profile.put("review_preference_signals", reviewPreferenceSignals);
        profile.put("preferenceProfile", recommendationPreferenceProfile);
        profile.put("preference_profile", recommendationPreferenceProfile);

        Map<String, Object> canonicalProfile = buildCanonicalProfile(interestCategories, shelfBooks, reviewedBooks);
        profile.putAll(canonicalProfile);
        profile.put("review_rating_preference_profile", buildReviewRatingPreferenceProfile(reviewPreferenceSignals, recommendationPreferenceProfile));
        profile.put("summary", buildSummary(onboardingProfile, interestCategories, interestKeywords, shelfBooks, reviewedBooks));
        return profile;
    }


    private Map<String, Object> buildCanonicalProfile(
            List<Map<String, Object>> interestCategories,
            List<Map<String, Object>> shelfBooks,
            List<Map<String, Object>> reviewedBooks
    ) {
        List<Map<String, Object>> preferredBooks = new ArrayList<>();
        List<Map<String, Object>> dislikedBooks = new ArrayList<>();
        List<Map<String, Object>> readingBooks = new ArrayList<>();
        List<Map<String, Object>> readBooks = new ArrayList<>();
        List<Map<String, Object>> highRatedBooks = new ArrayList<>();
        List<Map<String, Object>> lowRatedBooks = new ArrayList<>();
        List<Map<String, Object>> ratings = new ArrayList<>();
        Set<String> excludedIsbns = new HashSet<>();

        for (Map<String, Object> book : shelfBooks) {
            String shelfType = normalizeCode(book.get("shelfType"));
            Double rating = toDouble(book.get("reviewRating"));

            if ("INTERESTED".equals(shelfType)) {
                preferredBooks.add(stripReviewContent(book));
            } else if ("READING".equals(shelfType)) {
                readingBooks.add(stripReviewContent(book));
                preferredBooks.add(stripReviewContent(book));
            } else if ("READ".equals(shelfType)) {
                readBooks.add(stripReviewContent(book));
                addIsbn(excludedIsbns, book);
            } else if ("NOT_INTERESTED".equals(shelfType)) {
                dislikedBooks.add(stripReviewContent(book));
                addIsbn(excludedIsbns, book);
            }

            if (rating != null) {
                ratings.add(stripReviewContent(book));
                if (rating >= 4.0) {
                    highRatedBooks.add(stripReviewContent(book));
                    preferredBooks.add(stripReviewContent(book));
                } else if (rating <= 2.0) {
                    lowRatedBooks.add(stripReviewContent(book));
                    dislikedBooks.add(stripReviewContent(book));
                    addIsbn(excludedIsbns, book);
                }
            }
        }

        for (Map<String, Object> book : reviewedBooks) {
            Double rating = toDouble(book.get("reviewRating"));
            if (rating == null) {
                continue;
            }

            ratings.add(stripReviewContent(book));
            if (rating >= 4.0) {
                highRatedBooks.add(stripReviewContent(book));
                preferredBooks.add(stripReviewContent(book));
            } else if (rating <= 2.0) {
                lowRatedBooks.add(stripReviewContent(book));
                dislikedBooks.add(stripReviewContent(book));
                addIsbn(excludedIsbns, book);
            }
        }

        List<Map<String, Object>> preferredGenres = interestCategories.stream()
                .map(this::toGenreSignal)
                .filter(Objects::nonNull)
                .distinct()
                .toList();

        Map<String, Object> canonical = new LinkedHashMap<>();
        canonical.put("preferred_genres", preferredGenres);
        canonical.put("preferredGenres", preferredGenres);
        canonical.put("disliked_genres", List.of());
        canonical.put("dislikedGenres", List.of());
        canonical.put("preferred_books", dedupeBooks(preferredBooks));
        canonical.put("preferredBooks", dedupeBooks(preferredBooks));
        canonical.put("disliked_books", dedupeBooks(dislikedBooks));
        canonical.put("dislikedBooks", dedupeBooks(dislikedBooks));
        canonical.put("reading_books", dedupeBooks(readingBooks));
        canonical.put("readingBooks", dedupeBooks(readingBooks));
        canonical.put("read_books", dedupeBooks(readBooks));
        canonical.put("readBooks", dedupeBooks(readBooks));
        canonical.put("high_rated_books", dedupeBooks(highRatedBooks));
        canonical.put("highRatedBooks", dedupeBooks(highRatedBooks));
        canonical.put("low_rated_books", dedupeBooks(lowRatedBooks));
        canonical.put("lowRatedBooks", dedupeBooks(lowRatedBooks));
        canonical.put("ratings", dedupeBooks(ratings));
        canonical.put("excluded_isbns", excludedIsbns.stream().sorted().toList());
        canonical.put("excludedIsbns", excludedIsbns.stream().sorted().toList());
        return canonical;
    }

    private Map<String, Object> toGenreSignal(Map<String, Object> category) {
        String categoryCode = stringValue(category.get("categoryCode"));
        String label = stringValue(category.get("label"));
        String parentCategoryCode = stringValue(category.get("parentCategoryCode"));
        if (categoryCode == null && label == null) {
            return null;
        }

        Map<String, Object> signal = new LinkedHashMap<>();
        signal.put("categoryCode", categoryCode);
        signal.put("label", label);
        signal.put("parentCategoryCode", parentCategoryCode);
        signal.put("weight", stringValue(category.get("weight")));
        return compact(signal);
    }

    private List<Map<String, Object>> dedupeBooks(List<Map<String, Object>> books) {
        Set<String> seen = new HashSet<>();
        List<Map<String, Object>> result = new ArrayList<>();
        for (Map<String, Object> book : books) {
            Map<String, Object> safeBook = stripReviewContent(book);
            String isbn = normalizeIsbn(safeBook.get("isbn13"));
            String title = normalizeCode(safeBook.get("title"));
            if (isbn == null && title == null) {
                continue;
            }
            String key = isbn != null ? "isbn:" + isbn : "title:" + title;
            if (seen.contains(key)) {
                continue;
            }
            seen.add(key);
            result.add(safeBook);
        }
        return result;
    }

    private Map<String, Object> stripReviewContent(Map<String, Object> source) {
        Map<String, Object> result = new LinkedHashMap<>();
        source.forEach((key, value) -> {
            if (!"reviewContent".equals(key)) {
                result.put(key, value);
            }
        });
        return compact(result);
    }

    private void addIsbn(Set<String> excludedIsbns, Map<String, Object> book) {
        String isbn = normalizeIsbn(book.get("isbn13"));
        if (isbn != null) {
            excludedIsbns.add(isbn);
        }
    }

    private boolean hasDurablePreferenceSignals(
            List<Map<String, Object>> shelfBooks,
            List<Map<String, Object>> reviewedBooks,
            List<Map<String, Object>> reviewPreferenceSignals
    ) {
        return shelfBooks.stream().anyMatch(this::hasExplicitPreferenceSignal)
                || shelfBooks.stream().anyMatch(this::hasWeakPositiveReadSignal)
                || reviewedBooks.stream().anyMatch(this::hasRatingSignal)
                || !reviewPreferenceSignals.isEmpty();
    }

    private boolean hasProfileSearchSignals(
            List<Map<String, Object>> interestCategories,
            List<Map<String, Object>> interestKeywords,
            List<Map<String, Object>> shelfBooks,
            List<Map<String, Object>> reviewedBooks,
            List<Map<String, Object>> reviewPreferenceSignals,
            Map<String, Object> preferenceProfile
    ) {
        return !interestCategories.isEmpty()
                || !interestKeywords.isEmpty()
                || shelfBooks.stream().anyMatch(this::hasProfileSearchSeedSignal)
                || reviewedBooks.stream().anyMatch(this::hasRatingSignal)
                || !reviewPreferenceSignals.isEmpty()
                || stringValue(preferenceProfile.get("vectorPointId")) != null
                || stringValue(preferenceProfile.get("vector_point_id")) != null;
    }

    private boolean hasExplicitPreferenceSignal(Map<String, Object> row) {
        String type = normalizeCode(firstNonBlank(
                stringValue(row.get("shelfType")),
                stringValue(row.get("shelf_type")),
                stringValue(row.get("actionType")),
                stringValue(row.get("action_type"))
        ));
        return isExplicitPositiveAction(type) || hasRatingSignal(row);
    }

    private boolean hasProfileSearchSeedSignal(Map<String, Object> row) {
        return hasExplicitPreferenceSignal(row) || hasWeakPositiveReadSignal(row);
    }

    private boolean hasWeakPositiveReadSignal(Map<String, Object> row) {
        String type = normalizeCode(firstNonBlank(
                stringValue(row.get("shelfType")),
                stringValue(row.get("shelf_type")),
                stringValue(row.get("actionType")),
                stringValue(row.get("action_type"))
        ));
        return "READ".equals(type) && !hasRatingSignal(row) && !hasReviewText(row);
    }

    private boolean hasReviewText(Map<String, Object> row) {
        return stringValue(firstNonBlank(
                stringValue(row.get("reviewContent")),
                stringValue(row.get("review_content"))
        )) != null;
    }

    private boolean hasRatingSignal(Map<String, Object> row) {
        return toDouble(firstNonBlank(
                stringValue(row.get("reviewRating")),
                stringValue(row.get("review_rating")),
                stringValue(row.get("rating")),
                stringValue(row.get("score"))
        )) != null;
    }

    private Set<String> collectIsbnSet(List<Map<String, Object>> books) {
        Set<String> result = new HashSet<>();
        for (Map<String, Object> book : books) {
            addIsbn(result, book);
        }
        return result;
    }

    private boolean isExplicitPositiveAction(String actionType) {
        return actionType != null && List.of("LIKE", "INTERESTED", "FAVORITE", "WANT_TO_READ").contains(actionType);
    }

    private boolean isNegativeAction(String actionType) {
        return actionType != null && List.of("DISLIKE", "NOT_INTERESTED").contains(actionType);
    }

    private String normalizeCode(Object value) {
        String text = stringValue(value);
        if (text == null) {
            return null;
        }
        return text.toUpperCase().replace("-", "_").replace(" ", "_");
    }

    private String normalizeIsbn(Object value) {
        String text = stringValue(value);
        if (text == null) {
            return null;
        }
        String digits = text.replaceAll("\\D", "");
        return digits.isBlank() ? null : digits;
    }

    private Double toDouble(Object value) {
        if (value == null) {
            return null;
        }
        try {
            return Double.parseDouble(String.valueOf(value));
        } catch (NumberFormatException ex) {
            return null;
        }
    }

    private String stringValue(Object value) {
        if (value == null) {
            return null;
        }
        String text = String.valueOf(value).trim();
        return text.isBlank() ? null : text;
    }


    private Map<String, Object> findDemographicProfile(UUID userId) {
        List<Map<String, Object>> rows = safeQuery("""
                SELECT birth_date, resident_gender_digit
                FROM book.user_profiles
                WHERE user_id = ?
                """, (rs, rowNum) -> {
            LocalDate birthDate = rs.getObject("birth_date", LocalDate.class);
            String ageGroup = resolveAgeGroup(birthDate);
            String source = birthDate == null ? "UNKNOWN" : "RESIDENT_NUMBER_FRONT_DERIVED";
            Map<String, Object> audiencePolicy = new LinkedHashMap<>();
            audiencePolicy.put("defaultTargetReader", "SELF");
            audiencePolicy.put("default_target_reader", "SELF");
            audiencePolicy.put("priority", "REQUEST_THEN_PROFILE_THEN_USER_AGE");
            audiencePolicy.put("ageSignalRole", "DEFAULT_AUDIENCE_PRIOR");
            audiencePolicy.put("age_signal_role", "DEFAULT_AUDIENCE_PRIOR");

            Map<String, Object> row = new LinkedHashMap<>();
            row.put("ageGroup", ageGroup);
            row.put("age_group", ageGroup);
            row.put("userAgeGroup", ageGroup);
            row.put("user_age_group", ageGroup);
            row.put("ageGroupSource", source);
            row.put("age_group_source", source);
            row.put("targetReaderDefault", "SELF");
            row.put("target_reader_default", "SELF");
            row.put("audiencePolicy", audiencePolicy);
            row.put("audience_policy", audiencePolicy);
            return compact(row);
        }, userId);
        return rows.isEmpty() ? Map.of() : rows.getFirst();
    }

    private String resolveAgeGroup(LocalDate birthDate) {
        if (birthDate == null || birthDate.isAfter(LocalDate.now())) {
            return "UNKNOWN";
        }
        int age = Period.between(birthDate, LocalDate.now()).getYears();
        if (age < 13) {
            return "CHILD";
        }
        if (age < 19) {
            return "TEEN";
        }
        if (age < 30) {
            return "YOUNG_ADULT";
        }
        if (age < 65) {
            return "ADULT";
        }
        return "SENIOR";
    }

    private Map<String, Object> findOnboardingProfile(UUID userId) {
        List<Map<String, Object>> rows = safeQuery("""
                SELECT
                    up.onboarding_completed,
                    up.reading_purpose,
                    up.profile_summary,
                    up.preferred_radius_km,
                    up.reader_type_option_id,
                    reader_type.option_key AS reader_type_key,
                    reader_type.label AS reader_type_label
                FROM book.user_profiles up
                LEFT JOIN book.onboarding_options reader_type
                    ON reader_type.id = up.reader_type_option_id
                WHERE up.user_id = ?
                """, (rs, rowNum) -> {
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("onboardingCompleted", rs.getBoolean("onboarding_completed"));
            row.put("readingPurpose", trimToNull(rs.getString("reading_purpose")));
            row.put("profileSummary", truncate(rs.getString("profile_summary"), TEXT_LIMIT));
            row.put("preferredRadiusKm", toPlainString(rs.getBigDecimal("preferred_radius_km")));
            row.put("readerTypeOptionId", nullableLong(rs, "reader_type_option_id"));
            row.put("readerTypeKey", trimToNull(rs.getString("reader_type_key")));
            row.put("readerTypeLabel", trimToNull(rs.getString("reader_type_label")));
            return compact(row);
        }, userId);
        return rows.isEmpty() ? Map.of() : rows.getFirst();
    }

    private List<Map<String, Object>> findInterestCategories(UUID userId) {
        return safeQuery("""
                SELECT
                    uic.category_code,
                    uic.weight,
                    uic.source,
                    bc.category_name,
                    bc.parent_category_code,
                    option_value.label AS onboarding_label
                FROM book.user_interest_categories uic
                LEFT JOIN book.book_categories bc
                    ON bc.category_code = uic.category_code
                LEFT JOIN book.onboarding_options option_value
                    ON option_value.option_key = uic.category_code
                WHERE uic.user_id = ?
                ORDER BY uic.weight DESC, uic.updated_at DESC
                LIMIT ?
                """, (rs, rowNum) -> {
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("categoryCode", trimToNull(rs.getString("category_code")));
            row.put("label", firstNonBlank(rs.getString("category_name"), rs.getString("onboarding_label"), rs.getString("category_code")));
            row.put("parentCategoryCode", trimToNull(rs.getString("parent_category_code")));
            row.put("weight", toPlainString(rs.getBigDecimal("weight")));
            row.put("source", trimToNull(rs.getString("source")));
            return compact(row);
        }, userId, MAX_INTEREST_CATEGORIES);
    }

    private List<Map<String, Object>> findInterestKeywords(UUID userId) {
        return safeQuery("""
                SELECT keyword, weight, source, last_observed_at
                FROM book.user_interest_keywords
                WHERE user_id = ?
                ORDER BY weight DESC, last_observed_at DESC
                LIMIT ?
                """, (rs, rowNum) -> {
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("keyword", trimToNull(rs.getString("keyword")));
            row.put("weight", toPlainString(rs.getBigDecimal("weight")));
            row.put("source", trimToNull(rs.getString("source")));
            row.put("lastObservedAt", toIsoString(rs, "last_observed_at"));
            return compact(row);
        }, userId, MAX_INTEREST_KEYWORDS);
    }

    private List<Map<String, Object>> findShelfBooks(UUID userId) {
        return safeQuery("""
                SELECT
                    ubs.shelf_type,
                    ubs.note,
                    ubs.review_content,
                    ubs.review_rating,
                    ubs.completed_at,
                    ubs.updated_at,
                    b.isbn13,
                    b.title,
                    b.author,
                    b.publisher,
                    b.category_code,
                    b.description,
                    b.cover_url
                FROM book.user_book_shelves ubs
                JOIN book.books b ON b.id = ubs.book_id
                WHERE ubs.user_id = ?
                ORDER BY ubs.updated_at DESC
                LIMIT ?
                """, (rs, rowNum) -> toBookProfileRow(rs, true), userId, MAX_SHELF_BOOKS);
    }

    private List<Map<String, Object>> findReviewedBooks(UUID userId) {
        return safeQuery("""
                SELECT
                    ubs.shelf_type,
                    ubs.note,
                    ubs.review_content,
                    ubs.review_rating,
                    ubs.completed_at,
                    ubs.updated_at,
                    b.isbn13,
                    b.title,
                    b.author,
                    b.publisher,
                    b.category_code,
                    b.description,
                    b.cover_url
                FROM book.user_book_shelves ubs
                JOIN book.books b ON b.id = ubs.book_id
                WHERE ubs.user_id = ?
                  AND (ubs.review_content IS NOT NULL OR ubs.review_rating IS NOT NULL OR ubs.shelf_type = 'READ')
                ORDER BY COALESCE(ubs.completed_at, ubs.updated_at) DESC
                LIMIT ?
                """, (rs, rowNum) -> toBookProfileRow(rs, true), userId, MAX_REVIEW_BOOKS);
    }

    private List<Map<String, Object>> findReviewPreferenceSignals(UUID userId) {
        return safeQuery("""
                SELECT
                    sig.book_id,
                    sig.review_id,
                    sig.rating,
                    sig.overall_sentiment,
                    sig.sentiment_score,
                    sig.confidence,
                    sig.liked_aspects::text AS liked_aspects,
                    sig.disliked_aspects::text AS disliked_aspects,
                    sig.preference_terms::text AS preference_terms,
                    sig.avoid_terms::text AS avoid_terms,
                    sig.preferred_mood::text AS preferred_mood,
                    sig.avoid_mood::text AS avoid_mood,
                    sig.summary,
                    sig.analyzed_at,
                    b.isbn13,
                    b.title,
                    b.author,
                    b.category_code
                FROM book.user_review_preference_signals sig
                JOIN book.user_book_shelves ubs
                    ON ubs.user_id = sig.user_id
                   AND ubs.book_id = sig.book_id
                   AND (ubs.review_content IS NOT NULL OR ubs.review_rating IS NOT NULL OR ubs.shelf_type = 'READ')
                JOIN book.books b ON b.id = sig.book_id
                WHERE sig.user_id = ?
                  AND sig.active = TRUE
                  AND sig.analysis_status = 'SUCCEEDED'
                ORDER BY sig.analyzed_at DESC NULLS LAST, ubs.updated_at DESC
                LIMIT ?
                """, (rs, rowNum) -> {
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("bookId", rs.getLong("book_id"));
            row.put("reviewId", trimToNull(rs.getString("review_id")));
            row.put("rating", toPlainString(rs.getBigDecimal("rating")));
            row.put("overallSentiment", trimToNull(rs.getString("overall_sentiment")));
            row.put("sentimentScore", toPlainString(rs.getBigDecimal("sentiment_score")));
            row.put("confidence", toPlainString(rs.getBigDecimal("confidence")));
            row.put("likedAspects", trimToNull(rs.getString("liked_aspects")));
            row.put("dislikedAspects", trimToNull(rs.getString("disliked_aspects")));
            row.put("preferenceTerms", trimToNull(rs.getString("preference_terms")));
            row.put("avoidTerms", trimToNull(rs.getString("avoid_terms")));
            row.put("preferredMood", trimToNull(rs.getString("preferred_mood")));
            row.put("avoidMood", trimToNull(rs.getString("avoid_mood")));
            row.put("summary", truncate(rs.getString("summary"), 500));
            row.put("analyzedAt", toIsoString(rs, "analyzed_at"));
            row.put("isbn13", trimToNull(rs.getString("isbn13")));
            row.put("title", truncate(rs.getString("title"), 120));
            row.put("author", truncate(rs.getString("author"), 120));
            row.put("categoryCode", trimToNull(rs.getString("category_code")));
            return compact(row);
        }, userId, MAX_REVIEW_PREFERENCE_SIGNALS);
    }

    private Map<String, Object> findPreferenceProfile(UUID userId) {
        List<Map<String, Object>> rows = safeQuery("""
                SELECT profile_version,
                       profile_summary,
                       profile_text,
                       positive_terms::text,
                       negative_terms::text,
                       preferred_genres::text,
                       avoided_genres::text,
                       liked_aspects::text,
                       disliked_aspects::text,
                       high_signal_book_ids::text,
                       low_signal_book_ids::text,
                       source_counts::text,
                       vector_collection_name,
                       vector_point_id,
                       embedding_model,
                       embedding_dimension,
                       build_status,
                       built_at
                FROM book.user_preference_profiles
                WHERE user_id = ?
                """, (rs, rowNum) -> {
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("profileVersion", rs.getInt("profile_version"));
            row.put("profileSummary", truncate(rs.getString("profile_summary"), 1200));
            row.put("profileText", truncate(rs.getString("profile_text"), 2000));
            row.put("positiveTerms", trimToNull(rs.getString("positive_terms")));
            row.put("negativeTerms", trimToNull(rs.getString("negative_terms")));
            row.put("preferredGenres", trimToNull(rs.getString("preferred_genres")));
            row.put("avoidedGenres", trimToNull(rs.getString("avoided_genres")));
            row.put("likedAspects", trimToNull(rs.getString("liked_aspects")));
            row.put("dislikedAspects", trimToNull(rs.getString("disliked_aspects")));
            row.put("highSignalBookIds", trimToNull(rs.getString("high_signal_book_ids")));
            row.put("lowSignalBookIds", trimToNull(rs.getString("low_signal_book_ids")));
            row.put("sourceCounts", trimToNull(rs.getString("source_counts")));
            row.put("vectorCollectionName", trimToNull(rs.getString("vector_collection_name")));
            row.put("vectorPointId", trimToNull(rs.getString("vector_point_id")));
            row.put("embeddingModel", trimToNull(rs.getString("embedding_model")));
            row.put("embeddingDimension", rs.getObject("embedding_dimension"));
            row.put("buildStatus", trimToNull(rs.getString("build_status")));
            row.put("builtAt", toIsoString(rs, "built_at"));
            return compact(row);
        }, userId);
        return rows.isEmpty() ? Map.of() : rows.getFirst();
    }

    private Map<String, Object> buildReviewRatingPreferenceProfile(
            List<Map<String, Object>> reviewPreferenceSignals,
            Map<String, Object> preferenceProfile
    ) {
        Map<String, Object> profile = new LinkedHashMap<>();
        profile.put("signal_available", !reviewPreferenceSignals.isEmpty());
        profile.put("signals", reviewPreferenceSignals);
        profile.put("positive_terms", preferenceProfile.get("positiveTerms"));
        profile.put("negative_terms", preferenceProfile.get("negativeTerms"));
        profile.put("liked_aspects", preferenceProfile.get("likedAspects"));
        profile.put("disliked_aspects", preferenceProfile.get("dislikedAspects"));
        profile.put("vector_collection_name", preferenceProfile.get("vectorCollectionName"));
        profile.put("vector_point_id", preferenceProfile.get("vectorPointId"));
        profile.put("embedding_model", preferenceProfile.get("embeddingModel"));
        profile.put("embedding_dimension", preferenceProfile.get("embeddingDimension"));
        profile.put("build_status", preferenceProfile.get("buildStatus"));
        return compact(profile);
    }

    private List<Map<String, Object>> findPreferredLibraries(UUID userId) {
        return safeQuery("""
                SELECT
                    upl.lib_code,
                    upl.priority,
                    l.lib_name,
                    l.address
                FROM book.user_preferred_libraries upl
                LEFT JOIN book.libraries l ON l.lib_code = upl.lib_code
                WHERE upl.user_id = ?
                ORDER BY upl.priority ASC, upl.updated_at DESC
                LIMIT ?
                """, (rs, rowNum) -> {
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("libCode", trimToNull(rs.getString("lib_code")));
            row.put("priority", rs.getInt("priority"));
            row.put("libName", trimToNull(rs.getString("lib_name")));
            row.put("address", truncate(rs.getString("address"), 200));
            return compact(row);
        }, userId, MAX_PREFERRED_LIBRARIES);
    }

    private Map<String, Object> toBookProfileRow(ResultSet rs, boolean includeReview) throws SQLException {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("shelfType", trimToNull(rs.getString("shelf_type")));
        row.put("isbn13", trimToNull(rs.getString("isbn13")));
        row.put("title", truncate(rs.getString("title"), 120));
        row.put("author", truncate(rs.getString("author"), 120));
        row.put("publisher", truncate(rs.getString("publisher"), 120));
        row.put("categoryCode", trimToNull(rs.getString("category_code")));
        row.put("description", truncate(rs.getString("description"), 300));
        row.put("coverUrl", trimToNull(rs.getString("cover_url")));
        row.put("note", truncate(rs.getString("note"), 300));
        row.put("updatedAt", toIsoString(rs, "updated_at"));
        if (includeReview) {
            row.put("reviewRating", toPlainString(rs.getBigDecimal("review_rating")));
            row.put("reviewContent", truncate(rs.getString("review_content"), 500));
            row.put("completedAt", toIsoString(rs, "completed_at"));
        }
        return compact(row);
    }

    private String buildSummary(
            Map<String, Object> onboardingProfile,
            List<Map<String, Object>> interestCategories,
            List<Map<String, Object>> interestKeywords,
            List<Map<String, Object>> shelfBooks,
            List<Map<String, Object>> reviewedBooks
    ) {
        StringBuilder summary = new StringBuilder();
        Object profileSummary = onboardingProfile.get("profileSummary");
        if (profileSummary instanceof String value && !value.isBlank()) {
            summary.append(value);
        }

        appendLabels(summary, "선호 장르", interestCategories, "label", 8);
        appendLabels(summary, "관심 키워드", interestKeywords, "keyword", 8);
        appendLabels(summary, "서재 도서", shelfBooks, "title", 8);
        appendLabels(summary, "리뷰 도서", reviewedBooks, "title", 6);
        return truncate(summary.toString(), 1200);
    }

    private void appendLabels(StringBuilder summary, String title, List<Map<String, Object>> rows, String key, int limit) {
        List<String> labels = rows.stream()
                .map(row -> row.get(key))
                .filter(String.class::isInstance)
                .map(String.class::cast)
                .filter(value -> !value.isBlank())
                .distinct()
                .limit(limit)
                .toList();
        if (labels.isEmpty()) {
            return;
        }
        if (summary.length() > 0) {
            summary.append(" / ");
        }
        summary.append(title).append(": ").append(String.join(", ", labels));
    }

    private List<Map<String, Object>> safeQuery(String sql, RowMapper<Map<String, Object>> mapper, Object... args) {
        try {
            return jdbcTemplate.query(sql, mapper, args);
        } catch (DataAccessException ex) {
            log.warn("User recommendation profile lookup skipped. reason={}", ex.getMostSpecificCause().getMessage());
            return List.of();
        }
    }

    private Map<String, Object> compact(Map<String, Object> source) {
        Map<String, Object> result = new LinkedHashMap<>();
        source.forEach((key, value) -> {
            if (value == null) {
                return;
            }
            if (value instanceof String text && text.isBlank()) {
                return;
            }
            result.put(key, value);
        });
        return result;
    }

    private String firstNonBlank(String... values) {
        for (String value : values) {
            String normalized = trimToNull(value);
            if (normalized != null) {
                return normalized;
            }
        }
        return null;
    }

    private String trimToNull(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        return value.trim();
    }

    private String truncate(String value, int maxLength) {
        String normalized = trimToNull(value);
        if (normalized == null) {
            return null;
        }
        if (normalized.length() <= maxLength) {
            return normalized;
        }
        return normalized.substring(0, maxLength) + "...";
    }

    private String toPlainString(BigDecimal value) {
        return value == null ? null : value.stripTrailingZeros().toPlainString();
    }

    private Long nullableLong(ResultSet rs, String columnName) throws SQLException {
        long value = rs.getLong(columnName);
        return rs.wasNull() ? null : value;
    }

    private String toIsoString(ResultSet rs, String columnName) throws SQLException {
        OffsetDateTime value = rs.getObject(columnName, OffsetDateTime.class);
        return value == null ? null : value.toString();
    }
}
