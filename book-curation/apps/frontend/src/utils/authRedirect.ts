import type { MeResponse } from "../types/auth";

export type AuthRedirectUser = Pick<MeResponse, "role" | "onboardingCompleted">;

/**
 * 수정 포인트: 회원가입/로그인/소셜 로그인 완료 후 이동 규칙을 한 곳에서 관리해
 * 온보딩 미완료 사용자가 화면별로 서로 다른 경로로 이동하는 일을 막습니다.
 */
export const getPostAuthRedirectPath = (user: AuthRedirectUser): string => {
  if (user.role === "ADMIN") return "/admin";
  return user.onboardingCompleted ? "/" : "/onboarding";
};
