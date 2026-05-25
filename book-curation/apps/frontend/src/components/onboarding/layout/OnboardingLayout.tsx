import { Card, CardContent } from "../../ui/card";
import { onboardingStepItems } from "../constants/onboardingOptions";
import OnboardingProgress from "../shared/OnboardingProgress";
import OnboardingStepNav from "../shared/OnboardingStepNav";

type OnboardingLayoutProps = {
  step: number;
  completedSteps: number[];
  onStepClick: (step: number) => void;
  children: React.ReactNode;
};

export default function OnboardingLayout({
  step,
  completedSteps,
  onStepClick,
  children,
}: OnboardingLayoutProps) {
  const isIntroStep = step === 0;
  const requiredSteps = onboardingStepItems.filter((item) => item.required);
  const completedRequiredCount = requiredSteps.filter((item) =>
    completedSteps.includes(item.step)
  ).length;

  return (
    <main className="min-h-screen bg-muted/30 text-foreground">
      <div className="mx-auto flex min-h-screen w-full max-w-6xl flex-col px-4 py-6 md:px-6 md:py-8">
        {!isIntroStep && (
          <Card className="mb-5 border-border/80 bg-card/95 shadow-sm">
            <CardContent className="p-5">
              <OnboardingProgress
                completedRequiredCount={completedRequiredCount}
                totalRequiredCount={requiredSteps.length}
              />
            </CardContent>
          </Card>
        )}

        {isIntroStep ? (
          <section className="flex flex-1 items-center justify-center">
            <Card className="w-full max-w-2xl border-border/80 bg-card shadow-sm">
              <CardContent className="p-6 md:p-10">{children}</CardContent>
            </Card>
          </section>
        ) : (
          <div className="grid flex-1 gap-5 md:grid-cols-[280px_1fr]">
            <Card className="h-fit border-border/80 bg-card/95 shadow-sm">
              <CardContent className="p-4">
                <OnboardingStepNav
                  currentStep={step}
                  completedSteps={completedSteps}
                  onStepClick={onStepClick}
                />
              </CardContent>
            </Card>

            <section className="flex items-start justify-center">
              <Card className="w-full border-border/80 bg-card shadow-sm">
                <CardContent className="p-6 md:p-8">{children}</CardContent>
              </Card>
            </section>
          </div>
        )}
      </div>
    </main>
  );
}
