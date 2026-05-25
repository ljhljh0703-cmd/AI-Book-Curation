import { onboardingStepItems } from "../constants/onboardingOptions";

type OnboardingStepNavProps = {
  currentStep: number;
  completedSteps: number[];
  onStepClick: (step: number) => void;
};

export default function OnboardingStepNav({
  currentStep,
  completedSteps,
  onStepClick,
}: OnboardingStepNavProps) {
  return (
    <nav aria-label="온보딩 단계" className="space-y-3">
      <div className="hidden space-y-2 md:block">
        {onboardingStepItems.map((item) => {
          const active = currentStep === item.step;
          const completed = completedSteps.includes(item.step);

          return (
            <button
              key={item.step}
              type="button"
              onClick={() => onStepClick(item.step)}
              className={[
                "w-full rounded-xl border p-4 text-left transition",
                active
                  ? "border-primary bg-primary/10 shadow-sm"
                  : completed
                    ? "border-primary/30 bg-primary/5 hover:border-primary/50"
                    : "border-border bg-background hover:border-primary/50",
              ].join(" ")}
            >
              <div className="flex items-center justify-between gap-3">
                <span className="text-sm font-semibold">
                  {item.step}. {item.label}
                </span>
                <span
                  className={[
                    "rounded-full px-2 py-0.5 text-[11px]",
                    item.required
                      ? "bg-destructive/10 text-destructive"
                      : "bg-muted text-muted-foreground",
                  ].join(" ")}
                >
                  {item.required ? "필수" : "선택"}
                </span>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                {item.description}
              </p>
            </button>
          );
        })}
      </div>

      <div className="md:hidden">
        <div className="mx-auto flex w-fit items-center gap-2 rounded-full border bg-background/90 px-3 py-2 shadow-sm backdrop-blur">
          {onboardingStepItems.map((item) => {
            const active = currentStep === item.step;
            const completed = completedSteps.includes(item.step);

            return (
              <button
                key={item.step}
                type="button"
                onClick={() => onStepClick(item.step)}
                aria-label={`${item.label} 단계로 이동`}
                className={[
                  "flex h-9 min-w-9 items-center justify-center rounded-full text-xs font-semibold transition",
                  active
                    ? "scale-110 bg-primary text-primary-foreground shadow-sm"
                    : completed
                      ? "bg-primary/10 text-primary hover:bg-primary/15"
                      : "bg-muted text-muted-foreground hover:bg-muted/80",
                ].join(" ")}
              >
                <span>{item.step}</span>
                <span
                  className={[
                    "ml-1 h-1.5 w-1.5 rounded-full",
                    item.required ? "bg-destructive" : "bg-muted-foreground/40",
                  ].join(" ")}
                />
              </button>
            );
          })}
        </div>
      </div>
    </nav>
  );
}
