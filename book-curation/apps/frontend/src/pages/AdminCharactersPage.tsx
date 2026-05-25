import { Edit3, ImageIcon, KeyRound, Plus, RefreshCw, Save, X } from "lucide-react";
import { useEffect, useState, type ChangeEvent, type FormEvent } from "react";
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
import { toCacheBustedImageUrl } from "../utils/imageUrl";
import {
  createAdminCharacter,
  getAdminCharacters,
  updateAdminCharacter,
  uploadAdminCharacterImage,
} from "../api/adminCharacterApi";
import { getMe } from "../api/authApi";
import type {
  AdminCharacter,
  AdminCharacterImageUploadResponse,
  AdminCharacterRequest,
  CharacterLevelImage,
  CharacterLevelImageRequest,
} from "../types/adminCharacter";
import type { MeResponse } from "../types/auth";
import { saveUser } from "../utils/storage";

type LevelKey = "level1Image" | "level2Image" | "level3Image" | "level4Image";

type FormImageState = {
  imageUrl: string;
  originalFilename: string | null;
  contentType: string | null;
  sizeBytes: number | null;
};

type FormState = {
  characterKey: string;
  defaultName: string;
  level1Image: FormImageState;
  level2Image: FormImageState;
  level3Image: FormImageState;
  level4Image: FormImageState;
};

const levelKeys: LevelKey[] = ["level1Image", "level2Image", "level3Image", "level4Image"];

const LEVEL_LABELS: Record<LevelKey, string> = {
  level1Image: "레벨 1 이미지",
  level2Image: "레벨 2 이미지",
  level3Image: "레벨 3 이미지",
  level4Image: "레벨 4 이미지",
};

const emptyImage: FormImageState = {
  imageUrl: "",
  originalFilename: null,
  contentType: null,
  sizeBytes: null,
};

const MAX_IMAGE_SIZE_BYTES = 2 * 1024 * 1024;
const MIN_IMAGE_SIZE = 128;
const MAX_IMAGE_SIZE = 1024;
const MIN_ASPECT_RATIO = 0.8;
const MAX_ASPECT_RATIO = 1.25;
const ALLOWED_IMAGE_TYPES = ["image/png", "image/jpeg", "image/gif"];

const getErrorMessage = (error: unknown) => {
  if (error instanceof Error && error.message) return error.message;
  return "캐릭터 설정 처리 중 오류가 발생했습니다.";
};

// 수정 포인트: 빈 폼은 함수로만 생성해서 각 레벨 이미지 상태가 서로 공유되지 않게 하고,
// TypeScript noUnusedLocals 빌드 옵션에서 실패하던 미사용 emptyForm 상수는 제거했습니다.
const cloneEmptyForm = (): FormState => ({
  characterKey: "",
  defaultName: "",
  level1Image: { ...emptyImage },
  level2Image: { ...emptyImage },
  level3Image: { ...emptyImage },
  level4Image: { ...emptyImage },
});


const normalizeCharacterKey = (value: string) =>
  value
    .trim()
    .toUpperCase()
    .replace(/[^A-Z0-9_-]/g, "");

const validateImageFile = async (file: File) => {
  if (!ALLOWED_IMAGE_TYPES.includes(file.type)) {
    throw new Error("캐릭터 이미지는 PNG, JPG, GIF 파일만 업로드할 수 있습니다.");
  }

  if (file.size > MAX_IMAGE_SIZE_BYTES) {
    throw new Error("캐릭터 이미지 용량은 최대 2MB까지 업로드할 수 있습니다.");
  }

  const image = new Image();
  const objectUrl = URL.createObjectURL(file);

  try {
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve();
      image.onerror = () => reject(new Error("이미지 파일을 읽을 수 없습니다."));
      image.src = objectUrl;
    });

    if (image.width < MIN_IMAGE_SIZE || image.height < MIN_IMAGE_SIZE) {
      throw new Error("캐릭터 이미지는 최소 128x128px 이상이어야 합니다.");
    }

    if (image.width > MAX_IMAGE_SIZE || image.height > MAX_IMAGE_SIZE) {
      throw new Error("캐릭터 이미지는 최대 1024x1024px 이하만 업로드할 수 있습니다.");
    }

    const aspectRatio = image.width / image.height;
    if (aspectRatio < MIN_ASPECT_RATIO || aspectRatio > MAX_ASPECT_RATIO) {
      throw new Error("캐릭터 이미지는 정사각형에 가까운 비율이어야 합니다. 권장 비율은 1:1입니다.");
    }
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
};

