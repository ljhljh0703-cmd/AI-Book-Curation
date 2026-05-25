import type { MeResponse } from "../types/auth";

const USER_KEY = "user";
const AUTH_CHANGED_EVENT = "book-curation-auth-changed";

/** 수정 포인트: 같은 탭에서도 Navbar가 로그인/로그아웃 상태 변화를 즉시 감지하게 이벤트를 발생시킨다. */
const notifyAuthChanged = () => {
  window.dispatchEvent(new Event(AUTH_CHANGED_EVENT));
};

export const saveUser = (user: MeResponse) => {
  localStorage.setItem(USER_KEY, JSON.stringify(user));
  notifyAuthChanged();
};

export const getUser = (): MeResponse | null => {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;

  try {
    return JSON.parse(raw) as MeResponse;
  } catch {
    /** 수정 포인트: 깨진 localStorage 값 때문에 화면 렌더링이 터지지 않도록 방어한다. */
    localStorage.removeItem(USER_KEY);
    return null;
  }
};

export const clearUser = () => {
  localStorage.removeItem(USER_KEY);
  notifyAuthChanged();
};

export const onAuthChanged = (handler: () => void) => {
  window.addEventListener(AUTH_CHANGED_EVENT, handler);
  window.addEventListener("storage", handler);

  return () => {
    window.removeEventListener(AUTH_CHANGED_EVENT, handler);
    window.removeEventListener("storage", handler);
  };
};
