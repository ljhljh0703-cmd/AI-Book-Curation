import { Button } from "../../ui/button";
import type { CompleteOnboardingResponse } from "../../../types/onboarding";
import { toCacheBustedImageUrl } from "../../../utils/imageUrl";
import { onboardingPersonalizationGuides } from "../constants/onboardingOptions";
import PersonalizationHint from "../shared/PersonalizationHint";

type OnboardingRewardProps = {
  character: CompleteOnboardingResponse["character"] | null;
  onGoHome: () => void;
};

export default function OnboardingReward({
  character,
  onGoHome,
}: OnboardingRewardProps) {
  const characterName = character?.characterNickname?.trim() || "북케몬";
  const characterImageUrl = toCacheBustedImageUrl(character?.currentImageUrl);

  return (
    <div className="text-center">
      <div className="mx-auto inline-flex rounded-full bg-primary/10 px-4 py-2 text-sm font-semibold text-primary">
        온보딩 완료
      </div>

      <h1 className="mt-5 text-3xl font-bold tracking-tight md:text-4xl">
        짜잔! 새로운 북케몬이 찾아왔어요
      </h1>

      <p className="mt-3 text-sm text-muted-foreground md:text-base">
        선택한 독자 유형에 맞춰 <span className="font-semibold text-foreground">{characterName}</span>이 지급되었습니다.
      </p>

      <div className="mx-auto mt-8 max-w-sm rounded-3xl border bg-background p-6 shadow-sm">
        <div className="mx-auto flex h-48 w-48 items-center justify-center rounded-full bg-muted/60 p-5">
          {characterImageUrl ? (
            <img
              src={characterImageUrl}
              alt={`${characterName} 이미지`}
              className="h-full w-full object-contain drop-shadow-sm"
            />
          ) : (
            <div className="flex h-full w-full items-center justify-center rounded-full border border-dashed text-sm text-muted-foreground">
              이미지 준비 중
            </div>
          )}
        </div>

        <div className="mt-5 rounded-2xl bg-muted/60 px-4 py-3">
          <p className="text-xs text-muted-foreground">지급된 캐릭터</p>
          <p className="mt-1 text-xl font-bold">{characterName}</p>
        </div>
      </div>

      <PersonalizationHint
        {...onboardingPersonalizationGuides.reward}
        className="mx-auto mt-6 max-w-xl"
      />

      <p className="mx-auto mt-6 max-w-md text-sm leading-6 text-muted-foreground">
        마이페이지에서 캐릭터 이름을 변경하고 성장 상태를 확인할 수 있습니다.
      </p>

      <Button type="button" className="mt-8 px-8" onClick={onGoHome}>
        메인으로 이동
      </Button>
    </div>
  );
}
