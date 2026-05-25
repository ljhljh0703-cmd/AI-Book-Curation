package com.taeo.bookcuration.recommendation.service;

import lombok.RequiredArgsConstructor;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.OffsetDateTime;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.function.Function;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
public class RecommendationModelSettingService {

    public static final String DEFAULT_EMBEDDING_MODEL = "CLOVA";
    public static final String DEFAULT_RECOMMENDATION_STRATEGY = "AUTO_HYBRID";
    public static final String DEFAULT_PERSONALIZATION_MODEL = "LIGHTFM";
    public static final String DEFAULT_RERANKER_PROVIDER = "NONE";
    public static final boolean DEFAULT_BM25_ENABLED = false;

    // 수정 포인트: 기존 RECOMMENDATION_RANKING_MODEL 하나에 추천 전략/개인화 모델 의미가 섞여 있던 구조를 분리합니다.
    // rankingModel은 기존 로그/ai-server 요청 호환을 위해 personalizationModel alias로만 유지합니다.
    private static final String EMBEDDING_MODEL_KEY = "RECOMMENDATION_EMBEDDING_MODEL";
    private static final String LEGACY_RANKING_MODEL_KEY = "RECOMMENDATION_RANKING_MODEL";
    private static final String RECOMMENDATION_STRATEGY_KEY = "RECOMMENDATION_STRATEGY";
    private static final String PERSONALIZATION_MODEL_KEY = "PERSONALIZATION_MODEL";
    private static final String RERANKER_PROVIDER_KEY = "RERANKER_PROVIDER";
    private static final String BM25_ENABLED_KEY = "RECOMMENDATION_BM25_ENABLED";
    private static final String EMBEDDING_MODEL_DESCRIPTION = "추천 검색에 사용할 임베딩 모델(CLOVA 또는 KURE)";
    private static final String RECOMMENDATION_STRATEGY_DESCRIPTION = "추천 후보 처리 전략(AUTO_HYBRID 또는 RULE_BASED_ONLY)";
    private static final String PERSONALIZATION_MODEL_DESCRIPTION = "AUTO_HYBRID에서 사용할 개인화 모델(NONE, LIGHTFM, SASREC, BERT4REC)";
    private static final String RERANKER_PROVIDER_DESCRIPTION = "추천 후보 20개를 재정렬할 Reranker provider(NONE, GTE_MULTILINGUAL, HCX_RERANKER)";
    private static final String BM25_ENABLED_DESCRIPTION = "Qdrant hybrid collection 기반 BM25 RRF 검색 사용 여부";
    private static final List<String> EMBEDDING_MODEL_OPTIONS = List.of("CLOVA", "KURE");
    private static final List<String> RECOMMENDATION_STRATEGY_OPTIONS = List.of("AUTO_HYBRID", "RULE_BASED_ONLY");
    private static final List<String> PERSONALIZATION_MODEL_OPTIONS = List.of("NONE", "LIGHTFM", "SASREC", "BERT4REC");
    private static final List<String> RERANKER_PROVIDER_OPTIONS = List.of("NONE", "GTE_MULTILINGUAL", "HCX_RERANKER");

    private final JdbcTemplate jdbcTemplate;

    @Transactional(readOnly = true)
    public RecommendationModelSetting getSetting() {
        if (!serviceSettingsTableExists()) {
            return defaultSetting();
        }

        Map<String, ServiceSettingValue> values = jdbcTemplate.query(
                """
                SELECT setting_key, setting_value, updated_at
                FROM book.service_settings
                WHERE setting_key IN (?, ?, ?, ?, ?, ?)
                """,
                (rs, rowNum) -> new ServiceSettingValue(
                        rs.getString("setting_key"),
                        rs.getString("setting_value"),
                        rs.getObject("updated_at", OffsetDateTime.class)
                ),
                EMBEDDING_MODEL_KEY,
                RECOMMENDATION_STRATEGY_KEY,
                PERSONALIZATION_MODEL_KEY,
                RERANKER_PROVIDER_KEY,
                BM25_ENABLED_KEY,
                LEGACY_RANKING_MODEL_KEY
        ).stream().collect(Collectors.toMap(ServiceSettingValue::settingKey, Function.identity()));

        ServiceSettingValue embeddingModel = values.get(EMBEDDING_MODEL_KEY);
        ServiceSettingValue recommendationStrategy = values.get(RECOMMENDATION_STRATEGY_KEY);
        ServiceSettingValue personalizationModel = values.get(PERSONALIZATION_MODEL_KEY);
        ServiceSettingValue rerankerProvider = values.get(RERANKER_PROVIDER_KEY);
        ServiceSettingValue bm25Enabled = values.get(BM25_ENABLED_KEY);
        ServiceSettingValue legacyRankingModel = values.get(LEGACY_RANKING_MODEL_KEY);

        String normalizedPersonalizationModel = normalizePersonalizationModel(
                personalizationModel == null ? legacyRankingModel == null ? null : legacyRankingModel.settingValue() : personalizationModel.settingValue()
        );

        return new RecommendationModelSetting(
                normalizeEmbeddingModel(embeddingModel == null ? null : embeddingModel.settingValue()),
                normalizeRecommendationStrategy(recommendationStrategy == null ? null : recommendationStrategy.settingValue()),
                normalizedPersonalizationModel,
                normalizeRerankerProvider(rerankerProvider == null ? null : rerankerProvider.settingValue()),
                normalizeBm25Enabled(bm25Enabled == null ? null : bm25Enabled.settingValue()),
                // 수정 포인트: 기존 rankingModel 소비 코드와 추천 로그 호환을 위해 개인화 모델을 alias로 제공합니다.
                normalizedPersonalizationModel,
                latestUpdatedAt(embeddingModel, recommendationStrategy, personalizationModel, rerankerProvider, bm25Enabled, legacyRankingModel)
        );
    }

