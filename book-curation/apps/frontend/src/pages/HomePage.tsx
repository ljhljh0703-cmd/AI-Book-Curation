import {
  BookOpen,
  ChevronDown,
  Egg,
  Library,
  Loader2,
  LogIn,
  MessageCircle,
  MoreHorizontal,
  Plus,
  Send,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  Trash2,
} from "lucide-react";
import type { FormEvent, ReactNode } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  deleteChatSession,
  fetchChatMessages,
  fetchChatSessions,
  fetchGuestChatMessages,
  fetchGuestRecommendationReasons,
  fetchRecommendationReasons,
  sendChatMessage,
  sendGuestChatMessage,
  sendNewChatMessage,
} from "../api/chatApi";
import {
  checkBookAvailability,
  deleteMyBookShelfByIsbn,
  getMyBookShelfStates,
  getMyBookShelfSummary,
  getMyCharacter,
  saveMyBookShelf,
  sendRecommendationEvent,
  type BookAvailabilityResponse,
  type BookShelfSummary,
  type BookSnapshotPayload,
  type BookShelfType,
  type RecommendationEventType,
  type UserCharacterResponse,
} from "../api/userProfileApi";
import type {
  ChatMessage,
  ChatSession,
  RecommendedBookCandidate,
} from "../types/chat";
import type { MeResponse } from "../types/auth";
import { getUser, onAuthChanged } from "../utils/storage";
import {
  GUEST_MAX_CHAT_COUNT,
  GUEST_MAX_USER_MESSAGE_COUNT,
  appendGuestChatMessages,
  buildGuestHistory,
  buildGuestProfileSnapshot,
  createGuestChatSession,
  deleteGuestChatSession,
  getGuestChatMessages,
  getGuestSessionId,
  hydrateGuestStoredMessages,
  listGuestChatSessions,
  makeGuestChatMessage,
  replaceGuestChatMessages,
  touchGuestChatSession,
  updateGuestAssistantMessageByRequestId,
} from "../utils/guestChatStorage";

const EMPTY_TITLE_LINES = ["취향에 맞는 책을", "찾아드릴게요"];
const EMPTY_DESCRIPTION =
  "분위기, 장르, 고민을 적으면 어울리는 도서를 추천해드립니다.";
const WAITING_STATUS_MESSAGES = [
  "취향 단서를 정리하고 있어요",
  "어울리는 책 후보를 고르는 중이에요",
  "추천 이유를 읽기 좋게 다듬고 있어요",
  "북케몬이 마지막 책장을 넘겨보고 있어요",
];


const roleOrder: Record<ChatMessage["role"], number> = {
  USER: 0,
  ASSISTANT: 1,
  SYSTEM: 2,
  TOOL: 3,
};

const getMessageTime = (message: ChatMessage) => {
  const time = new Date(message.createdAt).getTime();
  return Number.isFinite(time) ? time : 0;
};

const makeMessageKey = (message: ChatMessage) => {
  if (message.id !== null && message.id !== undefined) {
    return `${message.sessionId}:${message.id}`;
  }
  return `${message.sessionId}:${message.role}:${message.createdAt}:${message.content}`;
};

const compareChatMessages = (left: ChatMessage, right: ChatMessage) => {
  const timeDiff = getMessageTime(left) - getMessageTime(right);
  if (timeDiff !== 0) return timeDiff;

  const idDiff = Number(left.id ?? 0) - Number(right.id ?? 0);
  if (idDiff !== 0) return idDiff;

  return (roleOrder[left.role] ?? 99) - (roleOrder[right.role] ?? 99);
};

const normalizeChatTimeline = (items: ChatMessage[] = []) => {
  const byKey = new Map<string, ChatMessage>();

  for (const item of items) {
    byKey.set(makeMessageKey(item), item);
  }

  return Array.from(byKey.values()).sort(compareChatMessages);
};

const mergeChatTimeline = (
  current: ChatMessage[],
  incoming: ChatMessage[],
  sessionId?: string,
) => {
  const scopedCurrent = sessionId
    ? current.filter((message) => message.sessionId === sessionId)
    : current;
  return normalizeChatTimeline([...scopedCurrent, ...incoming]);
};

const getMessageRequestId = (message: ChatMessage) =>
  typeof message.metadata?.requestId === "string"
    ? message.metadata.requestId
    : typeof message.metadata?.request_id === "string"
      ? message.metadata.request_id
      : null;

const isRecommendationReasonPending = (message: ChatMessage) => {
  if (message.role !== "ASSISTANT") return false;
  const metadataStatus = String(
    message.metadata?.recommendationReasonStatus ??
      message.metadata?.recommendation_reason_status ??
      "",
  ).toUpperCase();
  if (metadataStatus === "COMPLETED" || metadataStatus === "FAILED" || metadataStatus === "MISSING") {
    return false;
  }
  if (metadataStatus === "PENDING" || metadataStatus === "PARTIAL") return true;
  const candidates = Array.isArray(message.metadata?.candidates)
    ? message.metadata.candidates
    : [];
  return candidates.some((candidate) =>
    String(
      candidate.recommendationReasonStatus ??
        candidate.recommendation_reason_status ??
        "",
    ).toUpperCase() === "PENDING",
  );
};

const EmptyTitle = ({ large = false }: { large?: boolean }) => (
  <h1
    className={cn(
      "mx-auto max-w-3xl font-bold tracking-tight [word-break:keep-all]",
      large
        ? "text-4xl leading-tight sm:text-5xl lg:text-6xl"
        : "text-3xl leading-tight sm:text-4xl lg:text-5xl",
    )}
  >
    {EMPTY_TITLE_LINES.map((line) => (
      <span key={line} className="block">
        {line}
      </span>
    ))}
  </h1>
);

const EmptyChatIntro = () => (
  <div className="mx-auto flex max-w-3xl flex-1 flex-col items-center justify-center px-6 text-center">
    <EmptyTitle />
    <p className="mx-auto mt-4 max-w-2xl text-base leading-7 text-muted-foreground [word-break:keep-all] sm:text-lg">
      {EMPTY_DESCRIPTION}
    </p>
  </div>
);

const WaitingAssistantBubble = ({ status }: { status: string }) => (
  <div className="flex justify-start">
    <div className="max-w-[85%] overflow-hidden rounded-2xl border bg-white px-4 py-3 text-sm leading-6 text-card-foreground shadow-sm">
      <div className="flex items-center gap-2 font-semibold text-slate-900">
        <span className="flex size-8 items-center justify-center rounded-full bg-primary/10 text-primary">
          <Sparkles className="size-4 animate-pulse" />
        </span>
        <span>북케몬이 답변을 준비 중입니다</span>
      </div>
      <p className="mt-2 text-xs leading-5 text-muted-foreground [word-break:keep-all]">
        {status}
      </p>
      <div className="mt-3 flex items-center gap-2">
        {[0, 1, 2].map((index) => (
          <span
            key={index}
            className="size-2 animate-bounce rounded-full bg-primary/60"
            style={{ animationDelay: `${index * 140}ms` }}
          />
        ))}
      </div>
    </div>
  </div>
);

const RecommendationReasonPendingNotice = () => (
  <div className="mt-3 rounded-xl border border-primary/20 bg-primary/5 px-3 py-2 text-xs leading-5 text-primary [word-break:keep-all]">
    <div className="flex items-center gap-2 font-semibold">
      <Loader2 className="size-3.5 animate-spin" />
      추천 이유를 생성하고 있습니다
    </div>
    <p className="mt-1 text-primary/80">
      추천 카드는 먼저 확인할 수 있고, 이유가 완성되면 자동으로 갱신됩니다.
    </p>
  </div>
);

type MarkdownBlock =
  | { type: "heading"; level: number; text: string }
  | { type: "paragraph"; lines: string[] }
  | { type: "unorderedList"; items: string[] }
  | { type: "orderedList"; items: string[]; start: number }
  | { type: "blockquote"; lines: string[] }
  | { type: "code"; language?: string; content: string }
  | { type: "divider" };

