/**
 * 사용자 추가 프로필 API를 담당하는 파일.
 * authApi.ts에서 export 중인 공통 axios 인스턴스(api)를 재사용해서
 * 세션 쿠키, CSRF, 공통 에러 처리를 동일한 방식으로 적용한다.
 */

import { api } from "./authApi";

const API_PREFIX = "/api";

export type OnboardingOptionGroup = "READER_TYPE" | "BOOK_CATEGORY";

export type OnboardingOption = {
  id: number;
  optionGroup: OnboardingOptionGroup | string;
  optionKey: string;
  label: string;
  description: string | null;
  characterKey?: string | null;
  characterDefaultName?: string | null;
  characterImageUrl?: string | null;
  displayOrder: number;
};

export type UserProfileResponse = {
  userId: string;
  birthDate: string | null;
  residentGenderDigit: string | null;
  readerTypeOptionId: number | null;
  readerTypeLabel: string | null;
  readingPurpose: string | null;
  regionName: string | null;
  latitude: number | null;
  longitude: number | null;
  preferredRadiusKm: number;
  onboardingCompleted: boolean;
  categoryCodes: string[];
  keywords: string[];
};

export type UserCharacterResponse = {
  userId: string;
  characterKey: string;
  stage: string;
  characterNickname: string;
  reviewGrowthCount: number;
  currentImageUrl: string | null;
  characterLevel: number;
  experience: number;
  experienceToNextLevel: number;
  experiencePercent: number;
  maxLevel: number;
};

export type UpdateUserCharacterNicknameRequest = {
  characterNickname: string;
};

export type UpdateUserProfileRequest = {
  residentNumberFront?: string | null;
  residentGenderDigit?: string | null;
  readerTypeOptionId?: number | null;
  readingPurpose?: string | null;
  regionName?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  preferredRadiusKm?: number;
  categoryCodes?: string[];
  keywords?: string[];
};

export type UpdateUserProfileIdentityRequest = {
  residentNumberFront?: string | null;
  residentGenderDigit?: string | null;
};

export type UpdateUserProfileCategoriesRequest = {
  categoryCodes: string[];
};

export type UpdateUserProfileReadingPurposeRequest = {
  readingPurpose?: string | null;
};

export type UpdateUserProfilePreferredRadiusRequest = {
  preferredRadiusKm: number;
};

export type PreferredLibrary = {
  id: number;
  libCode: string;
  libName: string | null;
  address: string | null;
  latitude: number | null;
  longitude: number | null;
  priority: number;
};

export type PreferredLibraryRequest = {
  libCode: string;
  priority?: number;
};

export type NearbyLibrary = {
  libCode: string;
  libName: string;
  address: string | null;
  latitude: number | null;
  longitude: number | null;
  distanceMeters: number;
};

export type LibrarySearchResult = {
  libCode: string;
  libName: string;
  address: string | null;
  latitude: number | null;
  longitude: number | null;
};

export type BookSnapshotPayload = {
  bookId?: number | null;
  isbn13?: string | null;
  title?: string | null;
  author?: string | null;
  publisher?: string | null;
  coverUrl?: string | null;
  categoryCode?: string | null;
  metadata?: Record<string, unknown> | null;
};

export type RecommendationEventType =
  | "RECOMMENDATION_IMPRESSION"
  | "BOOK_CLICK"
  | "DETAIL_VIEW"
  | "FAVORITE_ADD"
  | "FAVORITE_REMOVE"
  | "READING_ADD"
  | "READ_ADD"
  | "RATING_ADD"
  | "REVIEW_ADD"
  | "DISLIKE_ADD"
  | "DISLIKE_REMOVE"
  | "SEARCH_QUERY";

export type RecommendationEventPayload = {
  requestId?: string | null;
  bookId?: number | null;
  book?: BookSnapshotPayload | null;
  eventType: RecommendationEventType;
  source?: string | null;
  query?: string | null;
  rank?: number | null;
  score?: number | null;
  metadata?: Record<string, unknown> | null;
};

export type RecommendationEventResponse = {
  id: number;
  requestId: string | null;
  bookId: number | null;
  eventType: RecommendationEventType;
  createdAt: string;
};

export type BookShelfType =
  | "READING"
  | "READ"
  | "INTERESTED"
  | "NOT_INTERESTED"
  | "WANT_TO_READ"
  | "FAVORITE";

export type BookShelf = {
  id: number;
  bookId: number;
  isbn13: string | null;
  title: string | null;
  author: string | null;
  publisher: string | null;
  coverUrl: string | null;
  shelfType: BookShelfType | string;
  note: string | null;
  reviewContent: string | null;
  reviewRating: number | null;
  reviewAvailableAt: string | null;
  reviewAvailable: boolean;
  reviewWaitMinutes: number;
  reviewWaitLabel: string;
  completedAt: string | null;
  createdAt: string;
  updatedAt: string;
};

