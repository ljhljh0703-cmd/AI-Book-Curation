package com.taeo.bookcuration.admin.recommendationmodel.dto;

import java.util.List;
import java.util.Map;

public final class AdminQueryEvaluationDtos {

    private AdminQueryEvaluationDtos() {
    }

    public record QueryEvaluationRunRequest(
            String casesPath,
            // 관리자 화면에서 직접 입력한 평가 질의입니다. 비어 있으면 ai-server 기본 JSONL 파일을 사용합니다.
            String casesJsonl,
            String outDir,
            String embeddingModel,
            Integer topK,
            Integer maxCorpusDocs,
            List<String> queryVariants,
            List<String> retrievalVariants,
            List<String> ruleVariants
    ) {
    }

    public record QueryEvaluationCommandResponse(
            String status,
            Integer exitCode,
            String outDir,
            String labelCsvPath,
            String autoSummaryPath,
            String labeledSummaryPath,
            String rawResultsPath,
            String stdoutTail,
            String stderrTail,
            String message,
            // 수정 포인트: local runner 비동기 실행 상태를 관리자 화면에서 polling할 수 있도록 job id를 전달합니다.
            String jobId,
            String logPath
    ) {
    }

    public record QueryEvaluationRowsResponse(
            String outDir,
            String fileName,
            List<String> columns,
            List<Map<String, Object>> rows,
            Integer totalRows,
            Integer offset,
            Integer limit
    ) {
    }

    public record QueryEvaluationJobListResponse(
            List<QueryEvaluationCommandResponse> jobs
    ) {
    }

    public record QueryEvaluationLabelSaveRequest(
            String outDir,
            List<QueryEvaluationLabelUpdate> rows,
            Integer topK
    ) {
    }

    public record QueryEvaluationLabelUpdate(
            String rowKey,
            String humanRelevance02,
            String humanMemo
    ) {
    }

    public record QueryEvaluationSummaryRequest(
            String outDir,
            Integer topK
    ) {
    }
}