const parseAssistantMarkdown = (content: string): MarkdownBlock[] => {
  const lines = content.replace(/\r\n/g, "\n").split("\n");
  const blocks: MarkdownBlock[] = [];
  const paragraphLines: string[] = [];

  const flushParagraph = () => {
    if (!paragraphLines.length) return;
    blocks.push({ type: "paragraph", lines: [...paragraphLines] });
    paragraphLines.length = 0;
  };

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const trimmed = line.trim();

    if (!trimmed) {
      flushParagraph();
      continue;
    }

    const codeFenceMatch = trimmed.match(/^```\s*([A-Za-z0-9_-]+)?\s*$/);
    if (codeFenceMatch) {
      flushParagraph();
      const codeLines: string[] = [];
      index += 1;
      while (index < lines.length && !lines[index].trim().startsWith("```")) {
        codeLines.push(lines[index]);
        index += 1;
      }
      blocks.push({
        type: "code",
        language: codeFenceMatch[1],
        content: codeLines.join("\n"),
      });
      continue;
    }

    const headingMatch = trimmed.match(/^(#{1,6})\s+(.+)$/);
    if (headingMatch) {
      flushParagraph();
      blocks.push({
        type: "heading",
        level: headingMatch[1].length,
        text: headingMatch[2].trim(),
      });
      continue;
    }

    if (/^(---|___|\*\*\*)$/.test(trimmed)) {
      flushParagraph();
      blocks.push({ type: "divider" });
      continue;
    }

    const unorderedMatch = line.match(/^\s*[-*]\s+(.+)$/);
    if (unorderedMatch) {
      flushParagraph();
      const items = [unorderedMatch[1].trim()];
      while (index + 1 < lines.length) {
        const nextMatch = lines[index + 1].match(/^\s*[-*]\s+(.+)$/);
        if (!nextMatch) break;
        items.push(nextMatch[1].trim());
        index += 1;
      }
      blocks.push({ type: "unorderedList", items });
      continue;
    }

    const orderedMatch = line.match(/^\s*(\d+)[.)]\s+(.+)$/);
    if (orderedMatch) {
      flushParagraph();
      const start = Number.parseInt(orderedMatch[1], 10) || 1;
      const items = [orderedMatch[2].trim()];
      while (index + 1 < lines.length) {
        const nextMatch = lines[index + 1].match(/^\s*(\d+)[.)]\s+(.+)$/);
        if (!nextMatch) break;
        items.push(nextMatch[2].trim());
        index += 1;
      }
      blocks.push({ type: "orderedList", items, start });
      continue;
    }

    const quoteMatch = line.match(/^>\s?(.+)$/);
    if (quoteMatch) {
      flushParagraph();
      const quoteLines = [quoteMatch[1].trim()];
      while (index + 1 < lines.length) {
        const nextMatch = lines[index + 1].match(/^>\s?(.+)$/);
        if (!nextMatch) break;
        quoteLines.push(nextMatch[1].trim());
        index += 1;
      }
      blocks.push({ type: "blockquote", lines: quoteLines });
      continue;
    }

    paragraphLines.push(line);
  }

  flushParagraph();
  return blocks;
};

const renderInlineMarkdown = (text: string, keyPrefix: string): ReactNode[] => {
  const nodes: ReactNode[] = [];
  const inlinePattern = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = inlinePattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }

    const token = match[0];
    if (token.startsWith("**")) {
      nodes.push(
        <strong
          key={`${keyPrefix}-strong-${match.index}`}
          className="font-semibold text-slate-950"
        >
          {token.slice(2, -2)}
        </strong>,
      );
    } else {
      nodes.push(
        <code
          key={`${keyPrefix}-code-${match.index}`}
          className="rounded bg-slate-100 px-1 py-0.5 text-[0.85em] text-slate-800"
        >
          {token.slice(1, -1)}
        </code>,
      );
    }
    lastIndex = match.index + token.length;
  }

  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }

  return nodes;
};

const renderMarkdownLines = (lines: string[], keyPrefix: string) =>
  lines.flatMap((line, index) => [
    ...renderInlineMarkdown(line, `${keyPrefix}-line-${index}`),
    index < lines.length - 1 ? <br key={`${keyPrefix}-br-${index}`} /> : null,
  ]);

const ChatMarkdown = ({ content }: { content: string }) => {
  const blocks = parseAssistantMarkdown(content);

  return (
    <div className="space-y-3 break-words text-sm leading-6">
      {blocks.map((block, index) => {
        const keyPrefix = `md-${index}`;

        if (block.type === "heading") {
          return (
            <div
              key={keyPrefix}
              className={cn(
                "font-bold text-slate-950 [word-break:keep-all]",
                block.level <= 2 ? "text-base" : "text-sm",
              )}
            >
              {renderInlineMarkdown(block.text, keyPrefix)}
            </div>
          );
        }

        if (block.type === "paragraph") {
          return (
            <p key={keyPrefix} className="text-slate-800 [word-break:keep-all]">
              {renderMarkdownLines(block.lines, keyPrefix)}
            </p>
          );
        }

        if (block.type === "unorderedList") {
          return (
            <ul
              key={keyPrefix}
              className="list-disc space-y-1 pl-5 text-slate-800"
            >
              {block.items.map((item, itemIndex) => (
                <li
                  key={`${keyPrefix}-item-${itemIndex}`}
                  className="[word-break:keep-all]"
                >
                  {renderInlineMarkdown(item, `${keyPrefix}-item-${itemIndex}`)}
                </li>
              ))}
            </ul>
          );
        }

        if (block.type === "orderedList") {
          return (
            <ol
              key={keyPrefix}
              start={block.start}
              className="list-decimal space-y-1 pl-5 text-slate-800"
            >
              {block.items.map((item, itemIndex) => (
                <li
                  key={`${keyPrefix}-item-${itemIndex}`}
                  className="[word-break:keep-all]"
                >
                  {renderInlineMarkdown(item, `${keyPrefix}-item-${itemIndex}`)}
                </li>
              ))}
            </ol>
          );
        }

        if (block.type === "blockquote") {
          return (
            <blockquote
              key={keyPrefix}
              className="border-l-4 border-slate-200 pl-3 text-slate-600 [word-break:keep-all]"
            >
              {renderMarkdownLines(block.lines, keyPrefix)}
            </blockquote>
          );
        }

        if (block.type === "code") {
          return (
            <pre
              key={keyPrefix}
              className="overflow-x-auto rounded-xl bg-slate-950 px-3 py-2 text-xs leading-5 text-slate-50"
            >
              <code>{block.content}</code>
            </pre>
          );
        }

        return <hr key={keyPrefix} className="border-slate-200" />;
      })}
    </div>
  );
};

const resolveCandidateCover = (
  candidate: RecommendedBookCandidate,
  fallbackCover?: string | null,
) =>
  candidate.cover_url ||
  candidate.coverUrl ||
  candidate.cover ||
  candidate.ori_cover_s ||
  candidate.oriCoverS ||
  fallbackCover ||
  null;

