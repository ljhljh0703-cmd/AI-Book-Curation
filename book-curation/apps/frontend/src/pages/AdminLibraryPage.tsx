import type { ReactNode } from "react";
import { AlertTriangle, CheckCircle2, DatabaseZap, RefreshCw, Settings } from "lucide-react";
import { useEffect, useState } from "react";
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
import { getMe } from "../api/authApi";
import { getLibrarySyncConfig, syncLibraries } from "../api/libraryAdminApi";
import type { MeResponse } from "../types/auth";
import type { LibrarySyncConfigResponse, LibrarySyncResponse } from "../types/library";
import { saveUser } from "../utils/storage";
import AdminLayout from "../components/admin/AdminLayout";

const getErrorMessage = (error: unknown) => {
  if (error instanceof Error && error.message) return error.message;
  return "Library API 요청 중 오류가 발생했습니다.";
};

const AdminLibraryPage = () => {
  const [user, setUser] = useState<MeResponse | null>(null);
  const [config, setConfig] = useState<LibrarySyncConfigResponse | null>(null);
  const [syncResult, setSyncResult] = useState<LibrarySyncResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncLoading, setSyncLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  useEffect(() => {
    const initialize = async () => {
      setLoading(true);
      setErrorMessage("");

      try {
        /** 수정 포인트: localStorage의 role만 믿지 않고 관리자 화면 진입 시 서버 세션의 현재 권한을 다시 확인한다. */
        const me = await getMe();
        setUser(me);
        saveUser(me);

        if (me.role !== "ADMIN") {
          setErrorMessage("관리자 권한이 있는 계정만 접근할 수 있습니다.");
          return;
        }

        const syncConfig = await getLibrarySyncConfig();
        setConfig(syncConfig);
      } catch (error) {
        setErrorMessage(getErrorMessage(error));
      } finally {
        setLoading(false);
      }
    };

    void initialize();
  }, []);

  const handleSync = async () => {
    setSyncLoading(true);
    setErrorMessage("");
    setSuccessMessage("");
    setSyncResult(null);

    try {
      /** 수정 포인트: 버튼 클릭 한 번으로 도서관 정보나루 Library API(libSrch)를 호출해 DB에 upsert한다. */
      const result = await syncLibraries();
      setSyncResult(result);
      setSuccessMessage("도서관 데이터 동기화가 완료되었습니다.");
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setSyncLoading(false);
    }
  };

  const isAdmin = user?.role === "ADMIN";
  const canSync = isAdmin && config?.configured === true && !syncLoading;

  return (
    <AdminLayout
      title="도서관 데이터 관리"
      description="정보나루 Library API를 통해 주변 도서관 검색에 사용할 도서관 데이터를 동기화합니다."
    >
      <Card className="shadow-xl shadow-primary/5">
        <CardHeader>
          <CardDescription>관리자 전용</CardDescription>
          <CardTitle className="flex flex-col gap-2 text-2xl sm:flex-row sm:items-center sm:justify-between">
            <span className="flex items-center gap-2">
              <DatabaseZap className="size-6 text-primary" />
              Library API 동기화
            </span>
            {isAdmin && <Badge variant="secondary">ADMIN</Badge>}
          </CardTitle>
        </CardHeader>

        <CardContent className="space-y-6">
          {loading && (
            <div className="flex flex-col items-center justify-center gap-3 rounded-lg border bg-muted/30 py-10 text-muted-foreground">
              <div className="size-10 animate-spin rounded-full border-2 border-primary border-t-transparent" />
              <span className="text-sm">관리자 설정을 확인하는 중...</span>
            </div>
          )}

          {errorMessage && <Alert variant="destructive">{errorMessage}</Alert>}
          {successMessage && <Alert variant="success">{successMessage}</Alert>}

          {!loading && isAdmin && config && (
            <>
              <section className="grid gap-4 md:grid-cols-3">
                <InfoCard
                  icon={<Settings className="size-5" />}
                  label="토큰 설정"
                  value={config.configured ? "설정됨" : "미설정"}
                  helper="DATA4LIBRARY_AUTH_KEY"
                  good={config.configured}
                />
                <InfoCard label="API Base URL" value={config.baseUrl || "-"} helper="DATA4LIBRARY_BASE_URL" />
                <InfoCard label="페이지 크기" value={String(config.pageSize)} helper="DATA4LIBRARY_PAGE_SIZE" />
              </section>

              {!config.configured && (
                <Alert variant="destructive" className="flex gap-2">
                  <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                  <span>
                    NAS 백엔드 컨테이너 또는 실행 환경에 DATA4LIBRARY_AUTH_KEY가 설정되어야 동기화 버튼을 사용할 수 있습니다.
                  </span>
                </Alert>
              )}

              <section className="rounded-xl border bg-muted/20 p-5">
                <div className="space-y-2">
                  <h2 className="text-lg font-semibold">도서관 데이터 수동 동기화</h2>
                  <p className="text-sm leading-6 text-muted-foreground">
                    버튼을 누르면 백엔드가 Library API의 libSrch 엔드포인트를 호출하고, 응답받은 도서관 정보를 book.libraries 테이블에 저장 또는 갱신합니다.
                  </p>
                </div>

                <div className="mt-5 flex flex-col gap-2 sm:flex-row">
                  <Button type="button" onClick={handleSync} disabled={!canSync}>
                    <RefreshCw className={syncLoading ? "size-4 animate-spin" : "size-4"} />
                    {syncLoading ? "동기화 중..." : "Library API 동기화 실행"}
                  </Button>
                </div>
              </section>

              {syncResult && (
                <section className="grid gap-4 md:grid-cols-3">
                  <ResultCard label="API 전체 건수" value={syncResult.totalCount} />
                  <ResultCard label="저장/갱신 건수" value={syncResult.savedCount} />
                  <ResultCard label="처리 페이지 수" value={syncResult.pageCount} />
                </section>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </AdminLayout>
  );
};

type InfoCardProps = {
  icon?: ReactNode;
  label: string;
  value: string;
  helper: string;
  good?: boolean;
};

const InfoCard = ({ icon, label, value, helper, good }: InfoCardProps) => (
  <div className="rounded-xl border bg-card p-4">
    <div className="flex items-center justify-between gap-2">
      <p className="text-sm font-medium text-muted-foreground">{label}</p>
      {good === true ? <CheckCircle2 className="size-5 text-emerald-600" /> : icon}
    </div>
    <p className="mt-2 break-all text-lg font-semibold">{value}</p>
    <p className="mt-1 break-all text-xs text-muted-foreground">{helper}</p>
  </div>
);

type ResultCardProps = {
  label: string;
  value: number;
};

const ResultCard = ({ label, value }: ResultCardProps) => (
  <div className="rounded-xl border bg-card p-4 text-center">
    <p className="text-sm text-muted-foreground">{label}</p>
    <p className="mt-2 text-3xl font-bold tracking-tight">{value.toLocaleString()}</p>
  </div>
);

export default AdminLibraryPage;
