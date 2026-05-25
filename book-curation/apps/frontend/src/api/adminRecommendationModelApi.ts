import { api } from "./authApi";
import type {
  AudienceLabelJob,
  AudienceLabelJobStartRequest,
  AudienceLabelSummary,
  LightFmArtifactSummary,
  LightFmTrainingJob,
  LightFmTrainingStartRequest,
  RecommendationModelSetting,
  RecommendationModelSettingUpdateRequest,
  QueryEvaluationCommandResponse,
  QueryEvaluationJobListResponse,
  QueryEvaluationLabelSaveRequest,
  QueryEvaluationRowsResponse,
  QueryEvaluationRunRequest,
  QueryEvaluationSummaryRequest,
} from "../types/adminRecommendationModel";

const API_PREFIX = "/api";

export const getAdminRecommendationModelSetting = async (): Promise<RecommendationModelSetting> => {
  const res = await api.get<RecommendationModelSetting>(
    `${API_PREFIX}/admin/recommendation-model-settings`
  );
  return res.data;
};

export const updateAdminRecommendationModelSetting = async (
  payload: RecommendationModelSettingUpdateRequest
): Promise<RecommendationModelSetting> => {
  const res = await api.put<RecommendationModelSetting>(
    `${API_PREFIX}/admin/recommendation-model-settings`,
    payload
  );
  return res.data;
};

export const getAudienceLabelSummary = async (): Promise<AudienceLabelSummary> => {
  const res = await api.get<AudienceLabelSummary>(
    `${API_PREFIX}/admin/recommendation-model-settings/audience-label-summary`
  );
  return res.data;
};

export const startAudienceLabelJob = async (
  payload: AudienceLabelJobStartRequest
): Promise<AudienceLabelJob> => {
  const res = await api.post<AudienceLabelJob>(
    `${API_PREFIX}/admin/recommendation-model-settings/audience-label-jobs`,
    payload
  );
  return res.data;
};

export const getAudienceLabelJob = async (jobId: string): Promise<AudienceLabelJob> => {
  const res = await api.get<AudienceLabelJob>(
    `${API_PREFIX}/admin/recommendation-model-settings/audience-label-jobs/${jobId}`
  );
  return res.data;
};

export const getLightFmArtifactSummary = async (): Promise<LightFmArtifactSummary> => {
  const res = await api.get<LightFmArtifactSummary>(
    `${API_PREFIX}/admin/recommendation-model-settings/lightfm-artifact-summary`
  );
  return res.data;
};

export const getLatestLightFmTrainingJob = async (): Promise<LightFmTrainingJob | null> => {
  const res = await api.get<LightFmTrainingJob | null>(
    `${API_PREFIX}/admin/recommendation-model-settings/lightfm-training-jobs/latest`
  );
  return res.data;
};

export const startLightFmTrainingJob = async (
  payload: LightFmTrainingStartRequest = {}
): Promise<LightFmTrainingJob> => {
  const res = await api.post<LightFmTrainingJob>(
    `${API_PREFIX}/admin/recommendation-model-settings/lightfm-training-jobs`,
    payload
  );
  return res.data;
};

export const getLightFmTrainingJob = async (jobId: string): Promise<LightFmTrainingJob> => {
  const res = await api.get<LightFmTrainingJob>(
    `${API_PREFIX}/admin/recommendation-model-settings/lightfm-training-jobs/${jobId}`
  );
  return res.data;
};


export const runQueryPayloadRuleEvaluation = async (
  payload: QueryEvaluationRunRequest
): Promise<QueryEvaluationCommandResponse> => {
  const res = await api.post<QueryEvaluationCommandResponse>(
    `${API_PREFIX}/admin/recommendation-model-settings/query-evaluation/run`,
    payload
  );
  return res.data;
};

export const getQueryPayloadRuleEvaluationJob = async (
  jobId: string
): Promise<QueryEvaluationCommandResponse> => {
  const res = await api.get<QueryEvaluationCommandResponse>(
    `${API_PREFIX}/admin/recommendation-model-settings/query-evaluation/jobs/${jobId}`
  );
  return res.data;
};

export const getQueryPayloadRuleEvaluationJobs = async (
  limit = 50
): Promise<QueryEvaluationJobListResponse> => {
  const res = await api.get<QueryEvaluationJobListResponse>(
    `${API_PREFIX}/admin/recommendation-model-settings/query-evaluation/jobs`,
    { params: { limit } }
  );
  return res.data;
};

export const getQueryPayloadRuleLabels = async (
  outDir?: string,
  offset = 0,
  limit = 200
): Promise<QueryEvaluationRowsResponse> => {
  const res = await api.get<QueryEvaluationRowsResponse>(
    `${API_PREFIX}/admin/recommendation-model-settings/query-evaluation/labels`,
    { params: { outDir, offset, limit } }
  );
  return res.data;
};

export const saveQueryPayloadRuleLabels = async (
  payload: QueryEvaluationLabelSaveRequest
): Promise<QueryEvaluationCommandResponse> => {
  const res = await api.put<QueryEvaluationCommandResponse>(
    `${API_PREFIX}/admin/recommendation-model-settings/query-evaluation/labels`,
    payload
  );
  return res.data;
};

export const summarizeQueryPayloadRuleLabels = async (
  payload: QueryEvaluationSummaryRequest
): Promise<QueryEvaluationCommandResponse> => {
  const res = await api.post<QueryEvaluationCommandResponse>(
    `${API_PREFIX}/admin/recommendation-model-settings/query-evaluation/summarize`,
    payload
  );
  return res.data;
};

export const getQueryPayloadRuleSummary = async (
  outDir?: string,
  summaryType: "auto" | "labeled" | "dimension" = "labeled",
  offset = 0,
  limit = 200
): Promise<QueryEvaluationRowsResponse> => {
  const res = await api.get<QueryEvaluationRowsResponse>(
    `${API_PREFIX}/admin/recommendation-model-settings/query-evaluation/summary`,
    { params: { outDir, summaryType, offset, limit } }
  );
  return res.data;
};
