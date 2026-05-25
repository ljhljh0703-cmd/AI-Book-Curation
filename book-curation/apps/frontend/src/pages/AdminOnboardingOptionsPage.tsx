import {
  CheckCircle2,
  Edit3,
  GripVertical,
  Plus,
  RefreshCw,
  Save,
  Trash2,
  X,
  XCircle,
} from "lucide-react";
import { useEffect, useMemo, useState, type DragEvent, type FormEvent } from "react";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import AdminLayout from "../components/admin/AdminLayout";
import { getMe } from "../api/authApi";
import {
  createOnboardingOption,
  deleteOnboardingOption,
  getOnboardingOptions,
  reorderOnboardingOptions,
  updateOnboardingOption,
} from "../api/adminOnboardingApi";
import { getAdminCharacters } from "../api/adminCharacterApi";
import type { MeResponse } from "../types/auth";
import type {
  OnboardingOption,
  OnboardingOptionGroup,
  OnboardingOptionRequest,
} from "../types/onboardingAdmin";
import type { AdminCharacter } from "../types/adminCharacter";
import { saveUser } from "../utils/storage";

const GROUP_LABELS: Record<OnboardingOptionGroup, string> = {
  READER_TYPE: "독자 유형 카드",
  BOOK_CATEGORY: "희망 도서 카테고리",
};

const GROUP_DESCRIPTIONS: Record<OnboardingOptionGroup, string> = {
  READER_TYPE: "온보딩의 ‘당신은 어떤 독자인가요?’ 단계에 노출될 카드입니다.",
  BOOK_CATEGORY: "온보딩의 ‘어떤 책을 만나고 싶은가요?’ 단계에 노출될 카테고리입니다.",
};

type FormState = {
  label: string;
  description: string;
  characterGroupCode: string;
  active: boolean;
};

const emptyForm: FormState = {
  label: "",
  description: "",
  characterGroupCode: "",
  active: true,
};

const getErrorMessage = (error: unknown) => {
  if (error instanceof Error && error.message) return error.message;
  return "온보딩 항목 처리 중 오류가 발생했습니다.";
};

const sortOptions = (options: OnboardingOption[]) =>
  [...options].sort((a, b) => a.displayOrder - b.displayOrder || a.id - b.id);

const buildReorderedOptions = (
  options: OnboardingOption[],
  draggingId: number,
  targetId: number
) => {
  const ordered = sortOptions(options);
  const fromIndex = ordered.findIndex((option) => option.id === draggingId);
  const toIndex = ordered.findIndex((option) => option.id === targetId);

  if (fromIndex < 0 || toIndex < 0 || fromIndex === toIndex) {
    return ordered;
  }

  const [moved] = ordered.splice(fromIndex, 1);
  ordered.splice(toIndex, 0, moved);

  // 수정 포인트: 화면에서도 displayOrder를 1부터 다시 매겨 드래그 결과와 서버 저장값을 맞춥니다.
  return ordered.map((option, index) => ({
    ...option,
    displayOrder: index + 1,
  }));
};

