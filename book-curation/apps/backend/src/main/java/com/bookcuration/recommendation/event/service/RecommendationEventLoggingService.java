package com.taeo.bookcuration.recommendation.event.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.taeo.bookcuration.chat.client.AiRecommendationClient.AiRecommendationResponse;
import com.taeo.bookcuration.chat.client.AiRecommendationClient.BookCandidate;
import com.taeo.bookcuration.recommendation.audience.AudienceLabelBatchService;
import com.taeo.bookcuration.recommendation.event.dto.RecommendationEventDtos.RecommendationEventRequest;
import com.taeo.bookcuration.recommendation.event.dto.RecommendationEventDtos.RecommendationEventResponse;
import com.taeo.bookcuration.recommendation.event.dto.RecommendationEventDtos.UserBehaviorEventType;
import com.taeo.bookcuration.recommendation.service.RecommendationModelSettingService.RecommendationModelSetting;
import com.taeo.bookcuration.user.dto.UserDtos.BookSnapshotRequest;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import java.math.BigDecimal;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class RecommendationEventLoggingService {

    private static final String DEFAULT_RECOMMENDATION_SOURCE = "CHAT_RECOMMENDATION";

    private final JdbcTemplate jdbcTemplate;
    private final ObjectMapper objectMapper;
    private final AudienceLabelBatchService audienceLabelBatchService;

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void startRecommendationRequestSafely(UUID requestId, UUID userId, String query, RecommendationModelSetting modelSetting) {
        try {
            upsertRecommendationRequest(
                    requestId,
                    userId,
                    query,
                    modelSetting == null ? null : modelSetting.embeddingModel(),
                    modelSetting == null ? null : modelSetting.rankingModel(),
                    "PROFILE_VECTOR",
                    "NONE",
                    "NONE",
                    Map.of("status", "STARTED")
            );
        } catch (RuntimeException e) {
            // 수정 포인트: 추천 로그 테이블 미반영/일시 DB 오류가 있어도 추천 API 자체는 실패시키지 않습니다.
            log.warn("Recommendation request start log skipped. requestId={}, userId={}, reason={}", requestId, userId, e.getMessage());
        }
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void logSearchQuerySafely(UUID userId, UUID requestId, String query) {
        try {
            insertBehaviorEvent(
                    userId,
                    requestId,
                    null,
                    UserBehaviorEventType.SEARCH_QUERY,
                    "CHAT_QUERY",
                    query,
                    null,
                    BigDecimal.valueOf(0.1),
                    Map.of("weightHint", "WEAK_INTEREST")
            );
        } catch (RuntimeException e) {
            // 수정 포인트: 검색 질의는 약한 관심 신호로만 누적하고, 기록 실패가 채팅 전송을 막지 않도록 합니다.
            log.warn("Search query behavior log skipped. requestId={}, userId={}, reason={}", requestId, userId, e.getMessage());
        }
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void logRecommendationResponseSafely(UUID requestId, UUID userId, String query, AiRecommendationResponse response) {
        try {
            Map<String, Object> pipeline = response == null || response.pipeline() == null ? Map.of() : response.pipeline();
            upsertRecommendationRequest(
                    requestId,
                    userId,
                    query,
                    response == null ? null : response.embeddingModel(),
                    response == null ? null : response.rankingModel(),
                    response == null ? null : response.personalizationProvider(),
                    response == null ? null : response.sequenceProvider(),
                    response == null ? null : response.rerankerProvider(),
                    pipeline
            );

            if (response == null || response.candidates() == null || response.candidates().isEmpty()) {
                return;
            }

            List<Long> responseBookIds = new ArrayList<>();
            for (int index = 0; index < response.candidates().size(); index++) {
                BookCandidate candidate = response.candidates().get(index);
                int rank = candidate.rank() == null ? index + 1 : candidate.rank();
                Long bookId = upsertBookFromCandidate(candidate).orElse(null);
                if (bookId != null) {
                    responseBookIds.add(bookId);
                    // 수정 포인트: 응답 카드에 이미 구조화 audience label이 포함된 경우 book.books 캐시 row에도 즉시 저장합니다.
                    // 수동 배치 전까지 label 컬럼이 비어 soft reranking에 재사용되지 못하는 문제를 줄입니다.
                    audienceLabelBatchService.cacheReadyLabelFromResponseCard(bookId, candidate.audienceProfile());
                }
                insertRecommendationResult(requestId, userId, query, bookId, candidate, rank);
                insertBehaviorEvent(
                        userId,
                        requestId,
                        bookId,
                        UserBehaviorEventType.RECOMMENDATION_IMPRESSION,
                        DEFAULT_RECOMMENDATION_SOURCE,
                        query,
                        rank,
                        toBigDecimal(candidate.finalScore()),
                        candidateMetadata(candidate)
                );
            }
            enqueueAudienceLabelingAfterCommit(responseBookIds);
        } catch (RuntimeException e) {
            // 수정 포인트: 추천 노출 로그 저장 실패는 운영 중 사용자 추천 응답을 깨지 않도록 격리합니다.
            log.warn("Recommendation response log skipped. requestId={}, userId={}, reason={}", requestId, userId, e.getMessage());
        }
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public RecommendationEventResponse logRecommendationEvent(UUID userId, RecommendationEventRequest request) {
        // 수정 포인트: 프론트가 bookId를 모르는 추천 카드 클릭/상세보기 이벤트는 후보 snapshot만으로 내부 books row를 확보합니다.
        Long bookId = resolveBookId(request.bookId(), request.book()).orElse(null);
        return insertBehaviorEvent(
                userId,
                request.requestId(),
                bookId,
                request.eventType(),
                blankToNull(request.source()) == null ? DEFAULT_RECOMMENDATION_SOURCE : request.source().trim(),
                request.query(),
                request.rank(),
                request.score(),
                request.metadata()
        );
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void logBehaviorEventSafely(
            UUID userId,
            Long bookId,
            UserBehaviorEventType eventType,
            String source,
            UUID requestId,
            String query,
            Integer rank,
            BigDecimal score,
            Map<String, Object> metadata
    ) {
        try {
            insertBehaviorEvent(userId, requestId, bookId, eventType, source, query, rank, score, metadata);
        } catch (RuntimeException e) {
            // 수정 포인트: 기존 관심/비선호/리뷰 저장 성공 여부와 행동 로그 저장 성공 여부를 분리합니다.
            log.warn("User behavior log skipped. eventType={}, userId={}, bookId={}, reason={}", eventType, userId, bookId, e.getMessage());
        }
    }

    private void upsertRecommendationRequest(
            UUID requestId,
            UUID userId,
            String query,
            String embeddingModel,
            String rankingModel,
            String personalizationProvider,
            String sequenceProvider,
            String rerankerProvider,
            Map<String, Object> pipeline
    ) {
        jdbcTemplate.update("""
                INSERT INTO book.recommendation_requests (
                    request_id,
                    user_id,
                    query,
                    embedding_model,
                    ranking_model,
                    personalization_provider,
                    sequence_provider,
                    reranker_provider,
                    pipeline_config
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CAST(? AS jsonb))
                ON CONFLICT (request_id) DO UPDATE SET
                    user_id = COALESCE(EXCLUDED.user_id, book.recommendation_requests.user_id),
                    query = COALESCE(EXCLUDED.query, book.recommendation_requests.query),
                    embedding_model = COALESCE(EXCLUDED.embedding_model, book.recommendation_requests.embedding_model),
                    ranking_model = COALESCE(EXCLUDED.ranking_model, book.recommendation_requests.ranking_model),
                    personalization_provider = COALESCE(EXCLUDED.personalization_provider, book.recommendation_requests.personalization_provider),
                    sequence_provider = COALESCE(EXCLUDED.sequence_provider, book.recommendation_requests.sequence_provider),
                    reranker_provider = COALESCE(EXCLUDED.reranker_provider, book.recommendation_requests.reranker_provider),
                    pipeline_config = COALESCE(EXCLUDED.pipeline_config, book.recommendation_requests.pipeline_config)
                """,
                requestId,
                userId,
                blankToNull(query),
                blankToNull(embeddingModel),
                blankToNull(rankingModel),
                blankToNull(personalizationProvider),
                blankToNull(sequenceProvider),
                blankToNull(rerankerProvider),
                toJson(pipeline == null ? Map.of() : pipeline)
        );
    }

    private void insertRecommendationResult(UUID requestId, UUID userId, String query, Long bookId, BookCandidate candidate, int rank) {
        jdbcTemplate.update("""
                INSERT INTO book.recommendation_results (
                    request_id,
                    user_id,
                    book_id,
                    isbn13,
                    title,
                    rank,
                    qdrant_score,
                    rule_score,
                    profile_vector_score,
                    lightfm_score,
                    sasrec_score,
                    reranker_score,
                    pre_score,
                    final_score,
                    metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CAST(? AS jsonb))
                ON CONFLICT (request_id, rank) DO UPDATE SET
                    book_id = EXCLUDED.book_id,
                    isbn13 = EXCLUDED.isbn13,
                    title = EXCLUDED.title,
                    qdrant_score = EXCLUDED.qdrant_score,
                    rule_score = EXCLUDED.rule_score,
                    profile_vector_score = EXCLUDED.profile_vector_score,
                    lightfm_score = EXCLUDED.lightfm_score,
                    sasrec_score = EXCLUDED.sasrec_score,
                    reranker_score = EXCLUDED.reranker_score,
                    pre_score = EXCLUDED.pre_score,
                    final_score = EXCLUDED.final_score,
                    metadata = EXCLUDED.metadata
                """,
                requestId,
                userId,
                bookId,
                normalizeIsbn13(candidate.isbn()).orElse(null),
                blankToNull(candidate.title()),
                rank,
                toBigDecimal(candidate.qdrantScore()),
                toBigDecimal(candidate.ruleScore()),
                toBigDecimal(candidate.profileVectorScore()),
                toBigDecimal(candidate.lightfmScore()),
                toBigDecimal(candidate.sasrecScore()),
                toBigDecimal(candidate.rerankerScore()),
                toBigDecimal(candidate.preScore()),
                toBigDecimal(candidate.finalScore()),
                toJson(candidateMetadata(candidate))
        );
    }

    private void enqueueAudienceLabelingAfterCommit(List<Long> bookIds) {
        if (bookIds == null || bookIds.isEmpty()) {
            return;
        }
        List<Long> distinctBookIds = bookIds.stream()
                .filter(id -> id != null)
                .distinct()
                .toList();
        if (distinctBookIds.isEmpty()) {
            return;
        }

        Runnable enqueue = () -> audienceLabelBatchService.enqueueResponseCardLabeling(distinctBookIds);
        if (!TransactionSynchronizationManager.isSynchronizationActive()) {
            enqueue.run();
            return;
        }

        // 수정 포인트: book.books upsert 트랜잭션이 커밋된 뒤 비동기 label 생성을 시작합니다.
        // 커밋 전 별도 스레드가 조회하면 방금 캐시한 응답 카드 row를 못 볼 수 있기 때문입니다.
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                enqueue.run();
            }
        });
    }

    private RecommendationEventResponse insertBehaviorEvent(
            UUID userId,
            UUID requestId,
            Long bookId,
            UserBehaviorEventType eventType,
            String source,
            String query,
            Integer rank,
            BigDecimal score,
            Map<String, Object> metadata
    ) {
        return jdbcTemplate.queryForObject("""
                INSERT INTO book.user_behavior_events (
                    user_id,
                    request_id,
                    book_id,
                    event_type,
                    source,
                    query,
                    rank,
                    score,
                    metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CAST(? AS jsonb))
                RETURNING id, request_id, book_id, event_type, created_at
                """,
                (rs, rowNum) -> toEventResponse(rs),
                userId,
                requestId,
                bookId,
                eventType.name(),
                blankToNull(source),
                blankToNull(query),
                rank,
                score,
                toJson(metadata == null ? Map.of() : metadata)
        );
    }

    private RecommendationEventResponse toEventResponse(ResultSet rs) throws SQLException {
        return new RecommendationEventResponse(
                rs.getLong("id"),
                rs.getObject("request_id", UUID.class),
                rs.getObject("book_id", Long.class),
                UserBehaviorEventType.valueOf(rs.getString("event_type")),
                rs.getObject("created_at", OffsetDateTime.class)
        );
    }

    private Optional<Long> resolveBookId(Long bookId, BookSnapshotRequest book) {
        if (bookId != null && existsBookId(bookId)) {
            return Optional.of(bookId);
        }
        if (book == null) {
            return Optional.empty();
        }
        return upsertBookFromSnapshot(book);
    }

    private Optional<Long> upsertBookFromCandidate(BookCandidate candidate) {
        if (candidate == null) {
            return Optional.empty();
        }
        BookSnapshotRequest book = new BookSnapshotRequest(
                null,
                normalizeIsbn13(candidate.isbn()).orElse(null),
                candidate.title(),
                candidate.author(),
                candidate.publisher(),
                candidate.oriCoverS(),
                null,
                candidateMetadata(candidate)
        );
        return upsertBookFromSnapshot(book);
    }

    private Optional<Long> upsertBookFromSnapshot(BookSnapshotRequest book) {
        Optional<String> isbn13 = normalizeIsbn13(book.isbn13());
        if (isbn13.isEmpty()) {
            return Optional.empty();
        }
        String title = blankToNull(book.title()) == null ? "제목 정보 없음" : book.title().trim();
        Long id = jdbcTemplate.queryForObject("""
                INSERT INTO book.books (isbn13, title, author, publisher, cover_url, source, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, CAST(? AS jsonb))
                ON CONFLICT (isbn13) DO UPDATE SET
                    title = COALESCE(NULLIF(EXCLUDED.title, ''), books.title),
                    author = COALESCE(EXCLUDED.author, books.author),
                    publisher = COALESCE(EXCLUDED.publisher, books.publisher),
                    cover_url = COALESCE(EXCLUDED.cover_url, books.cover_url),
                    raw_json = COALESCE(EXCLUDED.raw_json, books.raw_json),
                    updated_at = NOW()
                RETURNING id
                """,
                Long.class,
                isbn13.get(),
                title,
                blankToNull(book.author()),
                blankToNull(book.publisher()),
                blankToNull(book.coverUrl()),
                DEFAULT_RECOMMENDATION_SOURCE,
                toJson(book.metadata() == null ? Map.of() : book.metadata())
        );
        return Optional.ofNullable(id);
    }

    private boolean existsBookId(Long bookId) {
        Boolean exists = jdbcTemplate.queryForObject("SELECT EXISTS (SELECT 1 FROM book.books WHERE id = ?)", Boolean.class, bookId);
        return Boolean.TRUE.equals(exists);
    }

    private Map<String, Object> candidateMetadata(BookCandidate candidate) {
        if (candidate == null) {
            return Map.of();
        }
        Map<String, Object> metadata = objectMapper.convertValue(candidate, new TypeReference<Map<String, Object>>() {});
        metadata.values().removeIf(value -> value == null || (value instanceof List<?> list && list.isEmpty()));
        return new LinkedHashMap<>(metadata);
    }

    private BigDecimal toBigDecimal(Double value) {
        return value == null ? null : BigDecimal.valueOf(value);
    }

    private Optional<String> normalizeIsbn13(String isbn) {
        if (isbn == null) {
            return Optional.empty();
        }
        String digits = isbn.replaceAll("\\D", "");
        return digits.length() == 13 ? Optional.of(digits) : Optional.empty();
    }

    private String toJson(Map<String, Object> metadata) {
        try {
            return objectMapper.writeValueAsString(metadata == null ? Map.of() : metadata);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("행동 로그 메타데이터를 JSON으로 변환하지 못했습니다.", e);
        }
    }

    private String blankToNull(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        return value.trim();
    }
}
