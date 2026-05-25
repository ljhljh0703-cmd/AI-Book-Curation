/**
 * 온보딩 도서관 선택 전용 API 파일.
 * 전체 도서관 기능이 아니라 온보딩 Step6에서 대표 도서관을 검색하고 선택하는 용도로만 사용한다.
 */

import { api } from "./authApi";

export const LIBRARY_PAGE_SIZE = 10;

export type LibraryPageResponse<T> = {
  content: T[];
  page: number;
  size: number;
  totalElements: number;
  totalPages: number;
  hasNext: boolean;
  hasPrevious: boolean;
};

export type OnboardingLibrarySearchItem = {
  libCode: string;
  libName: string;
  address: string | null;
  latitude: number | null;
  longitude: number | null;
  distanceMeters?: number | null;
};

/**
 * 도서관명, 주소 기준으로 도서관을 검색한다.
 * 수정 포인트: libCode는 내부 저장/대출 가능 여부 조회용으로만 사용하고, 사용자 입력 검색 조건에서는 제외한다.
 * 로그인 세션이 필요한 API이므로 온보딩 페이지는 로그인 이후에 접근해야 한다.
 */
export async function searchOnboardingLibraries(
  keyword: string,
  page = 0
): Promise<LibraryPageResponse<OnboardingLibrarySearchItem>> {
  const response = await api.get<LibraryPageResponse<OnboardingLibrarySearchItem>>(
    "/api/libraries/search",
    {
      params: {
        keyword,
        page,
      },
    }
  );

  return response.data;
}

/**
 * 브라우저 현재 위치를 기준으로 가까운 도서관을 조회한다.
 * 위치 정보는 검색 순간에만 사용하고 온보딩 완료 요청에는 도서관 코드만 저장한다.
 */
export async function getNearbyOnboardingLibraries(params: {
  latitude: number;
  longitude: number;
  radiusMeters?: number;
  page?: number;
}): Promise<LibraryPageResponse<OnboardingLibrarySearchItem>> {
  const response = await api.get<LibraryPageResponse<OnboardingLibrarySearchItem>>(
    "/api/libraries/nearby",
    {
      params: {
        latitude: params.latitude,
        longitude: params.longitude,
        radiusMeters: params.radiusMeters ?? 5000,
        page: params.page ?? 0,
      },
    }
  );

  return response.data;
}
