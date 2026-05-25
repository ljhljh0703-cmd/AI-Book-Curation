import { BookOpen, CheckCircle2, Clock3, Heart, HeartOff, Star, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  completeMyBookShelfReview,
  deleteMyBookShelf,
  getMyBookShelves,
  getMyBookShelfSummary,
  type BookShelf,
  type BookShelfReviewResponse,
  type BookShelfSummary,
  type BookShelfType,
} from "../../api/userProfileApi";
import { cn } from "@/lib/utils";

type BookstandTab = "READING" | "READ" | "INTERESTED" | "NOT_INTERESTED";

const tabs: Array<{ key: BookstandTab; label: string; icon: typeof BookOpen; description: string }> = [
  { key: "READING", label: "읽는 중", icon: BookOpen, description: "현재 읽고 있는 책은 최대 3권까지 등록됩니다." },
  { key: "READ", label: "읽은 책", icon: CheckCircle2, description: "온보딩에서 재밌게 읽은 책과 리뷰 완료 도서가 모입니다." },
  { key: "INTERESTED", label: "관심있는 책", icon: Heart, description: "추천 카드에서 관심을 누른 책입니다. 최대 20권까지 유지합니다." },
  { key: "NOT_INTERESTED", label: "관심없는 책", icon: HeartOff, description: "추천 카드에서 비관심을 누른 책입니다. 최대 20권까지 유지합니다." },
];

const formatDateTime = (value?: string | null) => {
  if (!value) return "-";
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
};

const roundToHalf = (value: number) => Math.round(value * 2) / 2;

const StarRating = ({
  value,
  onChange,
  readOnly = false,
}: {
  value: number;
  onChange?: (value: number) => void;
  readOnly?: boolean;
}) => {
  const safeValue = Math.min(5, Math.max(0, roundToHalf(value || 0)));

  return (
    <div className="flex items-center gap-1" aria-label={`평점 ${safeValue}점`}>
      {Array.from({ length: 5 }, (_, index) => {
        const starScore = index + 1;
        const leftScore = index + 0.5;
        const fillPercent = safeValue >= starScore ? 100 : safeValue >= leftScore ? 50 : 0;

        return (
          <span key={starScore} className="relative inline-flex size-7 shrink-0">
            <Star className="absolute inset-0 size-7 text-slate-300" />
            <span className="absolute inset-0 overflow-hidden" style={{ width: `${fillPercent}%` }}>
              <Star className="size-7 fill-amber-400 text-amber-400" />
            </span>
            {!readOnly && (
              <>
                {/* 수정 포인트: 별 1개를 좌/우 2개 클릭 영역으로 나눠 0.5점 단위 선택을 지원합니다. */}
                <button
                  type="button"
                  className="absolute inset-y-0 left-0 w-1/2 cursor-pointer"
                  aria-label={`${leftScore}점 선택`}
                  onClick={() => onChange?.(leftScore)}
                />
                <button
                  type="button"
                  className="absolute inset-y-0 right-0 w-1/2 cursor-pointer"
                  aria-label={`${starScore}점 선택`}
                  onClick={() => onChange?.(starScore)}
                />
              </>
            )}
          </span>
        );
      })}
    </div>
  );
};

