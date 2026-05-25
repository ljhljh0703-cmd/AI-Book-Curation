package com.taeo.bookcuration.recommendation.evaluation;

import com.taeo.bookcuration.admin.recommendationmodel.dto.AdminQueryEvaluationDtos.QueryEvaluationCommandResponse;
import com.taeo.bookcuration.admin.recommendationmodel.dto.AdminQueryEvaluationDtos.QueryEvaluationJobListResponse;
import com.taeo.bookcuration.admin.recommendationmodel.dto.AdminQueryEvaluationDtos.QueryEvaluationLabelSaveRequest;
import com.taeo.bookcuration.admin.recommendationmodel.dto.AdminQueryEvaluationDtos.QueryEvaluationRowsResponse;
import com.taeo.bookcuration.admin.recommendationmodel.dto.AdminQueryEvaluationDtos.QueryEvaluationRunRequest;
import com.taeo.bookcuration.admin.recommendationmodel.dto.AdminQueryEvaluationDtos.QueryEvaluationSummaryRequest;
import com.taeo.bookcuration.config.AiServerProperties;
import com.taeo.bookcuration.config.QueryEvaluationRunnerProperties;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Slf4j
@Component
public class QueryEvaluationAdminClient {

    private static final String AI_INTERNAL_HEADER_NAME = "X-AI-Internal-Key";
    private static final String RUNNER_HEADER_NAME = "X-Runner-Key";

    private final RestClient restClient;
    private final RestClient longRunningRestClient;
    private final RestClient localRunnerRestClient;
    private final String internalApiKey;
    private final QueryEvaluationRunnerProperties runnerProperties;

    public QueryEvaluationAdminClient(AiServerProperties properties, QueryEvaluationRunnerProperties runnerProperties) {
        SimpleClientHttpRequestFactory requestFactory = new SimpleClientHttpRequestFactory();
        requestFactory.setConnectTimeout(toMillis(properties.connectTimeout()));
        requestFactory.setReadTimeout(toMillis(properties.readTimeout()));

        SimpleClientHttpRequestFactory longRunningRequestFactory = new SimpleClientHttpRequestFactory();
        longRunningRequestFactory.setConnectTimeout(toMillis(properties.connectTimeout()));
        longRunningRequestFactory.setReadTimeout(toMillis(properties.lightfmTrainingReadTimeout()));

        this.internalApiKey = properties.internalApiKey();
        this.runnerProperties = runnerProperties;
        this.restClient = RestClient.builder()
                .baseUrl(properties.baseUrl())
                .requestFactory(requestFactory)
                .build();
        this.longRunningRestClient = RestClient.builder()
                .baseUrl(properties.baseUrl())
                .requestFactory(longRunningRequestFactory)
                .build();
        this.localRunnerRestClient = buildRunnerClient(runnerProperties);
    }

    public QueryEvaluationCommandResponse run(QueryEvaluationRunRequest request) {
        if (runnerProperties.enabled()) {
            return runOnLocalRunner(request);
        }
        return runOnAiServer(request);
    }

    public QueryEvaluationCommandResponse job(String jobId) {
        if (!runnerProperties.configured()) {
            throw new IllegalStateException("Local query evaluation runner가 설정되어 있지 않습니다.");
        }
        Map<String, Object> response = localRunnerRestClient.get()
                .uri("/evaluation/jobs/{jobId}", jobId)
                .headers(this::applyRunnerApiKey)
                .retrieve()
                .onStatus(HttpStatusCode::isError, (req, res) -> {
                    log.warn("Local query evaluation job API failed. status={}", res.getStatusCode());
                    throw new IllegalStateException("Local query 평가 job 상태를 읽을 수 없습니다.");
                })
                .body(Map.class);
        return runnerResponseToCommand(response, "local runner job status");
    }

