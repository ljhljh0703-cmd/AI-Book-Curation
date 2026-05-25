package com.taeo.bookcuration.admin.recommendationmodel.controller;

import com.taeo.bookcuration.admin.recommendationmodel.dto.AdminAudienceLabelDtos.AudienceLabelBatchJobResponse;
import com.taeo.bookcuration.admin.recommendationmodel.dto.AdminAudienceLabelDtos.AudienceLabelBatchStartRequest;
import com.taeo.bookcuration.admin.recommendationmodel.dto.AdminAudienceLabelDtos.AudienceLabelSummaryResponse;
import com.taeo.bookcuration.admin.recommendationmodel.dto.AdminLightFmTrainingDtos.LightFmArtifactSummaryResponse;
import com.taeo.bookcuration.admin.recommendationmodel.dto.AdminLightFmTrainingDtos.LightFmTrainingJobResponse;
import com.taeo.bookcuration.admin.recommendationmodel.dto.AdminLightFmTrainingDtos.LightFmTrainingStartRequest;
import com.taeo.bookcuration.admin.recommendationmodel.dto.AdminQueryEvaluationDtos.QueryEvaluationCommandResponse;
import com.taeo.bookcuration.admin.recommendationmodel.dto.AdminQueryEvaluationDtos.QueryEvaluationJobListResponse;
import com.taeo.bookcuration.admin.recommendationmodel.dto.AdminQueryEvaluationDtos.QueryEvaluationLabelSaveRequest;
import com.taeo.bookcuration.admin.recommendationmodel.dto.AdminQueryEvaluationDtos.QueryEvaluationRowsResponse;
import com.taeo.bookcuration.admin.recommendationmodel.dto.AdminQueryEvaluationDtos.QueryEvaluationRunRequest;
import com.taeo.bookcuration.admin.recommendationmodel.dto.AdminQueryEvaluationDtos.QueryEvaluationSummaryRequest;
import com.taeo.bookcuration.admin.recommendationmodel.dto.AdminRecommendationModelDtos.RecommendationModelSettingResponse;
import com.taeo.bookcuration.admin.recommendationmodel.dto.AdminRecommendationModelDtos.RecommendationModelSettingUpdateRequest;
import com.taeo.bookcuration.auth.service.AuthUser;
import com.taeo.bookcuration.recommendation.audience.AudienceLabelBatchService;
import com.taeo.bookcuration.recommendation.lightfm.LightFmTrainingJobService;
import com.taeo.bookcuration.recommendation.evaluation.QueryEvaluationAdminClient;
import com.taeo.bookcuration.recommendation.service.RecommendationModelSettingService;
import com.taeo.bookcuration.recommendation.service.RecommendationModelSettingService.RecommendationModelSetting;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.UUID;

@RestController
@RequestMapping("/api/admin/recommendation-model-settings")
@PreAuthorize("hasRole('ADMIN')")
@RequiredArgsConstructor
public class AdminRecommendationModelController {

    private final RecommendationModelSettingService recommendationModelSettingService;
    private final AudienceLabelBatchService audienceLabelBatchService;
    private final LightFmTrainingJobService lightFmTrainingJobService;
    private final QueryEvaluationAdminClient queryEvaluationAdminClient;

    @GetMapping
    public RecommendationModelSettingResponse getSetting() {
        return toResponse(recommendationModelSettingService.getSetting());
    }

    @PutMapping
    public RecommendationModelSettingResponse updateSetting(@Valid @RequestBody RecommendationModelSettingUpdateRequest request) {
        RecommendationModelSetting setting = recommendationModelSettingService.updateSetting(
                request.embeddingModel(),
                request.recommendationStrategy(),
                request.personalizationModel(),
                request.rerankerProvider(),
                request.bm25Enabled()
        );
        return toResponse(setting);
    }

    @GetMapping("/audience-label-summary")
    public AudienceLabelSummaryResponse getAudienceLabelSummary() {
        return audienceLabelBatchService.summary();
    }

    @PostMapping("/audience-label-jobs")
    public AudienceLabelBatchJobResponse startAudienceLabelJob(@Valid @RequestBody AudienceLabelBatchStartRequest request) {
        return audienceLabelBatchService.start(
                request == null ? null : request.limit(),
                request == null ? null : request.force()
        );
    }

    @GetMapping("/audience-label-jobs/{jobId}")
    public AudienceLabelBatchJobResponse getAudienceLabelJob(@PathVariable UUID jobId) {
        return audienceLabelBatchService.get(jobId);
    }


