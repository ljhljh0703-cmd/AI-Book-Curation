export type Provider = "GOOGLE" | "KAKAO";

export interface LoginRequest {
  email: string;
  password: string;
}

export interface SignupRequest {
  email: string;
  password: string;
  nickname: string;
}

export interface PasswordResetSendCodeRequest {
  email: string;
}

export interface PasswordResetConfirmRequest {
  email: string;
  code: string;
  newPassword: string;
}

export interface DormantReleaseSendCodeRequest {
  email: string;
}

export interface DormantReleaseConfirmRequest {
  email: string;
  code: string;
}

export interface MessageResponse {
  message: string;
}


export interface UpdateNicknameRequest {
  nickname: string;
}
export interface EmailAvailabilityResponse {
  available: boolean;
  message: string;

}

export interface MeResponse {
  id: string;
  email: string;
  nickname: string;
  role: string;
  onboardingCompleted: boolean;
  linkedProviders: Provider[];
}

export interface PendingSocialSignupResponse {
  provider: Provider;
  email: string | null;
  nickname: string;
}

export interface SocialLinkStartResponse {
  authorizationUrl: string;
}

export interface CsrfResponse {
  headerName: string;
  parameterName: string;
  token: string;
}

export interface OAuth2ProviderItem {
  provider: Provider;
  authorizationUrl: string;
}

export interface OAuth2ProviderResponse {
  providers: OAuth2ProviderItem[];
}
