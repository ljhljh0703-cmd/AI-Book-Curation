import { Clock3, RefreshCw, Save, ShieldCheck } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
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
import { getAdminReviewPolicy, updateAdminReviewPolicy } from "../api/adminReviewPolicyApi";
import { getMe } from "../api/authApi";
import AdminLayout from "../components/admin/AdminLayout";
import type { ReviewPolicy } from "../types/adminReviewPolicy";
import type { MeResponse } from "../types/auth";
import { saveUser } from "../utils/storage";

const MAX_REVIEW_WAIT_MINUTES = 60 * 24 * 30;

const getErrorMessage = (error: unknown) => {
  if (error instanceof Error && error.message) return error.message;
  return "리뷰 정책 정보를 처리하지 못했습니다.";
};

const formatUpdatedAt = (value?: string | null) => {
  if (!value) return "아직 DB 기본값으로 동작 중";
  return new Date(value).toLocaleString("ko-KR");
};

const AdminReviewPolicyPage = () => {
  const [user, setUser] = useState<MeResponse | null>(null);
  const [policy, setPolicy] = useState<ReviewPolicy | null>(null);
  const [reviewWaitMinutes, setReviewWaitMinutes] = useState("4320");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  const loadPolicy = async () => {
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

      const response = await getAdminReviewPolicy();
      setPolicy(response);
      setReviewWaitMinutes(String(response.reviewWaitMinutes));
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadPolicy();
  }, []);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setErrorMessage("");
    setSuccessMessage("");

    const minutes = Number(reviewWaitMinutes);
    if (!Number.isInteger(minutes) || minutes < 0 || minutes > MAX_REVIEW_WAIT_MINUTES) {
      setErrorMessage("리뷰 작성 대기시간은 0분 이상 43200분(30일) 이하의 정수로 입력해 주세요.");
      return;
    }

    setSaving(true);
    try {
      const response = await updateAdminReviewPolicy({ reviewWaitMinutes: minutes });
      setPolicy(response);
      setReviewWaitMinutes(String(response.reviewWaitMinutes));
      setSuccessMessage("리뷰 작성 가능 시기 설정을 저장했습니다.");
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setSaving(false);
    }
  };

  const isAdmin = user?.role === "ADMIN";

  return (
    <AdminLayout
      title="리뷰 정책 설정"
      description="읽는 중 도서 등록 후 리뷰와 평점을 작성할 수 있는 대기시간을 관리자 화면에서 조정합니다."
    >
      <Card className="rounded-[2rem] border-slate-200/80 shadow-xl shadow-slate-200/60">
        <CardHeader className="gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-1">
            <CardDescription>서비스 정책</CardDescription>
            <CardTitle className="flex items-center gap-2 text-2xl">
              <Clock3 className="size-6 text-primary" />
              리뷰 작성 가능 시기
            </CardTitle>
          </div>
          <Button
            type="button"
            variant="outline"
            className="rounded-2xl"
            onClick={() => loadPolicy()}
            disabled={loading || saving || !isAdmin}
          >
            <RefreshCw className={loading ? "size-4 animate-spin" : "size-4"} />
            새로고침
          </Button>
        </CardHeader>

        <CardContent className="space-y-5">
          {errorMessage && <Alert variant="destructive">{errorMessage}</Alert>}
          {successMessage && <Alert variant="success">{successMessage}</Alert>}

          <div className="rounded-[1.75rem] border border-slate-200 bg-slate-50/70 p-5">
            <div className="grid gap-4 md:grid-cols-3">
              <div className="rounded-2xl bg-white p-4 shadow-sm">
                <p className="text-xs font-semibold text-slate-500">현재 대기시간</p>
                <p className="mt-2 text-2xl font-black text-slate-950">
                  {policy?.reviewWaitLabel ?? "-"}
                </p>
              </div>
              <div className="rounded-2xl bg-white p-4 shadow-sm">
                <p className="text-xs font-semibold text-slate-500">분 단위 값</p>
                <p className="mt-2 text-2xl font-black text-slate-950">
                  {policy ? `${policy.reviewWaitMinutes}분` : "-"}
                </p>
              </div>
              <div className="rounded-2xl bg-white p-4 shadow-sm">
                <p className="text-xs font-semibold text-slate-500">최종 수정</p>
                <p className="mt-2 text-sm font-bold leading-6 text-slate-950">
                  {formatUpdatedAt(policy?.updatedAt)}
                </p>
              </div>
            </div>
          </div>

          <form className="rounded-[1.75rem] border border-slate-200 bg-white p-5 shadow-sm" onSubmit={handleSubmit}>
            <div className="space-y-2">
              <Label htmlFor="reviewWaitMinutes" className="text-sm font-bold text-slate-800">
                리뷰 작성 대기시간(분)
              </Label>
              <Input
                id="reviewWaitMinutes"
                type="number"
                min={0}
                max={MAX_REVIEW_WAIT_MINUTES}
                step={1}
                value={reviewWaitMinutes}
                onChange={(event) => setReviewWaitMinutes(event.target.value)}
                className="max-w-sm rounded-2xl"
                disabled={loading || saving || !isAdmin}
              />
              <p className="text-xs leading-5 text-slate-500">
                0분은 즉시 작성 가능, 60분은 1시간, 1440분은 1일, 4320분은 기존 정책인 3일입니다.
              </p>
            </div>

            <div className="mt-5 flex flex-wrap items-center gap-3">
              <Button type="submit" className="rounded-2xl" disabled={loading || saving || !isAdmin}>
                <Save className="size-4" />
                {saving ? "저장 중..." : "설정 저장"}
              </Button>
              <div className="inline-flex items-center gap-2 rounded-full bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-500">
                <ShieldCheck className="size-4 text-primary" />
                저장 즉시 백엔드 검증과 마이페이지 안내 문구에 반영됩니다.
              </div>
            </div>
          </form>
        </CardContent>
      </Card>
    </AdminLayout>
  );
};

export default AdminReviewPolicyPage;
