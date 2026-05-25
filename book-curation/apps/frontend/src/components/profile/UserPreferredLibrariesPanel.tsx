/**
 * 나만의 도서관 전용 패널.
 * 위치 좌표는 저장하지 않고, 검색 시점의 브라우저 현재 위치 또는 도서관명/주소 검색으로 등록한다.
 */

import { Crosshair, GripVertical, MapPin, RefreshCw, Search, Star, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import {
  LIBRARY_PAGE_SIZE,
  deleteMyPreferredLibrary,
  getMyPreferredLibraries,
  saveMyPreferredLibrary,
  searchLibrariesByKeyword,
  searchNearbyLibraries,
  type LibraryPageResponse,
  type LibrarySearchResult,
  type NearbyLibrary,
  type PreferredLibrary,
  type UserProfileResponse,
} from "../../api/userProfileApi";

type Props = {
  profile: UserProfileResponse | null;
};

type SearchMode = "nearby" | "keyword";
type LibraryResult = NearbyLibrary | LibrarySearchResult;

const emptyLibraryPage: LibraryPageResponse<LibraryResult> = {
  content: [],
  page: 0,
  size: LIBRARY_PAGE_SIZE,
  totalElements: 0,
  totalPages: 0,
  hasNext: false,
  hasPrevious: false,
};

const getErrorMessage = (error: unknown) => {
  if (error instanceof Error && error.message) return error.message;
  return "도서관 정보를 처리하지 못했습니다.";
};

const formatDistance = (distanceMeters?: number | null) => {
  if (distanceMeters == null) return null;
  if (distanceMeters < 1000) return `${Math.round(distanceMeters)}m`;
  return `${(distanceMeters / 1000).toFixed(1)}km`;
};

const formatAccuracy = (accuracyMeters: number) => {
  if (accuracyMeters < 1000) return `약 ${Math.round(accuracyMeters)}m`;
  return `약 ${(accuracyMeters / 1000).toFixed(1)}km`;
};

const RADIUS_OPTIONS = [
  ...Array.from({ length: 10 }, (_, index) => {
    const value = String(index + 1);
    return { value, label: value + " km" };
  }),
  { value: "50", label: "10~50 km" },
];

const hasDistance = (library: LibraryResult): library is NearbyLibrary => "distanceMeters" in library;

const getCurrentPosition = () => new Promise<GeolocationPosition>((resolve, reject) => {
  navigator.geolocation.getCurrentPosition(resolve, reject, {
    enableHighAccuracy: true,
    timeout: 15000,
    maximumAge: 0,
  });
});

const UserPreferredLibrariesPanel = ({ profile }: Props) => {
  const [preferredLibraries, setPreferredLibraries] = useState<PreferredLibrary[]>([]);
  const [nearbyLibraries, setNearbyLibraries] = useState<NearbyLibrary[]>([]);
  const [keywordLibraries, setKeywordLibraries] = useState<LibrarySearchResult[]>([]);
  const [nearbyPageInfo, setNearbyPageInfo] = useState<LibraryPageResponse<LibraryResult>>(emptyLibraryPage);
  const [keywordPageInfo, setKeywordPageInfo] = useState<LibraryPageResponse<LibraryResult>>(emptyLibraryPage);
  const [lastNearbySearch, setLastNearbySearch] = useState<{ latitude: number; longitude: number; radius: number } | null>(null);
  const [lastKeywordSearch, setLastKeywordSearch] = useState("");
  const [searchMode, setSearchMode] = useState<SearchMode>("nearby");
  const [keyword, setKeyword] = useState("");
  const [radiusKm, setRadiusKm] = useState(profile?.preferredRadiusKm == null ? "5" : String(profile.preferredRadiusKm));
  const [locationAccuracy, setLocationAccuracy] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [searching, setSearching] = useState(false);
  const [draggingLibraryId, setDraggingLibraryId] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const [infoMessage, setInfoMessage] = useState("");

  const loadPreferredLibraries = async () => {
    setLoading(true);
    setMessage("");
    try {
      setPreferredLibraries(await getMyPreferredLibraries());
    } catch (error) {
      setMessage(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadPreferredLibraries();
  }, []);

  useEffect(() => {
    setRadiusKm(profile?.preferredRadiusKm == null ? "5" : String(profile.preferredRadiusKm));
  }, [profile?.preferredRadiusKm]);

  const handleNearbySearch = async (targetPage = 0) => {
    setMessage("");
    setInfoMessage("");

    const radius = Number(radiusKm);
    if (Number.isNaN(radius) || !RADIUS_OPTIONS.some((option) => Number(option.value) === radius)) {
      setMessage("반경은 1~10km 또는 10~50km 중 하나로 선택해 주세요.");
      return;
    }

    if (!navigator.geolocation && targetPage === 0) {
      setMessage("이 브라우저에서는 현재 위치 정보를 지원하지 않습니다. 도서관 검색 탭을 사용해 주세요.");
      return;
    }

    setSearching(true);
    try {
      let latitude: number;
      let longitude: number;
      let effectiveRadius = radius;
      let accuracy: number | null = null;

      if (targetPage > 0 && lastNearbySearch) {
        latitude = lastNearbySearch.latitude;
        longitude = lastNearbySearch.longitude;
        effectiveRadius = lastNearbySearch.radius;
      } else {
        const position = await getCurrentPosition();
        latitude = position.coords.latitude;
        longitude = position.coords.longitude;
        accuracy = position.coords.accuracy;
        setLocationAccuracy(accuracy);
        setLastNearbySearch({ latitude, longitude, radius });
      }

      // 수정 포인트: 위치 좌표는 DB에 저장하지 않고, 검색 API 호출 시점에만 사용합니다. limit 대신 page만 전달하고 서버는 10개 단위로 반환합니다.
      const pageData = await searchNearbyLibraries(latitude, longitude, effectiveRadius, targetPage);
      setNearbyLibraries(pageData.content);
      setNearbyPageInfo(pageData as LibraryPageResponse<LibraryResult>);

      if (accuracy != null && accuracy > 1000) {
        setInfoMessage(
          `브라우저가 제공한 위치 정확도가 ${formatAccuracy(accuracy)}입니다. 데스크톱/Wi-Fi/IP 기반 위치는 실제 위치와 다를 수 있으니 결과가 맞지 않으면 도서관 검색 탭을 이용해 주세요.`
        );
      } else if (accuracy != null) {
        setInfoMessage(`현재 위치 정확도 ${formatAccuracy(accuracy)} 기준으로 주변 도서관을 조회했습니다.`);
      }
    } catch {
      setNearbyLibraries([]);
      setNearbyPageInfo(emptyLibraryPage);
      setMessage("현재 위치를 가져오지 못했습니다. 브라우저 위치 권한을 확인하거나 도서관 검색 탭을 이용해 주세요.");
    } finally {
      setSearching(false);
    }
  };

  const handleKeywordSearch = async (targetPage = 0) => {
    setMessage("");
    setInfoMessage("");
    const trimmedKeyword = targetPage > 0 && lastKeywordSearch ? lastKeywordSearch : keyword.trim();
    if (trimmedKeyword.length < 2) {
      setKeywordLibraries([]);
      setKeywordPageInfo(emptyLibraryPage);
      setMessage("도서관명 또는 주소를 2글자 이상 입력해 주세요.");
      return;
    }

    setSearching(true);
    try {
      // 수정 포인트: 도서관 검색은 limit 값을 보내지 않고 page 기준 10개 단위로 조회합니다.
      const pageData = await searchLibrariesByKeyword(trimmedKeyword, targetPage);
      setKeywordLibraries(pageData.content);
      setKeywordPageInfo(pageData as LibraryPageResponse<LibraryResult>);
      setLastKeywordSearch(trimmedKeyword);
    } catch (error) {
      setKeywordLibraries([]);
      setKeywordPageInfo(emptyLibraryPage);
      setMessage(getErrorMessage(error));
    } finally {
      setSearching(false);
    }
  };

  const handleSavePreferred = async (libCode: string, priority?: number) => {
    setMessage("");
    if (!preferredLibraries.some((library) => library.libCode === libCode) && preferredLibraries.length >= 3) {
      setMessage("나만의 도서관은 최대 3개까지 등록할 수 있습니다.");
      return;
    }

    try {
      await saveMyPreferredLibrary({ libCode, priority: priority ?? preferredLibraries.length + 1 });
      await loadPreferredLibraries();
    } catch (error) {
      setMessage(getErrorMessage(error));
    }
  };

  const handleDeletePreferred = async (library: PreferredLibrary) => {
    if (!window.confirm(`'${library.libName || library.libCode}' 도서관을 나만의 도서관에서 삭제할까요?`)) return;

    setMessage("");
    try {
      await deleteMyPreferredLibrary(library.libCode);
      await loadPreferredLibraries();
    } catch (error) {
      setMessage(getErrorMessage(error));
    }
  };

  const handleDropPreferred = async (targetLibraryId: number) => {
    if (draggingLibraryId == null || draggingLibraryId === targetLibraryId) {
      setDraggingLibraryId(null);
      return;
    }

    const currentIndex = preferredLibraries.findIndex((library) => library.id === draggingLibraryId);
    const targetIndex = preferredLibraries.findIndex((library) => library.id === targetLibraryId);
    if (currentIndex < 0 || targetIndex < 0) {
      setDraggingLibraryId(null);
      return;
    }

    const reordered = [...preferredLibraries];
    const [moved] = reordered.splice(currentIndex, 1);
    reordered.splice(targetIndex, 0, moved);

    setPreferredLibraries(reordered.map((library, index) => ({ ...library, priority: index + 1 })));
    setDraggingLibraryId(null);
    setMessage("");

    try {
      // 수정 포인트: 화면의 드래그 순서를 priority 1~3으로 저장하고, 이 순서가 대출 가능 여부 조회에서 먼저 사용됩니다.
      await Promise.all(reordered.map((library, index) => saveMyPreferredLibrary({ libCode: library.libCode, priority: index + 1 })));
      await loadPreferredLibraries();
    } catch (error) {
      setMessage(getErrorMessage(error));
      await loadPreferredLibraries();
    }
  };

  const registeredCodes = useMemo(
    () => new Set(preferredLibraries.map((library) => library.libCode)),
    [preferredLibraries]
  );
  const currentResults: LibraryResult[] = searchMode === "nearby" ? nearbyLibraries : keywordLibraries;
  const currentPageInfo = searchMode === "nearby" ? nearbyPageInfo : keywordPageInfo;

  const renderLibraryResult = (library: LibraryResult) => {
    const registered = registeredCodes.has(library.libCode);
    const distance = hasDistance(library) ? formatDistance(library.distanceMeters) : null;

    return (
      <article key={`${searchMode}-${library.libCode}`} className="flex flex-col gap-3 rounded-2xl border bg-slate-50/80 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-bold text-slate-950">{library.libName}</p>
            {distance && <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-semibold text-primary">{distance}</span>}
          </div>
          <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">{library.address || "주소 정보 없음"}</p>
        </div>
        <Button type="button" variant={registered ? "secondary" : "default"} disabled={registered} onClick={() => void handleSavePreferred(library.libCode)}>
          <Star className="size-4" /> {registered ? "등록됨" : "등록"}
        </Button>
      </article>
    );
  };

  const handlePageMove = (targetPage: number) => {
    if (searchMode === "nearby") {
      void handleNearbySearch(targetPage);
      return;
    }
    void handleKeywordSearch(targetPage);
  };

  const renderPagination = () => {
    if (currentPageInfo.totalPages <= 1) return null;

    return (
      <div className="mt-4 flex items-center justify-between gap-3 rounded-2xl border bg-slate-50 px-4 py-3">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={!currentPageInfo.hasPrevious || searching}
          onClick={() => handlePageMove(currentPageInfo.page - 1)}
        >
          이전
        </Button>
        <span className="text-xs font-medium text-muted-foreground">
          {currentPageInfo.page + 1} / {currentPageInfo.totalPages} 페이지 · {LIBRARY_PAGE_SIZE}개씩 보기
        </span>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={!currentPageInfo.hasNext || searching}
          onClick={() => handlePageMove(currentPageInfo.page + 1)}
        >
          다음
        </Button>
      </div>
    );
  };

  return (
    <div className="space-y-5">
      {message && <Alert variant="destructive">{message}</Alert>}
      {infoMessage && <Alert>{infoMessage}</Alert>}

      <section className="rounded-3xl border bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <p className="text-sm font-semibold text-slate-500">등록 도서관</p>
            <h3 className="mt-1 text-2xl font-bold text-slate-950">나만의 도서관</h3>
            <p className="mt-2 text-sm text-muted-foreground">
              최대 3개까지 등록할 수 있습니다. 카드를 드래그해 우선순위를 바꾸면 대출 가능 여부 조회에서도 이 순서대로 먼저 표시됩니다.
            </p>
          </div>
          <Button type="button" variant="secondary" onClick={() => void loadPreferredLibraries()} disabled={loading}>
            <RefreshCw className="size-4" /> 새로고침
          </Button>
        </div>

        <div className="mt-5 grid gap-3 md:grid-cols-3">
          {preferredLibraries.map((library) => (
            <article
              key={library.id}
              draggable
              onDragStart={() => setDraggingLibraryId(library.id)}
              onDragOver={(event) => event.preventDefault()}
              onDrop={() => void handleDropPreferred(library.id)}
              onDragEnd={() => setDraggingLibraryId(null)}
              className={cn(
                "rounded-2xl border bg-slate-50/80 p-4 transition-all",
                draggingLibraryId === library.id && "scale-[0.98] opacity-60"
              )}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="mb-2 inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-xs font-semibold text-primary">
                    <GripVertical className="size-3" /> {library.priority}순위
                  </div>
                  <p className="truncate text-base font-bold text-slate-950">{library.libName || library.libCode}</p>
                  <p className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">{library.address || "주소 정보 없음"}</p>
                </div>
                <Button type="button" size="icon" variant="ghost" className="size-8 shrink-0 text-destructive" onClick={() => void handleDeletePreferred(library)} aria-label="나만의 도서관 삭제">
                  <Trash2 className="size-4" />
                </Button>
              </div>
            </article>
          ))}

          {preferredLibraries.length === 0 && (
            <div className="rounded-2xl border border-dashed bg-slate-50 px-4 py-10 text-center text-sm text-muted-foreground md:col-span-3">
              등록된 나만의 도서관이 없습니다. 아래에서 위치 기반 또는 이름 검색으로 등록해 주세요.
            </div>
          )}
        </div>
      </section>

      <section className="rounded-3xl border bg-white p-5 shadow-sm">
        <div className="flex items-start gap-3">
          <div className="flex size-11 shrink-0 items-center justify-center rounded-2xl bg-primary/10 text-primary">
            <MapPin className="size-5" />
          </div>
          <div>
            <h3 className="text-xl font-bold text-slate-950">도서관 찾기</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              위치가 맞지 않으면 도서관명/주소 검색을 사용해 주세요.
            </p>
          </div>
        </div>

        <div className="mt-5 flex gap-2 rounded-2xl bg-slate-100 p-1">
          <button
            type="button"
            onClick={() => setSearchMode("nearby")}
            className={cn("flex-1 rounded-xl px-4 py-2 text-sm font-semibold transition", searchMode === "nearby" ? "bg-white text-primary shadow-sm" : "text-slate-500")}
          >
            내 위치 주변 찾기
          </button>
          <button
            type="button"
            onClick={() => setSearchMode("keyword")}
            className={cn("flex-1 rounded-xl px-4 py-2 text-sm font-semibold transition", searchMode === "keyword" ? "bg-white text-primary shadow-sm" : "text-slate-500")}
          >
            도서관 검색
          </button>
        </div>

        {searchMode === "nearby" ? (
          <div className="mt-5 grid gap-3 sm:grid-cols-[180px_1fr]">
            <select value={radiusKm} onChange={(event) => setRadiusKm(event.target.value)} className="h-10 rounded-md border border-input bg-background px-3 text-sm">
              {RADIUS_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
            <Button type="button" onClick={() => void handleNearbySearch(0)} disabled={searching}>
              <Crosshair className="size-4" /> {searching ? "현재 위치 확인 중..." : "현재 위치로 주변 도서관 검색"}
            </Button>
            {locationAccuracy != null && (
              <p className="text-xs text-muted-foreground sm:col-span-2">마지막 위치 정확도: {formatAccuracy(locationAccuracy)}</p>
            )}
          </div>
        ) : (
          <div className="mt-5 grid gap-3 sm:grid-cols-[1fr_auto]">
            <Input
              value={keyword}
              placeholder="도서관명 또는 주소를 입력해 주세요. 예: 서울, 시립도서관, 어린이도서관"
              onChange={(event) => setKeyword(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") void handleKeywordSearch(0);
              }}
            />
            <Button type="button" onClick={() => void handleKeywordSearch(0)} disabled={searching}>
              <Search className="size-4" /> 검색
            </Button>
          </div>
        )}

        <div className="mt-5 space-y-2">
          {currentPageInfo.totalElements > 0 && (
            <p className="text-xs text-muted-foreground">
              총 {currentPageInfo.totalElements.toLocaleString()}개 도서관 중 {currentPageInfo.page * currentPageInfo.size + 1}
              ~{Math.min((currentPageInfo.page + 1) * currentPageInfo.size, currentPageInfo.totalElements).toLocaleString()}개를 표시합니다.
            </p>
          )}

          {currentResults.map(renderLibraryResult)}

          {renderPagination()}

          {!searching && currentResults.length === 0 && (
            <div className="rounded-2xl border border-dashed bg-slate-50 px-4 py-8 text-center text-sm text-muted-foreground">
              {searchMode === "nearby"
                ? "반경을 선택하고 현재 위치로 검색하면 주변 도서관이 표시됩니다."
                : "도서관명 또는 주소를 입력하고 검색하면 결과가 표시됩니다."}
            </div>
          )}
        </div>
      </section>
    </div>
  );
};

export default UserPreferredLibrariesPanel;