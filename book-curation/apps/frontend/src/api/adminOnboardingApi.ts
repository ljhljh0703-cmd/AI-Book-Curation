import { api } from "./authApi";
import type {
  OnboardingOption,
  OnboardingOptionGroup,
  OnboardingOptionReorderRequest,
  OnboardingOptionRequest,
} from "../types/onboardingAdmin";

const API_PREFIX = "/api";

export const getOnboardingOptions = async (
  optionGroup: OnboardingOptionGroup
): Promise<OnboardingOption[]> => {
  /** 수정 포인트: 관리자 화면의 선택된 그룹에 맞춰 온보딩 선택지를 조회합니다. */
  const res = await api.get<OnboardingOption[]>(
    `${API_PREFIX}/admin/onboarding-options`,
    { params: { optionGroup } }
  );
  return res.data;
};

export const createOnboardingOption = async (
  payload: OnboardingOptionRequest
): Promise<OnboardingOption> => {
  /** 수정 포인트: optionKey는 서버가 자동 생성하므로 관리자는 표시 이름/설명/구분값/사용 여부만 보냅니다. */
  const res = await api.post<OnboardingOption>(
    `${API_PREFIX}/admin/onboarding-options`,
    payload
  );
  return res.data;
};

export const updateOnboardingOption = async (
  id: number,
  payload: OnboardingOptionRequest
): Promise<OnboardingOption> => {
  /** 수정 포인트: 운영 중 표시 이름, 설명, 캐릭터 구분값, 활성 상태만 안전하게 변경합니다. */
  const res = await api.put<OnboardingOption>(
    `${API_PREFIX}/admin/onboarding-options/${id}`,
    payload
  );
  return res.data;
};

export const reorderOnboardingOptions = async (
  payload: OnboardingOptionReorderRequest
): Promise<OnboardingOption[]> => {
  /** 수정 포인트: 드래그앤드랍으로 정한 순서를 displayOrder에 일괄 저장합니다. */
  const res = await api.patch<OnboardingOption[]>(
    `${API_PREFIX}/admin/onboarding-options/display-order`,
    payload
  );
  return res.data;
};

export const deleteOnboardingOption = async (id: number): Promise<void> => {
  /** 수정 포인트: 관리자 화면에서 더 이상 쓰지 않는 선택지를 삭제합니다. */
  await api.delete(`${API_PREFIX}/admin/onboarding-options/${id}`);
};