    @Transactional
    public RecommendationModelSetting updateSetting(
            String embeddingModel,
            String recommendationStrategy,
            String personalizationModel,
            String rerankerProvider,
            Boolean bm25Enabled
    ) {
        if (!serviceSettingsTableExists()) {
            throw new IllegalStateException("book.service_settings 테이블이 없습니다. apps/backend/docs/sql/35-recommendation-model-settings.sql을 먼저 실행해 주세요.");
        }

        String normalizedEmbeddingModel = validateEmbeddingModel(embeddingModel);
        String normalizedRecommendationStrategy = validateRecommendationStrategy(recommendationStrategy);
        String normalizedPersonalizationModel = validatePersonalizationModel(personalizationModel);
        String normalizedRerankerProvider = validateRerankerProvider(rerankerProvider);
        boolean normalizedBm25Enabled = Boolean.TRUE.equals(bm25Enabled);

        upsertSetting(EMBEDDING_MODEL_KEY, normalizedEmbeddingModel, EMBEDDING_MODEL_DESCRIPTION);
        upsertSetting(RECOMMENDATION_STRATEGY_KEY, normalizedRecommendationStrategy, RECOMMENDATION_STRATEGY_DESCRIPTION);
        upsertSetting(PERSONALIZATION_MODEL_KEY, normalizedPersonalizationModel, PERSONALIZATION_MODEL_DESCRIPTION);
        upsertSetting(RERANKER_PROVIDER_KEY, normalizedRerankerProvider, RERANKER_PROVIDER_DESCRIPTION);
        // 수정 포인트: 기본 false를 유지하고 관리자가 명시적으로 켠 경우에만 hybrid 검색을 ai-server에 전달합니다.
        upsertSetting(BM25_ENABLED_KEY, Boolean.toString(normalizedBm25Enabled), BM25_ENABLED_DESCRIPTION);
        // 수정 포인트: 기존 추천 로그/구버전 ai-server 요청 호환을 위해 legacy key도 함께 갱신합니다.
        upsertSetting(LEGACY_RANKING_MODEL_KEY, normalizedPersonalizationModel, PERSONALIZATION_MODEL_DESCRIPTION);

        return getSetting();
    }

    public static List<String> embeddingModelOptions() {
        return sortedOptions(EMBEDDING_MODEL_OPTIONS);
    }

    public static List<String> recommendationStrategyOptions() {
        return sortedOptions(RECOMMENDATION_STRATEGY_OPTIONS);
    }

    public static List<String> personalizationModelOptions() {
        return sortedOptions(PERSONALIZATION_MODEL_OPTIONS);
    }

    public static List<String> rerankerProviderOptions() {
        return sortedOptions(RERANKER_PROVIDER_OPTIONS);
    }

    public static List<String> rankingModelOptions() {
        return personalizationModelOptions();
    }

    private void upsertSetting(String settingKey, String settingValue, String description) {
        jdbcTemplate.update(
                """
                INSERT INTO book.service_settings (setting_key, setting_value, description)
                VALUES (?, ?, ?)
                ON CONFLICT (setting_key)
                DO UPDATE SET
                    setting_value = EXCLUDED.setting_value,
                    description = EXCLUDED.description,
                    updated_at = NOW()
                """,
                settingKey,
                settingValue,
                description
        );
    }

    private static String validateEmbeddingModel(String value) {
        String normalized = normalize(value, DEFAULT_EMBEDDING_MODEL);
        if (!EMBEDDING_MODEL_OPTIONS.contains(normalized)) {
            throw new IllegalArgumentException("embeddingModel은 CLOVA 또는 KURE만 사용할 수 있습니다.");
        }
        return normalized;
    }

