import axios, {
  AxiosError,
  AxiosHeaders,
  type InternalAxiosRequestConfig,
} from "axios";
import type {
  CsrfResponse,
  EmailAvailabilityResponse,
  DormantReleaseConfirmRequest,
  DormantReleaseSendCodeRequest,
  LoginRequest,
  MeResponse,
  MessageResponse,
  OAuth2ProviderResponse,
  PasswordResetConfirmRequest,
  PasswordResetSendCodeRequest,
  PendingSocialSignupResponse,
  Provider,
  SignupRequest,
  UpdateNicknameRequest,
  SocialLinkStartResponse,
} from "../types/auth";
import { clearUser, getUser, saveUser } from "../utils/storage";
import { getPublicSiteBaseUrl, isNativeMobileApp, toNativeAbsoluteUrl } from "../utils/mobileRuntime";

const DEFAULT_API_BASE_URL = "";
const API_PREFIX = "/api";

// 수정 포인트: Capacitor WebView에서는 /api가 capacitor://localhost/api로 해석되므로
// 앱 실행 중에는 상대경로 모드를 강제로 끄고 실제 서비스 도메인을 사용합니다.
const isRelativeApiMode =
  import.meta.env.VITE_USE_RELATIVE_API !== "false" && !isNativeMobileApp();

export class ApiError extends Error {
  readonly code?: string;
  readonly email?: string;
  readonly status?: number;

  constructor(message: string, options?: { code?: string; email?: string; status?: number }) {
    super(message);
    this.name = "ApiError";
    this.code = options?.code;
    this.email = options?.email;
    this.status = options?.status;
  }
}

const normalizeApiBaseUrl = (value?: string): string => {
  if (isRelativeApiMode) return "";

  const raw = value?.trim() || (isNativeMobileApp() ? getPublicSiteBaseUrl() : DEFAULT_API_BASE_URL);
  const withoutTrailingSlash = raw.replace(/\/+$/, "");

  if (!withoutTrailingSlash || withoutTrailingSlash === API_PREFIX) {
    return "";
  }

  return withoutTrailingSlash.endsWith(API_PREFIX)
    ? withoutTrailingSlash.slice(0, -API_PREFIX.length)
    : withoutTrailingSlash;
};

const normalizeOAuthBaseUrl = (value?: string): string => {
  if (isRelativeApiMode) return "";

  const raw =
    value?.trim() ||
    import.meta.env.VITE_API_BASE_URL?.trim() ||
    (isNativeMobileApp() ? getPublicSiteBaseUrl() : DEFAULT_API_BASE_URL);

  const withoutTrailingSlash = raw.replace(/\/+$/, "");

  return withoutTrailingSlash.endsWith(API_PREFIX)
    ? withoutTrailingSlash.slice(0, -API_PREFIX.length)
    : withoutTrailingSlash;
};

const API_BASE_URL = normalizeApiBaseUrl(import.meta.env.VITE_API_BASE_URL);
const OAUTH_BASE_URL = normalizeOAuthBaseUrl(
  import.meta.env.VITE_OAUTH_BASE_URL
);

export const api = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
  xsrfCookieName: "",
  xsrfHeaderName: "",
  headers: {
    "Content-Type": "application/json",
  },
});

let csrfCache: CsrfResponse | null = null;
let csrfPromise: Promise<CsrfResponse> | null = null;

const isMutationMethod = (method?: string) => {
  if (!method) return false;
  return ["post", "put", "patch", "delete"].includes(method.toLowerCase());
};

const isCsrfRequest = (url?: string) => url === `${API_PREFIX}/auth/csrf`;
const isMeRequest = (url?: string) => url === `${API_PREFIX}/auth/me`;

const clearCsrfCache = () => {
  csrfCache = null;
  csrfPromise = null;
};

const clearClientAuthState = () => {
  clearCsrfCache();
  clearUser();
};

const setRequestHeader = (
  config: InternalAxiosRequestConfig,
  headerName: string,
  headerValue: string
) => {
  const headers = AxiosHeaders.from(config.headers);
  headers.set(headerName, headerValue);
  config.headers = headers as InternalAxiosRequestConfig["headers"];
};

