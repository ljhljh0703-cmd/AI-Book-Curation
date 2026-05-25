import {
  FileSpreadsheet,
  History,
  PlayCircle,
  RefreshCw,
  Save,
  TableProperties,
} from "lucide-react";
import { type ComponentProps, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Alert } from "@/components/ui/alert";
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
  getQueryPayloadRuleEvaluationJob,
  getQueryPayloadRuleEvaluationJobs,
  getQueryPayloadRuleLabels,
  getQueryPayloadRuleSummary,
  runQueryPayloadRuleEvaluation,
  saveQueryPayloadRuleLabels,
} from "../../api/adminRecommendationModelApi";
import type {
  EmbeddingModel,
  QueryEvaluationCommandResponse,
  QueryEvaluationLabelUpdate,
  QueryEvaluationRowsResponse,
} from "../../types/adminRecommendationModel";

type VariantOption = {
  value: string;
  label: string;
  description: string;
};

const QUERY_VARIANT_OPTIONS: VariantOption[] = [
  {
    value: "original",
    label: "원문 질의",
    description:
      "사용자가 입력한 문장을 그대로 후보군 검색에 사용합니다. baseline 비교용입니다.",
  },
  {
    value: "llm_search_query",
    label: "LLM search query",
    description:
      "현재 서비스가 LLM intent/parser에서 만든 검색용 query를 사용합니다.",
  },
  {
    value: "retrieval_query",
    label: "Retrieval query",
    description:
      "후보군 검색 전용으로 정리된 retrieval_query를 우선 사용합니다.",
  },
  {
    value: "retrieval_plus_genre",
    label: "Retrieval + 장르",
    description:
      "retrieval_query에 장르 정보를 추가했을 때 후보군 품질이 좋아지는지 봅니다.",
  },
  {
    value: "retrieval_plus_purpose",
    label: "Retrieval + 독서 목적",
    description: "독서 목적을 query text에 담았을 때 유의미한지 검증합니다.",
  },
  {
    value: "retrieval_plus_context",
    label: "Retrieval + 소비 맥락",
    description:
      "운전/출퇴근/자기 전 같은 context를 query에 넣었을 때 오염이 생기는지 봅니다.",
  },
  {
    value: "retrieval_plus_profile",
    label: "Retrieval + 프로필 요약",
    description:
      "온보딩/선호 정보 요약을 query에 섞었을 때 개인화 후보가 좋아지는지 봅니다.",
  },
];

const RETRIEVAL_VARIANT_OPTIONS: VariantOption[] = [
  {
    value: "dense",
    label: "Dense",
    description: "기존 books/books_kure collection의 dense vector search만 수행합니다.",
  },
  {
    value: "dense_bm25_rrf",
    label: "Dense + BM25 RRF",
    description:
      "hybrid collection의 dense/bm25_text 검색 결과를 ai-server 내부 RRF로 병합합니다.",
  },
  {
    value: "lookup_dense_bm25_rrf",
    label: "Lookup + Dense + BM25 RRF",
    description:
      "명확 조회 후보와 hybrid dense/BM25 후보를 함께 RRF로 비교합니다.",
  },
];

const RULE_VARIANT_OPTIONS: VariantOption[] = [
  {
    value: "current",
    label: "현재 룰",
    description:
      "운영 소스에 정의된 현재 rule-based weight를 그대로 적용합니다. 최초 평가는 이 값만 권장합니다.",
  },
  {
    value: "rule_off",
    label: "룰 OFF",
    description: "룰 가중치를 끄고 retrieval 후보 자체의 순서를 봅니다.",
  },
  {
    value: "no_genre",
    label: "장르 룰 제외",
    description: "선호 장르 가중치가 순위에 미치는 영향을 제거해서 비교합니다.",
  },
  {
    value: "no_purpose",
    label: "독서 목적 룰 제외",
    description: "독서 목적 기반 가중치의 효과를 비교합니다.",
  },
  {
    value: "no_review",
    label: "리뷰/평점 룰 제외",
    description: "리뷰 감성/평점 기반 가중치 효과를 제거합니다.",
  },
  {
    value: "no_bookshelf",
    label: "서재 행동 룰 제외",
    description: "읽음/읽는중/찜 등 사용자 행동 기반 가중치 효과를 제거합니다.",
  },
  {
    value: "no_negative",
    label: "부정 패널티 제외",
    description: "낮은 평점/싫어요/제외 성향 패널티가 필요한지 봅니다.",
  },
  {
    value: "no_audience",
    label: "독자층 룰 제외",
    description: "성인/아동 등 audience 가중치와 패널티 효과를 비교합니다.",
  },
  {
    value: "half_personalization",
    label: "개인화 0.5배",
    description: "개인화 가중치를 약하게 했을 때 품질 변화를 봅니다.",
  },
  {
    value: "strong_personalization",
    label: "개인화 1.5배",
    description: "개인화 가중치를 강하게 했을 때 품질 변화를 봅니다.",
  },
];

const DEFAULT_QUERY_VARIANTS = "original";
const DEFAULT_RETRIEVAL_VARIANTS = "dense,dense_bm25_rrf,lookup_dense_bm25_rrf";
const DEFAULT_RULE_VARIANTS = "current";
const JOB_FETCH_LIMIT = 200;
const JOB_PAGE_SIZE = 10;

const DEFAULT_CASE_HINT = [
  "운전하면서 듣기 좋은 책 추천해줘",
  "재밌는 책 한 권만 추천해줘",
  '{"id":"Q003","category":"audience","query":"초등학생 아이가 읽기 좋은 책 추천해줘"}',
].join("\n");

