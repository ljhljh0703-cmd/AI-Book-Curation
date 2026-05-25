import {
  Activity,
  BarChart3,
  CalendarDays,
  MessageSquareText,
  RefreshCw,
  Search,
  ThumbsDown,
  ThumbsUp,
  UserPlus,
  UsersRound,
  BookOpenCheck,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
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
import { cn } from "@/lib/utils";
import { getMe } from "../api/authApi";
import { getAdminMonitoring } from "../api/adminMonitoringApi";
import AdminLayout from "../components/admin/AdminLayout";
import type {
  MonitoringMetric,
  MonitoringMetricKey,
  MonitoringRangeType,
  MonitoringResponse,
} from "../types/adminMonitoring";
import type { MeResponse } from "../types/auth";
import { saveUser } from "../utils/storage";

const RANGE_OPTIONS: Array<{
  value: MonitoringRangeType;
  label: string;
  helper: string;
}> = [
  { value: "DAILY", label: "일일", helper: "오늘" },
  { value: "WEEKLY", label: "주간", helper: "최근 7일" },
  { value: "MONTHLY", label: "월간", helper: "최근 30일" },
  { value: "CUSTOM", label: "기간별", helper: "직접 선택" },
];

const METRIC_ICONS: Record<MonitoringMetricKey, typeof Activity> = {
  SIGNUPS: UserPlus,
  ACTIVE_USERS: UsersRound,
  CHAT_MESSAGES: MessageSquareText,
  CHAT_SESSIONS: BarChart3,
  LIKES: ThumbsUp,
  DISLIKES: ThumbsDown,
  READING_BUTTONS: BookOpenCheck,
};

const toLocalDateInputValue = (date: Date) => {
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  return `${year}-${month}-${day}`;
};

const getDefaultStartDate = () => {
  const date = new Date();
  date.setDate(date.getDate() - 6);
  return toLocalDateInputValue(date);
};

const getToday = () => toLocalDateInputValue(new Date());

const getErrorMessage = (error: unknown) => {
  if (error instanceof Error && error.message) return error.message;
  return "관리자 모니터링 정보를 불러오지 못했습니다.";
};

const formatCount = (value: number) => new Intl.NumberFormat("ko-KR").format(value);

const formatDateLabel = (date: string) => {
  const [, month, day] = date.split("-");
  return `${month}.${day}`;
};

const AdminMonitoringPage = () => {
  const [user, setUser] = useState<MeResponse | null>(null);
  const [rangeType, setRangeType] = useState<MonitoringRangeType>("DAILY");
  const [startDate, setStartDate] = useState(getDefaultStartDate);
  const [endDate, setEndDate] = useState(getToday);
  const [data, setData] = useState<MonitoringResponse | null>(null);
  const [activeMetricKey, setActiveMetricKey] = useState<MonitoringMetricKey>("SIGNUPS");
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");

  const selectedMetric = useMemo(
    () => data?.metrics.find((metric) => metric.key === activeMetricKey) ?? data?.metrics[0] ?? null,
    [activeMetricKey, data]
  );

  const fetchMonitoring = async (nextRangeType = rangeType) => {
    setLoading(true);
    setErrorMessage("");

    try {
      const me = await getMe();
      setUser(me);
      saveUser(me);

      if (me.role !== "ADMIN") {
        setErrorMessage("관리자 권한이 있는 계정만 접근할 수 있습니다.");
        return;
      }

      if (nextRangeType === "CUSTOM" && (!startDate || !endDate)) {
        setErrorMessage("기간별 검색은 시작일과 종료일을 모두 입력해 주세요.");
        return;
      }

      const response = await getAdminMonitoring({
        rangeType: nextRangeType,
        startDate,
        endDate,
      });

      setData(response);
      if (!response.metrics.some((metric) => metric.key === activeMetricKey)) {
        setActiveMetricKey(response.metrics[0]?.key ?? "SIGNUPS");
      }
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchMonitoring("DAILY");
    // 최초 진입 시 오늘 기준 지표만 조회합니다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleRangeChange = (nextRangeType: MonitoringRangeType) => {
    setRangeType(nextRangeType);
    if (nextRangeType !== "CUSTOM") {
      void fetchMonitoring(nextRangeType);
    }
  };

  const maxCount = Math.max(1, ...(selectedMetric?.series.map((point) => point.count) ?? [0]));
  const isAdmin = user?.role === "ADMIN";

  return (
    <AdminLayout
      title="서비스 모니터링"
      description="회원가입, 접속, 채팅, 추천 반응 지표를 사용자별 상세가 아닌 서비스 전체 통합 기준으로 확인합니다."
    >
      <Card className="rounded-[2rem] border-slate-200/80 shadow-xl shadow-slate-200/60">
        <CardHeader className="gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-1">
            <CardDescription>통합 지표</CardDescription>
            <CardTitle className="flex items-center gap-2 text-2xl">
              <Activity className="size-6 text-primary" />
              관리자 모니터링
            </CardTitle>
          </div>

          <Button
            type="button"
            variant="outline"
            className="rounded-2xl"
            onClick={() => fetchMonitoring(rangeType)}
            disabled={loading || !isAdmin}
          >
            <RefreshCw className={cn("size-4", loading && "animate-spin")} />
            새로고침
          </Button>
        </CardHeader>

        <CardContent className="space-y-6">
          {errorMessage && <Alert variant="destructive">{errorMessage}</Alert>}

          <section className="rounded-[1.75rem] border border-slate-200 bg-slate-50/70 p-4">
            <div className="grid gap-3 md:grid-cols-4">
              {RANGE_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className={cn(
                    "rounded-2xl border px-4 py-3 text-left transition-all",
                    rangeType === option.value
                      ? "border-slate-950 bg-slate-950 text-white shadow-lg shadow-slate-900/10"
                      : "border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:text-slate-950"
                  )}
                  onClick={() => handleRangeChange(option.value)}
                >
                  <span className="block text-sm font-bold">{option.label}</span>
                  <span
                    className={cn(
                      "mt-1 block text-xs",
                      rangeType === option.value ? "text-white/70" : "text-slate-400"
                    )}
                  >
                    {option.helper}
                  </span>
                </button>
              ))}
            </div>

            {rangeType === "CUSTOM" && (
              <div className="mt-4 grid gap-3 rounded-2xl bg-white p-4 md:grid-cols-[1fr_1fr_auto]">
                <label className="space-y-1 text-sm font-semibold text-slate-700">
                  시작일
                  <Input
                    type="date"
                    value={startDate}
                    onChange={(event) => setStartDate(event.target.value)}
                    className="rounded-2xl"
                  />
                </label>
                <label className="space-y-1 text-sm font-semibold text-slate-700">
                  종료일
                  <Input
                    type="date"
                    value={endDate}
                    onChange={(event) => setEndDate(event.target.value)}
                    className="rounded-2xl"
                  />
                </label>
                <Button
                  type="button"
                  className="self-end rounded-2xl"
                  onClick={() => fetchMonitoring("CUSTOM")}
                  disabled={loading || !isAdmin}
                >
                  <Search className="size-4" />
                  조회
                </Button>
              </div>
            )}
          </section>

          {loading && (
            <div className="flex flex-col items-center justify-center gap-3 rounded-[1.75rem] border bg-muted/30 py-14 text-muted-foreground">
              <div className="size-10 animate-spin rounded-full border-2 border-primary border-t-transparent" />
              <span className="text-sm">모니터링 데이터를 불러오는 중...</span>
            </div>
          )}

          {!loading && data && (
            <>
              <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                <SummaryCard label="조회 기간" value={`${data.startDate} ~ ${data.endDate}`} icon={CalendarDays} />
                <SummaryCard label="회원가입" value={formatCount(getTotal(data.metrics, "SIGNUPS"))} icon={UserPlus} />
                <SummaryCard label="접속회원" value={formatCount(getTotal(data.metrics, "ACTIVE_USERS"))} icon={UsersRound} />
                <SummaryCard label="채팅 발신" value={formatCount(getTotal(data.metrics, "CHAT_MESSAGES"))} icon={MessageSquareText} />
              </section>

              <section className="rounded-[2rem] border border-slate-200 bg-white p-4 shadow-sm">
                <div className="mb-4 flex flex-col gap-1">
                  <p className="text-sm font-semibold text-primary">지표 책갈피</p>
                  <p className="text-xs text-slate-500">
                    항목을 선택하면 아래 차트가 해당 지표로 전환됩니다.
                  </p>
                </div>

                <div className="flex gap-2 overflow-x-auto pb-2">
                  {data.metrics.map((metric) => {
                    const Icon = METRIC_ICONS[metric.key] ?? Activity;
                    const active = activeMetricKey === metric.key;

                    return (
                      <button
                        key={metric.key}
                        type="button"
                        className={cn(
                          "relative min-w-[150px] rounded-t-3xl rounded-b-xl border px-4 py-3 text-left transition-all",
                          "before:absolute before:-top-1 before:left-6 before:h-3 before:w-8 before:rounded-t-xl before:border before:border-b-0",
                          active
                            ? "border-slate-950 bg-slate-950 text-white shadow-lg shadow-slate-900/10 before:border-slate-950 before:bg-slate-950"
                            : "border-slate-200 bg-slate-50 text-slate-600 hover:border-slate-300 hover:bg-white hover:text-slate-950 before:border-slate-200 before:bg-slate-50"
                        )}
                        onClick={() => setActiveMetricKey(metric.key)}
                      >
                        <span className="flex items-center gap-2 text-xs font-semibold">
                          <Icon className="size-4" />
                          {metric.label}
                        </span>
                        <span className="mt-2 block text-2xl font-black">
                          {formatCount(metric.total)}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </section>

              {selectedMetric && (
                <section className="rounded-[2rem] border border-slate-200 bg-white p-5 shadow-xl shadow-slate-200/60">
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                      <p className="text-sm font-semibold text-primary">{selectedMetric.label}</p>
                      <h3 className="mt-1 text-2xl font-bold text-slate-950">
                        총 {formatCount(selectedMetric.total)}건
                      </h3>
                      <p className="mt-1 text-sm text-slate-500">{selectedMetric.description}</p>
                    </div>
                    <div className="rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
                      생성 시각: {new Date(data.generatedAt).toLocaleString("ko-KR")}
                    </div>
                  </div>

                  <div className="mt-6 overflow-x-auto">
                    <div
                      className="flex min-h-[280px] min-w-[720px] items-end gap-3 rounded-[1.5rem] bg-slate-50 p-5"
                      role="img"
                      aria-label={`${selectedMetric.label} 기간별 막대 차트`}
                    >
                      {selectedMetric.series.map((point) => {
                        const heightPercent = point.count === 0 ? 4 : Math.max(10, (point.count / maxCount) * 100);

                        return (
                          <div key={point.date} className="flex flex-1 flex-col items-center gap-2">
                            <div className="flex h-52 w-full items-end">
                              <div
                                className={cn(
                                  "w-full rounded-t-2xl bg-primary/85 transition-all",
                                  point.count === 0 && "bg-slate-200"
                                )}
                                style={{ height: `${heightPercent}%` }}
                                title={`${point.date}: ${formatCount(point.count)}건`}
                              />
                            </div>
                            <span className="text-xs font-bold text-slate-700">
                              {formatCount(point.count)}
                            </span>
                            <span className="whitespace-nowrap text-[11px] text-slate-400">
                              {formatDateLabel(point.date)}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </section>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </AdminLayout>
  );
};

type SummaryCardProps = {
  label: string;
  value: string;
  icon: typeof Activity;
};

const SummaryCard = ({ label, value, icon: Icon }: SummaryCardProps) => (
  <div className="rounded-[1.5rem] border border-slate-200 bg-white p-4 shadow-sm">
    <div className="flex items-center justify-between gap-3">
      <div>
        <p className="text-xs font-semibold text-slate-400">{label}</p>
        <p className="mt-1 text-lg font-black text-slate-950">{value}</p>
      </div>
      <span className="inline-flex size-11 items-center justify-center rounded-2xl bg-primary/10 text-primary">
        <Icon className="size-5" />
      </span>
    </div>
  </div>
);

const getTotal = (metrics: MonitoringMetric[], key: MonitoringMetricKey) =>
  metrics.find((metric) => metric.key === key)?.total ?? 0;

export default AdminMonitoringPage;
