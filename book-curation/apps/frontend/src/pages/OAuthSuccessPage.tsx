import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Alert } from "@/components/ui/alert";
import { Card, CardContent } from "@/components/ui/card";
import { getMe } from "../api/authApi";
import { getPostAuthRedirectPath } from "../utils/authRedirect";
import { saveUser } from "../utils/storage";

const getErrorMessage = (error: unknown) => {
  if (error instanceof Error && error.message) return error.message;
  return "소셜 로그인 처리 중 오류가 발생했습니다.";
};

const OAuthSuccessPage = () => {
  const navigate = useNavigate();
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    const run = async () => {
      try {
        const me = await getMe();
        saveUser(me);
        navigate(getPostAuthRedirectPath(me), { replace: true });
      } catch (error) {
        setErrorMessage(getErrorMessage(error));
      }
    };

    void run();
  }, [navigate]);

  return (
    <main className="mx-auto flex min-h-[calc(100vh-4rem)] w-full max-w-md items-center px-4 py-10">
      <Card className="w-full shadow-xl shadow-primary/5">
        <CardContent className="p-6 text-center">
          {!errorMessage ? (
            <div className="space-y-4">
              <div className="mx-auto size-10 animate-spin rounded-full border-2 border-primary border-t-transparent" />
              <div>
                <h1 className="text-xl font-semibold">소셜 로그인 처리 중...</h1>
                <p className="mt-2 text-sm text-muted-foreground">잠시만 기다려주세요.</p>
              </div>
            </div>
          ) : (
            <Alert variant="destructive">{errorMessage}</Alert>
          )}
        </CardContent>
      </Card>
    </main>
  );
};

export default OAuthSuccessPage;
