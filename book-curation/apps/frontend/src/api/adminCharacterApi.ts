import { api } from "./authApi";
import type {
  AdminCharacter,
  AdminCharacterImageUploadResponse,
  AdminCharacterRequest,
} from "../types/adminCharacter";

const API_PREFIX = "/api";

export const getAdminCharacters = async (): Promise<AdminCharacter[]> => {
  /** 수정 포인트: 독자 유형 카드에서 선택할 수 있는 관리자 등록 캐릭터 목록을 조회합니다. */
  const res = await api.get<AdminCharacter[]>(`${API_PREFIX}/admin/characters`);
  return res.data;
};

export const uploadAdminCharacterImage = async (
  file: File
): Promise<AdminCharacterImageUploadResponse> => {
  const formData = new FormData();
  formData.append("file", file);

  /** 수정 포인트: 이미지 파일은 JSON이 아니라 multipart/form-data로 업로드합니다. CSRF 토큰은 공통 api interceptor가 자동으로 붙입니다. */
  const res = await api.post<AdminCharacterImageUploadResponse>(
    `${API_PREFIX}/admin/characters/images`,
    formData,
    {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    }
  );
  return res.data;
};

export const createAdminCharacter = async (
  payload: AdminCharacterRequest
): Promise<AdminCharacter> => {
  /** 수정 포인트: 캐릭터 키는 온보딩 옵션 연결값으로 사용되므로 관리자 화면에서 수정 가능하게 전달합니다. */
  const res = await api.post<AdminCharacter>(`${API_PREFIX}/admin/characters`, payload);
  return res.data;
};

export const updateAdminCharacter = async (
  id: number,
  payload: AdminCharacterRequest
): Promise<AdminCharacter> => {
  /** 수정 포인트: 기존 사용자의 캐릭터 보유 이력을 보호하기 위해 삭제 없이 키/기본 이름/이미지만 갱신합니다. */
  const res = await api.put<AdminCharacter>(`${API_PREFIX}/admin/characters/${id}`, payload);
  return res.data;
};
