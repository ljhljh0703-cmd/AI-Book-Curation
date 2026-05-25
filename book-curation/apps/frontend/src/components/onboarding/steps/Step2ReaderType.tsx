import type { OnboardingStepProps } from "../../../types/onboarding";
import { onboardingPersonalizationGuides } from "../constants/onboardingOptions";
import PersonalizationHint from "../shared/PersonalizationHint";
import StepFooter from "../shared/StepFooter";

export default function Step2ReaderType({
  form,
  updateForm,
  goNext,
  goPrev,
  requestSkipOnboarding,
  skipping,
  readerTypeOptions,
  requiredMessage,
}: OnboardingStepProps) {
  return (
    <div>
      <div className="flex items-center gap-2">
        <h1 className="text-2xl font-bold">당신은 어떤 독자인가요?</h1>
        <span className="rounded-full bg-destructive/10 px-2 py-0.5 text-xs text-destructive">
          필수
        </span>
      </div>

      <p className="mt-2 text-sm text-muted-foreground">
        서버에서 불러온 독자 유형 중 가장 가까운 유형을 하나 선택해주세요.
      </p>

      <PersonalizationHint
        {...onboardingPersonalizationGuides.readerType}
        className="mt-4"
      />

      {requiredMessage && (
        <p className="mt-5 rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {requiredMessage}
        </p>
      )}

      <div className="mt-6 grid gap-3 md:grid-cols-2">
        {readerTypeOptions.map((item) => {
          const selected = form.readerTypeOptionId === item.id;

          return (
            <button
              key={item.id}
              type="button"
              onClick={() => updateForm("readerTypeOptionId", item.id)}
              className={[
                "rounded-2xl border p-4 text-left transition",
                selected
                  ? "border-primary bg-primary/10 shadow-sm"
                  : "border-border bg-background hover:border-primary/60",
              ].join(" ")}
            >
              <div className="text-base font-semibold">{item.label}</div>

              {item.description && (
                <p className="mt-2 text-sm leading-5 text-muted-foreground">
                  {item.description}
                </p>
              )}
            </button>
          );
        })}
      </div>

      <StepFooter
        onPrev={goPrev}
        onNext={goNext}
        onCancel={requestSkipOnboarding}
        cancelLoading={skipping}
        disabled={!form.readerTypeOptionId}
        helperText={!form.readerTypeOptionId ? "독자 유형을 선택해주세요." : undefined}
      />
    </div>
  );
}
