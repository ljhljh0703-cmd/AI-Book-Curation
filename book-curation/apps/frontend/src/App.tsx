import { useEffect } from "react";
import {
  BrowserRouter,
  HashRouter,
  Navigate,
  Route,
  Routes,
} from "react-router-dom";
import ProtectedRoute from "./components/common/ProtectedRoute";
import AppNavbar from "./components/layout/AppNavbar";
import { syncAuthenticatedUser } from "./api/authApi";
import {
  applyNativeMobileAppClass,
  isNativeMobileApp,
} from "./utils/mobileRuntime";
import AdminCharactersPage from "./pages/AdminCharactersPage";
import AdminLibraryPage from "./pages/AdminLibraryPage";
import AdminMonitoringPage from "./pages/AdminMonitoringPage";
import AdminRecommendationModelPage from "./pages/AdminRecommendationModelPage";
import AdminQueryEvaluationPage from "./pages/AdminQueryEvaluationPage";
import AdminReviewPolicyPage from "./pages/AdminReviewPolicyPage";
import AdminOnboardingOptionsPage from "./pages/AdminOnboardingOptionsPage";
import DormantReleasePage from "./pages/DormantReleasePage";
import ForgotPasswordPage from "./pages/ForgotPasswordPage";
import HomePage from "./pages/HomePage";
import LoginPage from "./pages/LoginPage";
import OAuthSuccessPage from "./pages/OAuthSuccessPage";
import ProfilePage from "./pages/ProfilePage";
import SignupPage from "./pages/SignupPage";
import OnboardingPage from "./pages/OnboardingPage";

// 수정 포인트: 관리자 라우트 권한 배열을 상수로 분리해 라우트 렌더링마다 새 배열이 생성되지 않게 합니다.
const ADMIN_ROLES = ["ADMIN"];

// 수정 포인트: Capacitor 앱에서는 새로고침/딥링크 시 파일 라우팅 문제가 생기지 않도록 HashRouter를 사용합니다.
const AppRouter = isNativeMobileApp() ? HashRouter : BrowserRouter;

function App() {
  useEffect(() => {
    // 수정 포인트: Android WebView에서 safe-area/mobile 전용 CSS를 적용하기 위한 클래스입니다.
    applyNativeMobileAppClass();

    const syncSession = () => {
      void syncAuthenticatedUser();
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        syncSession();
      }
    };

    syncSession();
    window.addEventListener("focus", syncSession);
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      window.removeEventListener("focus", syncSession);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, []);

  return (
    <AppRouter>
      <AppNavbar />
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/chat" element={<HomePage />} />
        <Route path="/chat/:sessionId" element={<HomePage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/dormant-release" element={<DormantReleasePage />} />
        <Route path="/signup" element={<SignupPage />} />
        <Route path="/oauth/success" element={<OAuthSuccessPage />} />
        <Route
          path="/onboarding"
          element={
            <ProtectedRoute>
              <OnboardingPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/profile"
          element={
            <ProtectedRoute>
              <ProfilePage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin"
          element={
            <ProtectedRoute allowedRoles={ADMIN_ROLES}>
              <Navigate to="/admin/monitoring" replace />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/monitoring"
          element={
            <ProtectedRoute allowedRoles={ADMIN_ROLES}>
              <AdminMonitoringPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/recommendation-model"
          element={
            <ProtectedRoute allowedRoles={ADMIN_ROLES}>
              <AdminRecommendationModelPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/evaluation"
          element={
            <ProtectedRoute allowedRoles={ADMIN_ROLES}>
              <AdminQueryEvaluationPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/review-policy"
          element={
            <ProtectedRoute allowedRoles={ADMIN_ROLES}>
              <AdminReviewPolicyPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/libraries"
          element={
            <ProtectedRoute allowedRoles={ADMIN_ROLES}>
              <AdminLibraryPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/onboarding-options"
          element={
            <ProtectedRoute allowedRoles={ADMIN_ROLES}>
              <AdminOnboardingOptionsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/characters"
          element={
            <ProtectedRoute allowedRoles={ADMIN_ROLES}>
              <AdminCharactersPage />
            </ProtectedRoute>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppRouter>
  );
}

export default App;