const AdminOnboardingOptionsPage = () => {
  const [user, setUser] = useState<MeResponse | null>(null);
  const [selectedGroup, setSelectedGroup] = useState<OnboardingOptionGroup>("READER_TYPE");
  const [options, setOptions] = useState<OnboardingOption[]>([]);
  const [characters, setCharacters] = useState<AdminCharacter[]>([]);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [editingOption, setEditingOption] = useState<OnboardingOption | null>(null);
  const [draggingId, setDraggingId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [reordering, setReordering] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  const isAdmin = user?.role === "ADMIN";

  const sortedOptions = useMemo(() => sortOptions(options), [options]);
  const characterByKey = useMemo(() => {
    return new Map(characters.map((character) => [character.characterKey, character]));
  }, [characters]);

  const loadOptions = async (group: OnboardingOptionGroup) => {
    setErrorMessage("");
    const result = await getOnboardingOptions(group);
    setOptions(result);
  };

  const loadCharacters = async () => {
    /** 수정 포인트: 독자 유형 카드의 캐릭터 연결값은 텍스트 입력이 아니라 관리자 등록 캐릭터 목록에서 선택합니다. */
    const result = await getAdminCharacters();
    setCharacters(result);
  };

  useEffect(() => {
    const initialize = async () => {
      setLoading(true);
      setErrorMessage("");

      try {
        /** 수정 포인트: 관리자 메뉴 진입 시 서버 세션 기준 권한을 다시 확인합니다. */
        const me = await getMe();
        setUser(me);
        saveUser(me);

        if (me.role !== "ADMIN") {
          setErrorMessage("관리자 권한이 있는 계정만 접근할 수 있습니다.");
          return;
        }

        await Promise.all([loadOptions(selectedGroup), loadCharacters()]);
      } catch (error) {
        setErrorMessage(getErrorMessage(error));
      } finally {
        setLoading(false);
      }
    };

    void initialize();
  }, [selectedGroup]);

  const handleGroupChange = (group: OnboardingOptionGroup) => {
    setSelectedGroup(group);
    setEditingOption(null);
    setForm(emptyForm);
    setSuccessMessage("");
    setDraggingId(null);
  };

  const handleEdit = (option: OnboardingOption) => {
    setEditingOption(option);
    setForm({
      label: option.label,
      description: option.description ?? "",
      characterGroupCode: option.characterGroupCode ?? "",
      active: option.active,
    });
    setErrorMessage("");
    setSuccessMessage("");
  };

  const handleCancelEdit = () => {
    setEditingOption(null);
    setForm(emptyForm);
    setErrorMessage("");
  };

  const buildPayload = (): OnboardingOptionRequest => ({
    optionGroup: selectedGroup,
    label: form.label.trim(),
    description: form.description.trim() || null,
    characterGroupCode: selectedGroup === "READER_TYPE" ? form.characterGroupCode.trim() || null : null,
    active: form.active,
  });

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setErrorMessage("");
    setSuccessMessage("");

    if (!form.label.trim()) {
      setErrorMessage("화면에 표시할 이름을 입력해 주세요.");
      return;
    }

    setSaving(true);

    try {
      const payload = buildPayload();

      if (editingOption) {
        /** 수정 포인트: 기존 항목은 id 기준으로 표시 이름/설명/구분값/사용 여부만 수정합니다. */
        await updateOnboardingOption(editingOption.id, payload);
        setSuccessMessage("온보딩 항목을 수정했습니다.");
      } else {
        /** 수정 포인트: 신규 항목은 현재 그룹의 마지막 순서로 자동 등록합니다. */
        await createOnboardingOption(payload);
        setSuccessMessage("온보딩 항목을 등록했습니다.");
      }

      setEditingOption(null);
      setForm(emptyForm);
      await loadOptions(selectedGroup);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (option: OnboardingOption) => {
    const confirmed = window.confirm(`‘${option.label}’ 항목을 삭제할까요?`);
    if (!confirmed) return;

    setErrorMessage("");
    setSuccessMessage("");

    try {
      await deleteOnboardingOption(option.id);
      setSuccessMessage("온보딩 항목을 삭제했습니다.");
      if (editingOption?.id === option.id) {
        handleCancelEdit();
      }
      await loadOptions(selectedGroup);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    }
  };

  const handleDragStart = (event: DragEvent<HTMLDivElement>, optionId: number) => {
    setDraggingId(optionId);
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", String(optionId));
  };

  const handleDragOver = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  };

  const handleDrop = async (targetId: number) => {
    if (!draggingId || draggingId === targetId || reordering) {
      setDraggingId(null);
      return;
    }

    const nextOptions = buildReorderedOptions(options, draggingId, targetId);
    setOptions(nextOptions);
    setDraggingId(null);
    setReordering(true);
    setErrorMessage("");
    setSuccessMessage("");

    try {
      /** 수정 포인트: 드래그가 끝난 시점에 현재 전체 순서를 서버에 저장합니다. */
      const savedOptions = await reorderOnboardingOptions({
        optionGroup: selectedGroup,
        orderedIds: nextOptions.map((option) => option.id),
      });
      setOptions(savedOptions);
      setSuccessMessage("노출 순서를 저장했습니다.");
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
      await loadOptions(selectedGroup);
    } finally {
      setReordering(false);
    }
  };

  return (
    <AdminLayout
      title="온보딩 항목 관리"
      description="회원가입 이후 추가정보 입력 화면에 노출될 선택형 항목을 관리자 페이지에서 관리합니다."
    >
      {loading && (
        <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border bg-card py-12 text-muted-foreground">
          <div className="size-10 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          <span className="text-sm">관리자 권한과 온보딩 항목을 확인하는 중...</span>
        </div>
      )}

      {errorMessage && <Alert variant="destructive">{errorMessage}</Alert>}
      {successMessage && <Alert variant="success">{successMessage}</Alert>}

      {!loading && isAdmin && (
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_390px]">
          <Card>
            <CardHeader>
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <CardDescription>관리 대상</CardDescription>
                  <CardTitle>{GROUP_LABELS[selectedGroup]}</CardTitle>
                  <p className="mt-2 text-sm text-muted-foreground">
                    {GROUP_DESCRIPTIONS[selectedGroup]}
                  </p>
                </div>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() => void loadOptions(selectedGroup)}
                  disabled={reordering}
                >
                  <RefreshCw className="size-4" />
                  새로고침
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="grid gap-2 sm:grid-cols-2">
                {(Object.keys(GROUP_LABELS) as OnboardingOptionGroup[]).map((group) => (
                  <Button
                    key={group}
                    type="button"
                    variant={selectedGroup === group ? "default" : "outline"}
                    onClick={() => handleGroupChange(group)}
                    className="justify-start"
                  >
                    {GROUP_LABELS[group]}
                  </Button>
                ))}
              </div>

              <div className="rounded-2xl border bg-muted/20 p-3">
                <div className="mb-3 flex items-center justify-between gap-3 text-xs text-muted-foreground">
                  <span>위아래로 드래그해서 온보딩 노출 순서를 변경할 수 있습니다.</span>
                  {reordering && <span>순서 저장 중...</span>}
                </div>

                <div className="space-y-3">
                  {sortedOptions.map((option) => (
                    <div
                      key={option.id}
                      draggable={!reordering}
                      onDragStart={(event) => handleDragStart(event, option.id)}
                      onDragOver={handleDragOver}
                      onDrop={() => void handleDrop(option.id)}
                      className={`rounded-xl border bg-card p-4 shadow-sm transition ${
                        draggingId === option.id ? "opacity-50" : "opacity-100"
                      }`}
                    >
                      <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start">
                        <div className="min-w-0 space-y-2">
                          <div className="flex min-w-0 items-start gap-3">
                            <div className="flex shrink-0 items-center gap-2 pt-0.5 text-sm font-semibold text-muted-foreground">
                              <GripVertical className="size-5 cursor-grab" />
                              <span>{option.displayOrder}</span>
                            </div>

                            <div className="min-w-0 flex-1 space-y-2">
                              <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
                                <p className="min-w-0 break-words text-base font-semibold text-foreground">
                                  {option.label}
                                </p>
                                {option.active ? (
                                  <Badge className="shrink-0 gap-1 whitespace-nowrap px-2 py-1 leading-none">
                                    <CheckCircle2 className="size-3" />
                                    사용
                                  </Badge>
                                ) : (
                                  <Badge
                                    variant="secondary"
                                    className="shrink-0 gap-1 whitespace-nowrap px-2 py-1 leading-none"
                                  >
                                    <XCircle className="size-3" />
                                    미사용
                                  </Badge>
                                )}
                              </div>

                              {option.description && (
                                <p className="whitespace-pre-wrap break-words text-sm text-muted-foreground">
                                  {option.description}
                                </p>
                              )}
                              {selectedGroup === "READER_TYPE" && (
                                <p className="text-xs text-muted-foreground">
                                  연결 캐릭터: {option.characterGroupCode
                                    ? characterByKey.get(option.characterGroupCode)?.defaultName ?? option.characterGroupCode
                                    : "미지정"}
                                </p>
                              )}
                            </div>
                          </div>
                        </div>

                        <div className="flex shrink-0 items-center gap-2 sm:justify-end">
                          <Button
                            type="button"
                            size="icon"
                            variant="outline"
                            className="size-9 rounded-full"
                            onClick={() => handleEdit(option)}
                            title="수정"
                            aria-label={`${option.label} 수정`}
                          >
                            {/* 수정 포인트: 버튼 텍스트를 제거하고 아이콘만 남겨 카드 우측 영역이 좁아지는 문제를 줄입니다. */}
                            <Edit3 className="size-4" />
                          </Button>
                          <Button
                            type="button"
                            size="icon"
                            variant="destructive"
                            className="size-9 rounded-full"
                            onClick={() => void handleDelete(option)}
                            title="삭제"
                            aria-label={`${option.label} 삭제`}
                          >
                            {/* 수정 포인트: 삭제 버튼도 아이콘 전용으로 바꿔 상태 배지가 아래로 밀리지 않게 합니다. */}
                            <Trash2 className="size-4" />
                          </Button>
                        </div>
                      </div>
                    </div>
                  ))}

                  {sortedOptions.length === 0 && (
                    <div className="rounded-xl border border-dashed bg-card px-4 py-10 text-center text-sm text-muted-foreground">
                      등록된 항목이 없습니다.
                    </div>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="h-fit">
            <CardHeader>
              <CardDescription>{GROUP_LABELS[selectedGroup]}</CardDescription>
              <CardTitle className="flex items-center gap-2">
                {editingOption ? <Edit3 className="size-5" /> : <Plus className="size-5" />}
                {editingOption ? "항목 수정" : "항목 등록"}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <form className="space-y-4" onSubmit={handleSubmit}>
                <div className="space-y-2">
                  <Label htmlFor="label">표시 이름</Label>
                  <Input
                    id="label"
                    value={form.label}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        label: event.target.value,
                      }))
                    }
                    placeholder="예: 따뜻한 상담사"
                  />
                  <p className="text-xs text-muted-foreground">
                    실제 온보딩 화면에 보일 문구입니다. 내부 식별값은 서버가 자동 생성합니다.
                  </p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="description">설명</Label>
                  <textarea
                    id="description"
                    value={form.description}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        description: event.target.value,
                      }))
                    }
                    maxLength={300}
                    rows={4}
                    placeholder="예: 공감과 위로, 관계 중심의 책을 선호하는 사용자를 위한 독자 유형"
                    className="min-h-24 w-full rounded-xl border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none transition focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
                  />
                  <p className="text-xs text-muted-foreground">
                    관리자 참고용 설명입니다. 기획 의도나 추천/캐릭터 분기 기준을 적어둘 수 있습니다.
                  </p>
                </div>

                {selectedGroup === "READER_TYPE" && (
                  <div className="space-y-2">
                    <Label htmlFor="characterGroupCode">연결 캐릭터</Label>
                    <select
                      id="characterGroupCode"
                      value={form.characterGroupCode}
                      onChange={(event) =>
                        setForm((current) => ({
                          ...current,
                          characterGroupCode: event.target.value,
                        }))
                      }
                      className="h-10 w-full rounded-xl border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none transition focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
                    >
                      <option value="">캐릭터 선택 안 함</option>
                      {characters.map((character) => (
                        <option key={character.id} value={character.characterKey}>
                          {character.defaultName}
                        </option>
                      ))}
                    </select>
                    <p className="text-xs text-muted-foreground">
                      관리자 메뉴의 캐릭터 설정에 등록된 캐릭터만 선택할 수 있습니다.
                    </p>
                  </div>
                )}

                <label className="flex items-center gap-2 rounded-xl border bg-muted/20 px-3 py-3 text-sm font-medium">
                  <input
                    type="checkbox"
                    checked={form.active}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        active: event.target.checked,
                      }))
                    }
                    className="size-4 rounded border-input"
                  />
                  사용 상태로 노출
                </label>

                <div className="flex flex-col gap-2 sm:flex-row">
                  <Button type="submit" disabled={saving}>
                    <Save className="size-4" />
                    {saving ? "저장 중..." : editingOption ? "수정 저장" : "등록"}
                  </Button>
                  {editingOption && (
                    <Button type="button" variant="secondary" onClick={handleCancelEdit}>
                      <X className="size-4" />
                      취소
                    </Button>
                  )}
                </div>
              </form>
            </CardContent>
          </Card>
        </div>
      )}
    </AdminLayout>
  );
};

export default AdminOnboardingOptionsPage;
