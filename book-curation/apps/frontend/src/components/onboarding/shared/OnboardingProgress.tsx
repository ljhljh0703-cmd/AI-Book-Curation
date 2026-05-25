type OnboardingProgressProps = {
  completedRequiredCount: number;
  totalRequiredCount: number;
};

export default function OnboardingProgress({
  completedRequiredCount,
  totalRequiredCount,
}: OnboardingProgressProps) {
  const safeRequiredCount = Math.max(totalRequiredCount, 1);
  const normalizedCompletedCount = Math.min(
    Math.max(completedRequiredCount, 0),
    safeRequiredCount
  );
  const progress = Math.round((normalizedCompletedCount / safeRequiredCount) * 100);

  return (
    <div className="w-full">
      <div className="mb-3 flex items-center justify-between text-sm text-muted-foreground">
        <span>필수 입력 진행률</span>
        <span>{normalizedCompletedCount} / {safeRequiredCount}</span>
      </div>
      <div className="h-2 w-full rounded-full bg-muted">
        <div
          className="h-2 rounded-full bg-primary transition-all duration-300"
          style={{ width: `${progress}%` }}
        />
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        필수 3개 항목을 입력하면 온보딩 완료가 가능합니다. 선택 항목은 진행률에 반영하지 않습니다.
      </p>
    </div>
  );
}
