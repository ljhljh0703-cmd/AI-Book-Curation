import { useState } from "react";
import { Button } from "../../ui/button";
import { Input } from "../../ui/input";
import {
  LIBRARY_PAGE_SIZE,
  searchOnboardingLibraries,
  type LibraryPageResponse,
  type OnboardingLibrarySearchItem,
} from "../../../api/onboardingLibraryApi";
import type { OnboardingStepProps } from "../../../types/onboarding";
import { onboardingPersonalizationGuides } from "../constants/onboardingOptions";
import PersonalizationHint from "../shared/PersonalizationHint";
import StepFooter from "../shared/StepFooter";

const emptyLibraryPage: LibraryPageResponse<OnboardingLibrarySearchItem> = {
  content: [],
  page: 0,
  size: LIBRARY_PAGE_SIZE,
  totalElements: 0,
  totalPages: 0,
  hasNext: false,
  hasPrevious: false,
};

export default function Step6Library({
  form,
  updateForm,
  goPrev,
  completeOnboarding,
  requestSkipOnboarding,
  submitting,
  skipping,
}: OnboardingStepProps) {
  const [keyword, setKeyword] = useState("");
  const [results, setResults] = useState<OnboardingLibrarySearchItem[]>([]);
  const [pageInfo, setPageInfo] = useState<LibraryPageResponse<OnboardingLibrarySearchItem>>(emptyLibraryPage);
  const [searching, setSearching] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [searched, setSearched] = useState(false);

  const searchLibraries = async (targetPage = 0) => {
    const trimmed = keyword.trim();

    if (trimmed.length < 2) {
      setResults([]);
      setPageInfo(emptyLibraryPage);
      setSearched(false);
      setErrorMessage("도서관명 또는 주소를 2글자 이상 입력해주세요.");
      return;
    }

    setSearching(true);
    setErrorMessage("");

    try {
      // 수정 포인트: 도서관 검색은 limit 파라미터를 보내지 않고 page 기준 10개 단위로 조회합니다.
      const data = await searchOnboardingLibraries(trimmed, targetPage);
      setResults(data.content);
      setPageInfo(data);
      setSearched(true);
    } catch (error) {
      setResults([]);
      setPageInfo(emptyLibraryPage);
      setErrorMessage(
        error instanceof Error ? error.message : "도서관 검색에 실패했습니다."
      );
    } finally {
      setSearching(false);
    }
  };

  const selectLibrary = (library: OnboardingLibrarySearchItem) => {
    updateForm("selectedLibrary", {
      libCode: library.libCode,
      libName: library.libName,
      address: library.address,
    });
  };

  return (
    <div>
      <div className="flex items-center gap-2">
        <h1 className="text-2xl font-bold">자주 가는 도서관이 있나요?</h1>
        <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
          선택
        </span>
      </div>

      <p className="mt-2 text-sm text-muted-foreground">
        선택 항목입니다. 도서관명 또는 주소로 검색해 대표 도서관 1개를 선택할 수 있습니다.
      </p>

      <PersonalizationHint
        {...onboardingPersonalizationGuides.library}
        className="mt-4"
      />

      <div className="mt-6 flex gap-2">
        <Input
          value={keyword}
          placeholder="서울, 시립도서관, 어린이도서관"
          onChange={(event) => {
            setKeyword(event.target.value);
            setSearched(false);
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              void searchLibraries(0);
            }
          }}
        />

        <Button type="button" variant="outline" onClick={() => void searchLibraries(0)} disabled={searching}>
          {searching ? "검색 중" : "검색"}
        </Button>
      </div>

      <p className="mt-2 text-xs leading-5 text-muted-foreground">
        도서관을 선택하지 않아도 추천은 완료할 수 있습니다. 자주 이용하는 곳이 있다면 대표 도서관으로 저장됩니다.
      </p>

      {errorMessage && (
        <p className="mt-3 text-sm text-destructive">{errorMessage}</p>
      )}

      {form.selectedLibrary && (
        <div className="mt-4 rounded-2xl border border-primary/40 bg-primary/10 p-4">
          <p className="text-sm font-semibold">선택한 대표 도서관</p>
          <p className="mt-1 text-sm">{form.selectedLibrary.libName}</p>
          {form.selectedLibrary.address && (
            <p className="mt-1 text-xs text-muted-foreground">
              {form.selectedLibrary.address}
            </p>
          )}
          <button
            type="button"
            className="mt-3 text-xs text-muted-foreground underline"
            onClick={() => updateForm("selectedLibrary", null)}
          >
            선택 해제
          </button>
        </div>
      )}

      {searched && pageInfo.totalElements > 0 && (
        <p className="mt-4 text-xs text-muted-foreground">
          총 {pageInfo.totalElements.toLocaleString()}개 도서관 중 {pageInfo.page * pageInfo.size + 1}
          ~{Math.min((pageInfo.page + 1) * pageInfo.size, pageInfo.totalElements).toLocaleString()}개를 표시합니다.
        </p>
      )}

      <div className="mt-3 max-h-[300px] space-y-2 overflow-y-auto pr-1">
        {results.map((library) => {
          const selected = form.selectedLibrary?.libCode === library.libCode;

          return (
            <button
              key={library.libCode}
              type="button"
              onClick={() => selectLibrary(library)}
              className={[
                "w-full rounded-2xl border p-4 text-left transition",
                selected
                  ? "border-primary bg-primary/10"
                  : "border-border bg-background hover:border-primary/60",
              ].join(" ")}
            >
              <div className="text-sm font-semibold">{library.libName}</div>
              {library.address && (
                <p className="mt-1 text-xs text-muted-foreground">
                  {library.address}
                </p>
              )}
            </button>
          );
        })}

        {searched && !searching && results.length === 0 && (
          <div className="rounded-2xl border border-dashed bg-slate-50 px-4 py-8 text-center text-sm text-muted-foreground">
            검색 결과가 없습니다. 도서관명 또는 주소를 바꿔서 다시 검색해 주세요.
          </div>
        )}
      </div>

      {searched && pageInfo.totalPages > 1 && (
        <div className="mt-4 flex items-center justify-between gap-3 rounded-2xl border bg-slate-50 px-4 py-3">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={!pageInfo.hasPrevious || searching}
            onClick={() => void searchLibraries(pageInfo.page - 1)}
          >
            이전
          </Button>
          <span className="text-xs font-medium text-muted-foreground">
            {pageInfo.page + 1} / {pageInfo.totalPages} 페이지 · {LIBRARY_PAGE_SIZE}개씩 보기
          </span>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={!pageInfo.hasNext || searching}
            onClick={() => void searchLibraries(pageInfo.page + 1)}
          >
            다음
          </Button>
        </div>
      )}

      <StepFooter
        onPrev={goPrev}
        onNext={completeOnboarding}
        onCancel={requestSkipOnboarding}
        nextLabel="완료"
        loading={submitting}
        cancelLoading={skipping}
      />
    </div>
  );
}
