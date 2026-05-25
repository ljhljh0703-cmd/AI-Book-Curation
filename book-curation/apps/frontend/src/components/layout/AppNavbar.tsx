import { DatabaseZap, LogOut, Menu, UserRound, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { logout } from "../../api/authApi";
import type { MeResponse } from "../../types/auth";
import { clearUser, getUser, onAuthChanged } from "../../utils/storage";

const navLinkClass =
  "rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground";

const AppNavbar = () => {
  const navigate = useNavigate();
  const [user, setUser] = useState<MeResponse | null>(() => getUser());
  const [logoutLoading, setLogoutLoading] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const syncUser = () => {
      setUser(getUser());
    };

    /** 수정 포인트: 같은 탭에서 로그인/로그아웃해도 Navbar가 즉시 갱신되도록 커스텀 이벤트를 구독한다. */
    return onAuthChanged(syncUser);
  }, []);

  const handleLogout = async () => {
    setLogoutLoading(true);

    try {
      /** 수정 포인트: 세션 기반 인증이므로 서버 로그아웃 API를 호출해서 JSESSIONID를 무효화한다. */
      await logout();
    } finally {
      clearUser();
      setUser(null);
      setLogoutLoading(false);
      setOpen(false);
      navigate("/login", { replace: true });
    }
  };

  const closeMenu = () => setOpen(false);

  /** 수정 포인트: 관리자 계정은 user_profiles가 없으므로 홈/마이페이지 링크를 노출하지 않습니다. */
  const isAdmin = user?.role === "ADMIN";

  /** 수정 포인트: 관리자가 로고를 눌러도 일반 홈으로 가지 않고 관리자 화면으로 유지되도록 분기합니다. */
  const logoLinkTo = isAdmin ? "/admin" : "/";

  return (
    <header className="sticky top-0 z-40 border-b bg-background/90 backdrop-blur supports-[backdrop-filter]:bg-background/70">
      {/* 수정 포인트: Bootstrap Navbar를 Tailwind + shadcn/ui Button 기반 반응형 헤더로 교체했다. */}
      <div className="flex h-20 w-full items-center justify-between px-4 sm:px-6 lg:px-8">
        <Link to={logoLinkTo} onClick={closeMenu} className="flex items-center gap-2 font-semibold tracking-tight">
          {/* 수정 포인트: 텍스트/아이콘 로고 대신 public/bookemon.png 이미지를 사용합니다. */}
          <img
            src={`/bookemon.png?v=${Date.now()}`}
            alt="Bookemon"
            className="h-14 w-auto object-contain sm:h-16"
          />
        </Link>

        <nav className="hidden items-center gap-1 md:flex">
          {/* 수정 포인트: 관리자 계정은 운영 화면인 홈으로 이동할 일이 없으므로 홈 링크를 숨깁니다. */}
          {!isAdmin && (
            <Link to="/" className={navLinkClass}>
              홈
            </Link>
          )}

          {user ? (
            <>
              {isAdmin && (
                <Link to="/admin" className={cn(navLinkClass, "flex items-center gap-2")}>
                  <DatabaseZap className="size-4" />
                  관리자
                </Link>
              )}
              {!isAdmin && (
                <Link to="/profile" className={cn(navLinkClass, "flex items-center gap-2")}>
                  <UserRound className="size-4" />
                  {user.nickname || "내 정보"}
                </Link>
              )}
              <Button variant="outline" size="sm" onClick={handleLogout} disabled={logoutLoading}>
                <LogOut className="size-4" />
                {logoutLoading ? "처리 중..." : "로그아웃"}
              </Button>
            </>
          ) : (
            <>
              <Link to="/login" className={navLinkClass}>
                로그인
              </Link>
              <Button asChild size="sm">
                <Link to="/signup">회원가입</Link>
              </Button>
            </>
          )}
        </nav>

        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="md:hidden"
          onClick={() => setOpen((value) => !value)}
          aria-label="메뉴 열기"
          aria-expanded={open}
        >
          {open ? <X className="size-5" /> : <Menu className="size-5" />}
        </Button>
      </div>

      {open && (
        <div className="border-t bg-background px-4 py-3 shadow-sm md:hidden">
          <nav className="flex w-full flex-col gap-2">
            {/* 수정 포인트: 모바일 메뉴에서도 관리자 계정은 홈 링크를 숨깁니다. */}
            {!isAdmin && (
              <Link to="/" onClick={closeMenu} className={navLinkClass}>
                홈
              </Link>
            )}

            {user ? (
              <>
                {isAdmin && (
                  <Link to="/admin" onClick={closeMenu} className={navLinkClass}>
                    관리자
                  </Link>
                )}
                {!isAdmin && (
                  <Link to="/profile" onClick={closeMenu} className={navLinkClass}>
                    {user.nickname || "내 정보"}
                  </Link>
                )}
                <Button variant="outline" onClick={handleLogout} disabled={logoutLoading}>
                  {logoutLoading ? "처리 중..." : "로그아웃"}
                </Button>
              </>
            ) : (
              <>
                <Link to="/login" onClick={closeMenu} className={navLinkClass}>
                  로그인
                </Link>
                <Button asChild onClick={closeMenu}>
                  <Link to="/signup">회원가입</Link>
                </Button>
              </>
            )}
          </nav>
        </div>
      )}
    </header>
  );
};

export default AppNavbar;