    public QueryEvaluationJobListResponse jobs(Integer limit) {
        if (runnerProperties.configured()) {
            Map<String, Object> response = localRunnerRestClient.get()
                    .uri(builder -> builder
                            .path("/evaluation/jobs")
                            .queryParam("limit", limit == null ? 50 : Math.max(1, Math.min(200, limit)))
                            .build())
                    .headers(this::applyRunnerApiKey)
                    .retrieve()
                    .onStatus(HttpStatusCode::isError, (req, res) -> {
                        log.warn("Local query evaluation jobs API failed. status={}", res.getStatusCode());
                        throw new IllegalStateException("Local query 평가 job 목록을 읽을 수 없습니다.");
                    })
                    .body(Map.class);
            return runnerJobsResponseToList(response);
        }
        return restClient.get()
                .uri(builder -> builder
                        .path("/api/v1/admin/evaluation/query-payload-rules/jobs")
                        .queryParam("limit", limit == null ? 50 : Math.max(1, Math.min(200, limit)))
                        .build())
                .headers(this::applyInternalApiKey)
                .retrieve()
                .onStatus(HttpStatusCode::isError, (req, res) -> {
                    log.warn("AI query evaluation jobs API failed. status={}", res.getStatusCode());
                    throw new IllegalStateException("AI query 평가 job 목록을 읽을 수 없습니다.");
                })
                .body(QueryEvaluationJobListResponse.class);
    }

    private QueryEvaluationCommandResponse runOnAiServer(QueryEvaluationRunRequest request) {
        return longRunningRestClient.post()
                .uri("/api/v1/admin/evaluation/query-payload-rules/run")
                .headers(this::applyInternalApiKey)
                .body(request)
                .retrieve()
                .onStatus(HttpStatusCode::isError, (req, res) -> {
                    log.warn("AI query evaluation run API failed. status={}", res.getStatusCode());
                    throw new IllegalStateException("AI query 평가 실행 서버 응답이 올바르지 않습니다.");
                })
                .body(QueryEvaluationCommandResponse.class);
    }

    private QueryEvaluationCommandResponse runOnLocalRunner(QueryEvaluationRunRequest request) {
        if (!runnerProperties.configured()) {
            throw new IllegalStateException("QUERY_EVAL_LOCAL_RUNNER_ENABLED=true 이지만 QUERY_EVAL_LOCAL_RUNNER_BASE_URL이 비어 있습니다.");
        }
        Map<String, Object> response = localRunnerRestClient.post()
                .uri("/evaluation/run")
                .headers(this::applyRunnerApiKey)
                .body(toRunnerRequest(request))
                .retrieve()
                .onStatus(HttpStatusCode::isError, (req, res) -> {
                    log.warn("Local query evaluation run API failed. status={}", res.getStatusCode());
                    throw new IllegalStateException("Local query 평가 runner 실행 요청에 실패했습니다.");
                })
                .body(Map.class);
        return runnerResponseToCommand(response, "local runner evaluation requested");
    }

    public QueryEvaluationRowsResponse labels(String outDir, Integer offset, Integer limit) {
        return restClient.get()
                .uri(builder -> builder
                        .path("/api/v1/admin/evaluation/query-payload-rules/labels")
                        .queryParamIfPresent("out_dir", optionalText(outDir))
                        .queryParam("offset", offset == null ? 0 : Math.max(0, offset))
                        .queryParam("limit", limit == null ? 200 : Math.max(1, Math.min(1000, limit)))
                        .build())
                .headers(this::applyInternalApiKey)
                .retrieve()
                .onStatus(HttpStatusCode::isError, (req, res) -> {
                    log.warn("AI query evaluation labels API failed. status={}", res.getStatusCode());
                    throw new IllegalStateException("AI query 평가 label CSV를 읽을 수 없습니다.");
                })
                .body(QueryEvaluationRowsResponse.class);
    }