export type BookShelfSummary = {
  maxReadingCount: number;
  maxInterestedCount: number;
  maxNotInterestedCount: number;
  counts: Record<string, number>;
  remaining: Record<string, number>;
};

export type BookShelfState = {
  isbn13: string;
  interested: boolean;
  notInterested: boolean;
  reading: boolean;
};

export type SaveBookShelfRequest = {
  bookId?: number | null;
  book?: BookSnapshotPayload | null;
  shelfType: BookShelfType;
  note?: string | null;
};

export type BookShelfReviewRequest = {
  reviewContent: string;
  // 수정 포인트: 독서대 리뷰 평점은 별점 UI에서 0.5 단위로 선택한 0.5~5.0 값을 전달합니다.
  rating: number;
};

export type CharacterLevelUpEvent = {
  previousLevel: number;
  newLevel: number;
  characterNickname: string;
  characterImageUrl: string | null;
  experience: number;
  experienceToNextLevel: number;
  maxLevel: number;
  message: string;
};

export type BookShelfReviewResponse = {
  shelf: BookShelf;
  character: UserCharacterResponse;
  levelUpEvent: CharacterLevelUpEvent | null;
  reviewRewardGranted: boolean;
  reviewRewardMessage: string;
};

export type BookAvailabilityLibraryResult = {
  source: "PREFERRED" | "NEARBY" | string;
  libCode: string;
  libName: string | null;
  address: string | null;
  distanceMeters: number | null;
  hasBook: boolean | null;
  loanAvailable: boolean | null;
  message: string | null;
  success: boolean;
};

export type BookAvailabilityResponse = {
  isbn13: string;
  preferredLibraryCount: number;
  nearbyLibraryCount: number;
  libraries: BookAvailabilityLibraryResult[];
};

export const getMyProfile = async (): Promise<UserProfileResponse> => {
  const res = await api.get<UserProfileResponse>(`${API_PREFIX}/users/me/profile`);
  return res.data;
};

export const updateMyProfile = async (
  payload: UpdateUserProfileRequest
): Promise<UserProfileResponse> => {
  const res = await api.put<UserProfileResponse>(
    `${API_PREFIX}/users/me/profile`,
    payload
  );
  return res.data;
};

export const updateMyProfileIdentity = async (
  payload: UpdateUserProfileIdentityRequest
): Promise<UserProfileResponse> => {
  const res = await api.patch<UserProfileResponse>(
    `${API_PREFIX}/users/me/profile/identity`,
    payload
  );
  return res.data;
};

export const updateMyProfileCategories = async (
  payload: UpdateUserProfileCategoriesRequest
): Promise<UserProfileResponse> => {
  const res = await api.put<UserProfileResponse>(
    `${API_PREFIX}/users/me/profile/categories`,
    payload
  );
  return res.data;
};

export const updateMyProfileReadingPurpose = async (
  payload: UpdateUserProfileReadingPurposeRequest
): Promise<UserProfileResponse> => {
  const res = await api.patch<UserProfileResponse>(
    `${API_PREFIX}/users/me/profile/reading-purpose`,
    payload
  );
  return res.data;
};

export const updateMyProfilePreferredRadius = async (
  payload: UpdateUserProfilePreferredRadiusRequest
): Promise<UserProfileResponse> => {
  const res = await api.patch<UserProfileResponse>(
    `${API_PREFIX}/users/me/profile/preferred-radius`,
    payload
  );
  return res.data;
};

export const getOnboardingOptions = async (
  optionGroup: OnboardingOptionGroup
): Promise<OnboardingOption[]> => {
  const res = await api.get<OnboardingOption[]>(`${API_PREFIX}/onboarding/options`, {
    params: { optionGroup },
  });
  return res.data;
};

export const getMyCharacter = async (): Promise<UserCharacterResponse> => {
  const res = await api.get<UserCharacterResponse>(`${API_PREFIX}/users/me/character`);
  return res.data;
};

export const updateMyCharacterNickname = async (
  payload: UpdateUserCharacterNicknameRequest
): Promise<UserCharacterResponse> => {
  const res = await api.put<UserCharacterResponse>(
    `${API_PREFIX}/users/me/character/nickname`,
    payload
  );
  return res.data;
};

export const getMyPreferredLibraries = async (): Promise<PreferredLibrary[]> => {
  const res = await api.get<PreferredLibrary[]>(`${API_PREFIX}/users/me/preferred-libraries`);
  return res.data;
};

