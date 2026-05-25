/**
 * 온보딩 기반 독서 프로필을 책갈피 탭 방식으로 조회/수정하는 컴포넌트.
 * 위치 좌표/지역명은 저장하지 않고, 개인화 추천에 직접 활용할 정보만 관리한다.
 */

import { Ruler, Save, Tags, Target, UserRound, X, type LucideIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import {
  getOnboardingOptions,
  updateMyProfileCategories,
  updateMyProfileIdentity,
  updateMyProfilePreferredRadius,
  updateMyProfileReadingPurpose,
  type OnboardingOption,
  type UserProfileResponse,
} from "../../api/userProfileApi";

type Props = {
  profile: UserProfileResponse;
  onSaveSuccess: (updatedProfile: UserProfileResponse) => void;
};

type EditSection = "identity" | "bookCategory" | "purpose" | "radius";

type ProfileForm = {
  residentNumberFront: string;
  residentGenderDigit: string;
  bookCategoryCodes: string[];
  readingPurpose: string;
  preferredRadiusKm: string;
};

type ProfileTab = {
  key: EditSection;
  label: string;
  icon: LucideIcon;
};

const profileTabs: ProfileTab[] = [
  { key: "identity", label: "기본 정보", icon: UserRound },
  { key: "bookCategory", label: "희망 장르", icon: Tags },
  { key: "purpose", label: "독서 목적", icon: Target },
  { key: "radius", label: "선호 반경", icon: Ruler },
];

const RADIUS_OPTIONS = [
  ...Array.from({ length: 10 }, (_, index) => {
    const value = String(index + 1);
    return { value, label: value + " km" };
  }),
  { value: "50", label: "10~50 km" },
];

const formatRadiusLabel = (radiusKm?: number | null) => {
  if (radiusKm == null) return "5 km";
  return radiusKm > 10 ? "10~50 km" : String(radiusKm) + " km";
};

const getErrorMessage = (error: unknown) => {
  if (error instanceof Error && error.message) return error.message;
  return "독서 프로필을 저장하지 못했습니다.";
};

const toResidentFront = (birthDate?: string | null) => {
  if (!birthDate) return "";
  const compact = birthDate.replace(/-/g, "");
  return compact.length === 8 ? compact.slice(2) : "";
};

const createFormFromProfile = (profile: UserProfileResponse): ProfileForm => ({
  residentNumberFront: toResidentFront(profile.birthDate),
  residentGenderDigit: profile.residentGenderDigit ?? "",
  // 수정 포인트: 희망 장르는 KDC/대표 장르 ID가 아니라 onboarding_options.optionKey 목록만 사용합니다.
  bookCategoryCodes: profile.categoryCodes ?? [],
  readingPurpose: profile.readingPurpose ?? "",
  preferredRadiusKm: profile.preferredRadiusKm == null ? "5" : String(profile.preferredRadiusKm),
});

const UserProfileViewCard = ({ profile, onSaveSuccess }: Props) => {
  const [activeTab, setActiveTab] = useState<EditSection>("identity");
  const [form, setForm] = useState<ProfileForm>(() => createFormFromProfile(profile));
  const [bookCategoryOptions, setBookCategoryOptions] = useState<OnboardingOption[]>([]);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    setForm(createFormFromProfile(profile));
  }, [profile]);

  useEffect(() => {
    const loadOptions = async () => {
      try {
        // 수정 포인트: 독자 유형은 캐릭터 발급 기준이므로 마이페이지에서 노출/수정하지 않고, 희망 장르만 수정 대상으로 불러옵니다.
        const bookCategories = await getOnboardingOptions("BOOK_CATEGORY");
        setBookCategoryOptions(bookCategories);
      } catch {
        setBookCategoryOptions([]);
      }
    };

    void loadOptions();
  }, []);

  const saveCurrentSection = async (): Promise<UserProfileResponse> => {
    // 수정 포인트: 마이페이지 저장은 현재 탭에 해당하는 필드만 전송합니다.
    // 독서 목적 저장 중 희망 장르 delete/insert가 같이 실행되지 않도록 API를 분리합니다.
    if (activeTab === "identity") {
      return updateMyProfileIdentity({
        residentNumberFront: form.residentNumberFront.trim() || null,
        residentGenderDigit: form.residentGenderDigit.trim() || null,
      });
    }

    if (activeTab === "bookCategory") {
      return updateMyProfileCategories({
        categoryCodes: form.bookCategoryCodes,
      });
    }

    if (activeTab === "purpose") {
      return updateMyProfileReadingPurpose({
        readingPurpose: form.readingPurpose.trim() || null,
      });
    }

    return updateMyProfilePreferredRadius({
      preferredRadiusKm: form.preferredRadiusKm.trim() ? Number(form.preferredRadiusKm) : 5,
    });
  };

  const validate = () => {
    if (activeTab === "identity") {
      if (form.residentNumberFront.trim() && !/^\d{6}$/.test(form.residentNumberFront.trim())) {
        return "주민등록번호 앞자리는 6자리 숫자로 입력해 주세요.";
      }
      // 수정 포인트: DB 제약조건과 동일하게 주민등록번호 뒷자리 첫 숫자는 1~4만 허용합니다.
      // 5~8 같은 값은 서버까지 보내지 않고 마이페이지에서 먼저 안내합니다.
      if (form.residentGenderDigit.trim() && !/^[1-4]$/.test(form.residentGenderDigit.trim())) {
        return "주민등록번호 뒷자리 첫 숫자는 1~4 중 하나로 입력해 주세요.";
      }
    }

    if (activeTab === "bookCategory" && form.bookCategoryCodes.length > 3) {
      return "희망 장르는 최대 3개까지 선택할 수 있습니다.";
    }

    if (activeTab === "purpose" && form.readingPurpose.trim().length > 300) {
      return "독서 목적은 300자 이하로 입력해 주세요.";
    }

    if (activeTab === "radius" && form.preferredRadiusKm.trim()) {
      const radius = Number(form.preferredRadiusKm);
      if (Number.isNaN(radius) || !RADIUS_OPTIONS.some((option) => Number(option.value) === radius)) {
        return "선호 반경은 1~10km 또는 10~50km 중 하나로 선택해 주세요.";
      }
    }

    return null;
  };

  const handleSave = async () => {
    setMessage("");
    const validationMessage = validate();
    if (validationMessage) {
      setMessage(validationMessage);
      return;
    }

    setSaving(true);
    try {
      const updatedProfile = await saveCurrentSection();
      onSaveSuccess(updatedProfile);
      setMessage("저장했습니다.");
    } catch (error) {
      setMessage(getErrorMessage(error));
    } finally {
      setSaving(false);
    }
  };

  const resetCurrentForm = () => {
    setForm(createFormFromProfile(profile));
    setMessage("");
  };

  const selectedCategoryLabels = bookCategoryOptions
    .filter((option) => profile.categoryCodes.includes(option.optionKey))
    .map((option) => option.label);

  const displayedCategoryLabel =
    selectedCategoryLabels.length > 0 ? selectedCategoryLabels.join(", ") : "미입력";

  return (
    <div className="space-y-5">
      {message && (
        <Alert variant={message === "저장했습니다." ? "success" : "destructive"}>
          {message}
        </Alert>
      )}

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <SummaryCard
          title="기본 정보"
          value={profile.birthDate || "미입력"}
          helper="생년월일 기준"
          icon={UserRound}
        />
        <SummaryCard
          title="희망 장르"
          value={displayedCategoryLabel}
          helper="최대 3개까지 추천 후보에 반영"
          icon={Tags}
        />
        <SummaryCard
          title="독서 목적"
          value={profile.readingPurpose || "미입력"}
          helper="추천 의도와 설명에 반영"
          icon={Target}
        />
        <SummaryCard
          title="선호 반경"
          value={formatRadiusLabel(profile.preferredRadiusKm)}
          helper="도서관 검색 시 기본 반경"
          icon={Ruler}
        />
      </div>

      <div className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">
        <div className="flex gap-1 overflow-x-auto border-b bg-slate-50/80 px-3 pt-3">
          {profileTabs.map((tab) => {
            const Icon = tab.icon;
            const active = activeTab === tab.key;

            return (
              <button
                key={tab.key}
                type="button"
                onClick={() => {
                  setActiveTab(tab.key);
                  setMessage("");
                }}
                className={cn(
                  "flex shrink-0 items-center gap-2 rounded-t-2xl border border-b-0 px-4 py-3 text-sm font-semibold transition-all",
                  active
                    ? "border-primary/30 bg-white text-primary shadow-sm"
                    : "border-transparent text-slate-500 hover:bg-white/70 hover:text-slate-950"
                )}
              >
                <Icon className="size-4" />
                {tab.label}
              </button>
            );
          })}
        </div>

        <div className="p-5">
          {activeTab === "identity" && (
            <div className="grid gap-4 lg:grid-cols-2">
              <div className="grid gap-2">
                <Label htmlFor="residentNumberFront">주민등록번호 앞자리</Label>
                <Input
                  id="residentNumberFront"
                  value={form.residentNumberFront}
                  maxLength={6}
                  placeholder="YYMMDD"
                  onChange={(event) =>
                    setForm((prev) => ({
                      ...prev,
                      residentNumberFront: event.target.value.replace(/\D/g, ""),
                    }))
                  }
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="residentGenderDigit">주민등록번호 뒷자리 첫 숫자</Label>
                <Input
                  id="residentGenderDigit"
                  value={form.residentGenderDigit}
                  maxLength={1}
                  inputMode="numeric"
                  placeholder="예: 1, 2, 3, 4"
                  onChange={(event) =>
                    setForm((prev) => ({
                      ...prev,
                      residentGenderDigit: event.target.value.replace(/\D/g, ""),
                    }))
                  }
                />
                {/* 수정 포인트: 주민번호 전체가 아니라 출생연도 판별에 필요한 첫 숫자만 받는다는 점을 명확히 안내합니다. */}
                <p className="text-xs text-muted-foreground">
                  1900년대 출생자는 1 또는 2, 2000년대 출생자는 3 또는 4를 입력해 주세요.
                </p>
              </div>
            </div>
          )}

          {activeTab === "bookCategory" && (
            <MultiOptionGrid
              label="희망 장르"
              options={bookCategoryOptions}
              selectedValues={form.bookCategoryCodes}
              maxCount={3}
              onChange={(values) =>
                setForm((prev) => ({
                  ...prev,
                  bookCategoryCodes: values,
                }))
              }
            />
          )}

          {activeTab === "purpose" && (
            <div className="grid gap-2">
              <Label htmlFor="readingPurpose">독서 목적</Label>
              <Input
                id="readingPurpose"
                value={form.readingPurpose}
                maxLength={300}
                placeholder="예: 교양 확장, 자기계발, 취업 준비"
                onChange={(event) =>
                  setForm((prev) => ({
                    ...prev,
                    readingPurpose: event.target.value,
                  }))
                }
              />
              <p className="text-xs text-muted-foreground">최대 300자까지 입력할 수 있습니다.</p>
            </div>
          )}

          {activeTab === "radius" && (
            <div className="grid gap-2 sm:max-w-sm">
              <Label htmlFor="preferredRadiusKm">선호 반경</Label>
              <select
                id="preferredRadiusKm"
                value={form.preferredRadiusKm}
                onChange={(event) =>
                  setForm((prev) => ({
                    ...prev,
                    preferredRadiusKm: event.target.value,
                  }))
                }
                className="flex h-11 w-full rounded-2xl border border-input bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {RADIUS_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="mt-5 flex gap-2">
            <Button type="button" onClick={handleSave} disabled={saving}>
              <Save className="size-4" /> {saving ? "저장 중..." : "저장"}
            </Button>
            <Button type="button" variant="secondary" onClick={resetCurrentForm} disabled={saving}>
              <X className="size-4" /> 되돌리기
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};

const SummaryCard = ({
  title,
  value,
  helper,
  icon: Icon,
}: {
  title: string;
  value: string;
  helper: string;
  icon: LucideIcon;
}) => (
  <div className="rounded-3xl border border-slate-200/80 bg-gradient-to-br from-white to-slate-50 p-4 shadow-sm">
    <div className="flex items-start gap-3">
      <div className="flex size-11 shrink-0 items-center justify-center rounded-2xl bg-primary/10 text-primary ring-1 ring-primary/10">
        <Icon className="size-5" />
      </div>
      <div className="min-w-0">
        <p className="text-sm font-semibold text-slate-500">{title}</p>
        <p className="mt-1 truncate text-lg font-bold text-slate-950">{value}</p>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">{helper}</p>
      </div>
    </div>
  </div>
);

const MultiOptionGrid = ({
  label,
  options,
  selectedValues,
  maxCount,
  onChange,
}: {
  label: string;
  options: OnboardingOption[];
  selectedValues: string[];
  maxCount: number;
  onChange: (values: string[]) => void;
}) => {
  const toggle = (optionKey: string) => {
    if (selectedValues.includes(optionKey)) {
      onChange(selectedValues.filter((value) => value !== optionKey));
      return;
    }

    if (selectedValues.length >= maxCount) {
      return;
    }

    onChange([...selectedValues, optionKey]);
  };

  return (
    <div className="grid gap-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <Label>{label}</Label>
          <p className="mt-1 text-xs text-muted-foreground">
            최대 {maxCount}개까지 선택할 수 있습니다.
          </p>
        </div>
        <Button type="button" variant="ghost" size="sm" onClick={() => onChange([])}>
          선택 해제
        </Button>
      </div>

      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {options.map((option) => {
          const selected = selectedValues.includes(option.optionKey);
          const disabled = !selected && selectedValues.length >= maxCount;

          return (
            <button
              key={option.id}
              type="button"
              onClick={() => toggle(option.optionKey)}
              disabled={disabled}
              className={cn(
                "rounded-2xl border px-4 py-3 text-left text-sm font-semibold transition-all disabled:cursor-not-allowed disabled:opacity-45",
                selected
                  ? "border-primary bg-primary text-primary-foreground shadow-md shadow-primary/15"
                  : "border-slate-200 bg-white text-slate-700 hover:border-primary/40 hover:bg-primary/5"
              )}
            >
              {option.label}
              {option.description && (
                <span className="mt-1 block text-xs font-normal opacity-75">
                  {option.description}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {selectedValues.length >= maxCount && (
        <p className="text-xs text-primary">
          희망 장르는 {maxCount}개까지 선택 가능합니다. 다른 장르를 선택하려면 기존 선택을
          해제해 주세요.
        </p>
      )}

      {options.length === 0 && (
        <div className="rounded-2xl border border-dashed bg-slate-50 px-4 py-8 text-center text-sm text-muted-foreground">
          관리자 페이지에 등록된 항목이 없습니다.
        </div>
      )}
    </div>
  );
};

export default UserProfileViewCard;