    public QueryEvaluationCommandResponse saveLabels(QueryEvaluationLabelSaveRequest request) {
        return longRunningRestClient.put()
                .uri("/api/v1/admin/evaluation/query-payload-rules/labels")
                .headers(this::applyInternalApiKey)
                .body(request)
                .retrieve()
                .onStatus(HttpStatusCode::isError, (req, res) -> {
                    log.warn("AI query evaluation save labels API failed. status={}", res.getStatusCode());
                    throw new IllegalStateException("AI query 평가 label 저장/요약 갱신에 실패했습니다.");
                })
                .body(QueryEvaluationCommandResponse.class);
    }

    public QueryEvaluationCommandResponse summarize(QueryEvaluationSummaryRequest request) {
        return longRunningRestClient.post()
                .uri("/api/v1/admin/evaluation/query-payload-rules/summarize")
                .headers(this::applyInternalApiKey)
                .body(request)
                .retrieve()
                .onStatus(HttpStatusCode::isError, (req, res) -> {
                    log.warn("AI query evaluation summarize API failed. status={}", res.getStatusCode());
                    throw new IllegalStateException("AI query 평가 요약 생성에 실패했습니다.");
                })
                .body(QueryEvaluationCommandResponse.class);
    }

    public QueryEvaluationRowsResponse summary(String outDir, String summaryType, Integer offset, Integer limit) {
        return restClient.get()
                .uri(builder -> builder
                        .path("/api/v1/admin/evaluation/query-payload-rules/summary")
                        .queryParamIfPresent("out_dir", optionalText(outDir))
                        .queryParam("summary_type", (summaryType == null || summaryType.isBlank()) ? "labeled" : summaryType)
                        .queryParam("offset", offset == null ? 0 : Math.max(0, offset))
                        .queryParam("limit", limit == null ? 200 : Math.max(1, Math.min(1000, limit)))
                        .build())
                .headers(this::applyInternalApiKey)
                .retrieve()
                .onStatus(HttpStatusCode::isError, (req, res) -> {
                    log.warn("AI query evaluation summary API failed. status={}", res.getStatusCode());
                    throw new IllegalStateException("AI query 평가 요약 CSV를 읽을 수 없습니다.");
                })
                .body(QueryEvaluationRowsResponse.class);
    }