export const saveMyPreferredLibrary = async (
  payload: PreferredLibraryRequest
): Promise<PreferredLibrary> => {
  const res = await api.post<PreferredLibrary>(`${API_PREFIX}/users/me/preferred-libraries`, payload);
  return res.data;
};

export const deleteMyPreferredLibrary = async (libCode: string): Promise<void> => {
  await api.delete(`${API_PREFIX}/users/me/preferred-libraries/${encodeURIComponent(libCode)}`);
};

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

export const searchNearbyLibraries = async (
  latitude: number,
  longitude: number,
  radiusKm: number,
  page = 0
): Promise<LibraryPageResponse<NearbyLibrary>> => {
  const res = await api.get<LibraryPageResponse<NearbyLibrary>>(`${API_PREFIX}/libraries/nearby`, {
    params: {
      latitude,
      longitude,
      radiusMeters: Math.round(radiusKm * 1000),
      page,
    },
  });
  return res.data;
};

// 수정 포인트: 백엔드의 일반 사용자용 도서관 검색은 도서관명/주소 기준입니다. libCode는 응답 식별자와 저장 요청에만 사용합니다.
export const searchLibrariesByKeyword = async (
  keyword: string,
  page = 0
): Promise<LibraryPageResponse<LibrarySearchResult>> => {
  const res = await api.get<LibraryPageResponse<LibrarySearchResult>>(`${API_PREFIX}/libraries/search`, {
    params: { keyword, page },
  });
  return res.data;
};

export const getMyBookShelves = async (shelfType?: BookShelfType): Promise<BookShelf[]> => {
  const res = await api.get<BookShelf[]>(`${API_PREFIX}/users/me/book-shelves`, {
    params: shelfType ? { shelfType } : undefined,
  });
  return res.data;
};

export const getMyBookShelfSummary = async (): Promise<BookShelfSummary> => {
  const res = await api.get<BookShelfSummary>(`${API_PREFIX}/users/me/book-shelves/summary`);
  return res.data;
};

export const getMyBookShelfStates = async (
  isbn13s: string[]
): Promise<BookShelfState[]> => {
  const uniqueIsbn13s = Array.from(new Set(isbn13s.map((value) => value.trim()).filter(Boolean)));
  if (uniqueIsbn13s.length === 0) return [];

  // 수정 포인트: 채팅방 재접속 시 추천 카드의 관심/비관심/읽는 중 상태를 ISBN 기준으로 복원합니다.
  const res = await api.get<BookShelfState[]>(`${API_PREFIX}/users/me/book-shelves/states`, {
    params: { isbn13s: uniqueIsbn13s.join(",") },
  });
  return res.data;
};

export const saveMyBookShelf = async (
  payload: SaveBookShelfRequest
): Promise<BookShelf> => {
  const res = await api.post<BookShelf>(`${API_PREFIX}/users/me/book-shelves`, payload);
  return res.data;
};

export const deleteMyBookShelf = async (shelfId: number): Promise<void> => {
  await api.delete(`${API_PREFIX}/users/me/book-shelves/${shelfId}`);
};

export const deleteMyBookShelfByIsbn = async (
  isbn13: string,
  shelfType: BookShelfType
): Promise<void> => {
  // 수정 포인트: 추천 카드 버튼을 다시 눌렀을 때 해당 ISBN의 책장 등록을 취소합니다.
  await api.delete(`${API_PREFIX}/users/me/book-shelves/by-isbn/${encodeURIComponent(isbn13)}`, {
    params: { shelfType },
  });
};

export const completeMyBookShelfReview = async (
  shelfId: number,
  payload: BookShelfReviewRequest
): Promise<BookShelfReviewResponse> => {
  const res = await api.post<BookShelfReviewResponse>(`${API_PREFIX}/users/me/book-shelves/${shelfId}/review`, payload);
  return res.data;
};

export const checkBookAvailability = async (
  book: BookSnapshotPayload,
  latitude?: number | null,
  longitude?: number | null
): Promise<BookAvailabilityResponse> => {
  const res = await api.post<BookAvailabilityResponse>(
    `${API_PREFIX}/users/me/book-availability`,
    {
      book,
      latitude,
      longitude,
    }
  );
  return res.data;
};

export const sendRecommendationEvent = async (
  payload: RecommendationEventPayload
): Promise<RecommendationEventResponse> => {
  // 수정 포인트: 추천 카드 클릭/상세보기는 알라딘 API를 호출하지 않고 현재 카드 snapshot만 backend 이벤트 로그로 전달합니다.
  const res = await api.post<RecommendationEventResponse>(
    `${API_PREFIX}/recommendation-events`,
    payload
  );
  return res.data;
};
