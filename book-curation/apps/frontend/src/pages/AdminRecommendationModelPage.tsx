import {
  Activity,
  BrainCircuit,
  DatabaseZap,
  PlayCircle,
  RefreshCw,
  Save,
  ServerCog,
  Tags,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
} from "react";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  getAdminRecommendationModelSetting,
  getAudienceLabelJob,
  getAudienceLabelSummary,
  getLightFmArtifactSummary,
  getLightFmTrainingJob,
  startAudienceLabelJob,
  startLightFmTrainingJob,
  updateAdminRecommendationModelSetting,
} from "../api/adminRecommendationModelApi";
import { getMe } from "../api/authApi";
import AdminLayout from "../components/admin/AdminLayout";
import type {
  AudienceLabelJob,
  AudienceLabelSummary,
  EmbeddingModel,
  LightFmArtifactSummary,
  LightFmTrainingJob,
  PersonalizationModel,
  RecommendationModelSetting,
  RecommendationStrategy,
  RerankerProvider,
} from "../types/adminRecommendationModel";
import type { MeResponse } from "../types/auth";
import { saveUser } from "../utils/storage";

type TabKey = "model" | "training" | "labels";

const modelLabels: Record<string, string> = {
  CLOVA: "CLOVA",
  KURE: "KURE",
  AUTO_HYBRID: "AUTO_HYBRID",
  RULE_BASED_ONLY: "RULE_BASED_ONLY",
  NONE: "NONE",
  LIGHTFM: "LIGHTFM",
  SASREC: "SASREC",
  BERT4REC: "BERT4REC",
  GTE_MULTILINGUAL: "GTE_MULTILINGUAL",
  HCX_RERANKER: "HCX_RERANKER",
};

const strategyDescriptions: Record<RecommendationStrategy, string> = {
  AUTO_HYBRID:
    "선택한 개인화 모델을 사용자별로 적용 가능할 때만 사용하고, 실패하면 자동 fallback합니다.",
  RULE_BASED_ONLY:
    "개인화 모델을 사용하지 않고 Qdrant/Rule 기반 후보만 사용합니다.",
};

const personalizationDescriptions: Record<PersonalizationModel, string> = {
  NONE: "개인화 모델을 사용하지 않습니다.",
  LIGHTFM:
    "current LightFM artifact에서 해당 사용자 scoring이 가능할 때만 사용합니다.",
  SASREC:
    "향후 시퀀스 모델 연결용 설정입니다. 현재 미구현이면 자동 fallback합니다.",
  BERT4REC:
    "향후 양방향 시퀀스 모델 연결용 설정입니다. 현재 미구현이면 자동 fallback합니다.",
};

const rerankerDescriptions: Record<RerankerProvider, string> = {
  NONE: "외부/로컬 reranker를 사용하지 않습니다.",
  GTE_MULTILINGUAL:
    "Local PC GPU primary → NAS k3s fallback 순서로 GTE reranker를 호출합니다.",
  HCX_RERANKER:
    "CLOVA Studio Reranker API를 호출합니다. live secret의 HCX_RERANKER_API_KEY 또는 CLOVA_API_KEY를 사용합니다.",
};

const audienceStatusLabels: Record<AudienceLabelJob["status"], string> = {
  REQUESTED: "요청됨",
  RUNNING: "처리 중",
  SUCCEEDED: "성공",
  FAILED: "실패",
};

const lightFmStatusLabels: Record<LightFmTrainingJob["status"], string> = {
  REQUESTED: "요청됨",
  RUNNING: "준비 중",
  EXPORTING: "데이터 export 중",
  TRAINING: "학습 중",
  PROMOTING: "artifact 승격 중",
  SUCCEEDED: "성공",
  FAILED: "실패",
  TIMEOUT: "Timeout",
  CANCELLED: "중단",
  SKIPPED: "건너뜀",
};

const getErrorMessage = (error: unknown) => {
  if (error instanceof Error && error.message) return error.message;
  return "추천 관리 정보를 처리하지 못했습니다.";
};

