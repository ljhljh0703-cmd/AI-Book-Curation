import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getMe } from "../api/authApi";
import {
  completeOnboarding as requestCompleteOnboarding,
  getOnboardingOptions,
  skipOnboarding as requestSkipOnboardingApi,
} from "../api/onboardingApi";
import OnboardingLayout from "../components/onboarding/layout/OnboardingLayout";
import Step0Intro from "../components/onboarding/steps/Step0Intro";
import Step1Profile from "../components/onboarding/steps/Step1Profile";
import Step2ReaderType from "../components/onboarding/steps/Step2ReaderType";
import Step3Category from "../components/onboarding/steps/Step3Category";
import Step4BookAuthor from "../components/onboarding/steps/Step4BookAuthor";
import Step5Purpose from "../components/onboarding/steps/Step5Purpose";
import Step6Library from "../components/onboarding/steps/Step6Library";
import OnboardingReward from "../components/onboarding/steps/OnboardingReward";
import { TOTAL_ONBOARDING_STEP } from "../components/onboarding/constants/onboardingOptions";
import type {
  AladinBookItem,
  CompleteOnboardingRequest,
  CompleteOnboardingResponse,
  OnboardingForm,
  OnboardingOption,
} from "../types/onboarding";
import { saveUser } from "../utils/storage";
import { getResidentProfileValidationMessage } from "../utils/onboardingValidation";

const initialForm: OnboardingForm = {
  birthDate: "",
  genderCode: "",
  readerTypeOptionId: null,
  bookCategoryOptionIds: [],
  selectedBooks: [],
  favoriteBook: "",
  favoriteAuthor: "",
  readingPurpose: "",
  selectedLibrary: null,
  keywords: [],
};

const toSelectedBookRequest = (item: AladinBookItem) => ({
  shelfType: "READ" as const,
  note: "온보딩에서 선택한 읽은 책",
  book: {
    isbn13: item.isbn13 ?? "",
    title: item.title,
    author: item.author,
    publisher: item.publisher,
    coverUrl: item.coverUrl,
    categoryCode: item.categoryId,
    metadata: {
      source: "ALADIN",
      aladinItemId: item.aladinItemId,
      isbn: item.isbn,
      pubDate: item.pubDate,
      description: item.description,
      categoryName: item.categoryName,
      customerReviewRank: item.customerReviewRank,
      priceSales: item.priceSales,
      priceStandard: item.priceStandard,
    },
  },
});

