import { useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
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
import { ApiError, login } from "../api/authApi";
import { getPostAuthRedirectPath } from "../utils/authRedirect";
import { saveUser } from "../utils/storage";
import SocialLoginButtons from "@/components/auth/SocialLoginButtons";

const getErrorMessage = (error: unknown) => {
  if (error instanceof Error && error.message) return error.message;
  return "로그인에 실패했습니다.";
};

const LoginPage = () => {
  const navigate = useNavigate();
  const location = useLocation();

  const successMessage =
    typeof location.state === "object" &&
    location.state !== null &&
    "message" in location.state &&
    typeof location.state.message === "string"
      ? location.state.message
      : "";

  const socialErrorState = useMemo(() => {
    const searchParams = new URLSearchParams(location.search);
    const socialError = searchParams.get("socialError");
    const message = searchParams.get("message");
    const errorCode = searchParams.get("errorCode");
    const email = searchParams.get("email") ?? "";

    if (socialError !== "true") {
      return null;
    }

    return {
      message: message || "소셜 로그인에 실패했습니다.",
      code: errorCode || "",
      email,
    };
  }, [location.search]);

  const [email, setEmail] = useState(socialErrorState?.email ?? "");
  const [password, setPassword] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [dormantEmail, setDormantEmail] = useState(socialErrorState?.email ?? "");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErrorMessage("");
    setLoading(true);

    try {
      const normalizedEmail = email.trim();
      const user = await login({ email: normalizedEmail, password });
      saveUser(user);

      navigate(getPostAuthRedirectPath(user), { replace: true });
    } catch (error) {
      if (error instanceof ApiError && error.code === "DORMANT_ACCOUNT") {
        const targetEmail = error.email || email.trim();
        setDormantEmail(targetEmail);
        navigate(`/dormant-release?email=${encodeURIComponent(targetEmail)}`, {
          replace: true,
          state: { message: error.message },
        });
        return;
      }

      setErrorMessage(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  const showDormantSocialGuide = socialErrorState?.code === "DORMANT_ACCOUNT";

  return (
    <main className="mx-auto flex min-h-[calc(100vh-4rem)] w-full max-w-md items-center px-4 py-10">
      <Card className="w-full shadow-xl shadow-primary/5">
        <CardHeader className="text-center">
          <CardDescription>Bookemon 계정</CardDescription>
          <CardTitle>로그인</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          {successMessage && <Alert variant="success">{successMessage}</Alert>}
          {socialErrorState && (
            <Alert variant={showDormantSocialGuide ? "success" : "destructive"}>
              <div className="space-y-2">
                <p>{socialErrorState.message}</p>
                {showDormantSocialGuide && dormantEmail && (
                  <Link
                    to={`/dormant-release?email=${encodeURIComponent(dormantEmail)}`}
                    className="inline-block text-sm font-medium text-primary underline-offset-4 hover:underline"
                  >
                    휴면 해제하러 가기
                  </Link>
                )}
              </div>
            </Alert>
          )}
          {errorMessage && <Alert variant="destructive">{errorMessage}</Alert>}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="email">이메일</Label>
              <Input
                id="email"
                type="email"
                placeholder="이메일 입력"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                required
              />
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between gap-3">
                <Label htmlFor="password">비밀번호</Label>
                <Link
                  to="/forgot-password"
                  className="text-xs font-medium text-primary underline-offset-4 hover:underline"
                >
                  비밀번호 찾기
                </Link>
              </div>
              <Input
                id="password"
                type="password"
                placeholder="비밀번호 입력"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
            </div>

            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? "로그인 중..." : "로그인"}
            </Button>
          </form>

          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <div className="h-px flex-1 bg-border" />
              <span className="text-xs text-muted-foreground">또는 소셜 로그인</span>
              <div className="h-px flex-1 bg-border" />
            </div>

            <div className="flex justify-center">
              <SocialLoginButtons disabled={loading} />
            </div>
          </div>

          <p className="text-center text-sm text-muted-foreground">
            계정이 없으신가요?{" "}
            <Link to="/signup" className="font-medium text-primary underline-offset-4 hover:underline">
              회원가입
            </Link>
          </p>
        </CardContent>
      </Card>
    </main>
  );
};

export default LoginPage;
