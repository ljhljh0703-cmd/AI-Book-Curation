export type OnboardingOptionGroup = "READER_TYPE" | "BOOK_CATEGORY";

export type OnboardingOption = {
  id: number;
  optionGroup: OnboardingOptionGroup;
  optionKey: string;
  label: string;
  description: string | null;
  characterKey: string | null;
  characterDefaultName: string | null;
  characterImageUrl: string | null;
  displayOrder: number | null;
};

export type SelectedOnboardingLibrary = {
  libCode: string;
  libName: string;
  address: string | null;
};

export type AladinBookItem = {
  aladinItemId: string | null;
  isbn: string | null;
  isbn13: string | null;
  title: string | null;
  author: string | null;
  publisher: string | null;
  pubDate: string | null;
  description: string | null;
  coverUrl: string | null;
  categoryId: string | null;
  categoryName: string | null;
  customerReviewRank: number | null;
  priceSales: number | null;
  priceStandard: number | null;
};

export type AladinBookSearchResponse = {
  totalResults: number;
  startIndex: number;
  itemsPerPage: number;
  query: string;
  items: AladinBookItem[];
};

export type OnboardingBookItem = AladinBookItem;
export type OnboardingBookSearchResponse = AladinBookSearchResponse;

export type OnboardingBookSearchRequest = {
  keyword: string;
  limit?: number;
  start?: number;
};

export type SelectedOnboardingBook = {
  item: AladinBookItem;
  note?: string;
};

export type OnboardingForm = {
  birthDate: string;
  genderCode: string;
  readerTypeOptionId: number | null;
  bookCategoryOptionIds: number[];
  selectedBooks: SelectedOnboardingBook[];
  favoriteBook: string;
  favoriteAuthor: string;
  readingPurpose: string;
  selectedLibrary: SelectedOnboardingLibrary | null;
  keywords: string[];
};

export type BookSnapshotRequest = {
  isbn13: string;
  title?: string | null;
  author?: string | null;
  publisher?: string | null;
  coverUrl?: string | null;
  categoryCode?: string | null;
  metadata?: Record<string, unknown> | null;
};

export type SelectedBookRequest = {
  bookId?: number | null;
  book?: BookSnapshotRequest | null;
  shelfType?: "READ";
  note?: string | null;
};

export type CompleteOnboardingRequest = {
  residentNumberFront: string;
  residentGenderDigit: string;
  readerTypeOptionId: number;
  bookCategoryOptionIds: number[];
  readingPurpose?: string;
  preferredRadiusKm?: number;
  preferredLibraryCode?: string;
  selectedBooks?: SelectedBookRequest[];
};

export type CompleteOnboardingResponse = {
  onboardingCompleted: boolean;
  character?: {
    characterKey: string;
    characterNickname: string;
    currentImageUrl: string | null;
  };
};

export type OnboardingStepProps = {
  form: OnboardingForm;
  updateForm: <K extends keyof OnboardingForm>(
    key: K,
    value: OnboardingForm[K]
  ) => void;
  goNext: () => void;
  goPrev: () => void;
  goToStep: (step: number) => void;
  completeOnboarding: () => Promise<void>;
  skipOnboarding: () => Promise<void>;
  requestSkipOnboarding: () => void;
  submitting: boolean;
  skipping: boolean;
  canSubmit: boolean;
  requiredMessage: string;
  readerTypeOptions: OnboardingOption[];
  bookCategoryOptions: OnboardingOption[];
};