export default function OnboardingPage() {
  const navigate = useNavigate();

  const [step, setStep] = useState(0);
  const [form, setForm] = useState<OnboardingForm>(initialForm);
  const [readerTypeOptions, setReaderTypeOptions] = useState<OnboardingOption[]>([]);
  const [bookCategoryOptions, setBookCategoryOptions] = useState<OnboardingOption[]>([]);
  const [optionsLoading, setOptionsLoading] = useState(true);
  const [optionsError, setOptionsError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [skipping, setSkipping] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [skipConfirmOpen, setSkipConfirmOpen] = useState(false);
  const [issuedCharacter, setIssuedCharacter] = useState<
    CompleteOnboardingResponse["character"] | null | undefined
  >(undefined);

  useEffect(() => {
    let mounted = true;

    const loadOptions = async () => {
      setOptionsLoading(true);
      setOptionsError("");

      try {
        const [readerTypes, bookCategories] = await Promise.all([
          getOnboardingOptions("READER_TYPE"),
          getOnboardingOptions("BOOK_CATEGORY"),
        ]);

        if (!mounted) return;

        setReaderTypeOptions(readerTypes);
        setBookCategoryOptions(bookCategories);
      } catch (error) {
        if (!mounted) return;

        setOptionsError(
          error instanceof Error
            ? error.message
            : "온보딩 선택지를 불러오지 못했습니다."
        );
      } finally {
        if (mounted) {
          setOptionsLoading(false);
        }
      }
    };

    void loadOptions();

    return () => {
      mounted = false;
    };
  }, []);

  const updateForm = <K extends keyof OnboardingForm>(
    key: K,
    value: OnboardingForm[K]
  ) => {
    setForm((prev) => ({
      ...prev,
      [key]: value,
    }));
    // 수정 포인트: 완료 버튼 검증으로 이동한 단계에서 사용자가 값을 고치면 이전 필수값 안내를 제거합니다.
    setStepValidation(null);
  };

  const [stepValidation, setStepValidation] = useState<{
    step: number;
    message: string;
  } | null>(null);

  const getValidationResult = () => {
    const profileInvalid = getResidentProfileValidationMessage(
      form.birthDate,
      form.genderCode
    );

    if (profileInvalid) {
      return {
        canSubmit: false,
        targetStep: 1,
        message: "필수값을 입력해주세요.",
      };
    }

    if (form.readerTypeOptionId === null) {
      return {
        canSubmit: false,
        targetStep: 2,
        message: "필수값을 입력해주세요.",
      };
    }

    if (form.bookCategoryOptionIds.length === 0) {
      return {
        canSubmit: false,
        targetStep: 3,
        message: "필수값을 입력해주세요.",
      };
    }

    if (form.bookCategoryOptionIds.length > 3) {
      return {
        canSubmit: false,
        targetStep: 3,
        message: "도서 카테고리는 최대 3개까지 선택할 수 있습니다.",
      };
    }

    const selectedBooksValid =
      form.selectedBooks.length <= 3 &&
      form.selectedBooks.every((book) => /^\d{13}$/.test(book.item.isbn13 ?? ""));

    if (!selectedBooksValid) {
      return {
        canSubmit: false,
        targetStep: 4,
        message: "선택한 도서 정보를 확인해주세요.",
      };
    }

    if (form.readingPurpose.trim().length > 300) {
      return {
        canSubmit: false,
        targetStep: 5,
        message: "독서 목적은 300자 이하로 입력해 주세요.",
      };
    }

    return {
      canSubmit: true,
      targetStep: null,
      message: "",
    };
  };

  const completedSteps = useMemo(() => {
    const result: number[] = [];

    if (!getResidentProfileValidationMessage(form.birthDate, form.genderCode)) {
      result.push(1);
    }
    if (form.readerTypeOptionId !== null) {
      result.push(2);
    }
    if (form.bookCategoryOptionIds.length > 0) {
      result.push(3);
    }
    if (form.selectedBooks.length > 0) {
      result.push(4);
    }
    if (form.readingPurpose.trim().length > 0) {
      result.push(5);
    }
    if (form.selectedLibrary) {
      result.push(6);
    }

    return result;
  }, [form]);

  const goNext = () => {
    setStep((prev) => Math.min(prev + 1, TOTAL_ONBOARDING_STEP));
  };

  const goPrev = () => {
    setStep((prev) => Math.max(prev - 1, 0));
  };

  const goToStep = (targetStep: number) => {
    setStep(Math.max(1, Math.min(targetStep, TOTAL_ONBOARDING_STEP)));
  };

  const buildSubmitPayload = (): CompleteOnboardingRequest => {
    if (!form.readerTypeOptionId) {
      throw new Error("독자 유형을 선택해주세요.");
    }

    const selectedBooks = form.selectedBooks
      .filter((selected) => /^\d{13}$/.test(selected.item.isbn13 ?? ""))
      .map((selected) => toSelectedBookRequest(selected.item));

    return {
      residentNumberFront: form.birthDate,
      residentGenderDigit: form.genderCode,
      readerTypeOptionId: form.readerTypeOptionId,
      bookCategoryOptionIds: form.bookCategoryOptionIds,
      readingPurpose: form.readingPurpose.trim() || undefined,
      preferredRadiusKm: 5,
      preferredLibraryCode: form.selectedLibrary?.libCode,
      selectedBooks: selectedBooks.length > 0 ? selectedBooks : undefined,
    };
  };

  const completeOnboarding = async () => {
    if (submitting) {
      return;
    }

    const validation = getValidationResult();

    if (!validation.canSubmit && validation.targetStep !== null) {
      setSubmitError("");
      setStepValidation({
        step: validation.targetStep,
        message: validation.message,
      });
      setStep(validation.targetStep);
      return;
    }

    setStepValidation(null);
    setSubmitting(true);
    setSubmitError("");

    try {
      const response = await requestCompleteOnboarding(buildSubmitPayload());
      setIssuedCharacter(response.character ?? null);

      // 수정 포인트: 온보딩 완료 직후 자동 이동하지 않고, 발급된 북케몬을 먼저 보여줍니다.
      // 사용자 세션 정보는 메인 이동 전 최신 상태로 맞춰둡니다.
      const me = await getMe();
      saveUser(me);
    } catch (error) {
      setSubmitError(
        error instanceof Error ? error.message : "온보딩 저장에 실패했습니다."
      );
    } finally {
      setSubmitting(false);
    }
  };

  const requestSkipOnboarding = () => {
    // 수정 포인트: 중간 단계에서 바로 이탈하지 않고 확인 모달을 거쳐 입력값 유실을 명확히 안내합니다.
    setSubmitError("");
    setStepValidation(null);
    setSkipConfirmOpen(true);
  };

  const skipOnboarding = async () => {
    if (skipping) return;

    setSkipping(true);
    setSubmitError("");
    setStepValidation(null);

    try {
      const me = await requestSkipOnboardingApi();
      saveUser(me);
      setSkipConfirmOpen(false);
      navigate("/", { replace: true });
    } catch (error) {
      setSubmitError(
        error instanceof Error ? error.message : "온보딩 건너뛰기에 실패했습니다."
      );
    } finally {
      setSkipping(false);
    }
  };

  const stepProps = {
    form,
    updateForm,
    goNext,
    goPrev,
    goToStep,
    completeOnboarding,
    skipOnboarding,
    requestSkipOnboarding,
    submitting,
    skipping,
    canSubmit: getValidationResult().canSubmit,
    requiredMessage:
      stepValidation?.step === step ? stepValidation.message : submitError,
    readerTypeOptions,
    bookCategoryOptions,
  };

  const renderStep = () => {
    if (optionsLoading) {
      return (
        <div>
          <h1 className="text-2xl font-bold">온보딩 선택지를 불러오는 중입니다</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            서버에 등록된 독자 유형과 도서 카테고리를 확인하고 있습니다.
          </p>
        </div>
      );
    }

    if (optionsError) {
      return (
        <div>
          <h1 className="text-2xl font-bold">온보딩 선택지를 불러오지 못했습니다</h1>
          <p className="mt-2 text-sm text-destructive">{optionsError}</p>
          <button
            type="button"
            className="mt-6 rounded-md border px-4 py-2 text-sm"
            onClick={() => window.location.reload()}
          >
            다시 시도
          </button>
        </div>
      );
    }

    switch (step) {
      case 0:
        return <Step0Intro {...stepProps} />;
      case 1:
        return <Step1Profile {...stepProps} />;
      case 2:
        return <Step2ReaderType {...stepProps} />;
      case 3:
        return <Step3Category {...stepProps} />;
      case 4:
        return <Step4BookAuthor {...stepProps} />;
      case 5:
        return <Step5Purpose {...stepProps} />;
      case 6:
        return <Step6Library {...stepProps} />;
      default:
        return <Step0Intro {...stepProps} />;
    }
  };

  if (issuedCharacter !== undefined) {
    return (
      <OnboardingLayout
        step={0}
        completedSteps={completedSteps}
        onStepClick={goToStep}
      >
        <OnboardingReward
          character={issuedCharacter}
          onGoHome={() => navigate("/", { replace: true })}
        />
      </OnboardingLayout>
    );
  }

  return (
    <>
      <OnboardingLayout
        step={step}
        completedSteps={completedSteps}
        onStepClick={goToStep}
      >
        {renderStep()}
      </OnboardingLayout>

      {skipConfirmOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 px-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="onboarding-skip-title"
            className="w-full max-w-md rounded-3xl border bg-background p-6 shadow-2xl"
          >
            <p className="text-xs font-semibold uppercase tracking-wide text-primary">
              Onboarding
            </p>
            <h2 id="onboarding-skip-title" className="mt-2 text-xl font-bold">
              온보딩을 나중에 진행할까요?
            </h2>
            <p className="mt-3 text-sm leading-6 text-muted-foreground">
              지금 입력한 내용은 저장되지 않습니다. 나중에 마이페이지에서 다시 온보딩을 진행할 수 있습니다.
            </p>
            {submitError && (
              <p className="mt-4 rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {submitError}
              </p>
            )}
            <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <button
                type="button"
                className="rounded-md border px-4 py-2 text-sm font-medium transition hover:bg-muted disabled:cursor-not-allowed disabled:opacity-60"
                onClick={() => setSkipConfirmOpen(false)}
                disabled={skipping}
              >
                계속 작성
              </button>
              <button
                type="button"
                className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-60"
                onClick={() => void skipOnboarding()}
                disabled={skipping}
              >
                {skipping ? "이동 중..." : "나중에 하기"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
