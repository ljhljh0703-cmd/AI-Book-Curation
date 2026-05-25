import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
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
import { confirmPasswordReset, sendPasswordResetCode } from "@/api/authApi";

const getErrorMessage = (error: unknown) => {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return "비밀번호 재설정 중 오류가 발생했습니다.";
};

const ForgotPasswordPage = () => {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [sendMessage, setSendMessage] = useState("");
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
      const response = await sendPasswordResetCode({ email: email.trim() });
      setSendMessage(response.message);
      setCodeSent(true);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setSendingCode(false);
    }
  };

  const handleResetPassword = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setErrorMessage("");
    setSubmitMessage("");

    if (newPassword !== confirmPassword) {
      setErrorMessage("새 비밀번호와 비밀번호 확인이 일치하지 않습니다.");
      return;
    }

    setSubmitting(true);

    try {
      const response = await confirmPasswordReset({
        email: email.trim(),
        code: code.trim(),
        newPassword,
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
          <CardDescription>이메일 인증으로 비밀번호 재설정</CardDescription>
          <CardTitle>비밀번호 찾기</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          {sendMessage && <Alert variant="success">{sendMessage}</Alert>}
          {submitMessage && <Alert variant="success">{submitMessage}</Alert>}
          {errorMessage && <Alert variant="destructive">{errorMessage}</Alert>}

          <form onSubmit={handleSendCode} className="space-y-4 rounded-lg border p-4">
            <div className="space-y-2">
              <Label htmlFor="reset-email">가입한 이메일</Label>
              <Input
                id="reset-email"
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

          <form onSubmit={handleResetPassword} className="space-y-4 rounded-lg border p-4">
            <div className="space-y-2">
              <Label htmlFor="verification-code">인증번호</Label>
              <Input
                id="verification-code"
                type="text"
                inputMode="numeric"
                maxLength={6}
                placeholder="이메일로 받은 6자리 인증번호"
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="new-password">새 비밀번호</Label>
              <Input
                id="new-password"
                type="password"
                placeholder="8자 이상 입력"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                autoComplete="new-password"
                minLength={8}
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="confirm-password">새 비밀번호 확인</Label>
              <Input
                id="confirm-password"
                type="password"
                placeholder="새 비밀번호 다시 입력"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                autoComplete="new-password"
                minLength={8}
                required
              />
            </div>

            <Button
              type="submit"
              className="w-full"
              disabled={submitting || !codeSent}
            >
              {submitting ? "비밀번호 변경 중..." : "비밀번호 변경"}
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

export default ForgotPasswordPage;
