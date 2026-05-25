package com.taeo.bookcuration.admin.recommendationmodel.dto;

import java.time.OffsetDateTime;
import java.util.Map;
import java.util.UUID;

public final class AdminLightFmTrainingDtos {

    private AdminLightFmTrainingDtos() {
    }

    public record LightFmTrainingStartRequest(
            String trainingMode
    ) {
    }

    public record LightFmTrainingJobResponse(
            UUID jobId,
            String triggerType,
            String status,
            UUID requestedBy,
            String datasetManifestPath,
            String workDir,
            String artifactVersion,
            String artifactDir,
            String previousArtifactVersion,
            OffsetDateTime startedAt,
            OffsetDateTime finishedAt,
            Integer timeoutSeconds,
            Integer exitCode,
            String errorMessage,
            Map<String, Object> parameters,
            Map<String, Object> metrics,
            String message
    ) {
    }

    public record LightFmArtifactSummaryResponse(
            Boolean available,
            String artifactVersion,
            String artifactDir,
            Integer userCount,
            Integer itemCount,
            Integer positiveEventCount,
            OffsetDateTime trainedAt,
            LightFmTrainingJobResponse latestJob,
            String errorMessage
    ) {
    }
}
