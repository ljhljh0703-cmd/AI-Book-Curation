package com.taeo.bookcuration.recommendation.profile.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.taeo.bookcuration.chat.client.AiRecommendationClient;
import com.taeo.bookcuration.chat.client.AiRecommendationClient.ReviewPreferenceAnalysisRequest;
import com.taeo.bookcuration.chat.client.AiRecommendationClient.ReviewPreferenceAnalysisResponse;
import com.taeo.bookcuration.chat.client.AiRecommendationClient.UserPreferenceProfileVectorizeRequest;
import com.taeo.bookcuration.chat.client.AiRecommendationClient.UserPreferenceProfileVectorizeResponse;
import com.taeo.bookcuration.user.entity.UserBookShelfEntity;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class UserPreferenceProfileBuildService {

    private static final TypeReference<List<String>> STRING_LIST_TYPE = new TypeReference<>() {};
    private static final int MAX_PROFILE_TERMS = 40;
    private static final int MAX_PROFILE_BOOK_IDS = 60;
    private static final String DEFAULT_EMBEDDING_MODEL = "KURE";

    private final JdbcTemplate jdbcTemplate;
    private final ObjectMapper objectMapper;
    private final AiRecommendationClient aiRecommendationClient;

    /**
     * 수정 포인트: 리뷰/평점 저장 성공 후 별도 트랜잭션에서 감성분석과 프로필 갱신을 수행합니다.
     * 분석 실패가 기존 리뷰 저장 기능을 롤백하지 않도록 모든 예외를 흡수하고 FAILED 상태를 남깁니다.
     */
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void analyzeReviewAndRebuildProfile(UUID userId, UserBookShelfEntity shelf) {
        if (shelf == null || shelf.getReviewRating() == null || isBlank(shelf.getReviewContent())) {
            return;
        }

        Long bookId = shelf.getBookId();
        Long shelfId = shelf.getId();
        String reviewId = "shelf:" + shelfId;
        Map<String, Object> bookMetadata = findBookMetadata(bookId);

        markReviewSignalRunning(userId, bookId, shelfId, reviewId, shelf.getReviewRating());
        try {
            ReviewPreferenceAnalysisResponse response = aiRecommendationClient.analyzeReviewPreference(
                    new ReviewPreferenceAnalysisRequest(
                            userId.toString(),
                            bookId,
                            reviewId,
                            shelf.getReviewRating(),
                            shelf.getReviewContent(),
                            bookMetadata
                    )
            );
            upsertReviewSignal(userId, bookId, shelfId, reviewId, shelf.getReviewRating(), response);
        } catch (Exception ex) {
            log.warn("Review preference analysis failed. userId={}, bookId={}, reason={}", userId, bookId, ex.getMessage());
            markReviewSignalFailed(userId, bookId, shelfId, reviewId, shelf.getReviewRating(), ex.getMessage());
        }

        rebuildUserProfile(userId);
    }

    /**
     * 수정 포인트: 관심/읽는중/비선호/프로필 변경처럼 리뷰 분석이 필요 없는 행동은 사용자 프로필만 재집계합니다.
     */
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void rebuildUserProfileSafely(UUID userId) {
        try {
            rebuildUserProfile(userId);
        } catch (Exception ex) {
            log.warn("User preference profile rebuild skipped. userId={}, reason={}", userId, ex.getMessage());
        }
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void deactivateReviewSignalAndRebuild(UUID userId, Long bookId) {
        try {
            jdbcTemplate.update("""
                    UPDATE book.user_review_preference_signals
                    SET active = FALSE,
                        analysis_status = 'SKIPPED',
                        analysis_error_message = 'review or shelf was removed',
                        updated_at = NOW()
                    WHERE user_id = ? AND book_id = ?
                    """, userId, bookId);
        } catch (DataAccessException ex) {
            log.warn("Review preference signal deactivation skipped. userId={}, bookId={}, reason={}", userId, bookId, mostSpecificMessage(ex));
        }
        rebuildUserProfileSafely(userId);
    }

    @Transactional
    public Map<String, Object> rebuildUserProfile(UUID userId) {
        List<ReviewSignal> reviewSignals = findSucceededReviewSignals(userId);
        UserBaseProfile baseProfile = findBaseProfile(userId);
        List<GenreSignal> genres = findGenreSignals(userId);
        List<BookSignal> shelfBooks = findShelfBookSignals(userId);

        UserPreferenceProfile profile = aggregateProfile(userId, baseProfile, genres, shelfBooks, reviewSignals);
        int profileVersion = upsertPreferenceProfileRunning(profile);
        profile.profileVersion = profileVersion;

        try {
            UserPreferenceProfileVectorizeResponse response = aiRecommendationClient.vectorizeUserPreferenceProfile(
                    new UserPreferenceProfileVectorizeRequest(
                            userId.toString(),
                            profileVersion,
                            profile.profileText,
                            DEFAULT_EMBEDDING_MODEL
                    )
            );
            updateProfileBuildSucceeded(userId, response);
            return Map.of(
                    "userId", userId.toString(),
                    "profileVersion", profileVersion,
                    "buildStatus", "SUCCEEDED",
                    "vectorPointId", nullToEmpty(response == null ? null : response.pointId())
            );
        } catch (Exception ex) {
            log.warn("User preference profile vectorize failed. userId={}, reason={}", userId, ex.getMessage());
            updateProfileBuildFailed(userId, ex.getMessage());
            return Map.of(
                    "userId", userId.toString(),
                    "profileVersion", profileVersion,
                    "buildStatus", "FAILED",
                    "errorMessage", nullToEmpty(ex.getMessage())
            );
        }
    }

    @Transactional
    public Map<String, Object> backfillReviewSignals(int limit) {
        List<ReviewBackfillTarget> targets = findReviewBackfillTargets(limit, false);
        int succeeded = 0;
        int failed = 0;
        for (ReviewBackfillTarget target : targets) {
            try {
                analyzeReviewTarget(target);
                rebuildUserProfileSafely(target.userId());
                succeeded++;
            } catch (Exception ex) {
                failed++;
                log.warn("Review signal backfill item failed. shelfId={}, reason={}", target.shelfId(), ex.getMessage());
            }
        }
        return Map.of("requested", limit, "processed", targets.size(), "succeeded", succeeded, "failed", failed);
    }

    @Transactional
    public Map<String, Object> retryFailedReviewSignals(int limit) {
        List<ReviewBackfillTarget> targets = findReviewBackfillTargets(limit, true);
        int succeeded = 0;
        int failed = 0;
        for (ReviewBackfillTarget target : targets) {
            try {
                analyzeReviewTarget(target);
                rebuildUserProfileSafely(target.userId());
                succeeded++;
            } catch (Exception ex) {
                failed++;
                log.warn("Review signal retry item failed. shelfId={}, reason={}", target.shelfId(), ex.getMessage());
            }
        }
        return Map.of("requested", limit, "processed", targets.size(), "succeeded", succeeded, "failed", failed);
    }

    private void analyzeReviewTarget(ReviewBackfillTarget target) {
        String reviewId = "shelf:" + target.shelfId();
        markReviewSignalRunning(target.userId(), target.bookId(), target.shelfId(), reviewId, target.rating());
        try {
            ReviewPreferenceAnalysisResponse response = aiRecommendationClient.analyzeReviewPreference(
                    new ReviewPreferenceAnalysisRequest(
                            target.userId().toString(),
                            target.bookId(),
                            reviewId,
                            target.rating(),
                            target.reviewContent(),
                            target.bookMetadata()
                    )
            );
            upsertReviewSignal(target.userId(), target.bookId(), target.shelfId(), reviewId, target.rating(), response);
        } catch (Exception ex) {
            markReviewSignalFailed(target.userId(), target.bookId(), target.shelfId(), reviewId, target.rating(), ex.getMessage());
            throw ex;
        }
    }

    private void markReviewSignalRunning(UUID userId, Long bookId, Long shelfId, String reviewId, BigDecimal rating) {
        try {
            jdbcTemplate.update("""
                    INSERT INTO book.user_review_preference_signals (
                        user_id, book_id, review_id, shelf_id, rating,
                        overall_sentiment, sentiment_score, confidence,
                        analysis_status, active, analysis_error_message, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 'neutral', 0, 0, 'RUNNING', TRUE, NULL, NOW(), NOW())
                    ON CONFLICT (user_id, book_id) DO UPDATE SET
                        review_id = EXCLUDED.review_id,
                        shelf_id = EXCLUDED.shelf_id,
                        rating = EXCLUDED.rating,
                        analysis_status = 'RUNNING',
                        analysis_error_message = NULL,
                        active = TRUE,
                        updated_at = NOW()
                    """, userId, bookId, reviewId, shelfId, rating);
        } catch (DataAccessException ex) {
            log.warn("Review preference signal RUNNING mark skipped. reason={}", mostSpecificMessage(ex));
        }
    }

    private void upsertReviewSignal(UUID userId, Long bookId, Long shelfId, String reviewId, BigDecimal rating, ReviewPreferenceAnalysisResponse response) {
        ReviewPreferenceAnalysisResponse safe = response == null
                ? new ReviewPreferenceAnalysisResponse("neutral", 0.0, 0.0, List.of(), List.of(), List.of(), List.of(), List.of(), List.of(), null, "FAILED", "empty response")
                : response;
        String status = normalizeAnalysisStatus(safe.analysisStatus(), safe.analysisErrorMessage());
        jdbcTemplate.update("""
                INSERT INTO book.user_review_preference_signals (
                    user_id, book_id, review_id, shelf_id, rating,
                    overall_sentiment, sentiment_score, confidence,
                    liked_aspects, disliked_aspects, preference_terms, avoid_terms,
                    preferred_mood, avoid_mood, summary,
                    analysis_status, analysis_error_message, active, analyzed_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?::jsonb, ?::jsonb, ?::jsonb, ?::jsonb, ?::jsonb, ?::jsonb, ?, ?, ?, TRUE, NOW(), NOW(), NOW())
                ON CONFLICT (user_id, book_id) DO UPDATE SET
                    review_id = EXCLUDED.review_id,
                    shelf_id = EXCLUDED.shelf_id,
                    rating = EXCLUDED.rating,
                    overall_sentiment = EXCLUDED.overall_sentiment,
                    sentiment_score = EXCLUDED.sentiment_score,
                    confidence = EXCLUDED.confidence,
                    liked_aspects = EXCLUDED.liked_aspects,
                    disliked_aspects = EXCLUDED.disliked_aspects,
                    preference_terms = EXCLUDED.preference_terms,
                    avoid_terms = EXCLUDED.avoid_terms,
                    preferred_mood = EXCLUDED.preferred_mood,
                    avoid_mood = EXCLUDED.avoid_mood,
                    summary = EXCLUDED.summary,
                    analysis_status = EXCLUDED.analysis_status,
                    analysis_error_message = EXCLUDED.analysis_error_message,
                    active = TRUE,
                    analyzed_at = NOW(),
                    updated_at = NOW()
                """,
                userId,
                bookId,
                reviewId,
                shelfId,
                rating,
                normalizeSentiment(safe.overallSentiment()),
                clamp(safe.sentimentScore()),
                clamp(safe.confidence()),
                toJsonArray(safe.likedAspects()),
                toJsonArray(safe.dislikedAspects()),
                toJsonArray(safe.preferenceTerms()),
                toJsonArray(safe.avoidTerms()),
                toJsonArray(safe.preferredMood()),
                toJsonArray(safe.avoidMood()),
                trimToNull(safe.summary()),
                status,
                trimToNull(safe.analysisErrorMessage())
        );
    }

    private void markReviewSignalFailed(UUID userId, Long bookId, Long shelfId, String reviewId, BigDecimal rating, String message) {
        try {
            jdbcTemplate.update("""
                    INSERT INTO book.user_review_preference_signals (
                        user_id, book_id, review_id, shelf_id, rating,
                        overall_sentiment, sentiment_score, confidence,
                        analysis_status, analysis_error_message, active, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 'neutral', 0, 0, 'FAILED', ?, TRUE, NOW(), NOW())
                    ON CONFLICT (user_id, book_id) DO UPDATE SET
                        review_id = EXCLUDED.review_id,
                        shelf_id = EXCLUDED.shelf_id,
                        rating = EXCLUDED.rating,
                        analysis_status = 'FAILED',
                        analysis_error_message = EXCLUDED.analysis_error_message,
                        active = TRUE,
                        updated_at = NOW()
                    """, userId, bookId, reviewId, shelfId, rating, truncate(message, 1000));
        } catch (DataAccessException ex) {
            log.warn("Review preference signal FAILED mark skipped. reason={}", mostSpecificMessage(ex));
        }
    }

    private int upsertPreferenceProfileRunning(UserPreferenceProfile profile) {
        Integer version = jdbcTemplate.queryForObject("""
                INSERT INTO book.user_preference_profiles (
                    user_id, profile_version, profile_summary, profile_text,
                    positive_terms, negative_terms, preferred_genres, avoided_genres,
                    liked_aspects, disliked_aspects, high_signal_book_ids, low_signal_book_ids,
                    source_counts, build_status, build_error_message, created_at, updated_at
                ) VALUES (?, 1, ?, ?, ?::jsonb, ?::jsonb, ?::jsonb, ?::jsonb, ?::jsonb, ?::jsonb, ?::jsonb, ?::jsonb, ?::jsonb, 'RUNNING', NULL, NOW(), NOW())
                ON CONFLICT (user_id) DO UPDATE SET
                    profile_version = book.user_preference_profiles.profile_version + 1,
                    profile_summary = EXCLUDED.profile_summary,
                    profile_text = EXCLUDED.profile_text,
                    positive_terms = EXCLUDED.positive_terms,
                    negative_terms = EXCLUDED.negative_terms,
                    preferred_genres = EXCLUDED.preferred_genres,
                    avoided_genres = EXCLUDED.avoided_genres,
                    liked_aspects = EXCLUDED.liked_aspects,
                    disliked_aspects = EXCLUDED.disliked_aspects,
                    high_signal_book_ids = EXCLUDED.high_signal_book_ids,
                    low_signal_book_ids = EXCLUDED.low_signal_book_ids,
                    source_counts = EXCLUDED.source_counts,
                    build_status = 'RUNNING',
                    build_error_message = NULL,
                    updated_at = NOW()
                RETURNING profile_version
                """, Integer.class,
                profile.userId,
                profile.profileSummary,
                profile.profileText,
                toJsonArray(profile.positiveTerms),
                toJsonArray(profile.negativeTerms),
                toJsonArray(profile.preferredGenres),
                toJsonArray(profile.avoidedGenres),
                toJsonArray(profile.likedAspects),
                toJsonArray(profile.dislikedAspects),
                toJsonArray(profile.highSignalBookIds),
                toJsonArray(profile.lowSignalBookIds),
                toJsonObject(profile.sourceCounts)
        );
        return version == null ? 1 : version;
    }

    private void updateProfileBuildSucceeded(UUID userId, UserPreferenceProfileVectorizeResponse response) {
        if (response == null || isBlank(response.pointId())) {
            updateProfileBuildFailed(userId, "empty vectorize response");
            return;
        }
        jdbcTemplate.update("""
                UPDATE book.user_preference_profiles
                SET vector_collection_name = ?,
                    vector_point_id = ?,
                    embedding_model = ?,
                    embedding_dimension = ?,
                    build_status = 'SUCCEEDED',
                    build_error_message = NULL,
                    built_at = NOW(),
                    updated_at = NOW()
                WHERE user_id = ?
                """,
                response.collectionName(),
                response.pointId(),
                response.embeddingModel(),
                response.embeddingDimension(),
                userId
        );
    }

    private void updateProfileBuildFailed(UUID userId, String message) {
        try {
            jdbcTemplate.update("""
                    UPDATE book.user_preference_profiles
                    SET build_status = 'FAILED',
                        build_error_message = ?,
                        updated_at = NOW()
                    WHERE user_id = ?
                    """, truncate(message, 1000), userId);
        } catch (DataAccessException ex) {
            log.warn("User preference profile FAILED mark skipped. reason={}", mostSpecificMessage(ex));
        }
    }

    private UserPreferenceProfile aggregateProfile(
            UUID userId,
            UserBaseProfile baseProfile,
            List<GenreSignal> genres,
            List<BookSignal> shelfBooks,
            List<ReviewSignal> reviewSignals
    ) {
        Set<String> positiveTerms = new LinkedHashSet<>();
        Set<String> negativeTerms = new LinkedHashSet<>();
        Set<String> preferredGenres = new LinkedHashSet<>();
        Set<String> avoidedGenres = new LinkedHashSet<>();
        Set<String> likedAspects = new LinkedHashSet<>();
        Set<String> dislikedAspects = new LinkedHashSet<>();
        Set<String> highSignalBookIds = new LinkedHashSet<>();
        Set<String> lowSignalBookIds = new LinkedHashSet<>();

        genres.stream().map(GenreSignal::label).filter(Objects::nonNull).forEach(preferredGenres::add);
        if (!isBlank(baseProfile.readingPurpose())) {
            positiveTerms.add(baseProfile.readingPurpose());
        }

        for (BookSignal book : shelfBooks) {
            if ("INTERESTED".equals(book.shelfType()) || "READING".equals(book.shelfType())) {
                addIfPresent(positiveTerms, book.title());
                addIfPresent(highSignalBookIds, String.valueOf(book.bookId()));
            } else if ("NOT_INTERESTED".equals(book.shelfType())) {
                addIfPresent(negativeTerms, book.title());
                addIfPresent(lowSignalBookIds, String.valueOf(book.bookId()));
            }
        }

        for (ReviewSignal signal : reviewSignals) {
            if (signal.rating() != null && signal.rating().compareTo(new BigDecimal("4.0")) >= 0) {
                highSignalBookIds.add(String.valueOf(signal.bookId()));
            }
            if (signal.rating() != null && signal.rating().compareTo(new BigDecimal("2.0")) <= 0) {
                lowSignalBookIds.add(String.valueOf(signal.bookId()));
            }
            likedAspects.addAll(signal.likedAspects());
            dislikedAspects.addAll(signal.dislikedAspects());
            positiveTerms.addAll(signal.preferenceTerms());
            negativeTerms.addAll(signal.avoidTerms());
            positiveTerms.addAll(signal.preferredMood());
            negativeTerms.addAll(signal.avoidMood());
        }

        List<String> positive = limit(positiveTerms, MAX_PROFILE_TERMS);
        List<String> negative = limit(negativeTerms, MAX_PROFILE_TERMS);
        List<String> preferredGenreList = limit(preferredGenres, MAX_PROFILE_TERMS);
        List<String> avoidedGenreList = limit(avoidedGenres, MAX_PROFILE_TERMS);
        List<String> liked = limit(likedAspects, MAX_PROFILE_TERMS);
        List<String> disliked = limit(dislikedAspects, MAX_PROFILE_TERMS);
        List<String> highBookIds = limit(highSignalBookIds, MAX_PROFILE_BOOK_IDS);
        List<String> lowBookIds = limit(lowSignalBookIds, MAX_PROFILE_BOOK_IDS);

        Map<String, Object> sourceCounts = new LinkedHashMap<>();
        sourceCounts.put("reviewSignals", reviewSignals.size());
        sourceCounts.put("shelfBooks", shelfBooks.size());
        sourceCounts.put("preferredGenres", genres.size());
        sourceCounts.put("hasReadingPurpose", !isBlank(baseProfile.readingPurpose()));

        String profileSummary = buildProfileSummary(baseProfile, positive, negative, preferredGenreList, liked, disliked);
        String profileText = buildProfileText(baseProfile, positive, negative, preferredGenreList, liked, disliked);

        return new UserPreferenceProfile(
                userId,
                1,
                profileSummary,
                profileText,
                positive,
                negative,
                preferredGenreList,
                avoidedGenreList,
                liked,
                disliked,
                highBookIds,
                lowBookIds,
                sourceCounts
        );
    }

    private String buildProfileSummary(UserBaseProfile baseProfile, List<String> positive, List<String> negative, List<String> genres, List<String> liked, List<String> disliked) {
        List<String> parts = new ArrayList<>();
        if (!isBlank(baseProfile.readingPurpose())) {
            parts.add("독서목적: " + baseProfile.readingPurpose());
        }
        if (!genres.isEmpty()) {
            parts.add("선호 장르: " + String.join(", ", genres.stream().limit(6).toList()));
        }
        if (!liked.isEmpty()) {
            parts.add("좋아한 요소: " + String.join(", ", liked.stream().limit(6).toList()));
        }
        if (!disliked.isEmpty()) {
            parts.add("피해야 할 요소: " + String.join(", ", disliked.stream().limit(6).toList()));
        }
        if (parts.isEmpty() && !positive.isEmpty()) {
            parts.add("선호 요소: " + String.join(", ", positive.stream().limit(8).toList()));
        }
        if (parts.isEmpty() && !negative.isEmpty()) {
            parts.add("비선호 요소: " + String.join(", ", negative.stream().limit(8).toList()));
        }
        return truncate(String.join(" / ", parts), 1200);
    }

    private String buildProfileText(UserBaseProfile baseProfile, List<String> positive, List<String> negative, List<String> genres, List<String> liked, List<String> disliked) {
        StringBuilder builder = new StringBuilder();
        if (!isBlank(baseProfile.readingPurpose())) {
            builder.append("사용자의 독서 목적은 ").append(baseProfile.readingPurpose()).append("입니다.\n");
        }
        if (!genres.isEmpty()) {
            builder.append("선호 장르는 ").append(String.join(", ", genres)).append("입니다.\n");
        }
        if (!positive.isEmpty()) {
            builder.append("선호하는 요소는 ").append(String.join(", ", positive)).append("입니다.\n");
        }
        if (!liked.isEmpty()) {
            builder.append("좋아한 리뷰 요소는 ").append(String.join(", ", liked)).append("입니다.\n");
        }
        if (!negative.isEmpty()) {
            builder.append("피해야 할 요소는 ").append(String.join(", ", negative)).append("입니다.\n");
        }
        if (!disliked.isEmpty()) {
            builder.append("리뷰에서 싫어한 요소는 ").append(String.join(", ", disliked)).append("입니다.\n");
        }
        return truncate(builder.toString(), 3000);
    }

    private UserBaseProfile findBaseProfile(UUID userId) {
        List<UserBaseProfile> rows = jdbcTemplate.query("""
                SELECT reading_purpose, profile_summary
                FROM book.user_profiles
                WHERE user_id = ?
                """, (rs, rowNum) -> new UserBaseProfile(
                trimToNull(rs.getString("reading_purpose")),
                trimToNull(rs.getString("profile_summary"))
        ), userId);
        return rows.isEmpty() ? new UserBaseProfile(null, null) : rows.getFirst();
    }

    private List<GenreSignal> findGenreSignals(UUID userId) {
        return safeQuery("""
                SELECT uic.category_code,
                       COALESCE(bc.category_name, oo.label, uic.category_code) AS label
                FROM book.user_interest_categories uic
                LEFT JOIN book.book_categories bc ON bc.category_code = uic.category_code
                LEFT JOIN book.onboarding_options oo ON oo.option_key = uic.category_code
                WHERE uic.user_id = ?
                ORDER BY uic.weight DESC, uic.updated_at DESC
                LIMIT 30
                """, (rs, rowNum) -> new GenreSignal(trimToNull(rs.getString("category_code")), trimToNull(rs.getString("label"))), userId);
    }

    private List<BookSignal> findShelfBookSignals(UUID userId) {
        return safeQuery("""
                SELECT ubs.book_id, ubs.shelf_type, b.title
                FROM book.user_book_shelves ubs
                JOIN book.books b ON b.id = ubs.book_id
                WHERE ubs.user_id = ?
                ORDER BY ubs.updated_at DESC
                LIMIT 80
                """, (rs, rowNum) -> new BookSignal(rs.getLong("book_id"), trimToNull(rs.getString("shelf_type")), trimToNull(rs.getString("title"))), userId);
    }

    private List<ReviewSignal> findSucceededReviewSignals(UUID userId) {
        return safeQuery("""
                SELECT book_id, rating, overall_sentiment,
                       liked_aspects::text, disliked_aspects::text,
                       preference_terms::text, avoid_terms::text,
                       preferred_mood::text, avoid_mood::text
                FROM book.user_review_preference_signals
                WHERE user_id = ?
                  AND active = TRUE
                  AND analysis_status = 'SUCCEEDED'
                ORDER BY analyzed_at DESC NULLS LAST, updated_at DESC
                LIMIT 80
                """, (rs, rowNum) -> new ReviewSignal(
                rs.getLong("book_id"),
                rs.getBigDecimal("rating"),
                trimToNull(rs.getString("overall_sentiment")),
                readStringList(rs.getString("liked_aspects")),
                readStringList(rs.getString("disliked_aspects")),
                readStringList(rs.getString("preference_terms")),
                readStringList(rs.getString("avoid_terms")),
                readStringList(rs.getString("preferred_mood")),
                readStringList(rs.getString("avoid_mood"))
        ), userId);
    }

    private List<ReviewBackfillTarget> findReviewBackfillTargets(int limit, boolean failedOnly) {
        String filter = failedOnly
                ? "AND COALESCE(sig.analysis_status, 'FAILED') = 'FAILED'"
                : "AND sig.id IS NULL";
        String sql = """
                SELECT ubs.id AS shelf_id,
                       ubs.user_id,
                       ubs.book_id,
                       ubs.review_content,
                       ubs.review_rating,
                       b.isbn13,
                       b.title,
                       b.author,
                       b.publisher,
                       b.category_code,
                       b.description
                FROM book.user_book_shelves ubs
                JOIN book.books b ON b.id = ubs.book_id
                LEFT JOIN book.user_review_preference_signals sig
                  ON sig.user_id = ubs.user_id AND sig.book_id = ubs.book_id
                WHERE ubs.review_content IS NOT NULL
                  AND ubs.review_rating IS NOT NULL
                  %s
                ORDER BY ubs.updated_at DESC
                LIMIT ?
                """.formatted(filter);
        return safeQuery(sql, (rs, rowNum) -> new ReviewBackfillTarget(
                rs.getLong("shelf_id"),
                UUID.fromString(rs.getString("user_id")),
                rs.getLong("book_id"),
                rs.getString("review_content"),
                rs.getBigDecimal("review_rating"),
                bookMetadataFromResultSet(rs)
        ), Math.max(1, Math.min(limit, 100)));
    }

    private Map<String, Object> findBookMetadata(Long bookId) {
        List<Map<String, Object>> rows = jdbcTemplate.query("""
                SELECT isbn13, title, author, publisher, category_code, description
                FROM book.books
                WHERE id = ?
                """, (rs, rowNum) -> bookMetadataFromResultSet(rs), bookId);
        return rows.isEmpty() ? Map.of() : rows.getFirst();
    }

    private Map<String, Object> bookMetadataFromResultSet(ResultSet rs) throws SQLException {
        Map<String, Object> book = new LinkedHashMap<>();
        book.put("isbn13", trimToNull(rs.getString("isbn13")));
        book.put("title", trimToNull(rs.getString("title")));
        book.put("author", trimToNull(rs.getString("author")));
        book.put("publisher", trimToNull(rs.getString("publisher")));
        book.put("categoryCode", trimToNull(rs.getString("category_code")));
        book.put("description", truncate(rs.getString("description"), 800));
        return compact(book);
    }

    private <T> List<T> safeQuery(String sql, org.springframework.jdbc.core.RowMapper<T> mapper, Object... args) {
        try {
            return jdbcTemplate.query(sql, mapper, args);
        } catch (DataAccessException ex) {
            log.warn("Preference profile query skipped. reason={}", mostSpecificMessage(ex));
            return List.of();
        }
    }

    private List<String> readStringList(String json) {
        if (isBlank(json)) {
            return List.of();
        }
        try {
            return objectMapper.readValue(json, STRING_LIST_TYPE);
        } catch (JsonProcessingException ex) {
            return List.of();
        }
    }

    private String toJsonArray(List<String> values) {
        try {
            List<String> safe = values == null ? List.of() : values.stream()
                    .filter(Objects::nonNull)
                    .map(String::trim)
                    .filter(value -> !value.isBlank())
                    .distinct()
                    .limit(MAX_PROFILE_TERMS)
                    .toList();
            return objectMapper.writeValueAsString(safe);
        } catch (JsonProcessingException ex) {
            return "[]";
        }
    }

    private String toJsonObject(Map<String, Object> values) {
        try {
            return objectMapper.writeValueAsString(values == null ? Map.of() : values);
        } catch (JsonProcessingException ex) {
            return "{}";
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

    private List<String> limit(Set<String> source, int limit) {
        return source.stream()
                .filter(Objects::nonNull)
                .map(String::trim)
                .filter(value -> !value.isBlank())
                .distinct()
                .limit(limit)
                .toList();
    }

    private void addIfPresent(Set<String> target, String value) {
        if (!isBlank(value)) {
            target.add(value.trim());
        }
    }

    private String normalizeSentiment(String value) {
        String normalized = value == null ? "neutral" : value.trim().toLowerCase();
        if (List.of("positive", "negative", "mixed", "neutral").contains(normalized)) {
            return normalized;
        }
        return "neutral";
    }

    private String normalizeAnalysisStatus(String status, String errorMessage) {
        if (!isBlank(errorMessage)) {
            return "FAILED";
        }
        String normalized = status == null ? "SUCCEEDED" : status.trim().toUpperCase();
        if (List.of("PENDING", "RUNNING", "SUCCEEDED", "FAILED", "SKIPPED").contains(normalized)) {
            return normalized;
        }
        return "SUCCEEDED";
    }

    private double clamp(Double value) {
        if (value == null || value.isNaN() || value.isInfinite()) {
            return 0.0;
        }
        return Math.max(-1.0, Math.min(1.0, value));
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

    private boolean isBlank(String value) {
        return value == null || value.isBlank();
    }

    private String mostSpecificMessage(DataAccessException ex) {
        return ex.getMostSpecificCause() == null ? ex.getMessage() : ex.getMostSpecificCause().getMessage();
    }

    private String nullToEmpty(String value) {
        return value == null ? "" : value;
    }

    private record UserBaseProfile(String readingPurpose, String profileSummary) {}
    private record GenreSignal(String categoryCode, String label) {}
    private record BookSignal(Long bookId, String shelfType, String title) {}
    private record ReviewSignal(
            Long bookId,
            BigDecimal rating,
            String overallSentiment,
            List<String> likedAspects,
            List<String> dislikedAspects,
            List<String> preferenceTerms,
            List<String> avoidTerms,
            List<String> preferredMood,
            List<String> avoidMood
    ) {}
    private record ReviewBackfillTarget(
            Long shelfId,
            UUID userId,
            Long bookId,
            String reviewContent,
            BigDecimal rating,
            Map<String, Object> bookMetadata
    ) {}

    private static class UserPreferenceProfile {
        private final UUID userId;
        private int profileVersion;
        private final String profileSummary;
        private final String profileText;
        private final List<String> positiveTerms;
        private final List<String> negativeTerms;
        private final List<String> preferredGenres;
        private final List<String> avoidedGenres;
        private final List<String> likedAspects;
        private final List<String> dislikedAspects;
        private final List<String> highSignalBookIds;
        private final List<String> lowSignalBookIds;
        private final Map<String, Object> sourceCounts;

        private UserPreferenceProfile(
                UUID userId,
                int profileVersion,
                String profileSummary,
                String profileText,
                List<String> positiveTerms,
                List<String> negativeTerms,
                List<String> preferredGenres,
                List<String> avoidedGenres,
                List<String> likedAspects,
                List<String> dislikedAspects,
                List<String> highSignalBookIds,
                List<String> lowSignalBookIds,
                Map<String, Object> sourceCounts
        ) {
            this.userId = userId;
            this.profileVersion = profileVersion;
            this.profileSummary = profileSummary;
            this.profileText = profileText;
            this.positiveTerms = positiveTerms;
            this.negativeTerms = negativeTerms;
            this.preferredGenres = preferredGenres;
            this.avoidedGenres = avoidedGenres;
            this.likedAspects = likedAspects;
            this.dislikedAspects = dislikedAspects;
            this.highSignalBookIds = highSignalBookIds;
            this.lowSignalBookIds = lowSignalBookIds;
            this.sourceCounts = sourceCounts;
        }
    }
}