const normalizeDisplayText = (value?: string | null) =>
  (value || "")
    .replace(/\s+/g, " ")
    .replace(/[\s.,!?;:()\[\]{}'"“”‘’·…-]/g, "")
    .trim()
    .toLowerCase();

const isTextTooSimilar = (left?: string | null, right?: string | null) => {
  const a = normalizeDisplayText(left);
  const b = normalizeDisplayText(right);
  if (!a || !b) return false;
  if (a === b) return true;
  const shorter = a.length <= b.length ? a : b;
  const longer = a.length > b.length ? a : b;
  return shorter.length >= 18 && longer.includes(shorter);
};

const resolveCandidateIntro = (candidate: RecommendedBookCandidate) =>
  candidate.simple_intro ||
  candidate.simpleIntro ||
  candidate.description ||
  candidate.book_intro ||
  candidate.bookIntro ||
  "추천 도서 소개 정보가 없습니다.";

const resolveCandidateRecommendationReason = (
  candidate: RecommendedBookCandidate,
) => {
  const reason = candidate.recommendationReason || candidate.recommendation_reason || "";
  const intro = resolveCandidateIntro(candidate);
  if (!reason.trim()) return "";
  if (isTextTooSimilar(reason, intro)) return "";
  return reason;
};

const isAssistantFailurePlaceholder = (content?: string | null) => {
  const text = (content || "").trim();
  return (
    text.startsWith("추천 결과를 생성하지 못했습니다") ||
    text.startsWith("죄송합니다. 현재 조건에 맞는 도서를 찾지 못했습니다")
  );
};

const normalizeIsbn13 = (value?: string | null) => {
  const digits = (value || "").replace(/\D/g, "");
  return digits.length === 13 ? digits : null;
};

const resolveCandidateScore = (candidate: RecommendedBookCandidate) =>
  candidate.finalScore ??
  candidate.rerankerScore ??
  candidate.rerankScore ??
  candidate.rerank_score ??
  candidate.profileVectorScore ??
  candidate.ruleScore ??
  candidate.qdrantScore ??
  candidate.score ??
  null;

type RecommendationInteractionContext = {
  requestId?: string | null;
  query?: string | null;
  rank: number;
};

type RecommendationDetailState = {
  candidate: RecommendedBookCandidate;
  fallbackCover?: string | null;
};

type CandidateActionState = Partial<
  Record<"INTERESTED" | "NOT_INTERESTED" | "READING", boolean>
>;

const toBookPayload = (
  candidate: RecommendedBookCandidate,
  fallbackCover?: string | null,
): BookSnapshotPayload => ({
  isbn13: normalizeIsbn13(candidate.isbn),
  title: candidate.title || "제목 정보 없음",
  author: candidate.author || null,
  publisher: candidate.publisher || null,
  coverUrl: resolveCandidateCover(candidate, fallbackCover),
  metadata: { ...candidate },
});

const formatAvailability = (availability: BookAvailabilityResponse) => {
  if (!availability.libraries.length) {
    return "조회할 나만의 도서관이나 주변 도서관이 없습니다.";
  }

  return availability.libraries
    .map((item) => {
      const source =
        item.source === "PREFERRED" ? "나만의 도서관" : "주변 도서관";
      const hasBook =
        item.hasBook === null
          ? "소장 여부 미확인"
          : item.hasBook
            ? "소장"
            : "미소장";
      const loan =
        item.loanAvailable === null
          ? "대출 여부 미확인"
          : item.loanAvailable
            ? "대출 가능"
            : "대출 불가";
      return `${source} · ${item.libName || item.libCode}: ${hasBook} / ${loan}`;
    })
    .join("\n");
};

const getCurrentPositionForAvailability = () =>
  new Promise<GeolocationPosition>((resolve, reject) => {
    navigator.geolocation.getCurrentPosition(resolve, reject, {
      enableHighAccuracy: true,
      timeout: 15000,
      maximumAge: 0,
    });
  });

const formatLocationAccuracy = (accuracyMeters: number) => {
  if (accuracyMeters < 1000) {
    return `현재 위치 정확도: 약 ${Math.round(accuracyMeters)}m`;
  }
  return `현재 위치 정확도: 약 ${(accuracyMeters / 1000).toFixed(1)}km`;
};

const RecommendationBookCard = ({
  candidate,
  fallbackCover,
  shelfSummary,
  availabilityMessage,
  actionState,
  isAuthenticated,
  interactionContext,
  onAddShelf,
  onCheckAvailability,
  onCardClick,
  onOpenDetail,
  onRequireLogin,
}: {
  candidate: RecommendedBookCandidate;
  fallbackCover?: string | null;
  shelfSummary: BookShelfSummary | null;
  availabilityMessage?: string;
  actionState?: CandidateActionState;
  isAuthenticated: boolean;
  interactionContext: RecommendationInteractionContext;
  onAddShelf: (
    candidate: RecommendedBookCandidate,
    shelfType: BookShelfType,
    fallbackCover?: string | null,
  ) => void;
  onCheckAvailability: (
    candidate: RecommendedBookCandidate,
    fallbackCover?: string | null,
  ) => void;
  onCardClick: (
    candidate: RecommendedBookCandidate,
    context: RecommendationInteractionContext,
    fallbackCover?: string | null,
  ) => void;
  onOpenDetail: (
    candidate: RecommendedBookCandidate,
    context: RecommendationInteractionContext,
    fallbackCover?: string | null,
  ) => void;
  onRequireLogin: () => void;
}) => {
  const coverUrl = resolveCandidateCover(candidate, fallbackCover);
  const interestedFull = (shelfSummary?.remaining?.INTERESTED ?? 20) <= 0;
  const notInterestedFull =
    (shelfSummary?.remaining?.NOT_INTERESTED ?? 20) <= 0;
  const readingFull = (shelfSummary?.remaining?.READING ?? 3) <= 0;
  const missingIsbn = !normalizeIsbn13(candidate.isbn);
  const recommendationReason = resolveCandidateRecommendationReason(candidate);
  const interestedActive = actionState?.INTERESTED === true;
  const notInterestedActive = actionState?.NOT_INTERESTED === true;
  const readingActive = actionState?.READING === true;

  return (
    <article
      className="mt-3 cursor-pointer overflow-hidden rounded-2xl border bg-slate-50/80 p-3 transition hover:border-primary/40 hover:bg-slate-50"
      role="button"
      tabIndex={0}
      onClick={() => onCardClick(candidate, interactionContext, fallbackCover)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onCardClick(candidate, interactionContext, fallbackCover);
        }
      }}
    >
      <div className="flex gap-3">
        {coverUrl ? (
          <img
            src={coverUrl}
            alt={candidate.title || "추천 도서 표지"}
            className="h-24 w-16 shrink-0 rounded-lg object-cover shadow-sm"
            loading="lazy"
          />
        ) : null}
        <div className="min-w-0 flex-1">
          <p className="line-clamp-2 text-sm font-bold text-slate-950 [word-break:keep-all]">
            {candidate.title || "제목 정보 없음"}
          </p>
          <p className="mt-1 truncate text-xs text-muted-foreground">
            {candidate.author || "저자 정보 없음"}
          </p>
          <p className="mt-2 line-clamp-3 text-xs leading-5 text-muted-foreground [word-break:keep-all]">
            {resolveCandidateIntro(candidate)}
          </p>

          {String(candidate.recommendationReasonStatus ?? candidate.recommendation_reason_status ?? "").toUpperCase() === "PENDING" ? (
            <div className="mt-2 flex items-center gap-1.5 text-[11px] font-medium text-primary">
              <Loader2 className="size-3 animate-spin" />
              추천 이유 생성 중
            </div>
          ) : recommendationReason ? (
            <p className="mt-2 rounded-lg bg-white px-2.5 py-2 text-[11px] leading-5 text-slate-600 [word-break:keep-all]">
              {recommendationReason}
            </p>
          ) : null}

          <div className="mt-3 flex flex-wrap gap-1.5">
            <Button
              type="button"
              size="icon"
              variant={interestedActive ? "default" : "outline"}
              className="size-8 rounded-full"
              disabled={isAuthenticated && (missingIsbn || interestedFull)}
              title={
                !isAuthenticated
                  ? "로그인 후 관심있는 책으로 저장할 수 있습니다."
                  : interestedFull
                    ? "관심있는 책은 최대 20권까지 등록할 수 있습니다."
                    : missingIsbn
                      ? "ISBN 정보가 없어 등록할 수 없습니다."
                      : interestedActive
                        ? "관심있는 책에 등록되었습니다. 다시 누르면 취소됩니다."
                        : "관심있는 책으로 등록"
              }
              aria-label="관심있는 책으로 등록"
              onClick={(event) => {
                event.stopPropagation();
                isAuthenticated
                  ? onAddShelf(candidate, "INTERESTED", fallbackCover)
                  : onRequireLogin();
              }}
            >
              <ThumbsUp
                className={cn("size-3.5", interestedActive && "fill-current")}
              />
            </Button>

            <Button
              type="button"
              size="icon"
              variant={notInterestedActive ? "default" : "outline"}
              className="size-8 rounded-full"
              disabled={isAuthenticated && (missingIsbn || notInterestedFull)}
              title={
                !isAuthenticated
                  ? "로그인 후 관심없는 책으로 반영할 수 있습니다."
                  : notInterestedFull
                    ? "관심없는 책은 최대 20권까지 등록할 수 있습니다."
                    : missingIsbn
                      ? "ISBN 정보가 없어 등록할 수 없습니다."
                      : notInterestedActive
                        ? "관심없는 책에 등록되었습니다. 다시 누르면 취소됩니다."
                        : "관심없는 책으로 등록"
              }
              aria-label="관심없는 책으로 등록"
              onClick={(event) => {
                event.stopPropagation();
                isAuthenticated
                  ? onAddShelf(candidate, "NOT_INTERESTED", fallbackCover)
                  : onRequireLogin();
              }}
            >
              <ThumbsDown
                className={cn(
                  "size-3.5",
                  notInterestedActive && "fill-current",
                )}
              />
            </Button>

            <Button
              type="button"
              size="sm"
              variant={readingActive ? "default" : "outline"}
              className="h-8 rounded-full px-2.5 text-xs"
              disabled={
                isAuthenticated &&
                (missingIsbn || (readingFull && !readingActive))
              }
              title={
                !isAuthenticated
                  ? "로그인 후 읽는 중인 책으로 저장할 수 있습니다."
                  : readingFull && !readingActive
                    ? "읽는 중인 책은 최대 3권까지 등록할 수 있습니다."
                    : missingIsbn
                      ? "ISBN 정보가 없어 등록할 수 없습니다."
                      : readingActive
                        ? "읽는 중인 책에 등록되었습니다. 다시 누르면 취소됩니다."
                        : "읽는 중인 책으로 등록"
              }
              aria-label="읽는 중인 책으로 등록"
              onClick={(event) => {
                event.stopPropagation();
                isAuthenticated
                  ? onAddShelf(candidate, "READING", fallbackCover)
                  : onRequireLogin();
              }}
            >
              <BookOpen
                className={cn("size-3.5", readingActive && "fill-current")}
              />
              책읽기
            </Button>

            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-8 rounded-full px-2.5 text-xs"
              title="보유 추천 데이터로 상세 정보를 확인합니다."
              onClick={(event) => {
                event.stopPropagation();
                onOpenDetail(candidate, interactionContext, fallbackCover);
              }}
            >
              상세보기
            </Button>

            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-8 rounded-full px-2.5 text-xs"
              disabled={isAuthenticated && missingIsbn}
              title={
                !isAuthenticated
                  ? "로그인 후 대출 가능 여부를 조회할 수 있습니다."
                  : missingIsbn
                    ? "ISBN 정보가 없어 조회할 수 없습니다."
                    : "나만의 도서관과 주변 도서관 대출 가능 여부 조회"
              }
              onClick={(event) => {
                event.stopPropagation();
                isAuthenticated
                  ? onCheckAvailability(candidate, fallbackCover)
                  : onRequireLogin();
              }}
            >
              <Library className="size-3.5" /> 대출 확인
            </Button>
          </div>

          {availabilityMessage && (
            <pre className="mt-3 whitespace-pre-wrap rounded-xl border bg-white px-3 py-2 text-[11px] leading-5 text-slate-600">
              {availabilityMessage}
            </pre>
          )}
        </div>
      </div>
    </article>
  );
};