    private static String validateRecommendationStrategy(String value) {
        String normalized = normalize(value, DEFAULT_RECOMMENDATION_STRATEGY);
        if (!RECOMMENDATION_STRATEGY_OPTIONS.contains(normalized)) {
            throw new IllegalArgumentException("recommendationStrategy는 AUTO_HYBRID 또는 RULE_BASED_ONLY만 사용할 수 있습니다.");
        }
        return normalized;
    }

    private static String validatePersonalizationModel(String value) {
        String normalized = normalize(value, DEFAULT_PERSONALIZATION_MODEL);
        if (!PERSONALIZATION_MODEL_OPTIONS.contains(normalized)) {
            throw new IllegalArgumentException("personalizationModel은 NONE, LIGHTFM, SASREC, BERT4REC만 사용할 수 있습니다.");
        }
        return normalized;
    }

    private static String validateRerankerProvider(String value) {
        String normalized = normalize(value, DEFAULT_RERANKER_PROVIDER);
        if (!RERANKER_PROVIDER_OPTIONS.contains(normalized)) {
            throw new IllegalArgumentException("rerankerProvider는 NONE, GTE_MULTILINGUAL, HCX_RERANKER만 사용할 수 있습니다.");
        }
        return normalized;
    }

    private static String normalizeEmbeddingModel(String value) {
        String normalized = normalize(value, DEFAULT_EMBEDDING_MODEL);
        return EMBEDDING_MODEL_OPTIONS.contains(normalized) ? normalized : DEFAULT_EMBEDDING_MODEL;
    }

    private static String normalizeRecommendationStrategy(String value) {
        String normalized = normalize(value, DEFAULT_RECOMMENDATION_STRATEGY);
        return RECOMMENDATION_STRATEGY_OPTIONS.contains(normalized) ? normalized : DEFAULT_RECOMMENDATION_STRATEGY;
    }

    private static String normalizePersonalizationModel(String value) {
        String normalized = normalize(value, DEFAULT_PERSONALIZATION_MODEL);
        // 수정 포인트: 구버전 RULE_BASED 값은 개인화 모델 없음으로 해석합니다.
        if ("RULE_BASED".equals(normalized)) {
            return "NONE";
        }
        return PERSONALIZATION_MODEL_OPTIONS.contains(normalized) ? normalized : DEFAULT_PERSONALIZATION_MODEL;
    }

    private static String normalizeRerankerProvider(String value) {
        String normalized = normalize(value, DEFAULT_RERANKER_PROVIDER);
        return RERANKER_PROVIDER_OPTIONS.contains(normalized) ? normalized : DEFAULT_RERANKER_PROVIDER;
    }

    private static boolean normalizeBm25Enabled(String value) {
        if (value == null || value.isBlank()) {
            return DEFAULT_BM25_ENABLED;
        }
        String normalized = value.trim().toUpperCase(Locale.ROOT);
        return "TRUE".equals(normalized) || "Y".equals(normalized) || "ON".equals(normalized) || "1".equals(normalized);
    }

    private static String normalize(String value, String defaultValue) {
        if (value == null || value.isBlank()) {
            return defaultValue;
        }
        return value.trim().toUpperCase(Locale.ROOT);
    }

    private static OffsetDateTime latestUpdatedAt(ServiceSettingValue... values) {
        return Arrays.stream(values)
                .filter(Objects::nonNull)
                .map(ServiceSettingValue::updatedAt)
                .filter(Objects::nonNull)
                .max(OffsetDateTime::compareTo)
                .orElse(null);
    }

    private static List<String> sortedOptions(List<String> options) {
        return List.copyOf(options);
    }

    private RecommendationModelSetting defaultSetting() {
        return new RecommendationModelSetting(
                DEFAULT_EMBEDDING_MODEL,
                DEFAULT_RECOMMENDATION_STRATEGY,
                DEFAULT_PERSONALIZATION_MODEL,
                DEFAULT_RERANKER_PROVIDER,
                DEFAULT_BM25_ENABLED,
                DEFAULT_PERSONALIZATION_MODEL,
                null
        );
    }

    private boolean serviceSettingsTableExists() {
        try {
            Boolean exists = jdbcTemplate.queryForObject(
                    "SELECT to_regclass(?) IS NOT NULL",
                    Boolean.class,
                    "book.service_settings"
            );
            return Boolean.TRUE.equals(exists);
        } catch (DataAccessException ex) {
            return false;
        }
    }

    private record ServiceSettingValue(
            String settingKey,
            String settingValue,
            OffsetDateTime updatedAt
    ) {
    }

    public record RecommendationModelSetting(
            String embeddingModel,
            String recommendationStrategy,
            String personalizationModel,
            String rerankerProvider,
            Boolean bm25Enabled,
            String rankingModel,
            OffsetDateTime updatedAt
    ) {
    }
}
