export type OnboardingOptionGroup = "READER_TYPE" | "BOOK_CATEGORY";

export type OnboardingOption = {
  id: number;
  optionGroup: OnboardingOptionGroup;
  label: string;
  description: string | null;
  characterGroupCode: string | null;
  displayOrder: number;
  active: boolean;
  createdAt: string;
  updatedAt: string;
};

export type OnboardingOptionRequest = {
  optionGroup: OnboardingOptionGroup;
  label: string;
  description?: string | null;
  characterGroupCode?: string | null;
  active?: boolean;
};

export type OnboardingOptionReorderRequest = {
  optionGroup: OnboardingOptionGroup;
  orderedIds: number[];
};
