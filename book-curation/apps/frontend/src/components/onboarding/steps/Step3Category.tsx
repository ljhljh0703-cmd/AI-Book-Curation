import type { OnboardingStepProps } from "../../../types/onboarding";
import { onboardingPersonalizationGuides } from "../constants/onboardingOptions";
import PersonalizationHint from "../shared/PersonalizationHint";
import StepFooter from "../shared/StepFooter";

export default function Step3Category({
  form,
  updateForm,
  goNext,
  goPrev,
  requestSkipOnboarding,
  skipping,
  bookCategoryOptions,
  requiredMessage,
}: OnboardingStepProps) {
  const toggleCategory = (optionId: number) => {
    if (form.bookCategoryOptionIds.includes(optionId)) {
      updateForm(
        "bookCategoryOptionIds",
        form.bookCategoryOptionIds.filter((item) => item !== optionId)
      );
      return;
    }

    if (form.bookCategoryOptionIds.length >= 3) return;

    updateForm("bookCategoryOptionIds", [
      ...form.bookCategoryOptionIds,
      optionId,
    ]);
  };

  return (
    <div>
      <div className="flex items-center gap-2">
        <h1 className="text-2xl font-bold">어떤 책을 만나고 싶으신가요?</h1>
        <span className="rounded-full bg-destructive/10 px-2 py-0.5 text-xs text-destructive">
          필수
        </span>
      </div>

      <p className="mt-2 text-sm text-muted-foreground">
        도서 카테고리 중 최소 1개, 최대 3개까지 선택해주세요.
      </p>

      <PersonalizationHint
        {...onboardingPersonalizationGuides.category}
        className="mt-4"
      />

      {requiredMessage && (
        <p className="mt-5 rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {requiredMessage}
        </p>
      )}

      <div className="mt-6 grid max-h-[420px] gap-3 overflow-y-auto pr-1 sm:grid-cols-2 lg:grid-cols-3">
        {bookCategoryOptions.map((category) => {
          const selected = form.bookCategoryOptionIds.includes(category.id);
          const disabled = !selected && form.bookCategoryOptionIds.length >= 3;

          return (
            <button
              key={category.id}
              type="button"
              disabled={disabled}
              onClick={() => toggleCategory(category.id)}
              className={[
                "rounded-2xl border p-4 text-left transition disabled:cursor-not-allowed disabled:opacity-45",
                selected
                  ? "border-primary bg-primary/10 shadow-sm"
                  : "border-border bg-background hover:border-primary/60",
              ].join(" ")}
            >
              <div className="text-sm font-semibold">{category.label}</div>
              {category.description && (
                <p className="mt-2 line-clamp-3 text-xs leading-5 text-muted-foreground">
                  {category.description}
                </p>
              )}
            </button>
          );
        })}
      </div>

      <p className="mt-3 text-xs text-muted-foreground">
        현재 {form.bookCategoryOptionIds.length}개 선택됨
      </p>

      <StepFooter
        onPrev={goPrev}
        onNext={goNext}
        onCancel={requestSkipOnboarding}
        cancelLoading={skipping}
        disabled={form.bookCategoryOptionIds.length === 0}
        helperText={
          form.bookCategoryOptionIds.length === 0
            ? "도서 카테고리를 최소 1개 선택해주세요."
            : undefined
        }
      />
    </div>
  );
}
