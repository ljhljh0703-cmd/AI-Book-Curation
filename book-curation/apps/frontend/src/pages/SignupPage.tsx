/**
 * 회원가입 화면을 담당하는 파일.
 * 자체 회원가입과 소셜 회원가입 완료 흐름을 하나의 화면에서 처리한다.
 */

import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
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
  checkSignupEmailAvailability,
  completeSocialSignup,
  getPendingSocialSignup,
  signup,
} from "../api/authApi";
import type { PendingSocialSignupResponse } from "../types/auth";
import { getPostAuthRedirectPath } from "../utils/authRedirect";
import { saveUser } from "../utils/storage";
import {
  ALLOWED_SIGNUP_EMAIL_DOMAINS,
  validateSignupEmail,
} from "../utils/emailValidation";

const getErrorMessage = (error: unknown) => {
  if (error instanceof Error && error.message) return error.message;
  return "회원가입에 실패했습니다.";
};

const splitAllowedEmail = (email?: string | null) => {
  const normalized = email?.trim().toLowerCase() ?? "";
  const [localPart = "", domainPart = ""] = normalized.split("@");
  const domain = ALLOWED_SIGNUP_EMAIL_DOMAINS.includes(
    domainPart as (typeof ALLOWED_SIGNUP_EMAIL_DOMAINS)[number]
  )
    ? domainPart
    : ALLOWED_SIGNUP_EMAIL_DOMAINS[0];

  return {
    localPart,
    domain,
    isAllowedDomain: domain === domainPart && Boolean(localPart),
  };
};