const toFormImage = (image: CharacterLevelImage): FormImageState => ({
  imageUrl: image.imageUrl,
  originalFilename: image.originalFilename,
  contentType: image.contentType,
  sizeBytes: image.sizeBytes,
});

const toRequestImage = (image: FormImageState): CharacterLevelImageRequest => ({
  imageUrl: image.imageUrl,
  originalFilename: image.originalFilename,
  contentType: image.contentType,
  sizeBytes: image.sizeBytes,
});

const AdminCharactersPage = () => {
  const [user, setUser] = useState<MeResponse | null>(null);
  const [characters, setCharacters] = useState<AdminCharacter[]>([]);
  const [editingCharacter, setEditingCharacter] = useState<AdminCharacter | null>(null);
  const [form, setForm] = useState<FormState>(() => cloneEmptyForm());
  const [previewUrls, setPreviewUrls] = useState<Partial<Record<LevelKey, string>>>({});
  const [selectedFiles, setSelectedFiles] = useState<Partial<Record<LevelKey, File>>>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  const isAdmin = user?.role === "ADMIN";

  const loadCharacters = async () => {
    const result = await getAdminCharacters();
    // 수정 포인트: 등록 캐릭터 목록은 관리자 등록순으로 한 줄 카드 목록에 표시합니다.
    setCharacters([...result].sort((a, b) => a.id - b.id));
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

        await loadCharacters();
      } catch (error) {
        setErrorMessage(getErrorMessage(error));
      } finally {
        setLoading(false);
      }
    };

    void initialize();
  }, []);

  useEffect(() => {
    return () => {
      Object.values(previewUrls).forEach((url) => {
        if (url) URL.revokeObjectURL(url);
      });
    };
  }, [previewUrls]);

  const resetFilePreview = () => {
    Object.values(previewUrls).forEach((url) => {
      if (url) URL.revokeObjectURL(url);
    });
    setPreviewUrls({});
    setSelectedFiles({});
  };

  const handleEdit = (character: AdminCharacter) => {
    resetFilePreview();
    setEditingCharacter(character);
    setForm({
      characterKey: character.characterKey,
      defaultName: character.defaultName,
      level1Image: toFormImage(character.level1Image),
      level2Image: toFormImage(character.level2Image),
      level3Image: toFormImage(character.level3Image),
      level4Image: toFormImage(character.level4Image),
    });
    setErrorMessage("");
    setSuccessMessage("");
  };

  const handleCancelEdit = () => {
    resetFilePreview();
    setEditingCharacter(null);
    setForm(cloneEmptyForm());
    setErrorMessage("");
  };

  const handleFileChange = async (levelKey: LevelKey, event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] ?? null;
    setErrorMessage("");
    setSuccessMessage("");

    const existingPreview = previewUrls[levelKey];
    if (existingPreview) URL.revokeObjectURL(existingPreview);

    setPreviewUrls((current) => {
      const next = { ...current };
      delete next[levelKey];
      return next;
    });
    setSelectedFiles((current) => {
      const next = { ...current };
      delete next[levelKey];
      return next;
    });

    if (!file) return;

    try {
      await validateImageFile(file);
      setSelectedFiles((current) => ({ ...current, [levelKey]: file }));
      setPreviewUrls((current) => ({ ...current, [levelKey]: URL.createObjectURL(file) }));
    } catch (error) {
      event.target.value = "";
      setErrorMessage(getErrorMessage(error));
    }
  };

  const uploadSelectedImages = async () => {
    const uploaded: Partial<Record<LevelKey, AdminCharacterImageUploadResponse>> = {};

    for (const levelKey of levelKeys) {
      const file = selectedFiles[levelKey];
      if (file) {
        uploaded[levelKey] = await uploadAdminCharacterImage(file);
      }
    }

    return uploaded;
  };

  const buildImagePayload = (
    levelKey: LevelKey,
    uploadedImages: Partial<Record<LevelKey, AdminCharacterImageUploadResponse>>
  ): CharacterLevelImageRequest => {
    const uploadedImage = uploadedImages[levelKey];
    const currentImage = form[levelKey];

    return uploadedImage
      ? {
          imageUrl: uploadedImage.imageUrl,
          originalFilename: uploadedImage.originalFilename,
          contentType: uploadedImage.contentType,
          sizeBytes: uploadedImage.sizeBytes,
        }
      : toRequestImage(currentImage);
  };

  const buildPayload = (
    uploadedImages: Partial<Record<LevelKey, AdminCharacterImageUploadResponse>>
  ): AdminCharacterRequest => ({
    characterKey: normalizeCharacterKey(form.characterKey),
    defaultName: form.defaultName.trim(),
    level1Image: buildImagePayload("level1Image", uploadedImages),
    level2Image: buildImagePayload("level2Image", uploadedImages),
    level3Image: buildImagePayload("level3Image", uploadedImages),
    level4Image: buildImagePayload("level4Image", uploadedImages),
  });

  const validateForm = () => {
    if (!normalizeCharacterKey(form.characterKey)) {
      setErrorMessage("캐릭터 키를 입력해 주세요.");
      return false;
    }

    if (!form.defaultName.trim()) {
      setErrorMessage("캐릭터 기본 이름을 입력해 주세요.");
      return false;
    }

    for (const levelKey of levelKeys) {
      if (!selectedFiles[levelKey] && !form[levelKey].imageUrl.trim()) {
        setErrorMessage(`${LEVEL_LABELS[levelKey]}를 업로드해 주세요.`);
        return false;
      }
    }

    return true;
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setErrorMessage("");
    setSuccessMessage("");

    if (!validateForm()) return;

    setSaving(true);

    try {
      const uploadedImages = await uploadSelectedImages();
      const payload = buildPayload(uploadedImages);

      if (editingCharacter) {
        await updateAdminCharacter(editingCharacter.id, payload);
        setSuccessMessage("캐릭터 설정을 수정했습니다.");
      } else {
        await createAdminCharacter(payload);
        setSuccessMessage("캐릭터를 등록했습니다.");
      }

      resetFilePreview();
      setEditingCharacter(null);
      setForm(cloneEmptyForm());
      await loadCharacters();
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setSaving(false);
    }
  };

  const renderLevelPreview = (levelKey: LevelKey, image: FormImageState) => {
    const previewUrl = previewUrls[levelKey];
    const selectedFile = selectedFiles[levelKey];
    const imageUrl = previewUrl || image.imageUrl;
    const displayImageUrl = toCacheBustedImageUrl(
      imageUrl,
      editingCharacter?.updatedAt
    );

    if (!imageUrl) return null;

    return (
      <div className="rounded-xl border bg-muted/30 p-2">
        <div className="flex items-center gap-3">
          <div className="flex size-16 shrink-0 items-center justify-center overflow-hidden rounded-xl border bg-card">
            <img
              src={displayImageUrl}
              alt={`${LEVEL_LABELS[levelKey]} 미리보기`}
              className="h-full w-full object-cover"
            />
          </div>
          <div className="min-w-0 text-xs">
            <p className="font-medium text-foreground">현재 이미지</p>
            {selectedFile && (
              <p className="mt-1 truncate text-muted-foreground">선택 파일: {selectedFile.name}</p>
            )}
          </div>
        </div>
      </div>
    );
  };

  return (
    <AdminLayout
      title="캐릭터 설정"
      description=""
    >
      {loading && (
        <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border bg-card py-12 text-muted-foreground">
          <div className="size-10 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          <span className="text-sm">관리자 권한과 캐릭터 목록을 확인하는 중...</span>
        </div>
      )}

      {errorMessage && <Alert variant="destructive">{errorMessage}</Alert>}
      {successMessage && <Alert variant="success">{successMessage}</Alert>}

      {!loading && isAdmin && (
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1.2fr)_410px] 2xl:grid-cols-[minmax(0,1.35fr)_420px]">
          <Card>
            <CardHeader>
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <CardDescription>관리 대상</CardDescription>
                  <CardTitle>등록 캐릭터 목록</CardTitle>
                </div>
                <Button type="button" variant="secondary" size="sm" onClick={() => void loadCharacters()}>
                  <RefreshCw className="size-4" />
                  새로고침
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {characters.map((character) => (
                  <div key={character.id} className="rounded-2xl border bg-card px-5 py-4 shadow-sm">
                    <div className="grid gap-4 md:grid-cols-[auto_minmax(0,1fr)] md:items-center">
                      <div className="flex shrink-0 items-start gap-2">
                        {[character.level1Image, character.level2Image, character.level3Image, character.level4Image].map((image) => (
                          <div key={image.level} className="space-y-1 text-center">
                            <div className="flex size-12 items-center justify-center overflow-hidden rounded-xl border bg-muted">
                              {image.imageUrl ? (
                                <img
                                  src={toCacheBustedImageUrl(image.imageUrl, character.updatedAt)}
                                  alt={`${character.defaultName} 레벨 ${image.level}`}
                                  className="h-full w-full object-cover"
                                />
                              ) : (
                                <ImageIcon className="size-4 text-muted-foreground" />
                              )}
                            </div>
                            <span className="text-[10px] text-muted-foreground">Lv.{image.level}</span>
                          </div>
                        ))}
                      </div>

                      <div className="min-w-0">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0 flex-1">
                            <p
                              className="truncate text-xl font-semibold leading-tight"
                              title={character.defaultName}
                            >
                              {character.defaultName}
                            </p>
                            <Badge variant="secondary" className="mt-2 inline-flex max-w-full items-center gap-1 truncate">
                              {/* 수정 포인트: 키 문구는 아이콘으로 유지하되, 텍스트 영역을 더 넓게 확보합니다. */}
                              <KeyRound className="size-3" />
                              <span className="truncate">{character.characterKey}</span>
                            </Badge>
                          </div>

                          <Button
                            type="button"
                            size="icon"
                            variant="outline"
                            className="size-10 shrink-0 rounded-full"
                            onClick={() => handleEdit(character)}
                            title="수정"
                            aria-label={`${character.defaultName} 수정`}
                          >
                            <Edit3 className="size-4" />
                          </Button>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}

                {characters.length === 0 && (
                  <div className="rounded-xl border border-dashed bg-card px-4 py-10 text-center text-sm text-muted-foreground">
                    등록된 캐릭터가 없습니다.
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          <Card className="h-fit">
            <CardHeader>
              <CardDescription>캐릭터 설정</CardDescription>
              <CardTitle className="flex items-center gap-2">
                {editingCharacter ? <Edit3 className="size-5" /> : <Plus className="size-5" />}
                {editingCharacter ? "캐릭터 수정" : "캐릭터 등록"}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <form className="space-y-4" onSubmit={handleSubmit}>
                <div className="space-y-2">
                  <Label htmlFor="characterKey">캐릭터 키</Label>
                  <Input
                    id="characterKey"
                    value={form.characterKey}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        characterKey: normalizeCharacterKey(event.target.value),
                      }))
                    }
                    maxLength={50}
                    placeholder="예: BRIGHT_BOOKEMON"
                  />
                  <p className="text-xs text-muted-foreground">
                    온보딩 독자 유형 카드와 연결되는 값입니다. 영문, 숫자, _, -만 사용할 수 있습니다.
                  </p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="defaultName">캐릭터 기본 이름</Label>
                  <Input
                    id="defaultName"
                    value={form.defaultName}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        defaultName: event.target.value,
                      }))
                    }
                    maxLength={30}
                    placeholder="예: 밝은 북케몬"
                  />
                  <p className="text-xs text-muted-foreground">
                    유저에게 캐릭터를 처음 발급할 때 마이페이지에 기본으로 보일 이름입니다.
                  </p>
                </div>

                <div className="space-y-4 rounded-2xl border bg-muted/20 p-4">
                  <div>
                    <p className="text-sm font-semibold">레벨별 캐릭터 이미지</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      레벨 1~4 이미지는 모두 필수입니다. PNG, JPG, GIF / 최대 2MB / 128~1024px / 권장 1:1 비율입니다.
                    </p>
                  </div>

                  <div className="grid gap-3 md:grid-cols-2">
                    {levelKeys.map((levelKey) => (
                      <div key={levelKey} className="space-y-2 rounded-xl border bg-card p-3">
                        <Label htmlFor={levelKey}>{LEVEL_LABELS[levelKey]}</Label>
                        <Input
                          id={levelKey}
                          type="file"
                          accept="image/png,image/jpeg,image/gif"
                          onChange={(event) => void handleFileChange(levelKey, event)}
                        />
                        {renderLevelPreview(levelKey, form[levelKey])}
                      </div>
                    ))}
                  </div>
                </div>

                <div className="flex flex-col gap-2 sm:flex-row">
                  <Button type="submit" disabled={saving}>
                    <Save className="size-4" />
                    {saving ? "저장 중..." : editingCharacter ? "수정 저장" : "등록"}
                  </Button>
                  {editingCharacter && (
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

export default AdminCharactersPage;
