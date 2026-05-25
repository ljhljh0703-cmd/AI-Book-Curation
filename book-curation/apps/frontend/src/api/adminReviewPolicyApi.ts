import { api } from "./authApi";
import type { ReviewPolicy, ReviewPolicyUpdateRequest } from "../types/adminReviewPolicy";

const API_PREFIX = "/api";

export const getAdminReviewPolicy = async (): Promise<ReviewPolicy> => {
  const res = await api.get<ReviewPolicy>(`${API_PREFIX}/admin/review-policy`);
  return res.data;
};

export const updateAdminReviewPolicy = async (
  payload: ReviewPolicyUpdateRequest
): Promise<ReviewPolicy> => {
  const res = await api.put<ReviewPolicy>(`${API_PREFIX}/admin/review-policy`, payload);
  return res.data;
};
