package com.taeo.bookcuration.recommendation.audience;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.taeo.bookcuration.admin.recommendationmodel.dto.AdminAudienceLabelDtos.AudienceLabelBatchJobResponse;
import com.taeo.bookcuration.admin.recommendationmodel.dto.AdminAudienceLabelDtos.AudienceLabelSummaryResponse;
import com.taeo.bookcuration.chat.client.AiRecommendationClient;
import com.taeo.bookcuration.chat.client.AiRecommendationClient.AudienceLabelBatchRequest;
import com.taeo.bookcuration.chat.client.AiRecommendationClient.AudienceLabelBatchResponse;
import com.taeo.bookcuration.chat.client.AiRecommendationClient.AudienceLabelBook;
import com.taeo.bookcuration.chat.client.AiRecommendationClient.AudienceLabelResult;
import jakarta.annotation.PreDestroy;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.stream.Collectors;

@Slf4j
@Service
@RequiredArgsConstructor
public class AudienceLabelBatchService {

    private static final int DEFAULT_LIMIT = 50;
    private static final int MAX_LIMIT = 500;
    // 수정 포인트: limit 50을 한 번에 AI 서버/LLM으로 보내면 prompt가 과도하게 커져 전체 실패가 발생할 수 있습니다.
    // 내부 요청 chunk를 작게 유지해 일부 실패가 전체 실패로 번지지 않게 합니다.
    private static final int AI_REQUEST_CHUNK_SIZE = 5;
    private static final List<String> AUDIENCE_GROUPS = List.of(
            "INFANT", "CHILD", "ELEMENTARY", "MIDDLE_SCHOOL", "HIGH_SCHOOL",
            "YOUNG_ADULT", "ADULT", "GENERAL", "UNKNOWN"
    );
    private static final List<String> DIFFICULTY_LEVELS = List.of("EASY", "NORMAL", "HARD", "UNKNOWN");

    private final JdbcTemplate jdbcTemplate;
    private final AiRecommendationClient aiRecommendationClient;
    private final ObjectMapper objectMapper;
    private final Map<UUID, AudienceLabelJob> jobs = new ConcurrentHashMap<>();
    private final ExecutorService executor = Executors.newSingleThreadExecutor(runnable -> {
        Thread thread = new Thread(runnable, "audience-label-batch-worker");
        thread.setDaemon(true);
        return thread;
    });
    private final Object startLock = new Object();
    private volatile UUID activeJobId;

    public AudienceLabelBatchJobResponse start(Integer requestedLimit, Boolean force) {
        int limit = normalizeLimit(requestedLimit);
        boolean forceRefresh = Boolean.TRUE.equals(force);

        synchronized (startLock) {
            AudienceLabelJob active = activeJobId == null ? null : jobs.get(activeJobId);
            if (active != null && active.isRunning()) {
                active.message = "이미 audience label 배치가 실행 중입니다.";
                return toResponse(active);
            }

            AudienceLabelJob job = new AudienceLabelJob(UUID.randomUUID(), limit, forceRefresh);
            jobs.put(job.jobId, job);
            activeJobId = job.jobId;
            executor.submit(() -> runJob(job));
            return toResponse(job);
        }
    }

    public AudienceLabelBatchJobResponse get(UUID jobId) {
        AudienceLabelJob job = jobs.get(jobId);
        if (job == null) {
            throw new IllegalArgumentException("존재하지 않는 audience label job입니다.");
        }
        return toResponse(job);
    }

    @Transactional(readOnly = true)
    public AudienceLabelSummaryResponse summary() {
        if (!hasAudienceLabelColumns()) {
            return new AudienceLabelSummaryResponse(
                    false,
                    0L,
                    0L,
                    0L,
                    0L,
                    0L,
                    0L,
                    0L,
                    0L,
                    "book.books audience label 컬럼이 없습니다. DDL을 먼저 실행해 주세요."
            );
        }

        Long totalBookCount = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM book.books WHERE isbn13 IS NOT NULL",
                Long.class
        );
        Map<String, Long> counts = jdbcTemplate.query(
                """
                SELECT COALESCE(audience_label_status, 'PENDING') AS status,
                       COUNT(*) AS count
                FROM book.books
                WHERE isbn13 IS NOT NULL
                GROUP BY COALESCE(audience_label_status, 'PENDING')
                """,
                rs -> {
                    Map<String, Long> result = new LinkedHashMap<>();
                    while (rs.next()) {
                        result.put(rs.getString("status"), rs.getLong("count"));
                    }
                    return result;
                }
        );

