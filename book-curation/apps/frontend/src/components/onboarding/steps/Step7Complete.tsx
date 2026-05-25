import BookemonEgg from "../shared/BookemonEgg";

type Step7CompleteProps = {
  characterImageUrl?: string | null;
  characterName?: string | null;
};

export default function Step7Complete({
  characterImageUrl,
  characterName,
}: Step7CompleteProps) {
  return (
    <div className="text-center">
      <div className="mx-auto mb-6 flex justify-center">
        <BookemonEgg imageUrl={characterImageUrl} />
      </div>

      <h1 className="text-2xl font-bold">북케몬을 획득했어요</h1>

      <p className="mx-auto mt-3 max-w-md text-sm leading-6 text-muted-foreground">
        온보딩 정보가 저장되었습니다. 이제 입력한 취향을 바탕으로 도서 추천을 시작할 수 있습니다.
      </p>

      {characterName && (
        <p className="mt-4 rounded-full bg-primary/10 px-4 py-2 text-sm text-primary">
          첫 캐릭터: {characterName}
        </p>
      )}
    </div>
  );
}