export const fetchCsrfToken = async (
  forceRefresh = false
): Promise<CsrfResponse> => {
  if (!forceRefresh && csrfCache) return csrfCache;
  if (!forceRefresh && csrfPromise) return csrfPromise;

  csrfPromise = api
    .get<CsrfResponse>(`${API_PREFIX}/auth/csrf`)
    .then((res) => {
      csrfCache = res.data;
      return res.data;
    })
    .finally(() => {
      csrfPromise = null;
    });

  return csrfPromise;
};

api.interceptors.request.use(
  async (config: InternalAxiosRequestConfig) => {
    if (isMutationMethod(config.method) && !isCsrfRequest(config.url)) {
      const csrf = await fetchCsrfToken();
      setRequestHeader(config, csrf.headerName || "X-XSRF-TOKEN", csrf.token);
    }

    return config;
  },
  (error) => Promise.reject(error)
);

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<{ message?: string; error?: string; code?: string; email?: string }>) => {
    const originalRequest = error.config as
      | (InternalAxiosRequestConfig & { _csrfRetry?: boolean })
      | undefined;

    if (
      error.response?.status === 403 &&
      originalRequest &&
      !originalRequest._csrfRetry &&
      isMutationMethod(originalRequest.method) &&
      !isCsrfRequest(originalRequest.url)
    ) {
      originalRequest._csrfRetry = true;
      clearCsrfCache();

      const csrf = await fetchCsrfToken(true);
      setRequestHeader(
        originalRequest,
        csrf.headerName || "X-XSRF-TOKEN",
        csrf.token
      );

      return api.request(originalRequest);
    }

    if (error.response?.status === 401) {
      clearClientAuthState();
    }

    if (error.response?.status === 403) {
      clearCsrfCache();
      if (isMeRequest(originalRequest?.url)) {
        clearUser();
      }
    }

    const message =
      error.response?.data?.message ||
      error.response?.data?.error ||
      error.message ||
      "API 요청 중 오류가 발생했습니다.";

    return Promise.reject(
      new ApiError(message, {
        code: error.response?.data?.code,
        email: error.response?.data?.email,
        status: error.response?.status,
      })
    );
  }
);

export const checkSignupEmailAvailability = async (
  email: string
): Promise<EmailAvailabilityResponse> => {
  const res = await api.get<EmailAvailabilityResponse>(
    `${API_PREFIX}/auth/signup/email-availability`,
    {
      params: { email },
    }
  );
  return res.data;
};

export const signup = async (data: SignupRequest): Promise<MeResponse> => {
  const res = await api.post<MeResponse>(`${API_PREFIX}/auth/signup`, data);
  // 수정 포인트: 회원가입은 성공 즉시 로그인 세션을 생성하므로 이후 온보딩 POST가 이전 CSRF 캐시를 재사용하지 않게 합니다.
  clearCsrfCache();
  return res.data;
};

export const completeSocialSignup = async (
  data: SignupRequest
): Promise<MeResponse> => {
  const res = await api.post<MeResponse>(
    `${API_PREFIX}/auth/social-signup/complete`,
    data
  );
  clearCsrfCache();
  return res.data;
};

export const getPendingSocialSignup = async (): Promise<PendingSocialSignupResponse | null> => {
  const res = await api.get<PendingSocialSignupResponse | undefined>(
    `${API_PREFIX}/auth/social-signup/pending`,
    {
      // 수정 포인트: 소셜 가입 대기 정보가 없을 때 backend가 204를 내려도 axios가 오류로 처리하지 않게 합니다.
      validateStatus: (status) => (status >= 200 && status < 300) || status === 204,
    }
  );

  if (res.status === 204) {
    return null;
  }

  return res.data ?? null;
};

export const login = async (data: LoginRequest): Promise<MeResponse> => {
  const res = await api.post<MeResponse>(`${API_PREFIX}/auth/login`, data);
  clearCsrfCache();
  return res.data;
};

export const sendPasswordResetCode = async (
  data: PasswordResetSendCodeRequest
): Promise<MessageResponse> => {
  const res = await api.post<MessageResponse>(
    `${API_PREFIX}/auth/password-reset/send-code`,
    data
  );
  return res.data;
};