const RecommendationBookDetailModal = ({
  item,
  onClose,
}: {
  item: RecommendationDetailState;
  onClose: () => void;
}) => {
  const { candidate, fallbackCover } = item;
  const coverUrl = resolveCandidateCover(candidate, fallbackCover);
  const detailSections = [
    candidate.book_intro || candidate.bookIntro,
    candidate.description,
    candidate.simple_intro || candidate.simpleIntro,
    candidate.book_index || candidate.bookIndex,
    candidate.pub_review || candidate.pubReview,
  ].filter((value): value is string => Boolean(value && value.trim()));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 px-4 py-6">
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-3xl bg-white p-5 shadow-2xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-primary">
              추천 도서 상세
            </p>
            <h2 className="mt-1 text-xl font-bold leading-7 text-slate-950 [word-break:keep-all]">
              {candidate.title || "제목 정보 없음"}
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {candidate.author || "저자 정보 없음"}
              {candidate.publisher ? ` · ${candidate.publisher}` : ""}
            </p>
          </div>
          <Button type="button" variant="outline" size="sm" onClick={onClose}>
            닫기
          </Button>
        </div>

        <div className="mt-5 flex flex-col gap-4 sm:flex-row">
          {coverUrl ? (
            <img
              src={coverUrl}
              alt={candidate.title || "추천 도서 표지"}
              className="h-48 w-32 shrink-0 rounded-2xl object-cover shadow-sm"
            />
          ) : null}
          <div className="min-w-0 flex-1 space-y-3 text-sm leading-6 text-slate-700">
            <div className="grid gap-2 rounded-2xl border bg-slate-50 p-3 text-xs text-slate-600 sm:grid-cols-2">
              <span>ISBN: {normalizeIsbn13(candidate.isbn) || "정보 없음"}</span>
              <span>출간일: {candidate.publish_date || candidate.publishDate || "정보 없음"}</span>
              <span>페이지: {candidate.page ?? "정보 없음"}</span>
              <span>최종 점수: {resolveCandidateScore(candidate)?.toFixed(4) ?? "정보 없음"}</span>
            </div>

            {candidate.categories?.length ? (
              <div className="flex flex-wrap gap-1.5">
                {candidate.categories.slice(0, 6).map((category) => (
                  <span key={category} className="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-semibold text-primary">
                    {category}
                  </span>
                ))}
              </div>
            ) : null}

            {detailSections.length ? (
              detailSections.map((section, index) => (
                <p key={index} className="whitespace-pre-wrap [word-break:keep-all]">
                  {section}
                </p>
              ))
            ) : (
              <p className="text-muted-foreground">
                상세 설명은 현재 보유한 추천 후보 데이터 안에서만 표시합니다.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

const CharacterSummaryCard = ({
  nickname,
  imageUrl,
  compact = false,
}: {
  nickname?: string | null;
  imageUrl?: string | null;
  compact?: boolean;
}) => (
  <section
    className={cn(
      "relative overflow-hidden rounded-3xl border bg-gradient-to-br from-indigo-50 via-white to-violet-50 p-4 shadow-sm",
      compact && "rounded-2xl p-3",
    )}
  >
    <div className="pointer-events-none absolute -right-8 -top-8 size-24 rounded-full bg-primary/10 blur-2xl" />
    <div className="flex items-center gap-3">
      <div
        className={cn(
          "flex shrink-0 items-center justify-center overflow-hidden rounded-2xl bg-white shadow-inner ring-1 ring-primary/10",
          compact ? "size-16" : "size-20",
        )}
      >
        {imageUrl ? (
          <img
            src={imageUrl}
            alt={nickname || "북케몬 캐릭터"}
            className="h-full w-full object-cover"
          />
        ) : (
          <Egg className={cn("text-primary", compact ? "size-8" : "size-10")} />
        )}
      </div>
      <div className="min-w-0">
        <div className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-semibold text-primary">
          <Sparkles className="size-3" /> 나의 북케몬
        </div>
        <p
          className={cn(
            "mt-2 truncate font-bold tracking-tight text-slate-950",
            compact ? "text-sm" : "text-lg",
          )}
        >
          {nickname || "북케몬 알"}
        </p>
        <p className="mt-1 text-xs leading-5 text-muted-foreground [word-break:keep-all]">
          리뷰를 남기면 성장하는 캐릭터 영역입니다.
        </p>
      </div>
    </div>
  </section>
);

const HomePage = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { sessionId: routeSessionIdParam } = useParams<{ sessionId?: string }>();
  // 수정 포인트: 새로고침해도 현재 채팅방을 복원할 수 있도록 URL의 sessionId를 단일 출처로 사용합니다.
  const routeSessionId = routeSessionIdParam?.trim() || null;
  const [user, setUser] = useState<MeResponse | null>(() => getUser());
  const isGuest = !user;
  const [character, setCharacter] = useState<UserCharacterResponse | null>(
    null,
  );
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [maxChatCount, setMaxChatCount] = useState(8);
  const [maxUserMessageCount, setMaxUserMessageCount] = useState(10);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [sending, setSending] = useState(false);
  const [menuOpenSessionId, setMenuOpenSessionId] = useState<string | null>(
    null,
  );
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [shelfSummary, setShelfSummary] = useState<BookShelfSummary | null>(
    null,
  );
  const [availabilityMessages, setAvailabilityMessages] = useState<
    Record<string, string>
  >({});
  const [candidateActionStates, setCandidateActionStates] = useState<
    Record<string, CandidateActionState>
  >({});
  const [detailCandidate, setDetailCandidate] =
    useState<RecommendationDetailState | null>(null);
  const [pendingUserMessage, setPendingUserMessage] = useState<string | null>(
    null,
  );
  const [showJumpToBottom, setShowJumpToBottom] = useState(false);
  const [hasUnreadAssistantMessage, setHasUnreadAssistantMessage] =
    useState(false);
  const [waitingMessageIndex, setWaitingMessageIndex] = useState(0);
  const chatScrollRef = useRef<HTMLDivElement | null>(null);
  const chatBottomRef = useRef<HTMLDivElement | null>(null);
  const previousMessageCountRef = useRef(0);
  const activeSessionIdRef = useRef<string | null>(activeSessionId);
  const inFlightSendSeqRef = useRef(0);
  const sendingRef = useRef(false);
  const pendingUserMessageRef = useRef<string | null>(null);
  const activeReasonPollsRef = useRef<Set<string>>(new Set());

  const moveToChatRoute = useCallback(
    (sessionId: string | null, replace = false) => {
      const nextPath = sessionId ? `/chat/${encodeURIComponent(sessionId)}` : "/";
      if (location.pathname !== nextPath) {
        navigate(nextPath, { replace });
      }
    },
    [location.pathname, navigate],
  );

  const activateSession = useCallback(
    (sessionId: string | null, replaceRoute = false) => {
      setActiveSessionId(sessionId);
      activeSessionIdRef.current = sessionId;
      moveToChatRoute(sessionId, replaceRoute);
    },
    [moveToChatRoute],
  );

  const orderedMessages = useMemo(() => normalizeChatTimeline(messages), [messages]);

  const activeUserMessageCount = useMemo(
    () => orderedMessages.filter((message) => message.role === "USER").length,
    [orderedMessages],
  );
  const reachedUserMessageLimit =
    Boolean(activeSessionId) && activeUserMessageCount >= maxUserMessageCount;
  const hasVisibleChatContent =
    orderedMessages.length > 0 || Boolean(pendingUserMessage) || sending;
  const currentWaitingStatus =
    WAITING_STATUS_MESSAGES[
      waitingMessageIndex % WAITING_STATUS_MESSAGES.length
    ];

  const visibleRecommendationIsbn13s = useMemo(() => {
    return Array.from(
      new Set(
        orderedMessages
          .flatMap((message) => {
            const candidates = Array.isArray(message.metadata?.candidates)
              ? message.metadata.candidates
              : [];
            return candidates.map((candidate) =>
              normalizeIsbn13(candidate.isbn),
            );
          })
          .filter((isbn13): isbn13 is string => Boolean(isbn13)),
      ),
    );
  }, [orderedMessages]);

  const isChatScrolledNearBottom = () => {
    const element = chatScrollRef.current;
    if (!element) return true;
    const distanceFromBottom =
      element.scrollHeight - element.scrollTop - element.clientHeight;
    return distanceFromBottom < 120;
  };

  const scrollToLatestMessage = (behavior: ScrollBehavior = "smooth") => {
    chatBottomRef.current?.scrollIntoView({ behavior, block: "end" });
    setShowJumpToBottom(false);
    setHasUnreadAssistantMessage(false);
  };

  const handleChatScroll = () => {
    if (isChatScrolledNearBottom()) {
      setShowJumpToBottom(false);
      setHasUnreadAssistantMessage(false);
      return;
    }

    if (hasVisibleChatContent) {
      setShowJumpToBottom(true);
    }
  };

  useEffect(() => {
    return onAuthChanged(() => {
      setUser(getUser());
    });
  }, []);

  useEffect(() => {
    activeSessionIdRef.current = activeSessionId;
  }, [activeSessionId]);

  useEffect(() => {
    const pendingTargets = orderedMessages
      .filter(isRecommendationReasonPending)
      .map((message) => ({ message, requestId: getMessageRequestId(message), sessionId: message.sessionId }))
      .filter((item): item is { message: ChatMessage; requestId: string; sessionId: string } =>
        Boolean(item.requestId) && Boolean(item.sessionId),
      );

    for (const { requestId, sessionId } of pendingTargets) {
      if (activeReasonPollsRef.current.has(requestId)) continue;
      activeReasonPollsRef.current.add(requestId);

      void (async () => {
        try {
          for (let attempt = 0; attempt < 24; attempt += 1) {
            const delayMs = attempt < 3 ? 2000 : attempt < 8 ? 5000 : 10000;
            await new Promise((resolve) => window.setTimeout(resolve, delayMs));
            const result = isGuest
              ? await fetchGuestRecommendationReasons(requestId)
              : await fetchRecommendationReasons(requestId);
            const status = String(result.status || "").toUpperCase();
            if (status === "PENDING") continue;

            if (!isGuest && result.assistantMessage) {
              setMessages((prev) =>
                normalizeChatTimeline(
                  prev.map((item) =>
                    getMessageRequestId(item) === requestId
                      ? result.assistantMessage!
                      : item,
                  ),
                ),
              );
              if (status === "PARTIAL") continue;
              break;
            }

            if (isGuest) {
              const answer = result.answer?.trim();
              const candidates = Array.isArray(result.candidates)
                ? result.candidates
                : [];
              const applyReasonResult = (current: ChatMessage): ChatMessage => ({
                ...current,
                content: answer || current.content,
                metadata: {
                  ...(current.metadata ?? {}),
                  recommendationReasonStatus: status,
                  recommendationReasonErrorMessage:
                    result.errorMessage ?? result.error_message ?? null,
                  candidates: candidates.length
                    ? candidates
                    : current.metadata?.candidates,
                },
              });
              const nextMessages = updateGuestAssistantMessageByRequestId(
                sessionId,
                requestId,
                applyReasonResult,
              );
              setMessages((prev) => {
                const hasCurrentMessage = prev.some((item) => getMessageRequestId(item) === requestId);
                if (!hasCurrentMessage) {
                  return normalizeChatTimeline(nextMessages);
                }
                return normalizeChatTimeline(
                  prev.map((item) =>
                    getMessageRequestId(item) === requestId
                      ? applyReasonResult(item)
                      : item,
                  ),
                );
              });
              if (status === "PARTIAL") continue;
              break;
            }

            if (status === "PARTIAL") continue;

            if (status === "FAILED" || status === "MISSING") {
              setMessages((prev) =>
                normalizeChatTimeline(
                  prev.map((item) =>
                    getMessageRequestId(item) === requestId
                      ? {
                          ...item,
                          metadata: {
                            ...(item.metadata ?? {}),
                            recommendationReasonStatus: status,
                            recommendationReasonErrorMessage:
                              result.errorMessage ?? result.error_message ?? null,
                          },
                        }
                      : item,
                  ),
                ),
              );
              break;
            }
          }
        } finally {
          activeReasonPollsRef.current.delete(requestId);
        }
      })();
    }
  }, [isGuest, orderedMessages]);

  useEffect(() => {
    pendingUserMessageRef.current = pendingUserMessage;
  }, [pendingUserMessage]);

  useEffect(() => {
    if (user) {
      return;
    }

    const guestSessions = listGuestChatSessions();
    const routeMatchedSession = routeSessionId
      ? guestSessions.find((session) => session.id === routeSessionId)
      : null;
    const nextActiveSessionId = routeMatchedSession?.id ?? guestSessions[0]?.id ?? null;

    setCharacter(null);
    setSessions(guestSessions);
    setMaxChatCount(GUEST_MAX_CHAT_COUNT);
    setMaxUserMessageCount(GUEST_MAX_USER_MESSAGE_COUNT);
    setActiveSessionId(nextActiveSessionId);
    activeSessionIdRef.current = nextActiveSessionId;
    if (routeSessionId && !routeMatchedSession) {
      moveToChatRoute(nextActiveSessionId, true);
    }
    setMessages(
      nextActiveSessionId
        ? normalizeChatTimeline(getGuestChatMessages(nextActiveSessionId))
        : [],
    );
    const preservePendingMessage = sendingRef.current && Boolean(pendingUserMessageRef.current);
    if (!preservePendingMessage) {
      setPendingUserMessage(null);
      setShowJumpToBottom(false);
      setHasUnreadAssistantMessage(false);
    }
    setMenuOpenSessionId(null);
    setErrorMessage(null);
  }, [moveToChatRoute, routeSessionId, user]);

  useEffect(() => {
    if (!user) return;

    const loadCharacter = async () => {
      try {
        setCharacter(await getMyCharacter());
      } catch {
        setCharacter(null);
      }
    };

    void loadCharacter();
  }, [user?.id]);

  useEffect(() => {
    if (!user) return;

    const loadShelfSummary = async () => {
      try {
        setShelfSummary(await getMyBookShelfSummary());
      } catch {
        setShelfSummary(null);
      }
    };

    void loadShelfSummary();
  }, [user?.id]);

  useEffect(() => {
    if (!user) return;

    setActiveSessionId(null);
    activeSessionIdRef.current = null;
    setMessages([]);
    setPendingUserMessage(null);

    const loadSessions = async () => {
      setLoadingSessions(true);
      setErrorMessage(null);
      try {
        const data = await fetchChatSessions();
        const loadedSessions = Array.isArray(data?.sessions) ? data.sessions : [];
        setSessions(loadedSessions);
        const routeMatchedSession = routeSessionId
          ? loadedSessions.find((session) => session.id === routeSessionId)
          : null;
        if (routeSessionId && routeMatchedSession) {
          setActiveSessionId(routeMatchedSession.id);
          activeSessionIdRef.current = routeMatchedSession.id;
        } else if (routeSessionId && !routeMatchedSession) {
          moveToChatRoute(null, true);
        }
        setMaxChatCount(
          typeof data?.maxActiveChatCount === "number"
            ? data.maxActiveChatCount
            : 8,
        );
        setMaxUserMessageCount(
          typeof data?.maxUserMessageCount === "number"
            ? data.maxUserMessageCount
            : 10,
        );
      } catch (error) {
        setErrorMessage(
          error instanceof Error
            ? error.message
            : "채팅방 목록을 불러오지 못했습니다.",
        );
      } finally {
        setLoadingSessions(false);
      }
    };

    void loadSessions();
  }, [moveToChatRoute, routeSessionId, user?.id]);

  useEffect(() => {
    if (!user || loadingSessions) return;
    if (!routeSessionId) return;

    const routeMatchedSession = sessions.find((session) => session.id === routeSessionId);
    if (routeMatchedSession) {
      if (activeSessionId !== routeMatchedSession.id) {
        setActiveSessionId(routeMatchedSession.id);
        activeSessionIdRef.current = routeMatchedSession.id;
      }
      return;
    }

    if (sessions.length > 0) {
      moveToChatRoute(null, true);
    }
  }, [activeSessionId, loadingSessions, moveToChatRoute, routeSessionId, sessions, user]);

  useEffect(() => {
    const preservePendingMessage = sendingRef.current && Boolean(pendingUserMessageRef.current);
    if (!preservePendingMessage) {
      setPendingUserMessage(null);
      setShowJumpToBottom(false);
      setHasUnreadAssistantMessage(false);
    }

    if (!activeSessionId) {
      setMessages([]);
      previousMessageCountRef.current = 0;
      return;
    }

    if (isGuest) {
      const localGuestMessages = normalizeChatTimeline(getGuestChatMessages(activeSessionId));
      setMessages(localGuestMessages);

      let cancelled = false;
      const requestedSessionId = activeSessionId;
      const loadGuestMessages = async () => {
        try {
          const response = await fetchGuestChatMessages(
            getGuestSessionId(),
            requestedSessionId,
          );
          if (cancelled || !response.messages?.length) return;
          const redisMessages = normalizeChatTimeline(
            hydrateGuestStoredMessages(requestedSessionId, response.messages),
          );
          if (redisMessages.length > localGuestMessages.length) {
            replaceGuestChatMessages(requestedSessionId, redisMessages);
            setMessages(redisMessages);
          }
        } catch {
          // 수정 포인트: Valkey TTL 임시 저장소가 비어 있거나 일시 장애여도 localStorage 복원을 유지합니다.
        }
      };
      void loadGuestMessages();
      return () => {
        cancelled = true;
      };
    }

    let cancelled = false;
    const requestedSessionId = activeSessionId;

    const loadMessages = async () => {
      setLoadingMessages(true);
      setErrorMessage(null);
      try {
        const loadedMessages = await fetchChatMessages(requestedSessionId);
        if (!cancelled) {
          setMessages(normalizeChatTimeline(loadedMessages));
        }
      } catch (error) {
        if (!cancelled) {
          setErrorMessage(
            error instanceof Error
              ? error.message
              : "채팅 메시지를 불러오지 못했습니다.",
          );
        }
      } finally {
        if (!cancelled) {
          setLoadingMessages(false);
        }
      }
    };

    void loadMessages();

    return () => {
      cancelled = true;
    };
  }, [activeSessionId, isGuest]);

  useEffect(() => {
    if (!sending) {
      setWaitingMessageIndex(0);
      return;
    }

    const timer = window.setInterval(() => {
      setWaitingMessageIndex((index) => index + 1);
    }, 1800);

    return () => window.clearInterval(timer);
  }, [sending]);

  useEffect(() => {
    if (!pendingUserMessage) return;
    window.setTimeout(() => scrollToLatestMessage("smooth"), 0);
  }, [pendingUserMessage]);

  useEffect(() => {
    if (loadingMessages) return;
    if (!hasVisibleChatContent) {
      previousMessageCountRef.current = 0;
      setShowJumpToBottom(false);
      setHasUnreadAssistantMessage(false);
      return;
    }

    const currentCount = orderedMessages.length;
    const previousCount = previousMessageCountRef.current;
    const lastMessage = orderedMessages[currentCount - 1];

    if (currentCount > previousCount) {
      if (isChatScrolledNearBottom()) {
        window.setTimeout(() => scrollToLatestMessage("smooth"), 0);
      } else if (lastMessage?.role === "ASSISTANT") {
        setShowJumpToBottom(true);
        setHasUnreadAssistantMessage(true);
      }
    }

    previousMessageCountRef.current = currentCount;
  }, [orderedMessages, loadingMessages, hasVisibleChatContent]);

  useEffect(() => {
    if (loadingMessages || !hasVisibleChatContent) return;
    window.setTimeout(() => scrollToLatestMessage("auto"), 0);
  }, [activeSessionId, loadingMessages]);

  useEffect(() => {
    if (!sending || !isChatScrolledNearBottom()) return;
    window.setTimeout(() => scrollToLatestMessage("smooth"), 0);
  }, [currentWaitingStatus, sending]);

  useEffect(() => {
    if (!user || visibleRecommendationIsbn13s.length === 0) {
      return;
    }

    const loadRecommendationStates = async () => {
      try {
        const states = await getMyBookShelfStates(visibleRecommendationIsbn13s);
        setCandidateActionStates((current) => {
          const next = { ...current };
          states.forEach((state) => {
            next[state.isbn13] = {
              ...(next[state.isbn13] ?? {}),
              INTERESTED: state.interested,
              NOT_INTERESTED: state.notInterested,
              READING: state.reading,
            };
          });
          return next;
        });
      } catch {
        // 상태 복원 실패가 채팅 사용을 막지 않도록 조용히 무시합니다.
      }
    };

    void loadRecommendationStates();
  }, [user, visibleRecommendationIsbn13s]);

  const moveSessionToTop = (target: ChatSession) => {
    setSessions((prev) => {
      const safePrev = Array.isArray(prev) ? prev : [];
      return [
        target,
        ...safePrev.filter((session) => session.id !== target.id),
      ].slice(0, maxChatCount);
    });
  };

  const handleCreateChat = () => {
    if ((sessions ?? []).length >= maxChatCount) {
      alert(
        `채팅방은 최대 ${maxChatCount}개까지 생성할 수 있습니다. 기존 채팅방을 삭제한 뒤 다시 생성해주세요.`,
      );
      return;
    }

    setErrorMessage(null);
    setMenuOpenSessionId(null);
    setPendingUserMessage(null);
    setShowJumpToBottom(false);
    setHasUnreadAssistantMessage(false);
    setDraft("");

    if (isGuest) {
      try {
        const session = createGuestChatSession();
        setSessions(listGuestChatSessions());
        activateSession(session.id);
        setMessages([]);
      } catch (error) {
        setErrorMessage(
          error instanceof Error
            ? error.message
            : "비로그인 채팅방을 만들지 못했습니다.",
        );
      }
      return;
    }

    activateSession(null);
    setMessages([]);
  };

  const handleDeleteSession = async (session: ChatSession) => {
    setMenuOpenSessionId(null);
    if (!window.confirm(`'${session.title}' 채팅방을 삭제할까요?`)) return;
    try {
      if (isGuest) {
        deleteGuestChatSession(session.id);
        const nextSessions = listGuestChatSessions();
        setSessions(nextSessions);
        if (activeSessionId === session.id) {
          const nextActiveId = nextSessions[0]?.id ?? null;
          activateSession(nextActiveId, true);
          setMessages(nextActiveId ? getGuestChatMessages(nextActiveId) : []);
          setPendingUserMessage(null);
          setShowJumpToBottom(false);
          setHasUnreadAssistantMessage(false);
        }
        return;
      }

      await deleteChatSession(session.id);
      setSessions((prev) => prev.filter((item) => item.id !== session.id));
      if (activeSessionId === session.id) {
        activateSession(null, true);
        setMessages([]);
        setPendingUserMessage(null);
        setShowJumpToBottom(false);
        setHasUnreadAssistantMessage(false);
      }
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : "채팅방을 삭제하지 못했습니다.",
      );
    }
  };

  const handleRequireLogin = () => {
    setErrorMessage(
      "추천 결과 저장, 비선호 반영, 책 읽기, 대출 확인은 로그인 후 사용할 수 있습니다.",
    );
  };

  const finishSendingBeforeRender = (seq: number) => {
    if (inFlightSendSeqRef.current !== seq) return;
    pendingUserMessageRef.current = null;
    sendingRef.current = false;
    setPendingUserMessage(null);
    setSending(false);
  };

  const sendGuestMessage = async (content: string) => {
    let sessionId = activeSessionId;
    let session: ChatSession | null = null;

    if (!sessionId) {
      session = createGuestChatSession(content);
      sessionId = session.id;
      activateSession(sessionId, true);
    }

    const currentMessages = sessionId ? getGuestChatMessages(sessionId) : [];
    const userMessageCount = currentMessages.filter(
      (message) => message.role === "USER",
    ).length;
    if (userMessageCount >= GUEST_MAX_USER_MESSAGE_COUNT) {
      throw new Error(
        `비로그인 채팅방에서는 질문을 최대 ${GUEST_MAX_USER_MESSAGE_COUNT}개까지만 보낼 수 있습니다. 새 채팅방을 만들거나 로그인해 주세요.`,
      );
    }

    const userMessage = makeGuestChatMessage(sessionId, "USER", content, {
      guest: true,
    });
    const historySource = [...currentMessages, userMessage];
    const guestProfile = buildGuestProfileSnapshot(historySource);

    const response = await sendGuestChatMessage({
      guestSessionId: getGuestSessionId(),
      guestRoomId: sessionId,
      content,
      history: buildGuestHistory(currentMessages),
      guestProfile,
    });

    const assistantMessage = makeGuestChatMessage(
      sessionId,
      "ASSISTANT",
      response.assistantMessage.content,
      {
        ...(response.assistantMessage.metadata ?? {}),
        guest: true,
        personalized: false,
        loginPrompt: response.loginPrompt,
      },
    );

    appendGuestChatMessages(sessionId, [userMessage, assistantMessage]);
    session = touchGuestChatSession(sessionId, content) ?? session;

    return {
      session,
      sessionId,
      nextMessages: getGuestChatMessages(sessionId),
      nextSessions: listGuestChatSessions(),
      maxChatCount: response.maxGuestChatCount || GUEST_MAX_CHAT_COUNT,
      maxUserMessageCount:
        response.maxGuestUserMessageCount || GUEST_MAX_USER_MESSAGE_COUNT,
    };
  };

  const handleSendMessage = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const content = draft.trim();
    if (!content || sending) return;
    const sendSeq = inFlightSendSeqRef.current + 1;
    inFlightSendSeqRef.current = sendSeq;
    sendingRef.current = true;
    setSending(true);
    setErrorMessage(null);
    try {
      if (reachedUserMessageLimit) {
        setErrorMessage(
          `이 채팅방에서는 질문을 최대 ${maxUserMessageCount}개까지만 보낼 수 있습니다. 새 채팅으로 이어서 질문해 주세요.`,
        );
        return;
      }

      pendingUserMessageRef.current = content;
      setPendingUserMessage(content);
      setDraft("");
      setShowJumpToBottom(false);
      setHasUnreadAssistantMessage(false);

      if (isGuest) {
        const guestResult = await sendGuestMessage(content);
        finishSendingBeforeRender(sendSeq);
        activateSession(guestResult.sessionId, true);
        setSessions(guestResult.nextSessions);
        setMaxChatCount(guestResult.maxChatCount);
        setMaxUserMessageCount(guestResult.maxUserMessageCount);
        setMessages(normalizeChatTimeline(guestResult.nextMessages));
        return;
      }

      const requestSessionId = activeSessionId;
      const response = requestSessionId
        ? await sendChatMessage(requestSessionId, content)
        : await sendNewChatMessage(content);
      finishSendingBeforeRender(sendSeq);
      activateSession(response.session.id, true);
      moveSessionToTop(response.session);
      setMessages((prev) =>
        mergeChatTimeline(
          requestSessionId ? prev : [],
          [response.userMessage, response.assistantMessage],
          response.session.id,
        ),
      );
    } catch (error) {
      if (inFlightSendSeqRef.current === sendSeq) {
        setDraft(content);
      }
      setErrorMessage(
        error instanceof Error
          ? error.message
          : "메시지를 전송하지 못했습니다.",
      );
    } finally {
      if (inFlightSendSeqRef.current === sendSeq) {
        pendingUserMessageRef.current = null;
        sendingRef.current = false;
        setPendingUserMessage(null);
        setSending(false);
      }
    }
  };

  const logRecommendationInteraction = (
    eventType: RecommendationEventType,
    candidate: RecommendedBookCandidate,
    context: RecommendationInteractionContext,
    fallbackCover?: string | null,
  ) => {
    if (!user) {
      return;
    }

    void sendRecommendationEvent({
      requestId: context.requestId ?? null,
      eventType,
      source: "CHAT_RECOMMENDATION",
      query: context.query ?? null,
      rank: context.rank,
      score: resolveCandidateScore(candidate),
      book: toBookPayload(candidate, fallbackCover),
      metadata: {
        ...candidate,
        requestId: context.requestId ?? null,
        rank: context.rank,
      },
    }).catch(() => undefined);
  };

  const handleRecommendationCardClick = (
    candidate: RecommendedBookCandidate,
    context: RecommendationInteractionContext,
    fallbackCover?: string | null,
  ) => {
    logRecommendationInteraction("BOOK_CLICK", candidate, context, fallbackCover);
  };

  const handleOpenRecommendationDetail = (
    candidate: RecommendedBookCandidate,
    context: RecommendationInteractionContext,
    fallbackCover?: string | null,
  ) => {
    logRecommendationInteraction("DETAIL_VIEW", candidate, context, fallbackCover);
    setDetailCandidate({ candidate, fallbackCover });
  };

  const refreshShelfSummary = async () => {
    try {
      setShelfSummary(await getMyBookShelfSummary());
    } catch {
      setShelfSummary(null);
    }
  };

  const handleAddBookShelf = async (
    candidate: RecommendedBookCandidate,
    shelfType: BookShelfType,
    fallbackCover?: string | null,
  ) => {
    const isbn13 = normalizeIsbn13(candidate.isbn);
    if (!isbn13) {
      setErrorMessage("ISBN 정보가 없어 독서대에 등록할 수 없습니다.");
      return;
    }

    setErrorMessage(null);
    const currentState = candidateActionStates[isbn13] ?? {};
    const alreadyActive =
      shelfType === "INTERESTED"
        ? currentState.INTERESTED === true
        : shelfType === "NOT_INTERESTED"
          ? currentState.NOT_INTERESTED === true
          : shelfType === "READING"
            ? currentState.READING === true
            : false;

    try {
      if (alreadyActive) {
        await deleteMyBookShelfByIsbn(isbn13, shelfType);
        setCandidateActionStates((current) => {
          const nextState: CandidateActionState = {
            ...(current[isbn13] ?? {}),
          };
          if (shelfType === "INTERESTED") {
            nextState.INTERESTED = false;
          } else if (shelfType === "NOT_INTERESTED") {
            nextState.NOT_INTERESTED = false;
          } else if (shelfType === "READING") {
            nextState.READING = false;
          }
          return { ...current, [isbn13]: nextState };
        });
      } else {
        await saveMyBookShelf({
          shelfType,
          book: toBookPayload(candidate, fallbackCover),
        });

        setCandidateActionStates((current) => {
          const nextState: CandidateActionState = {
            ...(current[isbn13] ?? {}),
          };
          if (shelfType === "INTERESTED") {
            nextState.INTERESTED = true;
            nextState.NOT_INTERESTED = false;
          } else if (shelfType === "NOT_INTERESTED") {
            nextState.NOT_INTERESTED = true;
            nextState.INTERESTED = false;
          } else if (shelfType === "READING") {
            nextState.READING = true;
          }
          return { ...current, [isbn13]: nextState };
        });
      }

      await refreshShelfSummary();
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : "도서를 독서대에 등록하지 못했습니다.",
      );
    }
  };

  const handleCheckBookAvailability = async (
    candidate: RecommendedBookCandidate,
    fallbackCover?: string | null,
  ) => {
    const isbn13 = normalizeIsbn13(candidate.isbn);
    if (!isbn13) {
      setErrorMessage("ISBN 정보가 없어 대출 가능 여부를 조회할 수 없습니다.");
      return;
    }

    setErrorMessage(null);
    const key = isbn13;
    setAvailabilityMessages((current) => ({
      ...current,
      [key]: "현재 위치를 확인한 뒤 대출 가능 여부를 조회하는 중입니다...",
    }));

    let latitude: number | null = null;
    let longitude: number | null = null;
    let locationNotice = "";

    if (navigator.geolocation) {
      try {
        const position = await getCurrentPositionForAvailability();
        latitude = position.coords.latitude;
        longitude = position.coords.longitude;
        locationNotice = formatLocationAccuracy(position.coords.accuracy);
        if (position.coords.accuracy > 1000) {
          locationNotice +=
            " · 위치가 실제와 다르면 나만의 도서관 결과를 우선 확인하거나 도서관 검색으로 등록해 주세요.";
        }
      } catch {
        locationNotice =
          "현재 위치를 가져오지 못해 나만의 도서관 기준으로만 조회했습니다.";
      }
    } else {
      locationNotice =
        "이 브라우저는 위치 조회를 지원하지 않아 나만의 도서관 기준으로만 조회했습니다.";
    }

    try {
      const result = await checkBookAvailability(
        toBookPayload(candidate, fallbackCover),
        latitude,
        longitude,
      );
      setAvailabilityMessages((current) => ({
        ...current,
        [key]: `${locationNotice}\n${formatAvailability(result)}`.trim(),
      }));
    } catch (error) {
      setAvailabilityMessages((current) => ({
        ...current,
        [key]:
          error instanceof Error
            ? error.message
            : "대출 가능 여부를 조회하지 못했습니다.",
      }));
    }
  };

  return (
    <main className="flex h-[calc(100vh-4rem)] overflow-hidden bg-slate-50/80">
      <aside className="hidden w-80 shrink-0 border-r bg-white/90 p-4 shadow-[8px_0_30px_rgba(15,23,42,0.04)] backdrop-blur md:flex md:flex-col">
        <CharacterSummaryCard
          nickname={user ? character?.characterNickname : "비로그인 북케몬"}
          imageUrl={user ? character?.currentImageUrl : null}
        />

        {isGuest ? (
          <div className="mt-3 rounded-2xl border border-amber-200 bg-amber-50 px-3 py-3 text-xs leading-5 text-amber-800 [word-break:keep-all]">
            비로그인은 채팅방 {GUEST_MAX_CHAT_COUNT}개, 방당{" "}
            {GUEST_MAX_USER_MESSAGE_COUNT}턴까지 체험할 수 있습니다. 추천 저장과
            더 정교한 개인화는 로그인 후 사용할 수 있어요.
            <Button asChild size="sm" className="mt-3 w-full rounded-xl">
              <Link to="/login">
                <LogIn className="size-3.5" />
                로그인하기
              </Link>
            </Button>
          </div>
        ) : null}

        <Button
          className="mt-4 h-12 justify-start rounded-2xl text-base shadow-sm"
          onClick={handleCreateChat}
          disabled={loadingSessions || (sessions ?? []).length >= maxChatCount}
        >
          <Plus className="size-4" />새 채팅
        </Button>

        <div className="mt-5 flex items-center justify-between px-2 text-xs font-medium text-muted-foreground">
          <span>채팅방</span>
          <span>
            {(sessions ?? []).length}/{maxChatCount}
          </span>
        </div>
        <div className="mt-2 flex-1 space-y-1 overflow-y-auto pr-1">
          {loadingSessions ? (
            <div className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" /> 불러오는 중...
            </div>
          ) : null}
          {!loadingSessions && (sessions ?? []).length === 0 ? (
            <div className="rounded-2xl border border-dashed bg-slate-50 px-3 py-4 text-sm leading-6 text-muted-foreground">
              아직 채팅방이 없습니다. 새 채팅을 눌러 도서 추천 질문을
              시작해보세요.
            </div>
          ) : null}
          {(sessions ?? []).map((session) => (
            <div key={session.id} className="group relative">
              <button
                type="button"
                onClick={() => {
                  setMenuOpenSessionId(null);
                  setActiveSessionId(session.id);
                }}
                className={cn(
                  "flex w-full items-center gap-2 rounded-2xl px-3 py-3 pr-10 text-left text-sm transition-colors hover:bg-slate-100",
                  activeSessionId === session.id &&
                    "bg-primary/10 text-primary ring-1 ring-primary/10",
                )}
              >
                <MessageCircle className="size-4 shrink-0 text-muted-foreground" />
                <span className="truncate">{session.title || "새 채팅"}</span>
              </button>
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  setMenuOpenSessionId((value) =>
                    value === session.id ? null : session.id,
                  );
                }}
                className="absolute right-2 top-1/2 hidden size-7 -translate-y-1/2 items-center justify-center rounded-md text-muted-foreground hover:bg-background hover:text-foreground group-hover:flex"
                aria-label="채팅방 메뉴 열기"
              >
                <MoreHorizontal className="size-4" />
              </button>
              {menuOpenSessionId === session.id && (
                <div className="absolute right-2 top-10 z-20 rounded-xl border bg-popover p-1 shadow-lg">
                  <button
                    type="button"
                    onClick={() => void handleDeleteSession(session)}
                    className="flex w-28 items-center gap-2 rounded-lg px-2 py-2 text-sm text-destructive hover:bg-accent"
                  >
                    <Trash2 className="size-4" />
                    삭제
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      </aside>

      <section className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <div className="border-b bg-white/90 px-4 py-3 backdrop-blur md:hidden">
          <CharacterSummaryCard
            nickname={user ? character?.characterNickname : "비로그인 북케몬"}
            imageUrl={user ? character?.currentImageUrl : null}
            compact
          />
          <div className="mb-3 mt-3 flex items-center justify-between gap-3">
            <div className="text-xs text-muted-foreground">
              채팅방 {(sessions ?? []).length}/{maxChatCount}
            </div>
            <Button
              size="sm"
              onClick={handleCreateChat}
              disabled={(sessions ?? []).length >= maxChatCount}
            >
              <Plus className="size-4" />새 채팅
            </Button>
          </div>
          <div className="flex items-center gap-2 overflow-x-auto">
            {(sessions ?? []).map((session) => (
              <Button
                key={session.id}
                type="button"
                size="sm"
                variant={
                  activeSessionId === session.id ? "secondary" : "outline"
                }
                onClick={() => activateSession(session.id)}
                className="max-w-40 shrink-0 justify-start truncate"
              >
                {session.title || "새 채팅"}
              </Button>
            ))}
          </div>
        </div>

        {errorMessage && (
          <div className="mx-4 mt-4 rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive md:mx-6">
            {errorMessage}
          </div>
        )}

        <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden">
          {loadingMessages ? (
            <div className="flex flex-1 items-center justify-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" /> 메시지를 불러오는
              중...
            </div>
          ) : null}

          {!loadingMessages && !hasVisibleChatContent ? (
            <EmptyChatIntro />
          ) : null}

          {!loadingMessages && hasVisibleChatContent ? (
            <div
              ref={chatScrollRef}
              onScroll={handleChatScroll}
              className="flex-1 overflow-y-auto px-4 py-6 md:px-6"
            >
              <div className="mx-auto flex max-w-3xl flex-col gap-5 pb-4">
                {orderedMessages.map((message) => {
                  const isUserMessage = message.role === "USER";
                  const candidates =
                    !isUserMessage &&
                    Array.isArray(message.metadata?.candidates)
                      ? message.metadata.candidates
                      : [];
                  const fallbackCover =
                    typeof message.metadata?.cover === "string"
                      ? message.metadata.cover
                      : null;
                  const requestId =
                    typeof message.metadata?.requestId === "string"
                      ? message.metadata.requestId
                      : typeof message.metadata?.request_id === "string"
                        ? message.metadata.request_id
                        : null;
                  const recommendationQuery =
                    typeof message.metadata?.query === "string"
                      ? message.metadata.query
                      : null;
                  const shouldHideAssistantPlaceholder =
                    !isUserMessage &&
                    candidates.length > 0 &&
                    isAssistantFailurePlaceholder(message.content);

                  return (
                    <div
                      key={makeMessageKey(message)}
                      className={cn(
                        "flex",
                        isUserMessage ? "justify-end" : "justify-start",
                      )}
                    >
                      <div
                        className={cn(
                          "max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-6 shadow-sm",
                          isUserMessage
                            ? "whitespace-pre-wrap bg-primary text-primary-foreground"
                            : "border bg-white text-card-foreground",
                        )}
                      >
                        {isUserMessage ? (
                          <div>{message.content}</div>
                        ) : shouldHideAssistantPlaceholder ? null : (
                          <ChatMarkdown content={message.content} />
                        )}
                        {!isUserMessage && isRecommendationReasonPending(message) ? (
                          <RecommendationReasonPendingNotice />
                        ) : null}
                        {!isUserMessage &&
                        message.metadata?.guest === true &&
                        message.metadata?.loginPromptRequired === true &&
                        typeof message.metadata.loginPrompt === "string" ? (
                          <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800 [word-break:keep-all]">
                            {message.metadata.loginPrompt}
                          </div>
                        ) : null}
                        {candidates.slice(0, 5).map((candidate, index) => {
                          const isbnKey = normalizeIsbn13(candidate.isbn);
                          const candidateRank =
                            typeof candidate.rank === "number" && candidate.rank > 0
                              ? candidate.rank
                              : index + 1;
                          return (
                            <RecommendationBookCard
                              key={candidate.isbn || candidate.title || index}
                              candidate={candidate}
                              fallbackCover={fallbackCover}
                              shelfSummary={shelfSummary}
                              interactionContext={{
                                requestId,
                                query: recommendationQuery,
                                rank: candidateRank,
                              }}
                              availabilityMessage={
                                isbnKey
                                  ? availabilityMessages[isbnKey]
                                  : undefined
                              }
                              actionState={
                                isbnKey
                                  ? candidateActionStates[isbnKey]
                                  : undefined
                              }
                              isAuthenticated={Boolean(user)}
                              onAddShelf={handleAddBookShelf}
                              onCheckAvailability={handleCheckBookAvailability}
                              onCardClick={handleRecommendationCardClick}
                              onOpenDetail={handleOpenRecommendationDetail}
                              onRequireLogin={handleRequireLogin}
                            />
                          );
                        })}
                      </div>
                    </div>
                  );
                })}

                {pendingUserMessage && sending ? (
                  <div className="flex justify-end">
                    <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl bg-primary px-4 py-3 text-sm leading-6 text-primary-foreground shadow-sm">
                      {pendingUserMessage}
                    </div>
                  </div>
                ) : null}

                {sending ? (
                  <WaitingAssistantBubble status={currentWaitingStatus} />
                ) : null}

                <div ref={chatBottomRef} className="h-1" />
              </div>
            </div>
          ) : null}

          {showJumpToBottom && hasVisibleChatContent ? (
            <button
              type="button"
              onClick={() => scrollToLatestMessage("smooth")}
              className="absolute bottom-4 left-1/2 z-20 flex -translate-x-1/2 items-center gap-2 rounded-full border bg-white px-4 py-2 text-sm font-semibold text-slate-800 shadow-lg shadow-slate-200/70 transition hover:bg-slate-50"
              aria-label={
                hasUnreadAssistantMessage
                  ? "새 답변으로 이동"
                  : "채팅 맨 아래로 이동"
              }
            >
              <ChevronDown className="size-4" />
              {hasUnreadAssistantMessage ? "새 답변 도착" : "맨 아래로"}
            </button>
          ) : null}
        </div>

        <div className="sticky bottom-0 border-t bg-white/95 px-4 py-4 backdrop-blur md:px-6">
          {isGuest && (
            <div className="mx-auto mb-3 max-w-3xl rounded-2xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm leading-6 text-sky-800 [word-break:keep-all]">
              비로그인 대화 내용은 이 브라우저에만 저장됩니다. 로그인하면 서재,
              리뷰, 평점까지 반영한 추천을 받을 수 있어요.
            </div>
          )}
          {reachedUserMessageLimit && (
            <div className="mx-auto mb-3 max-w-3xl rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-800">
              이 채팅방에서는 질문을 최대 {maxUserMessageCount}개까지 보낼 수
              있습니다. 새 채팅으로 이어서 질문해 주세요.
            </div>
          )}
          <form
            onSubmit={handleSendMessage}
            className="mx-auto flex max-w-3xl items-end gap-2 rounded-3xl border bg-white p-2 shadow-lg shadow-slate-200/70"
          >
            <textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              rows={1}
              placeholder={
                reachedUserMessageLimit
                  ? "새 채팅으로 이어서 질문해 주세요."
                  : isGuest
                    ? "선호 장르, 싫어하는 분위기, 독서 레벨을 편하게 말해주세요."
                    : "찾고 싶은 책, 분위기, 장르를 입력해주세요."
              }
              className="max-h-36 min-h-10 flex-1 resize-none rounded-2xl bg-transparent px-4 py-2 text-sm outline-none placeholder:text-muted-foreground"
              disabled={reachedUserMessageLimit}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                }
              }}
            />
            <Button
              type="submit"
              size="icon"
              className="rounded-2xl"
              disabled={!draft.trim() || sending || reachedUserMessageLimit}
              aria-label="메시지 전송"
            >
              {sending ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Send className="size-4" />
              )}
            </Button>
          </form>
        </div>
      </section>

      {detailCandidate ? (
        <RecommendationBookDetailModal
          item={detailCandidate}
          onClose={() => setDetailCandidate(null)}
        />
      ) : null}
    </main>
  );
};

export default HomePage;
