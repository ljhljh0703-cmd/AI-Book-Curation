import { Button } from "../../ui/button";
import type { OnboardingStepProps } from "../../../types/onboarding";
import { onboardingPersonalizationGuides } from "../constants/onboardingOptions";
import PersonalizationHint from "../shared/PersonalizationHint";

export default function Step0Intro({
  goNext,
  skipOnboarding,
  skipping,
}: OnboardingStepProps) {
  return (
    <div className="text-center">
      <p className="text-sm font-medium text-primary">Bookemon Onboarding</p>

      <h1 className="mt-3 text-3xl font-bold tracking-tight">
        당신에 대해 더 알고 싶어요
      </h1>

      <p className="mx-auto mt-4 max-w-2xl text-sm leading-6 text-muted-foreground sm:text-base sm:leading-7">
        <span className="block">몇 가지 질문에 답하면 취향에 맞는 추천을 받을 수 있습니다.</span>
        <span className="block">나중에 시작해도 기본 북케몬은 유지됩니다.</span>
      </p>

      <PersonalizationHint
        {...onboardingPersonalizationGuides.intro}
        className="mx-auto mt-6 max-w-2xl"
      />

      <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row">
        <Button type="button" onClick={goNext} className="min-w-32">
          시작하기
        </Button>
        <Button
          type="button"
          variant="secondary"
          onClick={skipOnboarding}
          disabled={skipping}
          className="min-w-32"
        >
          {skipping ? "이동 중..." : "괜찮아요"}
        </Button>
      </div>
    </div>
  );
}