const formatUpdatedAt = (value?: string | null) => {
  if (!value) return "아직 DB 기본값으로 동작 중";
  return new Date(value).toLocaleString("ko-KR");
};

const formatJobTime = (value?: string | null) => {
  if (!value) return "-";
  return new Date(value).toLocaleString("ko-KR");
};

const formatNumber = (value?: number | null) =>
  typeof value === "number" && Number.isFinite(value)
    ? value.toLocaleString("ko-KR")
    : "-";

const isAudienceJobRunning = (job?: AudienceLabelJob | null) =>
  job?.status === "REQUESTED" || job?.status === "RUNNING";

const isLightFmJobRunning = (job?: LightFmTrainingJob | null) =>
  job?.status === "REQUESTED" ||
  job?.status === "RUNNING" ||
  job?.status === "EXPORTING" ||
  job?.status === "TRAINING" ||
  job?.status === "PROMOTING";

const AdminRecommendationModelPage = () => {
  const [activeTab, setActiveTab] = useState<TabKey>("model");
  const [user, setUser] = useState<MeResponse | null>(null);
  const [setting, setSetting] = useState<RecommendationModelSetting | null>(
    null,
  );
  const [embeddingModel, setEmbeddingModel] = useState<EmbeddingModel>("CLOVA");
  const [recommendationStrategy, setRecommendationStrategy] =
    useState<RecommendationStrategy>("AUTO_HYBRID");
  const [personalizationModel, setPersonalizationModel] =
    useState<PersonalizationModel>("LIGHTFM");
  const [rerankerProvider, setRerankerProvider] =
    useState<RerankerProvider>("NONE");
  const [bm25Enabled, setBm25Enabled] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  const [lightFmSummary, setLightFmSummary] =
    useState<LightFmArtifactSummary | null>(null);
  const [lightFmJob, setLightFmJob] = useState<LightFmTrainingJob | null>(null);
  const [lightFmLoading, setLightFmLoading] = useState(false);
  const [lightFmJobLoading, setLightFmJobLoading] = useState(false);

  const [audienceLimit, setAudienceLimit] = useState(50);
  const [audienceForce, setAudienceForce] = useState(false);
  const [audienceJob, setAudienceJob] = useState<AudienceLabelJob | null>(null);
  const [audienceSummary, setAudienceSummary] =
    useState<AudienceLabelSummary | null>(null);
  const [audienceJobLoading, setAudienceJobLoading] = useState(false);
  const [audienceSummaryLoading, setAudienceSummaryLoading] = useState(false);

  const isAdmin = user?.role === "ADMIN";
  const audienceBatchRunning =
    audienceJobLoading || isAudienceJobRunning(audienceJob);
  const lightFmBatchRunning =
    lightFmJobLoading || isLightFmJobRunning(lightFmJob);

  const embeddingOptions = useMemo(
    () =>
      setting?.embeddingModelOptions ?? (["CLOVA", "KURE"] as EmbeddingModel[]),
    [setting],
  );
  const strategyOptions = useMemo(
    () =>
      setting?.recommendationStrategyOptions ??
      (["AUTO_HYBRID", "RULE_BASED_ONLY"] as RecommendationStrategy[]),
    [setting],
  );
  const personalizationOptions = useMemo(
    () =>
      setting?.personalizationModelOptions ??
      (["NONE", "LIGHTFM", "SASREC", "BERT4REC"] as PersonalizationModel[]),
    [setting],
  );
  const rerankerOptions = useMemo(
    () =>
      setting?.rerankerProviderOptions ??
      (["NONE", "GTE_MULTILINGUAL", "HCX_RERANKER"] as RerankerProvider[]),
    [setting],
  );

  const normalizedAudienceLimit = useMemo(() => {
    if (!Number.isFinite(audienceLimit)) return 50;
    return Math.max(1, Math.min(500, audienceLimit));
  }, [audienceLimit]);

  const estimatedRunCount = useMemo(() => {
    const targetCount = audienceForce
      ? audienceSummary?.forceTargetCount
      : audienceSummary?.defaultTargetCount;
    if (!targetCount) return 0;
    return Math.ceil(targetCount / normalizedAudienceLimit);
  }, [audienceForce, audienceSummary, normalizedAudienceLimit]);

  const loadAudienceSummary = useCallback(async () => {
    setAudienceSummaryLoading(true);
    try {
      const response = await getAudienceLabelSummary();
      setAudienceSummary(response);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setAudienceSummaryLoading(false);
    }
  }, []);

  const loadLightFmSummary = useCallback(async () => {
    setLightFmLoading(true);
    try {
      const response = await getLightFmArtifactSummary();
      setLightFmSummary(response);
      setLightFmJob(response.latestJob ?? null);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setLightFmLoading(false);
    }
  }, []);

  const loadSetting = useCallback(async () => {
    setLoading(true);
    setErrorMessage("");
    setSuccessMessage("");
    try {
      const me = await getMe();
      setUser(me);
      saveUser(me);
      if (me.role !== "ADMIN") {
        setErrorMessage("관리자 권한이 있는 계정만 접근할 수 있습니다.");
        return;
      }
      const response = await getAdminRecommendationModelSetting();
      setSetting(response);
      setEmbeddingModel(response.embeddingModel);
      setRecommendationStrategy(response.recommendationStrategy);
      setPersonalizationModel(response.personalizationModel);
      setRerankerProvider(response.rerankerProvider);
      setBm25Enabled(Boolean(response.bm25Enabled));
      void loadAudienceSummary();
      void loadLightFmSummary();
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }, [loadAudienceSummary, loadLightFmSummary]);

  useEffect(() => {
    void loadSetting();
  }, [loadSetting]);

  useEffect(() => {
    if (!audienceJob?.jobId || !isAudienceJobRunning(audienceJob)) return;
    const timer = window.setInterval(() => {
      void getAudienceLabelJob(audienceJob.jobId)
        .then((job) => {
          setAudienceJob(job);
          if (!isAudienceJobRunning(job)) void loadAudienceSummary();
        })
        .catch((error) => setErrorMessage(getErrorMessage(error)));
    }, 2500);
    return () => window.clearInterval(timer);
  }, [audienceJob, loadAudienceSummary]);

  useEffect(() => {
    if (!lightFmJob?.jobId || !isLightFmJobRunning(lightFmJob)) return;
    const timer = window.setInterval(() => {
      void getLightFmTrainingJob(lightFmJob.jobId)
        .then((job) => {
          setLightFmJob(job);
          if (!isLightFmJobRunning(job)) void loadLightFmSummary();
        })
        .catch((error) => setErrorMessage(getErrorMessage(error)));
    }, 3000);
    return () => window.clearInterval(timer);
  }, [lightFmJob, loadLightFmSummary]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setErrorMessage("");
    setSuccessMessage("");
    setSaving(true);
    try {
      const response = await updateAdminRecommendationModelSetting({
        embeddingModel,
        recommendationStrategy,
        personalizationModel,
        rerankerProvider,
        bm25Enabled,
      });
      setSetting(response);
      setEmbeddingModel(response.embeddingModel);
      setRecommendationStrategy(response.recommendationStrategy);
      setPersonalizationModel(response.personalizationModel);
      setRerankerProvider(response.rerankerProvider);
      setBm25Enabled(Boolean(response.bm25Enabled));
      setSuccessMessage(
        "추천 모델 설정을 저장했습니다. 다음 recommend API 호출부터 반영됩니다.",
      );
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setSaving(false);
    }
  };

  const handleStartLightFmTrainingJob = async () => {
    setErrorMessage("");
    setSuccessMessage("");
    setLightFmJobLoading(true);
    try {
      const job = await startLightFmTrainingJob({
        trainingMode: "HYBRID_LITE",
      });
      setLightFmJob(job);
      setSuccessMessage("LightFM 학습 job 실행을 요청했습니다.");
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setLightFmJobLoading(false);
    }
  };

  const handleStartAudienceLabelJob = async () => {
    setErrorMessage("");
    setSuccessMessage("");
    setAudienceJobLoading(true);
    try {
      const job = await startAudienceLabelJob({
        limit: normalizedAudienceLimit,
        force: audienceForce,
      });
      setAudienceJob(job);
      setSuccessMessage("Audience label 배치 실행을 요청했습니다.");
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setAudienceJobLoading(false);
    }
  };

  const tabs: { key: TabKey; label: string; description: string }[] = [
    {
      key: "model",
      label: "추천 모델 설정",
      description: "추천 전략과 모델 provider만 관리",
    },
    {
      key: "training",
      label: "학습 관리",
      description: "LightFM 수동 학습과 artifact 확인",
    },
    {
      key: "labels",
      label: "라벨 관리",
      description: "Audience label 생성 batch 관리",
    },
  ];

  if (loading) {
    return (
      <AdminLayout
        title="추천 관리"
        description="추천 모델 설정, LightFM 학습, Audience label 생성을 분리해서 관리합니다."
      >
        <Card className="rounded-[2rem] border-slate-200 shadow-sm">
          <CardContent className="p-8 text-sm font-semibold text-slate-600">
            추천 관리 정보를 불러오는 중입니다...
          </CardContent>
        </Card>
      </AdminLayout>
    );
  }

  return (
    <AdminLayout
      title="추천 관리"
      description="추천 모델 설정, LightFM 학습, Audience label 생성을 분리해서 관리합니다."
    >
      <div className="space-y-6">
        <section className="rounded-[2rem] bg-slate-950 p-6 text-white shadow-sm">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <p className="text-sm font-bold text-slate-300">
                Recommendation Admin
              </p>
              <h1 className="mt-2 text-3xl font-black tracking-tight">
                추천 관리
              </h1>
              <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-300">
                추천 모델 설정, LightFM 학습, Audience label 생성을
                분리했습니다. query/retrieval/rule 평가는 좌측의 별도 평가 관리
                메뉴에서 다룹니다.
              </p>
            </div>
            <Button
              type="button"
              variant="secondary"
              className="rounded-2xl"
              onClick={() => void loadSetting()}
            >
              <RefreshCw className="size-4" />
              새로고침
            </Button>
          </div>
        </section>

        {errorMessage && (
          <Alert variant="destructive" className="rounded-2xl">
            {errorMessage}
          </Alert>
        )}
        {successMessage && (
          <Alert className="rounded-2xl">{successMessage}</Alert>
        )}

        <div className="grid gap-3 md:grid-cols-3">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              type="button"
              onClick={() => setActiveTab(tab.key)}
              className={`rounded-[1.5rem] border p-4 text-left transition ${
                activeTab === tab.key
                  ? "border-slate-950 bg-slate-950 text-white shadow-sm"
                  : "border-slate-200 bg-white text-slate-700 hover:border-slate-400"
              }`}
            >
              <p className="text-base font-black">{tab.label}</p>
              <p
                className={`mt-1 text-xs font-semibold ${activeTab === tab.key ? "text-slate-300" : "text-slate-500"}`}
              >
                {tab.description}
              </p>
            </button>
          ))}
        </div>

        {activeTab === "model" && (
          <Card className="rounded-[2rem] border-slate-200 shadow-sm">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-2xl font-black">
                <BrainCircuit className="size-6" />
                추천 모델 설정
              </CardTitle>
              <CardDescription>
                Auto Hybrid는 선택된 개인화 모델을 사용자별로 사용할 수 있을
                때만 적용하고, 불가능하면 자동 fallback합니다.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form className="space-y-6" onSubmit={handleSubmit}>
                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                  <SelectCard
                    id="embeddingModel"
                    label="임베딩 모델"
                    value={embeddingModel}
                    options={embeddingOptions}
                    onChange={(value) =>
                      setEmbeddingModel(value as EmbeddingModel)
                    }
                    description="Qdrant 검색에 사용할 embedding provider입니다."
                  />
                  <SelectCard
                    id="recommendationStrategy"
                    label="추천 전략"
                    value={recommendationStrategy}
                    options={strategyOptions}
                    onChange={(value) =>
                      setRecommendationStrategy(value as RecommendationStrategy)
                    }
                    description={strategyDescriptions[recommendationStrategy]}
                  />
                  <SelectCard
                    id="personalizationModel"
                    label="개인화 모델"
                    value={personalizationModel}
                    options={personalizationOptions}
                    onChange={(value) =>
                      setPersonalizationModel(value as PersonalizationModel)
                    }
                    description={
                      personalizationDescriptions[personalizationModel]
                    }
                  />
                  <SelectCard
                    id="rerankerProvider"
                    label="Reranker"
                    value={rerankerProvider}
                    options={rerankerOptions}
                    onChange={(value) =>
                      setRerankerProvider(value as RerankerProvider)
                    }
                    description={rerankerDescriptions[rerankerProvider]}
                  />
                </div>

                <div className="rounded-2xl border border-amber-200 bg-amber-50/70 p-4 text-sm leading-6 text-amber-900">
                  <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                    <div>
                      <p className="font-bold text-amber-950">BM25 Hybrid 검색</p>
                      <p className="mt-1">
                        기본값은 OFF입니다. ON으로 저장하면 다음 추천 API부터
                        books_hybrid / books_kure_hybrid collection을 사용하고, 실패 시 기존 dense lookup으로 fallback합니다.
                      </p>
                    </div>
                    <Label className="flex cursor-pointer items-center gap-3 rounded-2xl bg-white px-4 py-3 shadow-sm">
                      <input
                        type="checkbox"
                        className="size-5 accent-slate-950"
                        checked={bm25Enabled}
                        onChange={(event) => setBm25Enabled(event.target.checked)}
                        disabled={!isAdmin || saving}
                      />
                      <span className="font-black text-slate-950">
                        {bm25Enabled ? "BM25 ON" : "BM25 OFF"}
                      </span>
                    </Label>
                  </div>
                </div>

                <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm leading-6 text-slate-600">
                  <p>
                    <span className="font-bold text-slate-950">
                      현재 저장값:
                    </span>{" "}
                    {setting?.embeddingModel} /{" "}
                    {setting?.recommendationStrategy} /{" "}
                    {setting?.personalizationModel} /{" "}
                    {setting?.rerankerProvider} /{" "}
                    BM25 {setting?.bm25Enabled ? "ON" : "OFF"}
                  </p>
                  <p>
                    <span className="font-bold text-slate-950">
                      마지막 수정:
                    </span>{" "}
                    {formatUpdatedAt(setting?.updatedAt)}
                  </p>
                </div>

                <div className="flex justify-end">
                  <Button
                    type="submit"
                    className="rounded-2xl"
                    disabled={!isAdmin || saving}
                  >
                    {saving ? (
                      <RefreshCw className="size-4 animate-spin" />
                    ) : (
                      <Save className="size-4" />
                    )}
                    {saving ? "저장 중..." : "설정 저장"}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        )}

        {activeTab === "training" && (
          <Card className="rounded-[2rem] border-slate-200 shadow-sm">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-2xl font-black">
                <Activity className="size-6" />
                학습 관리
              </CardTitle>
              <CardDescription>
                현재는 LightFM 수동 학습을 제공하고, 이후 SASRec/BERT4Rec 학습
                버튼을 같은 탭에 확장합니다.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="grid gap-4 md:grid-cols-4">
                <MetricCard
                  label="Artifact"
                  value={lightFmSummary?.available ? "사용 가능" : "없음"}
                />
                <MetricCard
                  label="Users"
                  value={formatNumber(lightFmSummary?.userCount)}
                />
                <MetricCard
                  label="Items"
                  value={formatNumber(lightFmSummary?.itemCount)}
                />
                <MetricCard
                  label="Events"
                  value={formatNumber(lightFmSummary?.positiveEventCount)}
                />
              </div>
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm leading-6 text-slate-600">
                <p>
                  <span className="font-bold text-slate-950">Version:</span>{" "}
                  {lightFmSummary?.artifactVersion ?? "-"}
                </p>
                <p>
                  <span className="font-bold text-slate-950">
                    Artifact Dir:
                  </span>{" "}
                  {lightFmSummary?.artifactDir ?? "-"}
                </p>
                <p>
                  <span className="font-bold text-slate-950">Trained At:</span>{" "}
                  {formatJobTime(lightFmSummary?.trainedAt)}
                </p>
                {lightFmSummary?.errorMessage && (
                  <p className="text-red-600">
                    <span className="font-bold">오류:</span>{" "}
                    {lightFmSummary.errorMessage}
                  </p>
                )}
              </div>
              <div className="flex flex-wrap gap-3">
                <Button
                  type="button"
                  variant="outline"
                  className="rounded-2xl"
                  onClick={() => void loadLightFmSummary()}
                  disabled={lightFmLoading}
                >
                  {lightFmLoading ? (
                    <RefreshCw className="size-4 animate-spin" />
                  ) : (
                    <ServerCog className="size-4" />
                  )}
                  Artifact 새로고침
                </Button>
                <Button
                  type="button"
                  className="rounded-2xl"
                  onClick={() => void handleStartLightFmTrainingJob()}
                  disabled={!isAdmin || lightFmBatchRunning}
                >
                  {lightFmBatchRunning ? (
                    <RefreshCw className="size-4 animate-spin" />
                  ) : (
                    <PlayCircle className="size-4" />
                  )}
                  {lightFmBatchRunning
                    ? "학습 중..."
                    : "LightFM 수동 학습 실행"}
                </Button>
              </div>
              {lightFmJob && (
                <div className="rounded-2xl border border-slate-200 bg-white p-4 text-sm leading-6 text-slate-600">
                  <p>
                    <span className="font-bold text-slate-950">Job ID:</span>{" "}
                    {lightFmJob.jobId}
                  </p>
                  <p>
                    <span className="font-bold text-slate-950">상태:</span>{" "}
                    {lightFmStatusLabels[lightFmJob.status]}
                  </p>
                  <p>
                    <span className="font-bold text-slate-950">Artifact:</span>{" "}
                    {lightFmJob.artifactVersion ?? "-"}
                  </p>
                  <p>
                    <span className="font-bold text-slate-950">시작/종료:</span>{" "}
                    {formatJobTime(lightFmJob.startedAt)} /{" "}
                    {formatJobTime(lightFmJob.finishedAt)}
                  </p>
                  {lightFmJob.errorMessage && (
                    <p className="text-red-600">
                      <span className="font-bold">오류:</span>{" "}
                      {lightFmJob.errorMessage}
                    </p>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {activeTab === "labels" && (
          <Card className="rounded-[2rem] border-slate-200 shadow-sm">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-2xl font-black">
                <Tags className="size-6" />
                라벨 관리
              </CardTitle>
              <CardDescription>
                도서 audience label 생성 batch를 실행하고 처리 상태를
                확인합니다.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="grid gap-4 md:grid-cols-5">
                <MetricCard
                  label="전체 도서"
                  value={formatNumber(audienceSummary?.totalBookCount)}
                />
                <MetricCard
                  label="기본 대상"
                  value={formatNumber(audienceSummary?.defaultTargetCount)}
                />
                <MetricCard
                  label="READY"
                  value={formatNumber(audienceSummary?.readyCount)}
                />
                <MetricCard
                  label="FAILED"
                  value={formatNumber(audienceSummary?.failedCount)}
                />
                <MetricCard
                  label="예상 실행"
                  value={estimatedRunCount.toLocaleString("ko-KR")}
                />
              </div>

              {audienceSummary?.message && (
                <Alert
                  variant={
                    audienceSummary.schemaReady ? "default" : "destructive"
                  }
                  className="rounded-2xl"
                >
                  {audienceSummary.message}
                </Alert>
              )}

              <div className="grid gap-4 rounded-2xl border border-slate-200 bg-slate-50 p-4 md:grid-cols-[180px_1fr] md:items-end">
                <div className="space-y-2">
                  <Label htmlFor="audienceLimit">Limit / Batch size</Label>
                  <Input
                    id="audienceLimit"
                    type="number"
                    min={1}
                    max={500}
                    value={audienceLimit}
                    onChange={(event) =>
                      setAudienceLimit(Number(event.target.value || 1))
                    }
                    disabled={!isAdmin || audienceBatchRunning}
                    className="rounded-2xl"
                  />
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <Label className="flex cursor-pointer items-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold">
                    <input
                      type="checkbox"
                      checked={audienceForce}
                      onChange={(event) =>
                        setAudienceForce(event.target.checked)
                      }
                      disabled={!isAdmin || audienceBatchRunning}
                    />
                    READY/SKIPPED도 재생성
                  </Label>
                  <Button
                    type="button"
                    variant="outline"
                    className="rounded-2xl"
                    onClick={() => void loadAudienceSummary()}
                    disabled={audienceSummaryLoading}
                  >
                    {audienceSummaryLoading ? (
                      <RefreshCw className="size-4 animate-spin" />
                    ) : (
                      <DatabaseZap className="size-4" />
                    )}
                    요약 새로고침
                  </Button>
                  <Button
                    type="button"
                    className="rounded-2xl"
                    onClick={() => void handleStartAudienceLabelJob()}
                    disabled={!isAdmin || audienceBatchRunning}
                  >
                    {audienceBatchRunning ? (
                      <RefreshCw className="size-4 animate-spin" />
                    ) : (
                      <PlayCircle className="size-4" />
                    )}
                    {audienceBatchRunning ? "처리 중..." : "라벨 생성 실행"}
                  </Button>
                </div>
              </div>

              {audienceJob && (
                <div className="rounded-2xl border border-slate-200 bg-white p-4 text-sm leading-6 text-slate-600">
                  <p>
                    <span className="font-bold text-slate-950">Job ID:</span>{" "}
                    {audienceJob.jobId}
                  </p>
                  <p>
                    <span className="font-bold text-slate-950">상태:</span>{" "}
                    {audienceStatusLabels[audienceJob.status]}
                  </p>
                  <p>
                    <span className="font-bold text-slate-950">처리:</span>{" "}
                    {audienceJob.processedCount} /{" "}
                    {audienceJob.totalTargetCount}
                  </p>
                  <p>
                    <span className="font-bold text-slate-950">
                      성공/실패/건너뜀:
                    </span>{" "}
                    {audienceJob.successCount} / {audienceJob.failedCount} /{" "}
                    {audienceJob.skippedCount}
                  </p>
                  <p>
                    <span className="font-bold text-slate-950">
                      마지막 종료:
                    </span>{" "}
                    {formatJobTime(audienceJob.finishedAt)}
                  </p>
                  {audienceJob.message && (
                    <p>
                      <span className="font-bold text-slate-950">메시지:</span>{" "}
                      {audienceJob.message}
                    </p>
                  )}
                  {audienceJob.errorMessage && (
                    <p className="text-red-600">
                      <span className="font-bold">오류:</span>{" "}
                      {audienceJob.errorMessage}
                    </p>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </AdminLayout>
  );
};

const SelectCard = ({
  id,
  label,
  value,
  options,
  onChange,
  description,
}: {
  id: string;
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
  description: string;
}) => (
  <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
    <div className="flex items-center justify-between gap-3">
      <Label htmlFor={id} className="text-sm font-black text-slate-900">
        {label}
      </Label>
      <Badge variant="secondary" className="rounded-full">
        {modelLabels[value] ?? value}
      </Badge>
    </div>
    <select
      id={id}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="mt-3 w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-800 outline-none focus:border-slate-950"
    >
      {options.map((option) => (
        <option key={option} value={option}>
          {modelLabels[option] ?? option}
        </option>
      ))}
    </select>
    <p className="mt-3 min-h-12 text-xs font-semibold leading-5 text-slate-500">
      {description}
    </p>
  </div>
);

const MetricCard = ({ label, value }: { label: string; value: string }) => (
  <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
    <p className="text-xs font-semibold text-slate-500">{label}</p>
    <p className="mt-2 text-xl font-black text-slate-950">{value}</p>
  </div>
);

export default AdminRecommendationModelPage;