    @GetMapping("/lightfm-artifact-summary")
    public LightFmArtifactSummaryResponse getLightFmArtifactSummary() {
        return lightFmTrainingJobService.summary();
    }

    @PostMapping("/lightfm-training-jobs")
    public LightFmTrainingJobResponse startLightFmTrainingJob(
            @AuthenticationPrincipal AuthUser authUser,
            @RequestBody(required = false) LightFmTrainingStartRequest request
    ) {
        return lightFmTrainingJobService.startManual(
                authUser == null ? null : authUser.id(),
                request == null ? null : request.trainingMode()
        );
    }

    @GetMapping("/lightfm-training-jobs/latest")
    public LightFmTrainingJobResponse getLatestLightFmTrainingJob() {
        return lightFmTrainingJobService.latest().orElse(null);
    }

    @GetMapping("/lightfm-training-jobs/{jobId}")
    public LightFmTrainingJobResponse getLightFmTrainingJob(@PathVariable UUID jobId) {
        return lightFmTrainingJobService.get(jobId);
    }


    @PostMapping("/query-evaluation/run")
    public QueryEvaluationCommandResponse runQueryEvaluation(@RequestBody(required = false) QueryEvaluationRunRequest request) {
        return queryEvaluationAdminClient.run(request == null ? new QueryEvaluationRunRequest(
                null,
                null,
                null,
                "KURE",
                1,
                100,
                java.util.List.of("original"),
                java.util.List.of("dense", "dense_bm25_rrf", "lookup_dense_bm25_rrf"),
                java.util.List.of("current")
        ) : request);
    }

    @GetMapping("/query-evaluation/jobs")
    public QueryEvaluationJobListResponse getQueryEvaluationJobs(
            @RequestParam(required = false, defaultValue = "50") Integer limit
    ) {
        return queryEvaluationAdminClient.jobs(limit);
    }

    @GetMapping("/query-evaluation/jobs/{jobId}")
    public QueryEvaluationCommandResponse getQueryEvaluationJob(@PathVariable String jobId) {
        return queryEvaluationAdminClient.job(jobId);
    }

    @GetMapping("/query-evaluation/labels")
    public QueryEvaluationRowsResponse getQueryEvaluationLabels(
            @RequestParam(required = false) String outDir,
            @RequestParam(required = false, defaultValue = "0") Integer offset,
            @RequestParam(required = false, defaultValue = "200") Integer limit
    ) {
        return queryEvaluationAdminClient.labels(outDir, offset, limit);
    }

    @PutMapping("/query-evaluation/labels")
    public QueryEvaluationCommandResponse saveQueryEvaluationLabels(@RequestBody QueryEvaluationLabelSaveRequest request) {
        return queryEvaluationAdminClient.saveLabels(request);
    }

    @PostMapping("/query-evaluation/summarize")
    public QueryEvaluationCommandResponse summarizeQueryEvaluation(@RequestBody(required = false) QueryEvaluationSummaryRequest request) {
        return queryEvaluationAdminClient.summarize(request == null ? new QueryEvaluationSummaryRequest(null, 10) : request);
    }

    @GetMapping("/query-evaluation/summary")
    public QueryEvaluationRowsResponse getQueryEvaluationSummary(
            @RequestParam(required = false) String outDir,
            @RequestParam(required = false, defaultValue = "labeled") String summaryType,
            @RequestParam(required = false, defaultValue = "0") Integer offset,
            @RequestParam(required = false, defaultValue = "200") Integer limit
    ) {
        return queryEvaluationAdminClient.summary(outDir, summaryType, offset, limit);
    }

    private RecommendationModelSettingResponse toResponse(RecommendationModelSetting setting) {
        return new RecommendationModelSettingResponse(
                setting.embeddingModel(),
                setting.recommendationStrategy(),
                setting.personalizationModel(),
                setting.rerankerProvider(),
                setting.bm25Enabled(),
                setting.rankingModel(),
                RecommendationModelSettingService.embeddingModelOptions(),
                RecommendationModelSettingService.recommendationStrategyOptions(),
                RecommendationModelSettingService.personalizationModelOptions(),
                RecommendationModelSettingService.rerankerProviderOptions(),
                RecommendationModelSettingService.rankingModelOptions(),
                setting.updatedAt()
        );
    }
}
