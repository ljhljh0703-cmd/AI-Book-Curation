/**
 * 사용자 추가 프로필 수정 폼 컴포넌트.
 * 현재 마이페이지의 신규 책갈피형 UI가 주 사용 화면이지만,
 * 구버전 폼이 import되더라도 readingLevel/KDC categoryCode 의존성이 남지 않도록 정리한다.
 */

import type { ChangeEvent } from "react";
import { useState } from "react";
import { Save, X } from "lucide-react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  updateMyProfile,
  type UpdateUserProfileRequest,
  type UserProfileResponse,
} from "../../api/userProfileApi";

type Props = {
  profile: UserProfileResponse;
  onCancel: () => void;
  onSaveSuccess: (updatedProfile: UserProfileResponse) => void;
};

type UpdateUserProfileForm = {
  readingPurpose: string;
  preferredRadiusKm: string;
  categoryCodesText: string;
  keywordsText: string;
};

const getErrorMessage = (error: unknown) => {
  if (error instanceof Error && error.message) return error.message;
  return "추가 프로필 정보를 저장하지 못했습니다.";
};

const parseCommaSeparatedValues = (value: string) => {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
};

const createFormFromProfile = (
  profile: UserProfileResponse
): UpdateUserProfileForm => ({
  readingPurpose: profile.readingPurpose ?? "",
  preferredRadiusKm:
    profile.preferredRadiusKm == null ? "" : String(profile.preferredRadiusKm),
  // 수정 포인트: categoryCodes는 더 이상 KDC 코드가 아니라 onboarding_options.optionKey 목록입니다.
  categoryCodesText: profile.categoryCodes.join(", "),
  keywordsText: profile.keywords.join(", "),
});

const UserProfileEditForm = ({
  profile,
  onCancel,
  onSaveSuccess,
}: Props) => {
  const [form, setForm] = useState<UpdateUserProfileForm>(
    createFormFromProfile(profile)
  );
  const [saveLoading, setSaveLoading] = useState(false);
  const [saveErrorMessage, setSaveErrorMessage] = useState("");
  const [saveSuccessMessage, setSaveSuccessMessage] = useState("");

  const handleInputChange =
    (key: keyof UpdateUserProfileForm) =>
    (e: ChangeEvent<HTMLInputElement>) => {
      const value = e.target.value;
      setForm((prev) => ({ ...prev, [key]: value }));
    };

  const validateForm = () => {
    if (form.readingPurpose.trim().length > 300) {
      return "독서 목적은 300자 이하로 입력해 주세요.";
    }

    if (form.preferredRadiusKm.trim()) {
      const radius = Number(form.preferredRadiusKm);

      if (Number.isNaN(radius)) {
        return "선호 반경은 숫자로 입력해 주세요.";
      }

      if (radius < 1 || radius > 10) {
        return "선호 반경은 1km 이상 10km 이하로 입력해 주세요.";
      }
    }

    if (parseCommaSeparatedValues(form.categoryCodesText).length > 3) {
      return "희망 장르는 최대 3개까지 입력할 수 있습니다.";
    }

    return null;
  };

  const buildPayload = (): UpdateUserProfileRequest => {
    return {
      // 수정 포인트: readingLevel은 DB/API에서 제거되었으므로 전송하지 않습니다.
      readingPurpose: form.readingPurpose.trim() || null,
      preferredRadiusKm: form.preferredRadiusKm.trim()
        ? Number(form.preferredRadiusKm)
        : undefined,
      // 수정 포인트: 위치/지역명은 저장하지 않는 정책이므로 구버전 폼에서도 명시적으로 비웁니다.
      regionName: null,
      latitude: null,
      longitude: null,
      // 수정 포인트: 희망 장르는 KDC 코드가 아니라 관리자 온보딩 옵션의 optionKey 값을 사용합니다.
      categoryCodes: parseCommaSeparatedValues(form.categoryCodesText),
      keywords: parseCommaSeparatedValues(form.keywordsText),
    };
  };

  const handleSaveProfile = async () => {
    setSaveErrorMessage("");
    setSaveSuccessMessage("");

    const validationMessage = validateForm();
    if (validationMessage) {
      setSaveErrorMessage(validationMessage);
      return;
    }

    setSaveLoading(true);

    try {
      const updatedProfile = await updateMyProfile(buildPayload());
      setSaveSuccessMessage("추가 프로필 정보가 저장되었습니다.");
      onSaveSuccess(updatedProfile);
    } catch (error) {
      setSaveErrorMessage(getErrorMessage(error));
    } finally {
      setSaveLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {saveErrorMessage && (
        <Alert variant="destructive">{saveErrorMessage}</Alert>
      )}

      {saveSuccessMessage && <Alert>{saveSuccessMessage}</Alert>}

      <div className="grid gap-5">
        <div className="grid gap-2">
          <Label htmlFor="readingPurpose">독서 목적</Label>
          <Input
            id="readingPurpose"
            placeholder="예: 취미, 교양 확장, 자기계발"
            value={form.readingPurpose}
            onChange={handleInputChange("readingPurpose")}
            maxLength={300}
          />
          <p className="text-xs text-muted-foreground">
            최대 300자까지 입력할 수 있습니다.
          </p>
        </div>

        <div className="grid gap-2">
          <Label htmlFor="preferredRadiusKm">선호 반경 (km)</Label>
          <Input
            id="preferredRadiusKm"
            type="number"
            min="1"
            max="10"
            step="1"
            placeholder="예: 5"
            value={form.preferredRadiusKm}
            onChange={handleInputChange("preferredRadiusKm")}
          />
          <p className="text-xs text-muted-foreground">
            1km 이상 10km 이하 값을 입력해 주세요.
          </p>
        </div>

        <div className="grid gap-2">
          <Label htmlFor="categoryCodes">희망 장르 optionKey</Label>
          <Input
            id="categoryCodes"
            placeholder="예: NOVEL, COMPUTER_IT, HEALTH_HOBBY"
            value={form.categoryCodesText}
            onChange={handleInputChange("categoryCodesText")}
          />
          <p className="text-xs text-muted-foreground">
            KDC 코드가 아니라 관리자 온보딩 옵션의 optionKey를 쉼표로 구분해 입력합니다.
          </p>
        </div>

        <div className="grid gap-2">
          <Label htmlFor="keywords">관심 키워드</Label>
          <Input
            id="keywords"
            placeholder="예: 자기계발, AI, 입문서"
            value={form.keywordsText}
            onChange={handleInputChange("keywordsText")}
          />
          <p className="text-xs text-muted-foreground">
            여러 개는 쉼표로 구분해서 입력해 주세요.
          </p>
        </div>
      </div>

      <div className="flex flex-col gap-2 sm:flex-row">
        <Button
          type="button"
          variant="secondary"
          onClick={onCancel}
          disabled={saveLoading}
        >
          <X className="size-4" />
          취소
        </Button>

        <Button
          type="button"
          onClick={handleSaveProfile}
          disabled={saveLoading}
        >
          <Save className="size-4" />
          {saveLoading ? "저장 중..." : "저장"}
        </Button>
      </div>
    </div>
  );
};

export default UserProfileEditForm;