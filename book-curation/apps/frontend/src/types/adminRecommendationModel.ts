export type EmbeddingModel = "CLOVA" | "KURE";
export type RecommendationStrategy = "AUTO_HYBRID" | "RULE_BASED_ONLY";
export type PersonalizationModel = "NONE" | "LIGHTFM" | "SASREC" | "BERT4REC";
export type RerankerProvider = "NONE" | "GTE_MULTILINGUAL" | "HCX_RERANKER";
// 기존 코드 호환 alias입니다. 신규 화면에서는 personalizationModel을 사용합니다.
export type RankingModel = PersonalizationModel | "RULE_BASED";

export type RecommendationModelSetting = {
  embeddingModel: EmbeddingModel;
  recommendationStrategy: RecommendationStrategy;
  personalizationModel: PersonalizationModel;
  rerankerProvider: RerankerProvider;
  bm25Enabled: boolean;
  rankingModel?: RankingModel;
  embeddingModelOptions: EmbeddingModel[];
  recommendationStrategyOptions: RecommendationStrategy[];
  personalizationModelOptions: PersonalizationModel[];
  rerankerProviderOptions: RerankerProvider[];
  rankingModelOptions?: RankingModel[];
  updatedAt?: string | null;
};

export type RecommendationModelSettingUpdateRequest = {
  embeddingModel: EmbeddingModel;
  recommendationStrategy: RecommendationStrategy;
  personalizationModel: PersonalizationModel;
  rerankerProvider: RerankerProvider;
  bm25Enabled: boolean;
};

export type AudienceLabelJobStatus = "REQUESTED" | "RUNNING" | "SUCCEEDED" | "FAILED";

export type AudienceLabelJobStartRequest = {
  limit: number;
  force?: boolean;
};

export type AudienceLabelSummary = {
  schemaReady: boolean;
  totalBookCount: number;
  defaultTargetCount: number;
  forceTargetCount: number;
  pendingCount: number;
  failedCount: number;
  readyCount: number;
  skippedCount: number;
  unknownStatusCount: number;
  message?: string | null;
};

export type AudienceLabelJob = {
  jobId: string;
  status: AudienceLabelJobStatus;
  requestedLimit: number;
  force: boolean;
  totalTargetCount: number;
  processedCount: number;
  successCount: number;
  failedCount: number;
  skippedCount: number;
  message?: string | null;
  errorMessage?: string | null;
  startedAt?: string | null;
  finishedAt?: string | null;
};

export type LightFmTrainingJobStatus =
  | "REQUESTED"
  | "RUNNING"
  | "EXPORTING"
  | "TRAINING"
  | "PROMOTING"
  | "SUCCEEDED"
  | "FAILED"
  | "TIMEOUT"
  | "CANCELLED"
  | "SKIPPED";

export type LightFmTrainingJob = {
  jobId: string;
  triggerType: "MANUAL" | "SCHEDULED";
  status: LightFmTrainingJobStatus;
  requestedBy?: string | null;
  datasetManifestPath?: string | null;
  workDir?: string | null;
  artifactVersion?: string | null;
  artifactDir?: string | null;
  previousArtifactVersion?: string | null;
  startedAt?: string | null;
  finishedAt?: string | null;
  timeoutSeconds?: number | null;
  exitCode?: number | null;
  errorMessage?: string | null;
  parameters?: Record<string, unknown>;
  metrics?: Record<string, unknown>;
  message?: string | null;
};

export type LightFmArtifactSummary = {
  available: boolean;
  artifactVersion?: string | null;
  artifactDir?: string | null;
  userCount?: number | null;
  itemCount?: number | null;
  positiveEventCount?: number | null;
  trainedAt?: string | null;
  latestJob?: LightFmTrainingJob | null;
  errorMessage?: string | null;
};

export type LightFmTrainingStartRequest = {
  trainingMode?: string;
};

export type QueryEvaluationRunRequest = {
  casesPath?: string;
  /** 화면에서 직접 입력한 평가 질의입니다. 비어 있으면 ai-server 기본 평가 파일을 사용합니다. */
  casesJsonl?: string;
  embeddingModel?: EmbeddingModel;
  topK?: number;
  maxCorpusDocs?: number;
  queryVariants?: string[];
  retrievalVariants?: string[];
  ruleVariants?: string[];
};

export type QueryEvaluationCommandResponse = {
  status: "SUCCEEDED" | "FAILED" | "RUNNING" | "PENDING" | "CANCELED" | string;
  exitCode?: number | null;
  outDir: string;
  labelCsvPath: string;
  autoSummaryPath: string;
  labeledSummaryPath: string;
  rawResultsPath: string;
  stdoutTail?: string;
  stderrTail?: string;
  message?: string | null;
  jobId?: string | null;
  logPath?: string | null;
};

export type QueryEvaluationRowsResponse = {
  outDir: string;
  fileName: string;
  columns: string[];
  rows: Array<Record<string, unknown>>;
  totalRows: number;
  offset: number;
  limit: number;
};

export type QueryEvaluationJobListResponse = {
  jobs: QueryEvaluationCommandResponse[];
};

export type QueryEvaluationLabelUpdate = {
  rowKey: string;
  humanRelevance02?: string;
  humanMemo?: string;
};

export type QueryEvaluationLabelSaveRequest = {
  /** job별 평가 폴더를 지정합니다. 비우면 ai-server 기본 latest/job 저장소를 사용합니다. */
  outDir?: string;
  rows: QueryEvaluationLabelUpdate[];
  topK?: number;
};

export type QueryEvaluationSummaryRequest = {
  /** job별 평가 폴더를 지정합니다. 비우면 ai-server 기본 latest/job 저장소를 사용합니다. */
  outDir?: string;
  topK?: number;
};