const visibleLabelColumns = [
  "query_text",
  "title",
  "preview",
  "retrieval_variant",
  "rule_variant",
  "rank",
  "score",
] as const;

const labelColumnTitles: Record<(typeof visibleLabelColumns)[number], string> =
  {
    query_text: "질의",
    title: "제목",
    preview: "설명",
    retrieval_variant: "검색 방식",
    rule_variant: "룰",
    rank: "순위",
    score: "검색 점수",
  };

const detailColumns = [
  "query_id",
  "category",
  "query",
  "query_variant",
  "query_text",
  "retrieval_variant",
  "rule_variant",
  "rank",
  "isbn",
  "title",
  "author",
  "match_type",
  "retrieval_sources",
  "score",
  "rerank_score",
  "semantic_score",
  "genre_score",
  "purpose_score",
  "source_format",
  "is_audio_book",
  "preview",
] as const;

const splitCsv = (value: string) =>
  value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
const asText = (value: unknown) =>
  value === null || value === undefined ? "" : String(value);
const shortText = (value: unknown, max = 180) => {
  const text = asText(value);
  return text.length > max ? `${text.slice(0, max)}...` : text;
};
const escapeCsvValue = (value: unknown) => {
  const text = asText(value);
  if (/[",\n\r]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
};
const downloadRowsAsCsv = (
  fileName: string,
  columns: string[],
  rows: Array<Record<string, unknown>>,
) => {
  const header = columns.map(escapeCsvValue).join(",");
  const body = rows
    .map((row) => columns.map((column) => escapeCsvValue(row[column])).join(","))
    .join("\n");
  // 수정 포인트: 관리자 화면에서 보이는 결과를 즉시 파일로 검토할 수 있도록 브라우저에서 CSV를 생성합니다.
  const blob = new Blob([`\uFEFF${header}${body ? `\n${body}` : ""}`], {
    type: "text/csv;charset=utf-8",
  });
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.URL.revokeObjectURL(url);
};

const isTerminalEvaluationStatus = (status: string) =>
  ["SUCCEEDED", "FAILED", "CANCELED"].includes(status.toUpperCase());
const sleep = (milliseconds: number) =>
  new Promise((resolve) => window.setTimeout(resolve, milliseconds));

const AdminQueryEvaluationPanel = ({ isAdmin }: { isAdmin: boolean }) => {
  const [embeddingModel, setEmbeddingModel] = useState<EmbeddingModel>("KURE");
  const [topK, setTopK] = useState(1);
  const [maxCorpusDocs, setMaxCorpusDocs] = useState(100);
  const [casesJsonl, setCasesJsonl] = useState("");
  const [queryVariants, setQueryVariants] = useState(DEFAULT_QUERY_VARIANTS);
  const [retrievalVariants, setRetrievalVariants] = useState(
    DEFAULT_RETRIEVAL_VARIANTS,
  );
  const [ruleVariants, setRuleVariants] = useState(DEFAULT_RULE_VARIANTS);
  const [labelLimit, setLabelLimit] = useState(200);

  const [running, setRunning] = useState(false);
  const [loadingLabels, setLoadingLabels] = useState(false);
  const [savingLabels, setSavingLabels] = useState(false);
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [loadingJobs, setLoadingJobs] = useState(false);
  const [jobs, setJobs] = useState<QueryEvaluationCommandResponse[]>([]);
  const [jobPage, setJobPage] = useState(0);
  const [selectedJobOutDir, setSelectedJobOutDir] = useState("");
  const [commandResult, setCommandResult] =
    useState<QueryEvaluationCommandResponse | null>(null);
  const [labels, setLabels] = useState<QueryEvaluationRowsResponse | null>(
    null,
  );
  const [labeledSummary, setLabeledSummary] =
    useState<QueryEvaluationRowsResponse | null>(null);
  const [dimensionSummary, setDimensionSummary] =
    useState<QueryEvaluationRowsResponse | null>(null);
  const [editedScores, setEditedScores] = useState<Record<string, string>>({});
  const [editedMemos, setEditedMemos] = useState<Record<string, string>>({});
  const [detailRow, setDetailRow] = useState<Record<string, unknown> | null>(
    null,
  );
  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  const queryVariantRef = useRef<HTMLDivElement | null>(null);
  const retrievalVariantRef = useRef<HTMLDivElement | null>(null);
  const ruleVariantRef = useRef<HTMLDivElement | null>(null);
  const firstScoreRef = useRef<Record<string, HTMLSelectElement | null>>({});

  const effectiveOutDir = useMemo(
    () =>
      selectedJobOutDir ||
      commandResult?.outDir ||
      labels?.outDir ||
      labeledSummary?.outDir ||
      dimensionSummary?.outDir ||
      "",
    [
      commandResult?.outDir,
      dimensionSummary?.outDir,
      labeledSummary?.outDir,
      labels?.outDir,
      selectedJobOutDir,
    ],
  );
  const normalizedTopK = useMemo(
    () => Math.max(1, Math.min(50, Number(topK) || 10)),
    [topK],
  );
  const normalizedMaxCorpusDocs = useMemo(
    () => Math.max(1, Math.min(500000, Number(maxCorpusDocs) || 50000)),
    [maxCorpusDocs],
  );
  const normalizedLabelLimit = useMemo(
    () => Math.max(10, Math.min(1000, Number(labelLimit) || 200)),
    [labelLimit],
  );
  const scoreColumns = useMemo(
    () => [
      "dimension",
      "query_variant",
      "retrieval_variant",
      "rule_variant",
      "run_count",
      `avg_rel_at_${normalizedTopK}`,
      `precision_at_${normalizedTopK}`,
      `bad_rate_at_${normalizedTopK}`,
      `strong_hit_rate_at_${normalizedTopK}`,
      "avg_latency_ms",
      "query_contamination_rate",
      "avg_audio_evidence_rate",
    ],
    [normalizedTopK],
  );
  const labeledSummaryColumns = useMemo(
    () => [
      "query_id",
      "category",
      "query_variant",
      "retrieval_variant",
      "rule_variant",
      `avg_rel_at_${normalizedTopK}`,
      `precision_at_${normalizedTopK}`,
      `bad_rate_at_${normalizedTopK}`,
      `strong_hit_at_${normalizedTopK}`,
      "labeled_count",
      "latency_ms",
      "query_contamination",
      "audio_evidence_rate",
    ],
    [normalizedTopK],
  );

  const focusAndAlert = (message: string, target?: HTMLElement | null) => {
    setErrorMessage(message);
    window.alert(message);
    if (target) {
      target.scrollIntoView({ block: "center", behavior: "smooth" });
      setTimeout(() => target.focus(), 0);
    }
  };

  const validateRunOptions = () => {
    if (splitCsv(queryVariants).length === 0) {
      focusAndAlert(
        "Query variants는 최소 1개 이상 선택해야 합니다.",
        (queryVariantRef.current?.querySelector(
          "input",
        ) as HTMLElement | null) ?? queryVariantRef.current,
      );
      return false;
    }
    if (splitCsv(retrievalVariants).length === 0) {
      focusAndAlert(
        "Retrieval variants는 최소 1개 이상 선택해야 합니다.",
        (retrievalVariantRef.current?.querySelector(
          "input",
        ) as HTMLElement | null) ?? retrievalVariantRef.current,
      );
      return false;
    }
    if (splitCsv(ruleVariants).length === 0) {
      focusAndAlert(
        "Rule variants는 최소 1개 이상 선택해야 합니다. 최초 평가는 current만 선택해도 됩니다.",
        (ruleVariantRef.current?.querySelector(
          "input",
        ) as HTMLElement | null) ?? ruleVariantRef.current,
      );
      return false;
    }
    return true;
  };

  const loadLabels = useCallback(
    async (dir?: string) => {
      setLoadingLabels(true);
      setErrorMessage("");
      try {
        const targetDir = dir || effectiveOutDir || undefined;
        const response = await getQueryPayloadRuleLabels(
          targetDir,
          0,
          normalizedLabelLimit,
        );
        setLabels(response);
        setSelectedJobOutDir(response.outDir || targetDir || "");
        setEditedScores({});
        // 수정 포인트: 라벨링 화면에서는 메모 입력을 숨기지만 기존 CSV에 있던 memo 값은 저장 시 유지합니다.
        setEditedMemos({});
        setDetailRow(null);
        setSuccessMessage(
          `Label CSV ${response.totalRows.toLocaleString("ko-KR")}개 row를 불러왔습니다.`,
        );
      } catch (error) {
        setErrorMessage(
          error instanceof Error
            ? error.message
            : "Label CSV를 불러오지 못했습니다.",
        );
      } finally {
        setLoadingLabels(false);
      }
    },
    [effectiveOutDir, normalizedLabelLimit],
  );

  const loadSummaries = useCallback(
    async (dir?: string) => {
      setLoadingSummary(true);
      setErrorMessage("");
      try {
        const targetDir = dir || effectiveOutDir || undefined;
        const [labeled, dimension] = await Promise.all([
          getQueryPayloadRuleSummary(targetDir, "labeled", 0, 200),
          getQueryPayloadRuleSummary(targetDir, "dimension", 0, 200),
        ]);
        setLabeledSummary(labeled);
        setDimensionSummary(dimension);
      } catch (error) {
        setErrorMessage(
          error instanceof Error
            ? error.message
            : "요약 CSV를 불러오지 못했습니다.",
        );
      } finally {
        setLoadingSummary(false);
      }
    },
    [effectiveOutDir],
  );

  const loadJobs = useCallback(async () => {
    setLoadingJobs(true);
    setErrorMessage("");
    try {
      const response = await getQueryPayloadRuleEvaluationJobs(JOB_FETCH_LIMIT);
      setJobs(response.jobs ?? []);
      setJobPage(0);
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : "평가 job 목록을 불러오지 못했습니다.",
      );
    } finally {
      setLoadingJobs(false);
    }
  }, []);

  const selectJob = useCallback(
    async (job: QueryEvaluationCommandResponse) => {
      const targetDir = job.outDir || "";
      setCommandResult(job);
      setSelectedJobOutDir(targetDir);
      setSuccessMessage(
        job.jobId
          ? `${job.jobId} 평가 job을 선택했습니다.`
          : "평가 job을 선택했습니다.",
      );
      if (targetDir) {
        await loadLabels(targetDir);
        await loadSummaries(targetDir);
      }
    },
    [loadLabels, loadSummaries],
  );

  useEffect(() => {
    if (isAdmin) {
      void loadJobs();
    }
  }, [isAdmin, loadJobs]);

  const waitForEvaluationJob = useCallback(async (jobId: string) => {
    for (let attempt = 0; attempt < 300; attempt += 1) {
      await sleep(3000);
      const response = await getQueryPayloadRuleEvaluationJob(jobId);
      setCommandResult(response);
      if (isTerminalEvaluationStatus(response.status)) {
        return response;
      }
    }
    throw new Error(
      "Local runner 평가 job이 제한 시간 내에 완료되지 않았습니다. runner 로그를 확인해주세요.",
    );
  }, []);

  const handleRun = async () => {
    if (!validateRunOptions()) {
      return;
    }
    setRunning(true);
    setErrorMessage("");
    setSuccessMessage("");
    setCommandResult(null);
    setSelectedJobOutDir("");
    setLabeledSummary(null);
    setDimensionSummary(null);
    try {
      const response = await runQueryPayloadRuleEvaluation({
        casesJsonl: casesJsonl.trim() || undefined,
        embeddingModel,
        topK: normalizedTopK,
        maxCorpusDocs: normalizedMaxCorpusDocs,
        queryVariants: splitCsv(queryVariants),
        retrievalVariants: splitCsv(retrievalVariants),
        ruleVariants: splitCsv(ruleVariants),
      });
      setCommandResult(response);
      const finalResponse =
        response.jobId && !isTerminalEvaluationStatus(response.status)
          ? await waitForEvaluationJob(response.jobId)
          : response;
      if (finalResponse.status === "SUCCEEDED") {
        const completedOutDir = finalResponse.outDir || response.outDir || "";
        setSelectedJobOutDir(completedOutDir);
        setSuccessMessage(
          casesJsonl.trim()
            ? "입력한 질의로 평가 실행이 완료되었습니다."
            : "기본 평가 파일로 평가 실행이 완료되었습니다.",
        );
        await loadLabels(completedOutDir || undefined);
        await loadJobs();
      } else {
        setErrorMessage(
          finalResponse.stderrTail ||
            finalResponse.message ||
            "평가 실행에 실패했습니다.",
        );
      }
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : "평가 실행에 실패했습니다.",
      );
    } finally {
      setRunning(false);
    }
  };

  const handleSaveLabels = async () => {
    if (labelRows.length === 0) {
      return;
    }

    const invalidRow = labelRows.find((row) => {
      const rowKey = asText(row.row_key);
      const currentScore = (
        editedScores[rowKey] ?? asText(row.human_relevance_0_2)
      ).trim();
      return !["0", "1", "2"].includes(currentScore);
    });

    if (invalidRow) {
      const rowKey = asText(invalidRow.row_key);
      focusAndAlert(
        "모든 후보에 정성평가 점수 0, 1, 2 중 하나를 입력해야 저장할 수 있습니다.",
        firstScoreRef.current[rowKey],
      );
      return;
    }

    const rows: QueryEvaluationLabelUpdate[] = labelRows.map((row) => {
      const rowKey = asText(row.row_key);
      return {
        rowKey,
        humanRelevance02:
          editedScores[rowKey] ?? asText(row.human_relevance_0_2),
        humanMemo: editedMemos[rowKey] ?? asText(row.human_memo),
      };
    });

    setSavingLabels(true);
    setErrorMessage("");
    setSuccessMessage("");
    try {
      const targetDir = effectiveOutDir || undefined;
      const response = await saveQueryPayloadRuleLabels({
        outDir: targetDir,
        rows,
        topK: normalizedTopK,
      });
      setCommandResult(response);
      if (response.status === "SUCCEEDED") {
        setSelectedJobOutDir(response.outDir || targetDir || "");
        setSuccessMessage(
          response.message || "Label 저장과 점수 요약 갱신이 완료되었습니다.",
        );
        await loadLabels(response.outDir || targetDir);
        await loadSummaries(response.outDir || targetDir);
        await loadJobs();
      } else {
        setErrorMessage(
          response.stderrTail ||
            response.message ||
            "Label 저장 후 요약 생성에 실패했습니다.",
        );
      }
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : "Label 저장에 실패했습니다.",
      );
    } finally {
      setSavingLabels(false);
    }
  };

  const labelRows = labels?.rows ?? [];
  const labeledRows = labeledSummary?.rows ?? [];
  const dimensionRows = dimensionSummary?.rows ?? [];
  const jobPageCount = Math.max(1, Math.ceil(jobs.length / JOB_PAGE_SIZE));
  const safeJobPage = Math.min(jobPage, jobPageCount - 1);
  const pagedJobs = jobs.slice(
    safeJobPage * JOB_PAGE_SIZE,
    safeJobPage * JOB_PAGE_SIZE + JOB_PAGE_SIZE,
  );
  const labelDownloadColumns = labels?.columns?.length
    ? labels.columns
    : ["query_id", "human_relevance_0_2", ...visibleLabelColumns];

  return (
    <Card className="rounded-[2rem] border-slate-200 shadow-sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-2xl font-black">
          <TableProperties className="size-6" />
          평가 관리
        </CardTitle>
        <CardDescription>
          query payload, retrieval variant, rule weight 조합을 local runner 또는
          ai-server 평가 저장소 기준으로 실행하고 생성된 label CSV를 화면에서
          채점합니다.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {errorMessage && (
          <Alert variant="destructive" className="rounded-2xl">
            {errorMessage}
          </Alert>
        )}
        {successMessage && (
          <Alert className="rounded-2xl">{successMessage}</Alert>
        )}

        <div className="grid gap-4 rounded-2xl border border-slate-200 bg-slate-50 p-4 lg:grid-cols-4">
          <div className="space-y-2">
            <Label htmlFor="evalEmbeddingModel">Embedding</Label>
            <select
              id="evalEmbeddingModel"
              value={embeddingModel}
              onChange={(event) =>
                setEmbeddingModel(event.target.value as EmbeddingModel)
              }
              className="w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold outline-none"
            >
              <option value="KURE">KURE</option>
              <option value="CLOVA">CLOVA</option>
            </select>
          </div>
          <NumberInput
            id="evalTopK"
            label="Top-K"
            min={1}
            max={50}
            value={topK}
            onChange={setTopK}
          />
          <NumberInput
            id="evalMaxCorpusDocs"
            label="BM25/Lookup corpus limit"
            min={1}
            max={500000}
            value={maxCorpusDocs}
            onChange={setMaxCorpusDocs}
          />
          <NumberInput
            id="evalLabelLimit"
            label="화면 표시 row"
            min={10}
            max={1000}
            value={labelLimit}
            onChange={setLabelLimit}
          />
        </div>

        <div className="space-y-4 rounded-2xl border border-slate-200 bg-white p-4">
          <div className="space-y-2">
            <Label htmlFor="evalCasesJsonl">평가 질의 입력</Label>
            <textarea
              id="evalCasesJsonl"
              value={casesJsonl}
              onChange={(event) => setCasesJsonl(event.target.value)}
              placeholder={DEFAULT_CASE_HINT}
              className="min-h-36 w-full rounded-2xl border border-slate-200 bg-white px-3 py-3 font-mono text-xs leading-5 outline-none focus:border-slate-400"
            />
            <p className="text-xs font-semibold leading-5 text-slate-500">
              비워두면 ai-server 기본 평가 파일을 사용합니다. 한 줄에 일반 질의
              하나를 입력하거나 JSONL 형식으로 id/category/expected/profile을
              함께 넣을 수 있습니다.
            </p>
          </div>
          <div ref={queryVariantRef}>
            <VariantChecklist
              id="evalQueryVariants"
              label="Query variants"
              description="검색 query에 어떤 데이터를 담을지 선택합니다. 기본값은 안전한 original만 실행하고, LLM query 실험은 필요할 때 추가하세요."
              options={QUERY_VARIANT_OPTIONS}
              value={queryVariants}
              defaultValue={DEFAULT_QUERY_VARIANTS}
              onChange={setQueryVariants}
            />
          </div>
          <div ref={retrievalVariantRef}>
            <VariantChecklist
              id="evalRetrievalVariants"
              label="Retrieval variants"
              description="후보군 생성 방식을 선택합니다. 기본값은 KURE embedding + Qdrant dense 최소 평가입니다."
              options={RETRIEVAL_VARIANT_OPTIONS}
              value={retrievalVariants}
              defaultValue={DEFAULT_RETRIEVAL_VARIANTS}
              onChange={setRetrievalVariants}
            />
          </div>
          <div ref={ruleVariantRef}>
            <VariantChecklist
              id="evalRuleVariants"
              label="Rule variants"
              description="룰베이스 가중치 실험군입니다. current는 현재 운영 룰 그대로이며, 나머지는 특정 룰을 끄거나 개인화 강도를 조절하는 ablation입니다. 최초 실행은 current만 권장합니다."
              options={RULE_VARIANT_OPTIONS}
              value={ruleVariants}
              defaultValue={DEFAULT_RULE_VARIANTS}
              onChange={setRuleVariants}
            />
          </div>
          <div className="flex flex-wrap gap-3">
            <Button
              type="button"
              className="rounded-2xl"
              disabled={!isAdmin || running}
              onClick={() => void handleRun()}
            >
              {running ? (
                <RefreshCw className="size-4 animate-spin" />
              ) : (
                <PlayCircle className="size-4" />
              )}
              {running ? "평가 실행 중..." : "평가 실행"}
            </Button>
            <Button
              type="button"
              variant="outline"
              className="rounded-2xl"
              disabled={loadingLabels}
              onClick={() => void loadLabels()}
            >
              {loadingLabels ? (
                <RefreshCw className="size-4 animate-spin" />
              ) : (
                <FileSpreadsheet className="size-4" />
              )}
              Label CSV 불러오기
            </Button>
            <Button
              type="button"
              variant="outline"
              className="rounded-2xl"
              disabled={loadingSummary}
              onClick={() => void loadSummaries()}
            >
              {loadingSummary ? (
                <RefreshCw className="size-4 animate-spin" />
              ) : (
                <TableProperties className="size-4" />
              )}
              점수 요약 불러오기
            </Button>
          </div>
        </div>

        <div className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="flex items-center gap-2 text-lg font-black text-slate-950">
                <History className="size-5" />
                평가 job 목록
              </h3>
              <p className="text-xs font-semibold text-slate-500">
                과거 평가 job을 선택해 라벨링과 최종 점수를 확인합니다.
              </p>
            </div>
            <Button
              type="button"
              variant="outline"
              className="rounded-2xl"
              disabled={loadingJobs}
              onClick={() => void loadJobs()}
            >
              {loadingJobs ? (
                <RefreshCw className="size-4 animate-spin" />
              ) : (
                <RefreshCw className="size-4" />
              )}
              job 목록 새로고침
            </Button>
          </div>
          <div className="overflow-hidden rounded-2xl border border-slate-200">
            <table className="min-w-full text-left text-xs">
              <thead className="bg-slate-100 text-slate-600">
                <tr>
                  <th className="px-3 py-2">선택</th>
                  <th className="px-3 py-2">jobId</th>
                  <th className="px-3 py-2">상태</th>
                  <th className="px-3 py-2">메시지</th>
                </tr>
              </thead>
              <tbody>
                {pagedJobs.map((job) => {
                  const selected = Boolean(
                    job.outDir && job.outDir === effectiveOutDir,
                  );
                  return (
                    <tr
                      key={job.jobId || job.outDir}
                      className={`border-t border-slate-100 ${selected ? "bg-slate-50" : ""}`}
                    >
                      <td className="px-3 py-2">
                        <Button
                          type="button"
                          variant={selected ? "default" : "outline"}
                          size="sm"
                          className="rounded-xl"
                          onClick={() => void selectJob(job)}
                        >
                          {selected ? "선택됨" : "선택"}
                        </Button>
                      </td>
                      <td className="px-3 py-2 font-mono font-bold text-slate-700">
                        {job.jobId || "-"}
                      </td>
                      <td className="px-3 py-2 font-bold text-slate-700">
                        {job.status}
                      </td>
                      <td className="px-3 py-2 text-slate-500">
                        {shortText(job.message, 80) || "-"}
                      </td>
                    </tr>
                  );
                })}
                {jobs.length === 0 && (
                  <tr>
                    <td
                      colSpan={4}
                      className="px-4 py-8 text-center text-sm font-semibold text-slate-500"
                    >
                      아직 조회된 평가 job이 없습니다.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 text-xs font-semibold text-slate-500">
            <span>
              {jobs.length === 0
                ? "0개 job"
                : `${safeJobPage * JOB_PAGE_SIZE + 1}-${Math.min(
                    (safeJobPage + 1) * JOB_PAGE_SIZE,
                    jobs.length,
                  )} / ${jobs.length}개 job`}
            </span>
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="rounded-xl"
                disabled={safeJobPage === 0}
                onClick={() => setJobPage((prev) => Math.max(0, prev - 1))}
              >
                이전
              </Button>
              <span className="min-w-16 text-center">
                {safeJobPage + 1} / {jobPageCount}
              </span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="rounded-xl"
                disabled={safeJobPage >= jobPageCount - 1}
                onClick={() =>
                  setJobPage((prev) => Math.min(jobPageCount - 1, prev + 1))
                }
              >
                다음
              </Button>
            </div>
          </div>
        </div>

        {commandResult && (
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-xs leading-5 text-slate-600">
            <p>
              <span className="font-black text-slate-900">상태:</span>{" "}
              {commandResult.status}
            </p>
            {commandResult.jobId && (
              <p>
                <span className="font-black text-slate-900">Runner job:</span>{" "}
                {commandResult.jobId}
              </p>
            )}
            {commandResult.message && (
              <p>
                <span className="font-black text-slate-900">메시지:</span>{" "}
                {commandResult.message}
              </p>
            )}
            {commandResult.stderrTail && (
              <pre className="mt-2 max-h-32 overflow-auto rounded-xl bg-white p-3 text-red-600">
                {commandResult.stderrTail}
              </pre>
            )}
          </div>
        )}

        {labelRows.length > 0 && <ScoringGuide />}

        <div className="space-y-3">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div className="max-w-2xl">
              <h3 className="text-lg font-black text-slate-950">후보 라벨링</h3>
              <p className="text-xs font-semibold leading-5 text-slate-500">
                후보별로 0/1/2점을 입력하고 저장하면 query/retriever/rule 조합별 점수가 갱신됩니다. 빈 점수가 있으면 저장되지 않습니다.
              </p>
            </div>
            <div className="flex shrink-0 flex-wrap items-center justify-end gap-2 lg:flex-nowrap">
              <SecondaryActionButton
                disabled={labelRows.length === 0}
                onClick={() =>
                  downloadRowsAsCsv(
                    "query-evaluation-labels.csv",
                    labelDownloadColumns,
                    labelRows,
                  )
                }
              >
                <FileSpreadsheet className="size-4" />
                CSV 다운로드
              </SecondaryActionButton>
              <Button
                type="button"
                className="h-10 rounded-2xl px-4 text-sm font-semibold"
                disabled={!isAdmin || savingLabels || labelRows.length === 0}
                onClick={() => void handleSaveLabels()}
              >
                {savingLabels ? (
                  <RefreshCw className="size-4 animate-spin" />
                ) : (
                  <Save className="size-4" />
                )}
                점수 저장 후 요약 갱신
              </Button>
            </div>
          </div>
          <div className="max-h-[560px] overflow-auto rounded-2xl border border-slate-200">
            <table className="min-w-full text-left text-xs">
              <thead className="sticky top-0 bg-slate-100 text-slate-600">
                <tr>
                  <th className="w-24 px-3 py-3">query_id</th>
                  <th className="w-20 px-2 py-3">점수</th>
                  {visibleLabelColumns.map((column) => (
                    <th
                      key={column}
                      className={`px-4 py-3 ${column === "title" ? "min-w-72" : ""} ${
                        column === "preview" ? "min-w-[28rem]" : ""
                      }`}
                    >
                      {labelColumnTitles[column]}
                    </th>
                  ))}
                  <th className="w-24 px-4 py-3">상세</th>
                </tr>
              </thead>
              <tbody>
                {labelRows.map((row) => {
                  const rowKey = asText(row.row_key);
                  const currentScore =
                    editedScores[rowKey] ?? asText(row.human_relevance_0_2);
                  return (
                    <tr
                      key={rowKey}
                      className="border-t border-slate-100 align-top hover:bg-slate-50/70"
                    >
                      <td className="px-3 py-3 font-mono font-bold text-slate-700">
                        {asText(row.query_id) || "-"}
                      </td>
                      <td className="px-2 py-3">
                        <select
                          ref={(element) => {
                            firstScoreRef.current[rowKey] = element;
                          }}
                          value={currentScore}
                          onChange={(event) =>
                            setEditedScores((prev) => ({
                              ...prev,
                              [rowKey]: event.target.value,
                            }))
                          }
                          className="w-16 rounded-xl border border-slate-200 bg-white px-2 py-1 font-bold outline-none focus:border-slate-900"
                        >
                          <option value="">선택</option>
                          <option value="0">0</option>
                          <option value="1">1</option>
                          <option value="2">2</option>
                        </select>
                      </td>
                      {visibleLabelColumns.map((column) => (
                        <LabelCell
                          key={column}
                          column={column}
                          value={row[column]}
                        />
                      ))}
                      <td className="px-4 py-3">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="rounded-xl"
                          onClick={() => setDetailRow(row)}
                        >
                          보기
                        </Button>
                      </td>
                    </tr>
                  );
                })}
                {labelRows.length === 0 && (
                  <tr>
                    <td
                      colSpan={visibleLabelColumns.length + 3}
                      className="px-4 py-8 text-center text-sm font-semibold text-slate-500"
                    >
                      평가 실행 후 label CSV를 불러오면 후보가 표시됩니다.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <ScoreTable
          title="조합별 점수 요약"
          description="query_variant × retrieval_variant × rule_variant 기준 집계입니다. 어떤 데이터를 query에 넣고 어떤 retriever를 썼을 때 점수가 좋은지 비교합니다."
          columns={scoreColumns}
          rows={dimensionRows}
          emptyMessage="점수 저장 후 요약 갱신을 누르면 조합별 점수가 표시됩니다."
          downloadFileName="query-evaluation-dimension-summary.csv"
        />
        <ScoreTable
          title="질의별 상세 요약"
          description="각 query_id와 조합별 labeled summary입니다."
          columns={labeledSummaryColumns}
          rows={labeledRows}
          emptyMessage="점수 저장 후 요약 갱신을 누르면 질의별 점수가 표시됩니다."
          downloadFileName="query-evaluation-labeled-summary.csv"
        />
      </CardContent>
      {detailRow && (
        <CandidateDetailModal
          row={detailRow}
          onClose={() => setDetailRow(null)}
        />
      )}
    </Card>
  );
};

const LabelCell = ({
  column,
  value,
}: {
  column: (typeof visibleLabelColumns)[number];
  value: unknown;
}) => {
  const text = asText(value);
  if (column === "preview") {
    return (
      <td className="px-4 py-3 text-slate-700">
        {/* 수정 포인트: 긴 preview는 목록 높이를 밀어내지 않도록 2줄까지만 노출하고 전체 내용은 상세 팝업에서 확인합니다. */}
        <p
          className="max-w-2xl whitespace-normal break-words leading-5"
          style={{
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
            overflow: "hidden",
          }}
          title={text}
        >
          {text || "-"}
        </p>
      </td>
    );
  }
  if (column === "title") {
    return (
      <td className="px-4 py-3 font-bold text-slate-900">
        <p className="max-w-sm truncate" title={text}>
          {text || "-"}
        </p>
      </td>
    );
  }
  if (column === "query_text") {
    return (
      <td className="px-4 py-3 text-slate-700">
        <p className="max-w-xs truncate" title={text}>
          {text || "-"}
        </p>
      </td>
    );
  }
  return (
    <td className="px-4 py-3 text-slate-600">
      <p className="max-w-40 truncate" title={text}>
        {shortText(text, 80) || "-"}
      </p>
    </td>
  );
};

const shouldShowDetailColumn = (
  row: Record<string, unknown>,
  column: (typeof detailColumns)[number],
) => {
  if (column === "preview") return false;
  const value = asText(row[column]);
  if (!value) return false;
  // 수정 포인트: 외부 reranker를 쓰지 않아 score와 같은 값만 반복되는 rerank_score는 상세에서도 숨깁니다.
  if (column === "rerank_score" && value === asText(row.score)) return false;
  return true;
};

const CandidateDetailModal = ({
  row,
  onClose,
}: {
  row: Record<string, unknown>;
  onClose: () => void;
}) => (
  <div
    className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 px-4 py-6"
    role="dialog"
    aria-modal="true"
  >
    <div className="max-h-[88vh] w-full max-w-4xl overflow-hidden rounded-[2rem] bg-white shadow-2xl">
      <div className="flex items-start justify-between gap-4 border-b border-slate-200 px-6 py-5">
        <div>
          <p className="text-xs font-black uppercase tracking-wide text-slate-500">
            후보 상세
          </p>
          <h3 className="mt-1 text-xl font-black text-slate-950">
            {asText(row.title) || "제목 없음"}
          </h3>
        </div>
        <Button
          type="button"
          variant="outline"
          className="rounded-2xl"
          onClick={onClose}
        >
          닫기
        </Button>
      </div>
      <div className="max-h-[calc(88vh-5.5rem)] overflow-auto px-6 py-5">
        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <p className="text-sm font-black text-slate-900">설명</p>
          <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-6 text-slate-700">
            {asText(row.preview) || "-"}
          </p>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          {detailColumns
            .filter((column) => shouldShowDetailColumn(row, column))
            .map((column) => (
              <div
                key={column}
                className="rounded-2xl border border-slate-200 p-4"
              >
                <p className="text-xs font-black text-slate-500">{column}</p>
                <p className="mt-1 break-words text-sm font-semibold text-slate-800">
                  {asText(row[column])}
                </p>
              </div>
            ))}
        </div>
      </div>
    </div>
  </div>
);

const NumberInput = ({
  id,
  label,
  min,
  max,
  value,
  onChange,
}: {
  id: string;
  label: string;
  min: number;
  max: number;
  value: number;
  onChange: (value: number) => void;
}) => (
  <div className="space-y-2">
    <Label htmlFor={id}>{label}</Label>
    <Input
      id={id}
      type="number"
      min={min}
      max={max}
      value={value}
      onChange={(event) => onChange(Number(event.target.value || min))}
      className="rounded-2xl"
    />
  </div>
);

const VariantChecklist = ({
  id,
  label,
  description,
  options,
  value,
  defaultValue,
  onChange,
}: {
  id: string;
  label: string;
  description: string;
  options: VariantOption[];
  value: string;
  defaultValue: string;
  onChange: (value: string) => void;
}) => {
  const selected = new Set(splitCsv(value));
  const optionValues = options.map((option) => option.value);
  const updateSelection = (nextSelected: Set<string>) => {
    const ordered = optionValues.filter((optionValue) =>
      nextSelected.has(optionValue),
    );
    onChange(ordered.join(","));
  };
  const toggle = (optionValue: string) => {
    const next = new Set(selected);
    if (next.has(optionValue)) {
      next.delete(optionValue);
    } else {
      next.add(optionValue);
    }
    updateSelection(next);
  };

  return (
    <div
      id={id}
      className="space-y-3 rounded-2xl border border-slate-200 bg-slate-50 p-4"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <Label className="text-sm font-black text-slate-900">{label}</Label>
          <p className="text-xs font-semibold leading-5 text-slate-500">
            {description}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="rounded-xl"
            onClick={() => onChange(optionValues.join(","))}
          >
            전체 선택
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="rounded-xl"
            onClick={() => onChange(defaultValue)}
          >
            기본값
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="rounded-xl"
            onClick={() => onChange("")}
          >
            전체 해제
          </Button>
        </div>
      </div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {options.map((option) => {
          const checked = selected.has(option.value);
          return (
            <label
              key={option.value}
              className={`flex cursor-pointer gap-3 rounded-2xl border bg-white p-3 transition ${checked ? "border-slate-900 shadow-sm" : "border-slate-200 hover:border-slate-300"}`}
            >
              <input
                type="checkbox"
                checked={checked}
                onChange={() => toggle(option.value)}
                className="mt-1 size-4 accent-slate-900"
              />
              <span className="space-y-1">
                <span className="block text-sm font-black text-slate-900">
                  {option.label}
                </span>
                <span className="block font-mono text-[11px] font-bold text-slate-500">
                  {option.value}
                </span>
                <span className="block text-xs font-semibold leading-5 text-slate-500">
                  {option.description}
                </span>
              </span>
            </label>
          );
        })}
      </div>
      <p className="text-xs font-semibold text-slate-500">
        선택값:{" "}
        {splitCsv(value).length > 0 ? splitCsv(value).join(", ") : "선택 없음"}
      </p>
    </div>
  );
};

const ScoringGuide = () => (
  <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-950">
    <h3 className="font-black">정성평가 점수 가이드</h3>
    <div className="mt-2 grid gap-3 md:grid-cols-3">
      <div className="rounded-xl bg-white/70 p-3">
        <p className="font-black">2점: 매우 적합</p>
        <p className="text-xs font-semibold">
          질의 의도, 독자층, 소비 맥락, 후보 설명이 잘 맞습니다. 오디오북/아동
          등 근거가 필요한 조건도 충족합니다.
        </p>
      </div>
      <div className="rounded-xl bg-white/70 p-3">
        <p className="font-black">1점: 일부 적합</p>
        <p className="text-xs font-semibold">
          주제는 어느 정도 맞지만 맥락, 근거, 독자층, 설명이 약합니다. 추천
          후보로 쓸 수는 있으나 상위권은 애매합니다.
        </p>
      </div>
      <div className="rounded-xl bg-white/70 p-3">
        <p className="font-black">0점: 부적합</p>
        <p className="text-xs font-semibold">
          질의와 무관하거나, 검색 query가 오염되어 엉뚱한 후보가 나온
          경우입니다. guardrail 위반 후보도 0점입니다.
        </p>
      </div>
    </div>
    <p className="mt-2 text-xs font-semibold">
      저장 시 모든 후보에 0, 1, 2 중 하나가 입력되어야 하며, 빈 값은 허용하지
      않습니다.
    </p>
  </div>
);

const SecondaryActionButton = ({
  children,
  className = "",
  ...props
}: ComponentProps<typeof Button>) => (
  <Button
    type="button"
    variant="outline"
    className={`h-10 rounded-2xl border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 shadow-sm hover:bg-slate-50 ${className}`.trim()}
    {...props}
  >
    {children}
  </Button>
);

const ScoreTable = ({
  title,
  description,
  columns,
  rows,
  emptyMessage,
  downloadFileName,
}: {
  title: string;
  description: string;
  columns: string[];
  rows: Array<Record<string, unknown>>;
  emptyMessage: string;
  downloadFileName: string;
}) => (
  <div className="space-y-3">
    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div className="max-w-3xl">
        <h3 className="text-lg font-black text-slate-950">{title}</h3>
        <p className="text-xs font-semibold leading-5 text-slate-500">{description}</p>
      </div>
      <SecondaryActionButton
        disabled={rows.length === 0}
        onClick={() => downloadRowsAsCsv(downloadFileName, columns, rows)}
      >
        <FileSpreadsheet className="size-4" />
        CSV 다운로드
      </SecondaryActionButton>
    </div>
    <div className="max-h-80 overflow-auto rounded-2xl border border-slate-200">
      <table className="min-w-full text-left text-xs">
        <thead className="sticky top-0 bg-slate-100 text-slate-600">
          <tr>
            {columns.map((column) => (
              <th key={column} className="px-3 py-2">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`${title}-${index}`} className="border-t border-slate-100">
              {columns.map((column) => (
                <td key={column} className="px-3 py-2 text-slate-700">
                  {shortText(row[column], 140)}
                </td>
              ))}
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td
                colSpan={columns.length}
                className="px-4 py-8 text-center text-sm font-semibold text-slate-500"
              >
                {emptyMessage}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  </div>
);

export default AdminQueryEvaluationPanel;
