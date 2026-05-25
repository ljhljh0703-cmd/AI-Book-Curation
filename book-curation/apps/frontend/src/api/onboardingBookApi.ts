import { searchOnboardingBooks } from "./onboardingApi";
import type {
  AladinBookSearchResponse,
  OnboardingBookSearchRequest,
  OnboardingBookSearchResponse,
} from "../types/onboarding";

export type {
  AladinBookItem as OnboardingBookItem,
  AladinBookSearchResponse,
  OnboardingBookSearchRequest,
  OnboardingBookSearchResponse,
} from "../types/onboarding";

export async function searchOnboardingBook(
  request: OnboardingBookSearchRequest
): Promise<OnboardingBookSearchResponse> {
  return searchOnboardingBooks(request.keyword, request.limit ?? 10, request.start ?? 1);
}

export async function searchOnboardingBookByKeyword(
  keyword: string,
  limit = 10,
  start = 1
): Promise<AladinBookSearchResponse> {
  return searchOnboardingBooks(keyword, limit, start);
}

export { searchOnboardingBooks };
