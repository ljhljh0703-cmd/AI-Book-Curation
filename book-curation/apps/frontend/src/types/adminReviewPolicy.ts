export type ReviewPolicy = {
  reviewWaitMinutes: number;
  reviewWaitLabel: string;
  updatedAt: string | null;
};

export type ReviewPolicyUpdateRequest = {
  reviewWaitMinutes: number;
};