const BookCard = ({
  item,
  activeTab,
  onDelete,
  onReviewSaved,
  deleting = false,
}: {
  item: BookShelf;
  activeTab: BookstandTab;
  onDelete: (id: number) => void;
  onReviewSaved: (response: BookShelfReviewResponse) => void | Promise<void>;
  deleting?: boolean;
}) => {
  const [reviewContent, setReviewContent] = useState("");
  const [rating, setRating] = useState(0);
  const [saving, setSaving] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  const handleSaveReview = async () => {
    if (!reviewContent.trim()) {
      setErrorMessage("리뷰 내용을 입력해 주세요.");
      return;
    }

    if (rating < 0.5) {
      setErrorMessage("평점을 0.5점 이상 선택해 주세요.");
      return;
    }

    setSaving(true);
    setErrorMessage("");
    try {
      const response = await completeMyBookShelfReview(item.id, {
        reviewContent: reviewContent.trim(),
        rating: roundToHalf(rating),
      });
      setReviewContent("");
      setRating(0);
      await onReviewSaved(response);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "리뷰를 저장하지 못했습니다.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <article className="rounded-3xl border bg-white p-4 shadow-sm">
      <div className="flex gap-4">
        {item.coverUrl ? (
          <img src={item.coverUrl} alt={item.title || "도서 표지"} className="h-28 w-20 shrink-0 rounded-2xl object-cover shadow-sm" />
        ) : (
          <div className="flex h-28 w-20 shrink-0 items-center justify-center rounded-2xl bg-slate-100 text-slate-400">
            <BookOpen className="size-7" />
          </div>
        )}

        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h4 className="line-clamp-2 text-base font-bold text-slate-950 [word-break:keep-all]">{item.title || "제목 정보 없음"}</h4>
              <p className="mt-1 truncate text-sm text-muted-foreground">{item.author || "저자 정보 없음"}</p>
              {item.publisher && <p className="mt-1 truncate text-xs text-muted-foreground">{item.publisher}</p>}
            </div>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="shrink-0 rounded-full text-destructive"
              onClick={() => onDelete(item.id)}
              disabled={deleting}
              title={deleting ? "삭제 중" : "삭제"}
              aria-label={deleting ? "삭제 중" : "삭제"}
            >
              <Trash2 className="size-4" />
            </Button>
          </div>

          {activeTab === "READING" && (
            <div className="mt-3 rounded-2xl bg-slate-50 p-3 text-xs leading-5 text-slate-600">
              <div className="flex items-center gap-2 font-medium text-slate-700">
                <Clock3 className="size-3.5" /> 리뷰 가능 시점: {formatDateTime(item.reviewAvailableAt)}
              </div>
              {!item.reviewAvailable && (
                <p className="mt-1">
                  등록 후 {item.reviewWaitLabel || "관리자 설정 시간"}이 지나면 리뷰 작성 버튼이 활성화됩니다.
                </p>
              )}
              {item.reviewAvailable && (
                <div className="mt-3 space-y-2">
                  <textarea value={reviewContent} onChange={(event) => setReviewContent(event.target.value)} placeholder="이 책을 읽고 느낀 점을 적어주세요." className="min-h-24 w-full resize-y rounded-2xl border bg-white px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring" maxLength={2000} />
                  <div className="flex flex-wrap items-center gap-3">
                    <div className="flex items-center gap-2 rounded-2xl border bg-white px-3 py-2 text-xs">
                      <span className="font-semibold text-slate-700">평점</span>
                      <StarRating value={rating} onChange={setRating} />
                      <span className="min-w-10 text-right font-semibold text-amber-600">{rating > 0 ? `${rating.toFixed(1)}점` : "선택"}</span>
                    </div>
                    <Button type="button" size="sm" className="rounded-full" onClick={handleSaveReview} disabled={saving}>
                      {saving ? "저장 중..." : "리뷰 작성 완료"}
                    </Button>
                  </div>
                  {errorMessage && <p className="text-xs text-destructive">{errorMessage}</p>}
                </div>
              )}
            </div>
          )}

          {activeTab === "READ" && item.reviewContent && (
            <div className="mt-3 rounded-2xl bg-slate-50 p-3 text-sm leading-6 text-slate-700">
              {item.reviewRating && (
                <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-amber-600">
                  <StarRating value={item.reviewRating} readOnly />
                  <span>{item.reviewRating.toFixed(1)}/5.0</span>
                </div>
              )}
              <p className="whitespace-pre-wrap [word-break:keep-all]">{item.reviewContent}</p>
            </div>
          )}
        </div>
      </div>
    </article>
  );
};

type UserBookstandPanelProps = {
  onReviewSaved?: (response: BookShelfReviewResponse) => void | Promise<void>;
};

const UserBookstandPanel = ({ onReviewSaved }: UserBookstandPanelProps) => {
  const [activeTab, setActiveTab] = useState<BookstandTab>("READING");
  const [items, setItems] = useState<BookShelf[]>([]);
  const [summary, setSummary] = useState<BookShelfSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [deletingIds, setDeletingIds] = useState<Set<number>>(() => new Set());
  const [errorMessage, setErrorMessage] = useState("");

  const currentTab = useMemo(() => tabs.find((tab) => tab.key === activeTab) ?? tabs[0], [activeTab]);

  const loadData = async (
    tab: BookstandTab = activeTab,
    options: { silent?: boolean } = {},
  ) => {
    if (!options.silent) {
      setLoading(true);
    }
    setErrorMessage("");
    try {
      const [shelves, shelfSummary] = await Promise.all([
        getMyBookShelves(tab as BookShelfType),
        getMyBookShelfSummary(),
      ]);
      setItems(shelves);
      setSummary(shelfSummary);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "독서대 정보를 불러오지 못했습니다.");
    } finally {
      if (!options.silent) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    void loadData(activeTab);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);

  const handleDelete = async (id: number) => {
    if (deletingIds.has(id)) return;
    if (!window.confirm("이 도서를 독서대에서 삭제할까요?")) return;

    const previousItems = items;
    const previousSummary = summary;
    const deletedItem = items.find((item) => item.id === id);

    setErrorMessage("");
    setDeletingIds((current) => new Set(current).add(id));
    // 수정 포인트: 삭제 성공 여부를 새로고침 없이 즉시 확인할 수 있도록 optimistic update를 적용합니다.
    setItems((current) => current.filter((item) => item.id !== id));
    if (deletedItem) {
      setSummary((current) => {
        if (!current?.counts) return current;
        const currentCount = current.counts[activeTab] ?? 0;
        return {
          ...current,
          counts: {
            ...current.counts,
            [activeTab]: Math.max(0, currentCount - 1),
          },
        };
      });
    }

    try {
      await deleteMyBookShelf(id);
      await loadData(activeTab, { silent: true });
    } catch (error) {
      setItems(previousItems);
      setSummary(previousSummary);
      setErrorMessage(error instanceof Error ? error.message : "독서대에서 삭제하지 못했습니다.");
    } finally {
      setDeletingIds((current) => {
        const next = new Set(current);
        next.delete(id);
        return next;
      });
    }
  };

  const countLabel = (tab: BookstandTab) => {
    const count = summary?.counts?.[tab] ?? 0;
    if (tab === "READING") return `${count}/3`;
    if (tab === "INTERESTED" || tab === "NOT_INTERESTED") return `${count}/20`;
    return `${count}`;
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap gap-2 border-b border-slate-200 pb-2">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.key}
              type="button"
              onClick={() => setActiveTab(tab.key)}
              className={cn(
                "flex items-center gap-2 rounded-t-2xl border border-b-0 px-4 py-3 text-sm font-semibold transition-all",
                activeTab === tab.key
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "bg-slate-50 text-slate-500 hover:bg-white hover:text-slate-950"
              )}
            >
              <Icon className="size-4" />
              {tab.label}
              <span className="rounded-full bg-white/20 px-2 py-0.5 text-xs">{countLabel(tab.key)}</span>
            </button>
          );
        })}
      </div>

      <div className="rounded-3xl border bg-slate-50/70 p-4">
        <h3 className="text-lg font-bold text-slate-950">{currentTab.label}</h3>
        <p className="mt-1 text-sm leading-6 text-muted-foreground">{currentTab.description}</p>
      </div>

      {errorMessage && <Alert variant="destructive">{errorMessage}</Alert>}
      {loading && <div className="rounded-3xl border bg-white px-5 py-10 text-center text-sm text-muted-foreground">독서대 정보를 불러오는 중...</div>}
      {!loading && items.length === 0 && (
        <div className="rounded-3xl border border-dashed bg-white px-5 py-14 text-center text-sm text-muted-foreground">
          아직 등록된 도서가 없습니다.
        </div>
      )}
      {!loading && items.length > 0 && (
        <div className="grid gap-3">
          {items.map((item) => (
            <BookCard
              key={item.id}
              item={item}
              activeTab={activeTab}
              onDelete={handleDelete}
              deleting={deletingIds.has(item.id)}
              onReviewSaved={(response) => {
                // 수정 포인트: 리뷰 완료 후에는 읽은 책 탭으로 이동하고, 부모 마이페이지 캐릭터 카드/레벨업 모달도 즉시 갱신합니다.
                setActiveTab("READ");
                void onReviewSaved?.(response);
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
};

export default UserBookstandPanel;
