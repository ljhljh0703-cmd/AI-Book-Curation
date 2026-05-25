import { Button } from "../../ui/button";

type StepFooterProps = {
  showPrev?: boolean;
  nextLabel?: string;
  cancelLabel?: string;
  onPrev?: () => void;
  onNext: () => void;
  onCancel?: () => void;
  disabled?: boolean;
  loading?: boolean;
  cancelLoading?: boolean;
  helperText?: string;
};

export default function StepFooter({
  showPrev = true,
  nextLabel = "다음",
  cancelLabel = "나중에 하기",
  onPrev,
  onNext,
  onCancel,
  disabled = false,
  loading = false,
  cancelLoading = false,
  helperText,
}: StepFooterProps) {
  const actionDisabled = loading || cancelLoading;

  return (
    <div className="mt-8 space-y-3">
      {helperText && (
        <p className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {helperText}
        </p>
      )}
      <div className="grid gap-2 sm:grid-cols-[1fr_auto_1fr] sm:items-center">
        <div className="order-1 sm:order-1 sm:justify-self-start">
          {showPrev ? (
            <Button
              type="button"
              variant="outline"
              onClick={onPrev}
              disabled={actionDisabled}
              className="w-full sm:w-auto"
            >
              이전
            </Button>
          ) : (
            <div className="hidden sm:block" />
          )}
        </div>

        {onCancel && (
          <div className="order-3 sm:order-2 sm:justify-self-center">
            <Button
              type="button"
              variant="secondary"
              onClick={onCancel}
              disabled={actionDisabled}
              className="w-full sm:w-auto"
            >
              {cancelLoading ? "이동 중..." : cancelLabel}
            </Button>
          </div>
        )}

        <div className="order-2 sm:order-3 sm:justify-self-end">
          <Button
            type="button"
            onClick={onNext}
            disabled={disabled || actionDisabled}
            className="w-full sm:w-auto"
          >
            {loading ? "처리 중..." : nextLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