export const confirmPasswordReset = async (
  data: PasswordResetConfirmRequest
): Promise<MessageResponse> => {
  const res = await api.post<MessageResponse>(
    `${API_PREFIX}/auth/password-reset/confirm`,
    data
  );
  return res.data;
};

export const sendDormantReleaseCode = async (
  data: DormantReleaseSendCodeRequest
): Promise<MessageResponse> => {
  const res = await api.post<MessageResponse>(
    `${API_PREFIX}/auth/dormant/send-code`,
    data
  );
  return res.data;
};

export const confirmDormantRelease = async (
  data: DormantReleaseConfirmRequest
): Promise<MessageResponse> => {
  const res = await api.post<MessageResponse>(
    `${API_PREFIX}/auth/dormant/confirm`,
    data
  );
  return res.data;
};

export const getMe = async (): Promise<MeResponse> => {
  const res = await api.get<MeResponse>(`${API_PREFIX}/auth/me`);
  return res.data;
};

export const updateNickname = async (data: UpdateNicknameRequest): Promise<MeResponse> => {
  const res = await api.put<MeResponse>(`${API_PREFIX}/auth/me/nickname`, data);
  return res.data;
};

export const syncAuthenticatedUser = async (): Promise<MeResponse | null> => {
  if (!getUser()) {
    return null;
  }

  try {
    const me = await getMe();
    saveUser(me);
    return me;
  } catch {
    clearClientAuthState();
    return null;
  }
};

export const logout = async (): Promise<void> => {
  await api.post(`${API_PREFIX}/auth/logout`, {});
  clearClientAuthState();
};

export const withdraw = async (): Promise<MessageResponse> => {
  const res = await api.post<MessageResponse>(`${API_PREFIX}/auth/withdraw`, {});
  clearClientAuthState();
  return res.data;
};

export const getOAuthProviders = async (): Promise<OAuth2ProviderResponse> => {
  const res = await api.get<OAuth2ProviderResponse>(
    `${API_PREFIX}/auth/oauth2/providers`
  );

  return {
    ...res.data,
    providers: (res.data.providers ?? []).map((provider) => ({
      ...provider,
      // 수정 포인트: 앱에서는 백엔드가 내려준 /oauth2/... 상대경로를 실제 도메인 기준으로 보정합니다.
      authorizationUrl: toNativeAbsoluteUrl(provider.authorizationUrl),
    })),
  };
};

export const startSocialLink = async (
  provider: Provider
): Promise<SocialLinkStartResponse> => {
  const res = await api.post<SocialLinkStartResponse>(
    `${API_PREFIX}/auth/social-link/${provider.toLowerCase()}/start`,
    {}
  );

  return {
    ...res.data,
    // 수정 포인트: 소셜 연동 시작 URL도 앱에서는 실제 서비스 도메인 기준으로 이동해야 합니다.
    authorizationUrl: toNativeAbsoluteUrl(res.data.authorizationUrl),
  };
};

export const unlinkSocialLink = async (
  provider: Provider
): Promise<MeResponse> => {
  const res = await api.delete<MeResponse>(
    `${API_PREFIX}/auth/social-link/${provider.toLowerCase()}`
  );
  clearCsrfCache();
  return res.data;
};

const getOAuthAuthorizationUrl = (provider: "google" | "kakao") => {
  const path = `/oauth2/authorization/${provider}`;
  return OAUTH_BASE_URL ? `${OAUTH_BASE_URL}${path}` : toNativeAbsoluteUrl(path);
};

const moveToOAuthAuthorization = (provider: "google" | "kakao") => {
  window.location.assign(getOAuthAuthorizationUrl(provider));
};

export const getGoogleLoginUrl = () => getOAuthAuthorizationUrl("google");
export const getKakaoLoginUrl = () => getOAuthAuthorizationUrl("kakao");
export const startGoogleLogin = () => moveToOAuthAuthorization("google");
export const startKakaoLogin = () => moveToOAuthAuthorization("kakao");

export const resetAuthCache = () => {
  clearCsrfCache();
};

export function startSocialLogin(provider: "google" | "kakao") {
  moveToOAuthAuthorization(provider);
}