        long pendingCount = countOf(counts, "PENDING");
        long failedCount = countOf(counts, "FAILED");
        long readyCount = countOf(counts, "READY");
        long skippedCount = countOf(counts, "SKIPPED");
        long knownCount = pendingCount + failedCount + readyCount + skippedCount;
        long safeTotalBookCount = totalBookCount == null ? 0L : totalBookCount;
        long unknownStatusCount = Math.max(0L, safeTotalBookCount - knownCount);
        long defaultTargetCount = pendingCount + failedCount + unknownStatusCount;
        long forceTargetCount = defaultTargetCount + readyCount + skippedCount;

        // 수정 포인트: 관리자가 몇 번 실행해야 하는지 판단할 수 있도록 현재 남은 기본 처리 대상과
        // force 옵션 사용 시 처리 대상 수를 별도 값으로 제공합니다.
        return new AudienceLabelSummaryResponse(
                true,
                safeTotalBookCount,
                defaultTargetCount,
                forceTargetCount,
                pendingCount,
                failedCount,
                readyCount,
                skippedCount,
                unknownStatusCount,
                "체크하지 않으면 PENDING/FAILED 대상만 처리하고, 체크하면 READY/SKIPPED까지 포함합니다."
        );
    }

    @PreDestroy
    public void shutdown() {
        executor.shutdownNow();
    }

    public void cacheReadyLabelFromResponseCard(Long bookId, Map<String, Object> audienceProfile) {
        if (bookId == null || audienceProfile == null || audienceProfile.isEmpty()) {
            return;
        }
        try {
            if (!hasAudienceLabelColumns()) {
                return;
            }
            String audienceGroup = normalizeAudienceGroup(firstNonBlank(
                    textValue(audienceProfile.get("audience_group")),
                    textValue(audienceProfile.get("audienceGroup")),
                    textValue(audienceProfile.get("target_age_group")),
                    textValue(audienceProfile.get("targetAgeGroup"))
            ));
            String difficultyLevel = normalizeDifficultyLevel(firstNonBlank(
                    textValue(audienceProfile.get("difficulty_level")),
                    textValue(audienceProfile.get("difficultyLevel"))
            ));
            BigDecimal confidence = normalizeConfidence(numberValue(audienceProfile.get("confidence")));
            Integer minAge = intValue(firstNonNull(
                    audienceProfile.get("audience_min_age"),
                    audienceProfile.get("audienceMinAge")
            ));
            Integer maxAge = intValue(firstNonNull(
                    audienceProfile.get("audience_max_age"),
                    audienceProfile.get("audienceMaxAge")
            ));

            if ("UNKNOWN".equals(audienceGroup) && "UNKNOWN".equals(difficultyLevel)) {
                return;
            }

            jdbcTemplate.update(
                    """
                    UPDATE book.books
                    SET audience_label_status = 'READY',
                        audience_group = ?,
                        audience_min_age = ?,
                        audience_max_age = ?,
                        difficulty_level = ?,
                        audience_label_confidence = ?,
                        audience_label_reason = ?,
                        audience_labeled_at = NOW()
                    WHERE id = ?
                      AND COALESCE(audience_label_status, 'PENDING') <> 'READY'
                    """,
                    audienceGroup,
                    minAge,
                    maxAge,
                    difficultyLevel,
                    confidence,
                    firstNonBlank(textValue(audienceProfile.get("reason")), "Cached from recommendation response card."),
                    bookId
            );
        } catch (RuntimeException ex) {
            log.warn("Response card audience label cache skipped. bookId={}, reason={}", bookId, ex.getMessage());
        }
    }

    public void enqueueResponseCardLabeling(List<Long> bookIds) {
        if (bookIds == null || bookIds.isEmpty()) {
            return;
        }
        List<Long> distinctBookIds = bookIds.stream()
                .filter(Objects::nonNull)
                .distinct()
                .limit(MAX_LIMIT)
                .toList();
        if (distinctBookIds.isEmpty()) {
            return;
        }
        executor.submit(() -> labelResponseCardTargets(distinctBookIds));
    }

    private void runJob(AudienceLabelJob job) {
        job.status = "RUNNING";
        job.startedAt = OffsetDateTime.now();
        job.message = "처리 대상 도서를 조회하는 중입니다.";

        try {
            if (!hasAudienceLabelColumns()) {
                throw new IllegalStateException("book.books audience label 컬럼이 없습니다. apps/backend/docs/sql/38-book-audience-labels.sql을 먼저 실행해 주세요.");
            }

            List<BookTarget> targets = findTargets(job.requestedLimit, job.force);
            job.totalTargetCount = targets.size();
            if (targets.isEmpty()) {
                job.status = "SUCCEEDED";
                job.message = "처리할 audience label 대상이 없습니다.";
                job.finishedAt = OffsetDateTime.now();
                return;
            }

            job.message = "AI 서버에 audience label 생성을 요청했습니다.";
            List<String> failureSamples = new ArrayList<>();

            for (int start = 0; start < targets.size(); start += AI_REQUEST_CHUNK_SIZE) {
                List<BookTarget> chunk = targets.subList(start, Math.min(start + AI_REQUEST_CHUNK_SIZE, targets.size()));
                Map<String, AudienceLabelResult> resultByIsbn;
                try {
                    AudienceLabelBatchResponse response = aiRecommendationClient.classifyAudienceLabels(
                            new AudienceLabelBatchRequest(chunk.stream().map(BookTarget::book).toList())
                    );
                    resultByIsbn = (response == null || response.items() == null ? List.<AudienceLabelResult>of() : response.items())
                            .stream()
                            .filter(item -> item != null && item.isbn() != null && !item.isbn().isBlank())
                            .collect(Collectors.toMap(item -> item.isbn().trim(), item -> item, (left, right) -> right, LinkedHashMap::new));
                } catch (Exception ex) {
                    String reason = "AI 서버 audience label 요청 실패: " + firstNonBlank(ex.getMessage(), ex.getClass().getSimpleName());
                    addFailureSample(failureSamples, reason);
                    for (BookTarget target : chunk) {
                        markFailed(target.id(), reason);
                        job.failedCount++;
                        job.processedCount++;
                    }
                    job.message = progressMessage(job);
                    continue;
                }

                for (BookTarget target : chunk) {
                    AudienceLabelResult result = resultByIsbn.get(target.isbn13());
                    if (result == null) {
                        String reason = "AI 서버가 해당 ISBN label을 반환하지 않았습니다.";
                        markFailed(target.id(), reason);
                        addFailureSample(failureSamples, reason);
                        job.failedCount++;
                        job.processedCount++;
                        continue;
                    }

                    String resultStatus = normalizeStatus(result.status());
                    if ("READY".equals(resultStatus)) {
                        updateReady(target.id(), result);
                        job.successCount++;
                    } else if ("SKIPPED".equals(resultStatus)) {
                        String reason = firstNonBlank(result.reason(), result.errorMessage(), "AI 서버가 SKIPPED 상태를 반환했습니다.");
                        markSkipped(target.id(), reason);
                        job.skippedCount++;
                    } else {
                        String reason = firstNonBlank(result.errorMessage(), result.reason(), "AI 서버가 FAILED 상태를 반환했습니다.");
                        markFailed(target.id(), reason);
                        addFailureSample(failureSamples, reason);
                        job.failedCount++;
                    }
                    job.processedCount++;
                }
                job.message = progressMessage(job);
            }

            boolean allFailed = job.failedCount > 0 && job.successCount == 0 && job.skippedCount == 0;
            job.status = allFailed ? "FAILED" : "SUCCEEDED";
            job.errorMessage = failureSamples.isEmpty() ? null : String.join(" | ", failureSamples);
            if (allFailed) {
                job.message = "Audience label 배치가 완료됐지만 모든 대상이 실패했습니다. 오류 메시지와 ai-server 로그를 확인해 주세요.";
            } else if (job.failedCount > 0) {
                job.message = "Audience label 배치가 완료되었습니다. 일부 실패 대상은 FAILED 상태로 남아 다음 배치에서 재처리됩니다.";
            } else {
                job.message = "Audience label 배치가 완료되었습니다.";
            }
        } catch (Exception ex) {
            log.warn("Audience label batch failed. jobId={}", job.jobId, ex);
            job.status = "FAILED";
            job.errorMessage = ex.getMessage();
            job.message = "Audience label 배치가 실패했습니다.";
        } finally {
            job.finishedAt = OffsetDateTime.now();
            synchronized (startLock) {
                if (job.jobId.equals(activeJobId)) {
                    activeJobId = null;
                }
            }
        }
    }

    @Transactional(readOnly = true)
    protected List<BookTarget> findTargets(int limit, boolean force) {
        String statusPredicate = force
                ? "COALESCE(audience_label_status, 'PENDING') IN ('PENDING', 'FAILED', 'READY', 'SKIPPED')"
                : "COALESCE(audience_label_status, 'PENDING') IN ('PENDING', 'FAILED')";
        // 수정 포인트: Java text block 문자열 결합 시 `AND`와 동적 predicate 사이의 공백이 사라져
        // `ANDCOALESCE(...)` 형태의 SQL이 만들어질 수 있으므로 formatted()로 안전하게 조립합니다.
        String sql = """
                SELECT id,
                       isbn13,
                       title,
                       author,
                       publisher,
                       publication_year,
                       description,
                       category_code,
                       page_count,
                       raw_json::text AS raw_json
                FROM book.books
                WHERE isbn13 IS NOT NULL
                  AND %s
                ORDER BY
                    CASE COALESCE(audience_label_status, 'PENDING')
                        WHEN 'FAILED' THEN 0
                        WHEN 'PENDING' THEN 1
                        ELSE 2
                    END,
                    updated_at ASC,
                    id ASC
                LIMIT ?
                """.formatted(statusPredicate);

        return jdbcTemplate.query(sql, (ps) -> ps.setInt(1, limit), (rs, rowNum) -> toBookTarget(rs));
    }

    @Transactional(readOnly = true)
    protected List<BookTarget> findTargetsByIds(List<Long> bookIds) {
        if (bookIds == null || bookIds.isEmpty()) {
            return List.of();
        }
        String placeholders = bookIds.stream()
                .map(id -> "?")
                .collect(Collectors.joining(", "));
        String sql = """
                SELECT id,
                       isbn13,
                       title,
                       author,
                       publisher,
                       publication_year,
                       description,
                       category_code,
                       page_count,
                       raw_json::text AS raw_json
                FROM book.books
                WHERE id IN (%s)
                  AND isbn13 IS NOT NULL
                  AND COALESCE(audience_label_status, 'PENDING') IN ('PENDING', 'FAILED')
                ORDER BY updated_at DESC, id ASC
                """.formatted(placeholders);
        return jdbcTemplate.query(sql, bookIds.toArray(), (rs, rowNum) -> toBookTarget(rs));
    }

    private BookTarget toBookTarget(java.sql.ResultSet rs) throws java.sql.SQLException {
        Long id = rs.getLong("id");
        String isbn13 = rs.getString("isbn13");
        JsonNode raw = readRawJson(rs.getString("raw_json"));
        AudienceLabelBook book = new AudienceLabelBook(
                isbn13,
                firstNonBlank(text(raw, "title"), rs.getString("title")),
                firstNonBlank(text(raw, "author"), rs.getString("author")),
                firstNonBlank(text(raw, "publisher"), rs.getString("publisher")),
                text(raw, "publish_date"),
                firstInt(raw, "page", (Integer) rs.getObject("page_count")),
                firstNonBlank(rs.getString("description"), text(raw, "description")),
                text(raw, "simple_intro"),
                text(raw, "book_intro"),
                list(raw, "categories"),
                list(raw, "cate_depth1"),
                list(raw, "kcid"),
                text(raw, "author_intro"),
                text(raw, "book_index"),
                text(raw, "pub_review")
        );
        return new BookTarget(id, isbn13, book);
    }

    private void labelResponseCardTargets(List<Long> bookIds) {
        try {
            if (!hasAudienceLabelColumns()) {
                log.warn("Response card audience labeling skipped. book.books audience label columns are missing.");
                return;
            }
            List<BookTarget> targets = findTargetsByIds(bookIds);
            if (targets.isEmpty()) {
                return;
            }

            int successCount = 0;
            int failedCount = 0;
            int skippedCount = 0;
            for (int start = 0; start < targets.size(); start += AI_REQUEST_CHUNK_SIZE) {
                List<BookTarget> chunk = targets.subList(start, Math.min(start + AI_REQUEST_CHUNK_SIZE, targets.size()));
                Map<String, AudienceLabelResult> resultByIsbn;
                try {
                    AudienceLabelBatchResponse response = aiRecommendationClient.classifyAudienceLabels(
                            new AudienceLabelBatchRequest(chunk.stream().map(BookTarget::book).toList())
                    );
                    resultByIsbn = (response == null || response.items() == null ? List.<AudienceLabelResult>of() : response.items())
                            .stream()
                            .filter(item -> item != null && item.isbn() != null && !item.isbn().isBlank())
                            .collect(Collectors.toMap(item -> item.isbn().trim(), item -> item, (left, right) -> right, LinkedHashMap::new));
                } catch (Exception ex) {
                    String reason = "응답 카드 audience label 자동 생성 실패: " + firstNonBlank(ex.getMessage(), ex.getClass().getSimpleName());
                    for (BookTarget target : chunk) {
                        markFailed(target.id(), reason);
                        failedCount++;
                    }
                    continue;
                }

                for (BookTarget target : chunk) {
                    AudienceLabelResult result = resultByIsbn.get(target.isbn13());
                    if (result == null) {
                        markFailed(target.id(), "AI 서버가 응답 카드 ISBN label을 반환하지 않았습니다.");
                        failedCount++;
                        continue;
                    }

                    String resultStatus = normalizeStatus(result.status());
                    if ("READY".equals(resultStatus)) {
                        updateReady(target.id(), result);
                        successCount++;
                    } else if ("SKIPPED".equals(resultStatus)) {
                        String reason = firstNonBlank(result.reason(), result.errorMessage(), "AI 서버가 SKIPPED 상태를 반환했습니다.");
                        markSkipped(target.id(), reason);
                        skippedCount++;
                    } else {
                        String reason = firstNonBlank(result.errorMessage(), result.reason(), "AI 서버가 FAILED 상태를 반환했습니다.");
                        markFailed(target.id(), reason);
                        failedCount++;
                    }
                }
            }
            log.info(
                    "Response card audience labeling finished. requested={}, targets={}, success={}, failed={}, skipped={}",
                    bookIds.size(), targets.size(), successCount, failedCount, skippedCount
            );
        } catch (Exception ex) {
            log.warn("Response card audience labeling failed. bookIds={}, reason={}", bookIds, ex.getMessage(), ex);
        }
    }

    @Transactional
    protected void updateReady(Long bookId, AudienceLabelResult result) {
        String audienceGroup = normalizeAudienceGroup(result.audienceGroup());
        String difficultyLevel = normalizeDifficultyLevel(result.difficultyLevel());
        BigDecimal confidence = normalizeConfidence(result.confidence());
        jdbcTemplate.update(
                """
                UPDATE book.books
                SET audience_label_status = 'READY',
                    audience_group = ?,
                    audience_min_age = ?,
                    audience_max_age = ?,
                    difficulty_level = ?,
                    audience_label_confidence = ?,
                    audience_label_reason = ?,
                    audience_labeled_at = NOW()
                WHERE id = ?
                """,
                audienceGroup,
                result.audienceMinAge(),
                result.audienceMaxAge(),
                difficultyLevel,
                confidence,
                firstNonBlank(result.reason(), "LLM audience label generated."),
                bookId
        );
    }

    @Transactional
    protected void markFailed(Long bookId, String reason) {
        jdbcTemplate.update(
                """
                UPDATE book.books
                SET audience_label_status = 'FAILED',
                    audience_group = 'UNKNOWN',
                    difficulty_level = 'UNKNOWN',
                    audience_label_confidence = 0,
                    audience_label_reason = ?,
                    audience_labeled_at = NOW()
                WHERE id = ?
                """,
                reason,
                bookId
        );
    }

    @Transactional
    protected void markSkipped(Long bookId, String reason) {
        jdbcTemplate.update(
                """
                UPDATE book.books
                SET audience_label_status = 'SKIPPED',
                    audience_group = 'UNKNOWN',
                    difficulty_level = 'UNKNOWN',
                    audience_label_confidence = 0,
                    audience_label_reason = ?,
                    audience_labeled_at = NOW()
                WHERE id = ?
                """,
                reason,
                bookId
        );
    }

    private boolean hasAudienceLabelColumns() {
        try {
            Boolean exists = jdbcTemplate.queryForObject(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_schema = 'book'
                          AND table_name = 'books'
                          AND column_name = 'audience_label_status'
                    )
                    """,
                    Boolean.class
            );
            return Boolean.TRUE.equals(exists);
        } catch (DataAccessException ex) {
            return false;
        }
    }

    private JsonNode readRawJson(String rawJson) {
        if (rawJson == null || rawJson.isBlank()) {
            return objectMapper.createObjectNode();
        }
        try {
            JsonNode node = objectMapper.readTree(rawJson);
            return node == null ? objectMapper.createObjectNode() : node;
        } catch (Exception ex) {
            return objectMapper.createObjectNode();
        }
    }

    private static String text(JsonNode node, String key) {
        if (node == null || key == null) {
            return null;
        }
        JsonNode value = node.get(key);
        if (value == null || value.isNull()) {
            return null;
        }
        String text = value.isTextual() ? value.asText() : value.toString();
        return text == null || text.isBlank() ? null : text.trim();
    }

    private static Integer firstInt(JsonNode node, String key, Integer fallback) {
        JsonNode value = node == null ? null : node.get(key);
        if (value == null || value.isNull()) {
            return fallback;
        }
        if (value.isInt() || value.isLong()) {
            return value.asInt();
        }
        try {
            return Integer.valueOf(value.asText().replaceAll("[^0-9]", ""));
        } catch (Exception ex) {
            return fallback;
        }
    }

    private static List<String> list(JsonNode node, String key) {
        JsonNode value = node == null ? null : node.get(key);
        if (value == null || value.isNull()) {
            return List.of();
        }
        List<String> values = new ArrayList<>();
        if (value.isArray()) {
            value.forEach(item -> addIfPresent(values, item.isTextual() ? item.asText() : item.toString()));
        } else {
            addIfPresent(values, value.asText());
        }
        return values;
    }

    private static void addIfPresent(List<String> values, String value) {
        if (value != null && !value.isBlank()) {
            values.add(value.trim());
        }
    }



    private static Object firstNonNull(Object... values) {
        for (Object value : values) {
            if (value != null) {
                return value;
            }
        }
        return null;
    }

    private static String textValue(Object value) {
        if (value == null) {
            return null;
        }
        String text = String.valueOf(value).trim();
        return text.isBlank() ? null : text;
    }

    private static Integer intValue(Object value) {
        if (value == null) {
            return null;
        }
        if (value instanceof Number number) {
            return number.intValue();
        }
        try {
            String digits = String.valueOf(value).replaceAll("[^0-9]", "");
            return digits.isBlank() ? null : Integer.valueOf(digits);
        } catch (Exception ex) {
            return null;
        }
    }

    private static BigDecimal numberValue(Object value) {
        if (value == null) {
            return null;
        }
        if (value instanceof BigDecimal decimal) {
            return decimal;
        }
        if (value instanceof Number number) {
            return BigDecimal.valueOf(number.doubleValue());
        }
        try {
            return new BigDecimal(String.valueOf(value).trim());
        } catch (Exception ex) {
            return null;
        }
    }

    private static long countOf(Map<String, Long> counts, String status) {
        return counts.getOrDefault(status, 0L);
    }

    private static void addFailureSample(List<String> samples, String reason) {
        if (reason == null || reason.isBlank() || samples.size() >= 5) {
            return;
        }
        String trimmed = reason.trim();
        if (!samples.contains(trimmed)) {
            samples.add(trimmed);
        }
    }

    private static String progressMessage(AudienceLabelJob job) {
        return "Audience label 처리 중: "
                + job.processedCount + "/" + job.totalTargetCount
                + " (성공 " + job.successCount
                + ", 실패 " + job.failedCount
                + ", 스킵 " + job.skippedCount + ")";
    }

    private static int normalizeLimit(Integer value) {
        if (value == null) {
            return DEFAULT_LIMIT;
        }
        return Math.max(1, Math.min(MAX_LIMIT, value));
    }

    private static String normalizeStatus(String value) {
        String normalized = value == null ? "FAILED" : value.trim().toUpperCase(Locale.ROOT);
        return switch (normalized) {
            case "READY", "SUCCEEDED", "SUCCESS" -> "READY";
            case "SKIPPED" -> "SKIPPED";
            default -> "FAILED";
        };
    }

    private static String normalizeAudienceGroup(String value) {
        String normalized = value == null ? "UNKNOWN" : value.trim().toUpperCase(Locale.ROOT);
        return AUDIENCE_GROUPS.contains(normalized) ? normalized : "UNKNOWN";
    }

    private static String normalizeDifficultyLevel(String value) {
        String normalized = value == null ? "UNKNOWN" : value.trim().toUpperCase(Locale.ROOT);
        return DIFFICULTY_LEVELS.contains(normalized) ? normalized : "UNKNOWN";
    }

    private static BigDecimal normalizeConfidence(BigDecimal value) {
        if (value == null) {
            return BigDecimal.ZERO;
        }
        if (value.compareTo(BigDecimal.ZERO) < 0) {
            return BigDecimal.ZERO;
        }
        if (value.compareTo(BigDecimal.ONE) > 0) {
            return BigDecimal.ONE;
        }
        return value;
    }

    private static String firstNonBlank(String... values) {
        for (String value : values) {
            if (value != null && !value.isBlank()) {
                return value.trim();
            }
        }
        return null;
    }

    private AudienceLabelBatchJobResponse toResponse(AudienceLabelJob job) {
        return new AudienceLabelBatchJobResponse(
                job.jobId,
                job.status,
                job.requestedLimit,
                job.force,
                job.totalTargetCount,
                job.processedCount,
                job.successCount,
                job.failedCount,
                job.skippedCount,
                job.message,
                job.errorMessage,
                job.startedAt,
                job.finishedAt
        );
    }

    private record BookTarget(Long id, String isbn13, AudienceLabelBook book) {
    }

    private static final class AudienceLabelJob {
        private final UUID jobId;
        private final int requestedLimit;
        private final boolean force;
        private volatile String status = "REQUESTED";
        private volatile int totalTargetCount;
        private volatile int processedCount;
        private volatile int successCount;
        private volatile int failedCount;
        private volatile int skippedCount;
        private volatile String message = "Audience label 배치 실행이 요청되었습니다.";
        private volatile String errorMessage;
        private volatile OffsetDateTime startedAt;
        private volatile OffsetDateTime finishedAt;

        private AudienceLabelJob(UUID jobId, int requestedLimit, boolean force) {
            this.jobId = jobId;
            this.requestedLimit = requestedLimit;
            this.force = force;
        }

        private boolean isRunning() {
            return "REQUESTED".equals(status) || "RUNNING".equals(status);
        }
    }
}
