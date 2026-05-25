import type { ReactElement } from "react";
import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { getMe } from "../../api/authApi";
import { clearUser, saveUser } from "../../utils/storage";

type ProtectedRouteProps = {
  children: ReactElement;
  /**
   * 수정 포인트: 관리자 페이지처럼 특정 role만 접근 가능한 라우트를 보호하기 위해 허용 role을 선택적으로 받습니다.
   * 값을 넘기지 않으면 기존처럼 로그인 여부만 확인합니다.
   */
  allowedRoles?: string[];
  /** 수정 포인트: 로그인은 되었지만 권한이 없을 때 보낼 안전한 경로입니다. */
  unauthorizedTo?: string;
};

const ProtectedRoute = ({
  children,
  allowedRoles,
  unauthorizedTo = "/",
}: ProtectedRouteProps) => {
  const [loading, setLoading] = useState(true);
  const [ok, setOk] = useState(false);
  const [redirectTo, setRedirectTo] = useState<string | null>(null);

  useEffect(() => {
    const check = async () => {
      try {
        /** 수정 포인트: localStorage가 아니라 /api/auth/me 응답 기준으로 보호 라우트 접근을 판단합니다. */
        const me = await getMe();
        saveUser(me);

        if (allowedRoles && !allowedRoles.includes(me.role)) {
          /** 수정 포인트: 일반 사용자가 /admin/*에 직접 접근해도 관리자 화면을 렌더링하지 않습니다. */
          setOk(false);
          setRedirectTo(unauthorizedTo);
          return;
        }

        setOk(true);
        setRedirectTo(null);
      } catch {
        clearUser();
        setOk(false);
        setRedirectTo("/login");
      } finally {
        setLoading(false);
      }
    };

    void check();
  }, [allowedRoles, unauthorizedTo]);

  if (loading) {
    return (
      <div className="flex min-h-[calc(100vh-4rem)] items-center justify-center text-sm text-muted-foreground">
        <div className="mr-3 size-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        Loading...
      </div>
    );
  }

  if (redirectTo) return <Navigate to={redirectTo} replace />;
  if (!ok) return <Navigate to="/login" replace />;

  return children;
};

export default ProtectedRoute;
