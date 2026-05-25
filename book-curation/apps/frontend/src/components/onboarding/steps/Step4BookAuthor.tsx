import { useState } from "react";
import { Button } from "../../ui/button";
import { Input } from "../../ui/input";
import { searchOnboardingBooks } from "../../../api/onboardingApi";
import type {
  AladinBookItem,
  OnboardingStepProps,
} from "../../../types/onboarding";
import { onboardingPersonalizationGuides } from "../constants/onboardingOptions";
import PersonalizationHint from "../shared/PersonalizationHint";
import StepFooter from "../shared/StepFooter";

const getBookKey = (book: AladinBookItem) =>
  book.isbn13 || book.aladinItemId || book.title || "";

export default function Step4BookAuthor({
  form,
  updateForm,
  goNext,
  goPrev,
  requestSkipOnboarding,
  skipping,
}: OnboardingStepProps) {
  const [keyword, setKeyword] = useState("");
  const [results, setResults] = useState<AladinBookItem[]>([]);
  const [searching, setSearching] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  const selectedKeys = form.selectedBooks.map((book) => getBookKey(book.item));

  const searchBooks = async () => {
    const trimmed = keyword.trim();

    if (trimmed.length < 2) {
      setErrorMessage("책 검색어는 2글자 이상 입력해주세요.");
      return;
    }

    setSearching(true);
    setErrorMessage("");

    try {
      const data = await searchOnboardingBooks(trimmed, 10, 1);
      setResults(data.items ?? []);
    } catch (error) {
      setResults([]);
      setErrorMessage(
        error instanceof Error ? error.message : "책 검색에 실패했습니다."
      );
    } finally {
      setSearching(false);
    }
  };

  const selectBook = (book: AladinBookItem) => {
    const key = getBookKey(book);

    if (!book.isbn13 || !/^\d{13}$/.test(book.isbn13)) {
      setErrorMessage("ISBN13이 없는 도서는 온보딩 읽은 책으로 저장할 수 없습니다.");
      return;
    }

    if (selectedKeys.includes(key)) {
      updateForm(
        "selectedBooks",
        form.selectedBooks.filter((selected) => getBookKey(selected.item) !== key)
      );
      return;
    }

    if (form.selectedBooks.length >= 3) {
      setErrorMessage("재미있게 읽은 책은 최대 3권까지 선택할 수 있습니다.");
      return;
    }

    updateForm("selectedBooks", [...form.selectedBooks, { item: book }]);
  };

  const removeBook = (book: AladinBookItem) => {
    const key = getBookKey(book);
    updateForm(
      "selectedBooks",
      form.selectedBooks.filter((selected) => getBookKey(selected.item) !== key)
    );
  };

  return (
    <div>
      <div className="flex items-center gap-2">
        <h1 className="text-2xl font-bold">재미있게 읽은 책이 있나요?</h1>
        <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
          선택
        </span>
      </div>

      <p className="mt-2 text-sm text-muted-foreground">
        선택 항목입니다. 알라딘 검색 결과에서 최대 3권까지 선택하면 읽은 책으로 저장됩니다.
      </p>

      <PersonalizationHint
        {...onboardingPersonalizationGuides.bookAuthor}
        className="mt-4"
      />

      <div className="mt-6 flex gap-2">
        <Input
          value={keyword}
          placeholder="책 제목 또는 저자"
          onChange={(event) => setKeyword(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              void searchBooks();
            }
          }}
        />
        <Button type="button" variant="outline" onClick={searchBooks} disabled={searching}>
          {searching ? "검색 중" : "검색"}
        </Button>
      </div>

      <p className="mt-2 text-xs leading-5 text-muted-foreground">
        좋아했던 책 제목이나 저자를 검색해 선택하세요. 선택한 책은 비슷한 주제와 분위기의 책을 찾는 기준이 됩니다.
      </p>

      {errorMessage && (
        <p className="mt-3 text-sm text-destructive">{errorMessage}</p>
      )}

      {form.selectedBooks.length > 0 && (
        <div className="mt-4 rounded-2xl border border-primary/40 bg-primary/10 p-4">
          <p className="text-sm font-semibold">선택한 책</p>
          <div className="mt-3 space-y-2">
            {form.selectedBooks.map(({ item }) => (
              <div
                key={getBookKey(item)}
                className="flex items-center justify-between gap-3 rounded-xl bg-background px-3 py-2"
              >
                <span className="min-w-0 truncate text-sm">{item.title}</span>
                <button
                  type="button"
                  className="shrink-0 text-xs text-muted-foreground underline"
                  onClick={() => removeBook(item)}
                >
                  삭제
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="mt-4 max-h-[360px] space-y-2 overflow-y-auto pr-1">
        {results.map((book) => {
          const key = getBookKey(book);
          const selected = selectedKeys.includes(key);

          return (
            <button
              key={key}
              type="button"
              onClick={() => selectBook(book)}
              className={[
                "flex w-full gap-3 rounded-2xl border p-3 text-left transition",
                selected
                  ? "border-primary bg-primary/10"
                  : "border-border bg-background hover:border-primary/60",
              ].join(" ")}
            >
              {book.coverUrl ? (
                <img
                  src={book.coverUrl}
                  alt={book.title ?? "도서 표지"}
                  className="h-20 w-14 shrink-0 rounded-lg object-cover"
                />
              ) : (
                <div className="flex h-20 w-14 shrink-0 items-center justify-center rounded-lg bg-muted text-[10px] text-muted-foreground">
                  No Image
                </div>
              )}

              <div className="min-w-0">
                <p className="line-clamp-2 text-sm font-semibold">{book.title}</p>
                <p className="mt-1 line-clamp-1 text-xs text-muted-foreground">
                  {book.author || "저자 정보 없음"}
                </p>
                <p className="mt-1 line-clamp-1 text-xs text-muted-foreground">
                  {book.publisher || "출판사 정보 없음"}
                </p>
                {!book.isbn13 && (
                  <p className="mt-1 text-xs text-destructive">
                    ISBN13이 없어 저장할 수 없습니다.
                  </p>
                )}
              </div>
            </button>
          );
        })}
      </div>

      <StepFooter
        onPrev={goPrev}
        onNext={goNext}
        onCancel={requestSkipOnboarding}
        cancelLoading={skipping}
      />
    </div>
  );
}
