import type { OnboardingStepProps } from "../../../types/onboarding";
import { onboardingPersonalizationGuides } from "../constants/onboardingOptions";
import PersonalizationHint from "../shared/PersonalizationHint";
import StepFooter from "../shared/StepFooter";

const MAX_READING_PURPOSE_LENGTH = 300;

export default function Step5Purpose({
  form,
  updateForm,
  goNext,
  goPrev,
  requestSkipOnboarding,
  skipping,
  requiredMessage,
}: OnboardingStepProps) {
  const purposeLength = form.readingPurpose.length;

  return (
    <div>
      <div className="flex items-center gap-2">
        <h1 className="text-2xl font-bold">책을 읽는 목적은 무엇인가요?</h1>
        <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
          선택
        </span>
      </div>

      <p className="mt-2 text-sm text-muted-foreground">
        선택 항목입니다. 카드 선택 대신 자유롭게 문장으로 입력할 수 있습니다.
      </p>

      <PersonalizationHint
        {...onboardingPersonalizationGuides.purpose}
        className="mt-4"
      />

      {requiredMessage && (
        <p className="mt-5 rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {requiredMessage}
        </p>
      )}

      <div className="mt-6 space-y-2">
        <textarea
          value={form.readingPurpose}
          maxLength={MAX_READING_PURPOSE_LENGTH}
          placeholder="예: 업무 역량을 키우고 싶어요. 새로운 취미를 찾고 싶어요."
          onChange={(event) => updateForm("readingPurpose", event.target.value)}
          className="min-h-32 w-full resize-y rounded-xl border border-input bg-background px-3 py-3 text-sm shadow-sm outline-none transition placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
        />

        <div className="flex items-start justify-between gap-3 text-xs text-muted-foreground">
          <p className="leading-5">
            구체적으로 적을수록 공부용·업무용·취미용처럼 목적에 맞는 추천 이유를 만들기 쉬워집니다.
          </p>
          <p className="shrink-0">{purposeLength} / {MAX_READING_PURPOSE_LENGTH}</p>
        </div>
      </div>

      <StepFooter
        onPrev={goPrev}
        onNext={goNext}
        onCancel={requestSkipOnboarding}
        cancelLoading={skipping}
      />
    </div>
  );
}
