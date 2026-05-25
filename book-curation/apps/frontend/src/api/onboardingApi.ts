import { api } from "./authApi";
import type {
  AladinBookSearchResponse,
  CompleteOnboardingRequest,
  CompleteOnboardingResponse,
  OnboardingOption,
  OnboardingOptionGroup,
} from "../types/onboarding";
import type { MeResponse } from "../types/auth";

export async function getOnboardingOptions(
  optionGroup: OnboardingOptionGroup
): Promise<OnboardingOption[]> {
  const response = await api.get<OnboardingOption[]>("/api/onboarding/options", {
    params: { optionGroup },
  });

  return [...response.data].sort((a, b) => {
    const left = a.displayOrder ?? 0;
    const right = b.displayOrder ?? 0;
    return left - right || a.id - b.id;
  });
}

export async function searchOnboardingBooks(
  keyword: string,
  limit = 10,
  start = 1
): Promise<AladinBookSearchResponse> {
  const response = await api.get<AladinBookSearchResponse>(
    "/api/onboarding/books/search",
    {
      params: {
        keyword,
        limit,
        start,
      },
    }
  );

  return response.data;
}

export async function completeOnboarding(
  payload: CompleteOnboardingRequest
): Promise<CompleteOnboardingResponse> {
  const response = await api.post<CompleteOnboardingResponse>(
    "/api/onboarding/complete",
    payload
  );

  return response.data;
}

export async function skipOnboarding(): Promise<MeResponse> {
  const response = await api.post<MeResponse>("/api/onboarding/skip");
  return response.data;
}
