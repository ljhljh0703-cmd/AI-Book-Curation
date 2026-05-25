import { Input } from "../../ui/input";
import type { OnboardingStepProps } from "../../../types/onboarding";
import StepFooter from "../shared/StepFooter";
import { getResidentProfileValidationMessage } from "../../../utils/onboardingValidation";
import { onboardingPersonalizationGuides } from "../constants/onboardingOptions";
import PersonalizationHint from "../shared/PersonalizationHint";

export default function Step1Profile({
  form,
  updateForm,
  goNext,
  requestSkipOnboarding,
  skipping,
  requiredMessage,
}: OnboardingStepProps) {
  const validationMessage = getResidentProfileValidationMessage(
    form.birthDate,
    form.genderCode
  );
  const isValid = !validationMessage;
  const showRealtimeMessage =
    (form.birthDate.length > 0 || form.genderCode.length > 0) && !isValid;

  return (
    <div>
      <div className="flex items-center gap-2">
        <h1 className="text-2xl font-bold">프로필 정보를 알려주세요</h1>
        <span className="rounded-full bg-destructive/10 px-2 py-0.5 text-xs text-destructive">
          필수
        </span>
      </div>

      <p className="mt-2 text-sm text-muted-foreground">
        생년월일 6자리와 주민등록번호 뒷자리 첫 숫자 1~4 중 하나를 입력해주세요.
      </p>

      <PersonalizationHint
        {...onboardingPersonalizationGuides.profile}
        className="mt-4"
      />

      {requiredMessage && (
        <p className="mt-5 rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {requiredMessage}
        </p>
      )}

      <div className="mt-6 grid gap-4 md:grid-cols-2">
        <div>
          <label className="text-sm font-medium" htmlFor="onboarding-birth-date">
            생년월일 6자리
          </label>
          <Input
            id="onboarding-birth-date"
            className="mt-2"
            value={form.birthDate}
            maxLength={6}
            inputMode="numeric"
            placeholder="생년월일 예: 980506"
            onChange={(event) =>
              updateForm("birthDate", event.target.value.replace(/\D/g, ""))
            }
          />
          <p className="mt-2 text-xs leading-5 text-muted-foreground">
            연령대에 맞는 난이도와 설명 톤을 조정하는 데 사용합니다.
          </p>
        </div>

        <div>
          <label className="text-sm font-medium" htmlFor="onboarding-gender-code">
            성별코드 첫 숫자
          </label>
          <Input
            id="onboarding-gender-code"
            className="mt-2"
            value={form.genderCode}
            maxLength={1}
            inputMode="numeric"
            placeholder="성별코드 예: 2"
            onChange={(event) =>
              updateForm("genderCode", event.target.value.replace(/\D/g, ""))
            }
          />
          <p className="mt-2 text-xs leading-5 text-muted-foreground">
            생년월일의 세기를 확인해 정확한 출생연도를 계산하는 데 사용합니다.
          </p>
        </div>
      </div>

      <StepFooter
        showPrev={false}
        onNext={goNext}
        onCancel={requestSkipOnboarding}
        cancelLoading={skipping}
        disabled={!isValid}
        helperText={showRealtimeMessage ? validationMessage : undefined}
      />
    </div>
  );
}