const SignupPage = () => {
  const navigate = useNavigate();
  const location = useLocation();

  const [nickname, setNickname] = useState("");
  const [emailLocalPart, setEmailLocalPart] = useState("");
  const [emailDomain, setEmailDomain] = useState<string>(ALLOWED_SIGNUP_EMAIL_DOMAINS[0]);
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const [emailChecked, setEmailChecked] = useState(false);
  const [emailAvailable, setEmailAvailable] = useState<boolean | null>(null);
  const [emailCheckMessage, setEmailCheckMessage] = useState("");
  const [emailCheckLoading, setEmailCheckLoading] = useState(false);

  const [pendingSocial, setPendingSocial] =
    useState<PendingSocialSignupResponse | null>(null);
  const [pendingLoaded, setPendingLoaded] = useState(false);

  const [agreeTerms, setAgreeTerms] = useState(false);
  const [agreePrivacy, setAgreePrivacy] = useState(false);

  const [errorMessage, setErrorMessage] = useState("");
  const [loading, setLoading] = useState(false);

  const socialPendingRequested = useMemo(() => {
    const searchParams = new URLSearchParams(location.search);
    return searchParams.get("socialPending") === "true";
  }, [location.search]);

  const email = useMemo(
    () => `${emailLocalPart.trim()}@${emailDomain}`.toLowerCase(),
    [emailLocalPart, emailDomain]
  );

  const isPasswordLongEnough = password.length >= 8;
  const isPasswordMatched =
    confirmPassword.length > 0 && password === confirmPassword;
  const emailValidationMessage = validateSignupEmail(email);
  const isEmailFormatValid = !emailValidationMessage && emailLocalPart.trim().length > 0;

  useEffect(() => {
    let active = true;

    const loadPending = async () => {
      try {
        const pending = await getPendingSocialSignup();
        if (!active) return;

        setPendingSocial(pending);

        if (pending) {
          const parsedEmail = splitAllowedEmail(pending.email);
          setEmailLocalPart(parsedEmail.localPart);
          setEmailDomain(parsedEmail.domain);
          setNickname((current) => current || pending.nickname || "");

          if (pending.email && parsedEmail.isAllowedDomain) {
            setEmailChecked(true);
            setEmailAvailable(true);
            setEmailCheckMessage("소셜 인증으로 이메일 정보가 확인되었습니다.");
          } else if (pending.email) {
            setEmailChecked(false);
            setEmailAvailable(null);
            setEmailCheckMessage(
              "소셜 계정 이메일 도메인이 가입 허용 목록에 없어 사용할 도메인을 선택해 주세요."
            );
          }
        } else if (socialPendingRequested) {
          setErrorMessage(
            "완료할 소셜 회원가입 정보가 없습니다. 다시 소셜 로그인을 진행해 주세요."
          );
        }
      } catch (error) {
        if (!active) return;
        setErrorMessage(getErrorMessage(error));
      } finally {
        if (active) setPendingLoaded(true);
      }
    };

    void loadPending();

    return () => {
      active = false;
    };
  }, [socialPendingRequested]);

  const resetEmailCheckState = () => {
    setEmailChecked(false);
    setEmailAvailable(null);
    setEmailCheckMessage("");
  };

  const handleEmailCheck = async () => {
    const validationMessage = validateSignupEmail(email);

    if (validationMessage) {
      setEmailCheckMessage(validationMessage);
      setEmailAvailable(false);
      setEmailChecked(false);
      return;
    }

    setEmailCheckLoading(true);
    setEmailCheckMessage("");
    setErrorMessage("");

    try {
      const result = await checkSignupEmailAvailability(email);
      setEmailChecked(true);
      setEmailAvailable(result.available);
      setEmailCheckMessage(result.message);
    } catch (error) {
      setEmailChecked(true);
      setEmailAvailable(false);
      setEmailCheckMessage(getErrorMessage(error));
    } finally {
      setEmailCheckLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErrorMessage("");

    if (!nickname.trim()) {
      setErrorMessage("닉네임을 입력해 주세요.");
      return;
    }

    const validationMessage = validateSignupEmail(email);
    if (validationMessage) {
      setErrorMessage(validationMessage);
      setEmailAvailable(false);
      setEmailChecked(false);
      setEmailCheckMessage(validationMessage);
      return;
    }

    if (!emailChecked || !emailAvailable) {
      setErrorMessage("이메일 중복 확인을 완료해 주세요.");
      return;
    }

    if (!agreeTerms || !agreePrivacy) {
      setErrorMessage("필수 약관에 모두 동의해야 회원가입할 수 있습니다.");
      return;
    }

    if (password !== confirmPassword) {
      setErrorMessage("비밀번호와 비밀번호 확인이 일치하지 않습니다.");
      return;
    }

    if (password.length < 8) {
      setErrorMessage("비밀번호는 8자 이상 입력해야 합니다.");
      return;
    }

    setLoading(true);

    try {
      if (pendingSocial) {
        const me = await completeSocialSignup({
          email,
          password,
          nickname: nickname.trim(),
        });

        saveUser(me);
        navigate(getPostAuthRedirectPath(me), { replace: true });
        return;
      }

      const me = await signup({
        email,
        password,
        nickname: nickname.trim(),
      });

      saveUser(me);
      navigate(getPostAuthRedirectPath(me), { replace: true });
    } catch (error) {
      const message = getErrorMessage(error);
      if (message.includes("이미 가입된 이메일")) {
        setEmailChecked(true);
        setEmailAvailable(false);
        setEmailCheckMessage(message);
      }
      setErrorMessage(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="mx-auto flex min-h-[calc(100vh-4rem)] w-full max-w-2xl items-center px-4 py-10">
      <Card className="w-full shadow-xl shadow-primary/5">
        <CardHeader className="text-center">
          <CardDescription>Bookemon 계정</CardDescription>
          <CardTitle>{pendingSocial ? "소셜 회원가입 완료" : "회원가입"}</CardTitle>
        </CardHeader>

        <CardContent className="space-y-5">
          {pendingLoaded && pendingSocial && (
            <Alert>
              <div className="flex flex-col gap-2 text-sm">
                <div className="flex items-center gap-2">
                  <span>소셜 인증이 완료되었습니다.</span>
                  <Badge variant="secondary">{pendingSocial.provider}</Badge>
                </div>
                <span>
                  비밀번호를 설정해 자체 회원가입을 완료하면 소셜 계정도 함께
                  연동됩니다.
                </span>
              </div>
            </Alert>
          )}

          {errorMessage && <Alert variant="destructive">{errorMessage}</Alert>}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="nickname">닉네임</Label>
              <Input
                id="nickname"
                type="text"
                placeholder="닉네임 입력"
                value={nickname}
                onChange={(e) => setNickname(e.target.value)}
                minLength={2}
                maxLength={30}
                autoComplete="nickname"
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="signup-email-local">이메일</Label>

              <div className="flex flex-col gap-2 sm:flex-row">
                <Input
                  id="signup-email-local"
                  type="text"
                  placeholder="아이디"
                  value={emailLocalPart}
                  onChange={(e) => {
                    setEmailLocalPart(e.target.value.replace(/@/g, ""));
                    resetEmailCheckState();
                  }}
                  autoComplete="email"
                  required
                  className="min-w-0 sm:flex-[1.8]"
                />

                <select
                  aria-label="이메일 도메인"
                  value={emailDomain}
                  onChange={(e) => {
                    setEmailDomain(e.target.value);
                    resetEmailCheckState();
                  }}
                  className="h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring sm:w-44"
                >
                  {ALLOWED_SIGNUP_EMAIL_DOMAINS.map((domain) => (
                    <option key={domain} value={domain}>
                      @{domain}
                    </option>
                  ))}
                </select>

                <Button
                  type="button"
                  variant="outline"
                  onClick={handleEmailCheck}
                  disabled={emailCheckLoading || !emailLocalPart.trim() || !isEmailFormatValid}
                  className="w-full sm:w-auto sm:shrink-0"
                >
                  {emailCheckLoading ? "확인 중..." : "중복 확인"}
                </Button>
              </div>

              <p className="text-xs text-muted-foreground">
                가입 가능한 도메인만 선택할 수 있습니다.
              </p>

              {emailLocalPart.trim() && emailValidationMessage && (
                <p className="text-sm text-red-500">{emailValidationMessage}</p>
              )}

              {emailCheckMessage && !emailValidationMessage && (
                <p
                  className={`text-sm ${
                    emailAvailable ? "text-green-600" : "text-red-500"
                  }`}
                >
                  {emailCheckMessage}
                </p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="signup-password">비밀번호</Label>
              <Input
                id="signup-password"
                type="password"
                placeholder="비밀번호 입력"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                minLength={8}
                maxLength={72}
                autoComplete="new-password"
                required
              />

              <p
                className={`text-sm ${
                  isPasswordLongEnough
                    ? "text-green-600"
                    : "text-muted-foreground"
                }`}
              >
                비밀번호는 8자 이상이어야 합니다.
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="confirm-password">비밀번호 확인</Label>
              <Input
                id="confirm-password"
                type="password"
                placeholder="비밀번호 다시 입력"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                minLength={8}
                maxLength={72}
                autoComplete="new-password"
                required
              />

              {confirmPassword && (
                <p
                  className={`text-sm ${
                    isPasswordMatched ? "text-green-600" : "text-red-500"
                  }`}
                >
                  {isPasswordMatched
                    ? "비밀번호가 일치합니다."
                    : "비밀번호가 일치하지 않습니다."}
                </p>
              )}
            </div>

            <div className="space-y-3 rounded-lg border p-4">
              <div className="flex items-start gap-2">
                <input
                  id="agree-terms"
                  type="checkbox"
                  checked={agreeTerms}
                  onChange={(e) => setAgreeTerms(e.target.checked)}
                  className="mt-1 h-4 w-4"
                />
                <Label htmlFor="agree-terms" className="text-sm leading-6">
                  [필수] 이용약관에 동의합니다.
                </Label>
              </div>

              <div className="flex items-start gap-2">
                <input
                  id="agree-privacy"
                  type="checkbox"
                  checked={agreePrivacy}
                  onChange={(e) => setAgreePrivacy(e.target.checked)}
                  className="mt-1 h-4 w-4"
                />
                <Label htmlFor="agree-privacy" className="text-sm leading-6">
                  [필수] 개인정보 처리방침에 동의합니다.
                </Label>
              </div>
            </div>

            <Button
              type="submit"
              className="w-full"
              disabled={
                loading ||
                (socialPendingRequested && !pendingLoaded) ||
                !agreeTerms ||
                !agreePrivacy ||
                !isEmailFormatValid ||
                !emailChecked ||
                !emailAvailable
              }
            >
              {loading
                ? pendingSocial
                  ? "가입 완료 처리 중..."
                  : "가입 중..."
                : pendingSocial
                  ? "회원가입 완료 및 소셜 연동"
                  : "회원가입"}
            </Button>
          </form>

          <p className="text-center text-sm text-muted-foreground">
            이미 계정이 있으신가요?{" "}
            <Link
              to="/login"
              className="font-medium text-primary underline-offset-4 hover:underline"
            >
              로그인
            </Link>
          </p>
        </CardContent>
      </Card>
    </main>
  );
};

export default SignupPage;
