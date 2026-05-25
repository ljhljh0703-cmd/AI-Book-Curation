import { Sparkles, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { CharacterLevelUpEvent } from "../../api/userProfileApi";
import { toCacheBustedImageUrl } from "../../utils/imageUrl";

type CharacterLevelUpModalProps = {
  event: CharacterLevelUpEvent;
  onClose: () => void;
};

const CharacterLevelUpModal = ({ event, onClose }: CharacterLevelUpModalProps) => {
  const characterName = event.characterNickname?.trim() || "북케몬";
  const imageUrl = toCacheBustedImageUrl(event.characterImageUrl, event.newLevel);
  const isMaxLevel = event.newLevel >= event.maxLevel;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/70 px-4 py-6 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="character-level-up-title"
    >
      <div className="relative w-full max-w-md overflow-hidden rounded-[2rem] border border-white/20 bg-white p-6 text-center shadow-2xl">
        <div className="pointer-events-none absolute -left-12 -top-12 size-36 rounded-full bg-violet-200/70 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-14 -right-12 size-40 rounded-full bg-sky-200/70 blur-3xl" />

        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="absolute right-4 top-4 z-10 rounded-full"
          onClick={onClose}
          aria-label="레벨업 알림 닫기"
        >
          <X className="size-4" />
        </Button>

        <div className="relative z-10">
          <div className="mx-auto inline-flex items-center gap-2 rounded-full bg-primary/10 px-4 py-2 text-sm font-semibold text-primary">
            <Sparkles className="size-4 animate-pulse" /> 레벨업 완료
          </div>

          <h2 id="character-level-up-title" className="mt-5 text-3xl font-bold tracking-tight text-slate-950">
            짜잔! {characterName} 성장했어요
          </h2>

          <p className="mt-3 text-sm leading-6 text-muted-foreground">
            {event.previousLevel === 1 && event.newLevel === 2
              ? "첫 리뷰를 완료해서 Lv.2로 성장했습니다."
              : `Lv.${event.previousLevel}에서 Lv.${event.newLevel}로 성장했습니다.`}
          </p>

          <div className="mx-auto mt-7 max-w-xs rounded-3xl border bg-slate-50 p-5 shadow-sm">
            <div className="mx-auto flex h-44 w-44 items-center justify-center rounded-full bg-white p-5 shadow-inner">
              {imageUrl ? (
                <img
                  src={imageUrl}
                  alt={`${characterName} 레벨업 이미지`}
                  className="h-full w-full object-contain drop-shadow-sm"
                />
              ) : (
                <div className="flex h-full w-full items-center justify-center rounded-full border border-dashed text-sm text-muted-foreground">
                  이미지 준비 중
                </div>
              )}
            </div>

            <div className="mt-5 rounded-2xl bg-white px-4 py-3">
              <p className="text-xs text-muted-foreground">현재 성장 단계</p>
              <p className="mt-1 text-xl font-bold text-slate-950">
                Lv.{event.newLevel}{isMaxLevel ? " · 최대 레벨" : ""}
              </p>
            </div>
          </div>

          <p className="mx-auto mt-5 max-w-sm text-sm leading-6 text-muted-foreground">
            {event.message}
          </p>

          <Button type="button" className="mt-7 rounded-full px-8" onClick={onClose}>
            확인
          </Button>
        </div>
      </div>
    </div>
  );
};

export default CharacterLevelUpModal;
