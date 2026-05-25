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
import {
  confirmDormantRelease,
  sendDormantReleaseCode,
} from "../api/authApi";

const getErrorMessage = (error: unknown) => {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return "휴면 해제 처리 중 오류가 발생했습니다.";
};

const DormantReleasePage = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const queryEmail = useMemo(() => {
    const searchParams = new URLSearchParams(location.search);
    return searchParams.get("email") ?? "";
  }, [location.search]);

  const initialMessage =
    typeof location.state === "object" &&
    location.state !== null &&
    "message" in location.state &&
    typeof location.state.message === "string"
      ? location.state.message
      : "휴면회원입니다. 이메일 인증 후 휴면을 해제해 주세요.";

  const [email, setEmail] = useState(queryEmail);
  const [code, setCode] = useState("");
  const [sendMessage, setSendMessage] = useState(initialMessage);
  const [submitMessage, setSubmitMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [sendingCode, setSendingCode] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [codeSent, setCodeSent] = useState(false);

  const handleSendCode = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setErrorMessage("");
    setSubmitMessage("");
    setSendingCode(true);

    try {
      const response = await sendDormantReleaseCode({ email: email.trim() });
      setSendMessage(response.message);
      setCodeSent(true);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setSendingCode(false);
    }
  };

  const handleConfirm = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setErrorMessage("");
    setSubmitMessage("");
    setSubmitting(true);

    try {
      const response = await confirmDormantRelease({
        email: email.trim(),
        code: code.trim(),
      });
      setSubmitMessage(response.message);
      setTimeout(() => {
        navigate("/login", {
          replace: true,
          state: { message: response.message },
        });
      }, 1200);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="mx-auto flex min-h-[calc(100vh-4rem)] w-full max-w-md items-center px-4 py-10">
      <Card className="w-full shadow-xl shadow-primary/5">
        <CardHeader className="text-center">
          <CardDescription>이메일 인증으로 휴면회원 해제</CardDescription>
          <CardTitle>휴면 해제</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          {sendMessage && <Alert variant="success">{sendMessage}</Alert>}
          {submitMessage && <Alert variant="success">{submitMessage}</Alert>}
          {errorMessage && <Alert variant="destructive">{errorMessage}</Alert>}

          <form onSubmit={handleSendCode} className="space-y-4 rounded-lg border p-4">
            <div className="space-y-2">
              <Label htmlFor="dormant-email">가입한 이메일</Label>
              <Input
                id="dormant-email"
                type="email"
                placeholder="가입한 이메일 입력"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                required
              />
            </div>
            <Button type="submit" className="w-full" disabled={sendingCode}>
              {sendingCode ? "인증번호 전송 중..." : codeSent ? "인증번호 다시 받기" : "인증번호 받기"}
            </Button>
          </form>

          <form onSubmit={handleConfirm} className="space-y-4 rounded-lg border p-4">
            <div className="space-y-2">
              <Label htmlFor="dormant-code">인증번호</Label>
              <Input
                id="dormant-code"
                type="text"
                inputMode="numeric"
                maxLength={6}
                placeholder="이메일로 받은 6자리 인증번호"
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                required
              />
            </div>

            <Button type="submit" className="w-full" disabled={submitting || !codeSent}>
              {submitting ? "휴면 해제 중..." : "휴면 해제하기"}
            </Button>
          </form>

          <p className="text-center text-sm text-muted-foreground">
            <Link to="/login" className="font-medium text-primary underline-offset-4 hover:underline">
              로그인 화면으로 돌아가기
            </Link>
          </p>
        </CardContent>
      </Card>
    </main>
  );
};

export default DormantReleasePage;
