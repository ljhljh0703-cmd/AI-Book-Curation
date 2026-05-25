type CapacitorBridge = {
  isNativePlatform?: () => boolean;
  getPlatform?: () => string;
};

declare global {
  interface Window {
    Capacitor?: CapacitorBridge;
  }
}

const DEFAULT_PUBLIC_SITE_URL = "https://book.taeo-dev.com";

export const getPublicSiteBaseUrl = (): string => {
  const raw = import.meta.env.VITE_PUBLIC_SITE_URL?.trim() || DEFAULT_PUBLIC_SITE_URL;
  return raw.replace(/\/+$/, "");
};

export const isNativeMobileApp = (): boolean => {
  if (typeof window === "undefined") return false;
  return window.Capacitor?.isNativePlatform?.() === true;
};

export const getNativePlatform = (): string => {
  if (typeof window === "undefined") return "web";
  return window.Capacitor?.getPlatform?.() || "web";
};

export const toNativeAbsoluteUrl = (url?: string | null): string => {
  if (!url) return "";

  // 수정 포인트: blob/data URL, 절대 URL, tel/mail 링크는 그대로 둡니다.
  if (/^(https?:|blob:|data:|mailto:|tel:)/i.test(url)) {
    return url;
  }

  if (!url.startsWith("/")) {
    return url;
  }

  // 수정 포인트: Capacitor 앱에서는 /uploads, /oauth2, /api 같은 상대경로가
  // capacitor://localhost 기준으로 해석되므로 실제 서비스 도메인으로 보정합니다.
  if (isNativeMobileApp()) {
    return `${getPublicSiteBaseUrl()}${url}`;
  }

  return url;
};

export const applyNativeMobileAppClass = (): void => {
  if (typeof document === "undefined") return;

  document.documentElement.classList.toggle(
    "bookemon-native-app",
    isNativeMobileApp()
  );
  document.documentElement.dataset.platform = getNativePlatform();
};
