import { api } from "./authApi";
import type {
  LibrarySyncConfigResponse,
  LibrarySyncResponse,
} from "../types/library";

const API_PREFIX = "/api";

export const getLibrarySyncConfig = async (): Promise<LibrarySyncConfigResponse> => {
  /** 수정 포인트: 관리자 화면에서 Library API 토큰 설정 여부만 확인하고 실제 토큰 값은 노출하지 않는다. */
  const res = await api.get<LibrarySyncConfigResponse>(
    `${API_PREFIX}/admin/libraries/sync/config`
  );
  return res.data;
};

export const syncLibraries = async (): Promise<LibrarySyncResponse> => {
  /** 수정 포인트: Library API 동기화는 관리자 전용 POST API를 호출한다. CSRF 헤더는 authApi interceptor가 자동 주입한다. */
  const res = await api.post<LibrarySyncResponse>(
    `${API_PREFIX}/admin/libraries/sync`,
    {}
  );
  return res.data;
};