    private Map<String, Object> toRunnerRequest(QueryEvaluationRunRequest request) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("cases_path", request.casesPath());
        body.put("cases_jsonl", request.casesJsonl());
        body.put("embedding_model", nullToDefault(request.embeddingModel(), "KURE"));
        body.put("top_k", request.topK() == null ? 1 : request.topK());
        body.put("max_corpus_docs", request.maxCorpusDocs() == null ? 100 : request.maxCorpusDocs());
        body.put("query_variants", nullToDefaultList(request.queryVariants(), List.of("original")));
        body.put("retrieval_variants", nullToDefaultList(request.retrievalVariants(), List.of("dense", "dense_bm25_rrf", "lookup_dense_bm25_rrf")));
        body.put("rule_variants", nullToDefaultList(request.ruleVariants(), List.of("current")));
        return body;
    }

    private QueryEvaluationCommandResponse runnerResponseToCommand(Map<String, Object> response, String fallbackMessage) {
        String rawStatus = text(response, "status");
        String status = normalizeRunnerStatus(rawStatus);
        // local runner는 WSL mount path와 ai-server reader path를 함께 줄 수 있습니다.
        // 관리자 label/summary API는 ai-server가 읽을 수 있는 reader_out_dir을 우선 사용합니다.
        String outDir = firstText(response, "reader_out_dir", "readerOutDir");
        if (outDir.isBlank()) {
            outDir = firstText(response, "out_dir", "outDir");
        }
        if (outDir.isBlank()) {
            outDir = firstText(response, "output_dir", "outputDir");
        }
        String jobId = firstText(response, "job_id", "jobId");
        String logPath = firstText(response, "log_path", "logPath");
        String error = firstText(response, "error", "detail");
        String message = error.isBlank() ? fallbackMessage : error;
        Integer exitCode = switch (status) {
            case "SUCCEEDED" -> 0;
            case "FAILED", "CANCELED" -> 1;
            default -> null;
        };
        return new QueryEvaluationCommandResponse(
                status,
                exitCode,
                outDir,
                path(outDir, "candidate_label_template.csv"),
                path(outDir, "auto_summary.csv"),
                path(outDir, "labeled_summary.csv"),
                path(outDir, "raw_results.jsonl"),
                "",
                "FAILED".equals(status) ? error : "",
                message,
                jobId,
                logPath
        );
    }

    private QueryEvaluationJobListResponse runnerJobsResponseToList(Map<String, Object> response) {
        Object rawJobs = response == null ? null : response.get("jobs");
        if (!(rawJobs instanceof List<?> rawList)) {
            return new QueryEvaluationJobListResponse(List.of());
        }
        List<QueryEvaluationCommandResponse> jobs = rawList.stream()
                .filter(Map.class::isInstance)
                .map(item -> runnerResponseToCommand((Map<String, Object>) item, "local runner job"))
                .toList();
        return new QueryEvaluationJobListResponse(jobs);
    }

    private String normalizeRunnerStatus(String status) {
        String value = status == null ? "" : status.trim().toUpperCase();
        return switch (value) {
            case "COMPLETED", "SUCCEEDED", "SUCCESS" -> "SUCCEEDED";
            case "FAILED", "ERROR" -> "FAILED";
            case "CANCELED", "CANCELLED" -> "CANCELED";
            default -> value.isBlank() ? "RUNNING" : value;
        };
    }

    private RestClient buildRunnerClient(QueryEvaluationRunnerProperties properties) {
        if (!properties.configured()) {
            return RestClient.builder().baseUrl("http://localhost").build();
        }
        SimpleClientHttpRequestFactory requestFactory = new SimpleClientHttpRequestFactory();
        requestFactory.setConnectTimeout(toMillis(properties.connectTimeout()));
        requestFactory.setReadTimeout(toMillis(properties.readTimeout()));
        return RestClient.builder()
                .baseUrl(properties.baseUrl())
                .requestFactory(requestFactory)
                .build();
    }

    private java.util.Optional<String> optionalText(String value) {
        if (value == null || value.isBlank()) {
            return java.util.Optional.empty();
        }
        return java.util.Optional.of(value);
    }

    private void applyInternalApiKey(HttpHeaders headers) {
        if (internalApiKey != null && !internalApiKey.isBlank()) {
            headers.set(AI_INTERNAL_HEADER_NAME, internalApiKey);
        }
    }

    private void applyRunnerApiKey(HttpHeaders headers) {
        if (runnerProperties.apiKey() != null && !runnerProperties.apiKey().isBlank()) {
            headers.set(RUNNER_HEADER_NAME, runnerProperties.apiKey());
        }
    }

    private int toMillis(Duration duration) {
        return Math.toIntExact(duration.toMillis());
    }

    private static String path(String dir, String fileName) {
        if (dir == null || dir.isBlank()) {
            return "";
        }
        return dir.endsWith("/") ? dir + fileName : dir + "/" + fileName;
    }

    private static String text(Map<String, Object> map, String key) {
        if (map == null || map.get(key) == null) {
            return "";
        }
        return String.valueOf(map.get(key));
    }

    private static String firstText(Map<String, Object> map, String first, String second) {
        String value = text(map, first);
        if (!value.isBlank()) {
            return value;
        }
        return text(map, second);
    }

    private static String nullToDefault(String value, String defaultValue) {
        return value == null || value.isBlank() ? defaultValue : value;
    }

    private static List<String> nullToDefaultList(List<String> values, List<String> defaultValues) {
        if (values == null || values.isEmpty()) {
            return defaultValues;
        }
        return values;
    }
}
