import type {
  ChatMessage,
  ChatSession,
  GuestChatHistoryItem,
  GuestProfileSnapshot,
  GuestStoredMessage,
} from "../types/chat";

const GUEST_SESSION_ID_KEY = "book-curation-guest-session-id";
const GUEST_CHAT_STATE_KEY = "book-curation-guest-chat-state-v1";

// 수정 포인트: 비로그인은 로그인보다 채팅방 수는 적게, 방당 멀티턴은 조금 더 길게 제공합니다.
export const GUEST_MAX_CHAT_COUNT = 3;
export const GUEST_MAX_USER_MESSAGE_COUNT = 15;
export const GUEST_HISTORY_MESSAGE_LIMIT = 6;

interface GuestChatState {
  sessions: ChatSession[];
  messagesBySessionId: Record<string, ChatMessage[]>;
}

const nowIso = () => new Date().toISOString();

const createId = () => {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
};

const createMessageId = () => Date.now() + Math.floor(Math.random() * 1000);

const safeParseState = (raw: string | null): GuestChatState => {
  if (!raw) return { sessions: [], messagesBySessionId: {} };
  try {
    const parsed = JSON.parse(raw) as GuestChatState;
    return {
      sessions: Array.isArray(parsed.sessions)
        ? parsed.sessions.slice(0, GUEST_MAX_CHAT_COUNT)
        : [],
      messagesBySessionId: parsed.messagesBySessionId ?? {},
    };
  } catch {
    localStorage.removeItem(GUEST_CHAT_STATE_KEY);
    return { sessions: [], messagesBySessionId: {} };
  }
};

const readState = (): GuestChatState =>
  safeParseState(localStorage.getItem(GUEST_CHAT_STATE_KEY));

const writeState = (state: GuestChatState) => {
  localStorage.setItem(
    GUEST_CHAT_STATE_KEY,
    JSON.stringify({
      sessions: state.sessions.slice(0, GUEST_MAX_CHAT_COUNT),
      messagesBySessionId: state.messagesBySessionId,
    }),
  );
};

const normalizeTitle = (value: string) => {
  const compact = value.trim().replace(/\s+/g, " ");
  if (!compact) return "새 채팅";
  return compact.length > 40 ? `${compact.slice(0, 40)}...` : compact;
};

export const getGuestSessionId = () => {
  const existing = localStorage.getItem(GUEST_SESSION_ID_KEY);
  if (existing) return existing;

  const created = createId();
  localStorage.setItem(GUEST_SESSION_ID_KEY, created);
  return created;
};

export const listGuestChatSessions = () => readState().sessions;

export const getGuestChatMessages = (sessionId: string) => {
  const state = readState();
  return state.messagesBySessionId[sessionId] ?? [];
};

export const createGuestChatSession = (title = "새 채팅") => {
  const state = readState();
  if (state.sessions.length >= GUEST_MAX_CHAT_COUNT) {
    throw new Error(
      `비로그인 채팅방은 최대 ${GUEST_MAX_CHAT_COUNT}개까지 사용할 수 있습니다. 기존 채팅방을 삭제하거나 로그인해 주세요.`,
    );
  }

  const timestamp = nowIso();
  const session: ChatSession = {
    id: createId(),
    title: normalizeTitle(title),
    status: "GUEST_ACTIVE",
    createdAt: timestamp,
    updatedAt: timestamp,
  };

  writeState({
    sessions: [session, ...state.sessions].slice(0, GUEST_MAX_CHAT_COUNT),
    messagesBySessionId: { ...state.messagesBySessionId, [session.id]: [] },
  });

  return session;
};

export const deleteGuestChatSession = (sessionId: string) => {
  const state = readState();
  const nextMessages = { ...state.messagesBySessionId };
  delete nextMessages[sessionId];
  writeState({
    sessions: state.sessions.filter((session) => session.id !== sessionId),
    messagesBySessionId: nextMessages,
  });
};

export const touchGuestChatSession = (
  sessionId: string,
  titleSeed?: string,
) => {
  const state = readState();
  const updatedAt = nowIso();
  const sessions = state.sessions.map((session) => {
    if (session.id !== sessionId) return session;
    const hasDefaultTitle = !session.title || session.title === "새 채팅";
    return {
      ...session,
      title:
        hasDefaultTitle && titleSeed
          ? normalizeTitle(titleSeed)
          : session.title,
      updatedAt,
    };
  });
  const target = sessions.find((session) => session.id === sessionId);
  const ordered = target
    ? [target, ...sessions.filter((session) => session.id !== sessionId)]
    : sessions;
  writeState({ ...state, sessions: ordered });
  return target ?? null;
};

export const makeGuestChatMessage = (
  sessionId: string,
  role: ChatMessage["role"],
  content: string,
  metadata: ChatMessage["metadata"] = {},
): ChatMessage => ({
  id: createMessageId(),
  sessionId,
  role,
  content,
  metadata,
  createdAt: nowIso(),
});

export const appendGuestChatMessages = (
  sessionId: string,
  newMessages: ChatMessage[],
) => {
  const state = readState();
  const current = state.messagesBySessionId[sessionId] ?? [];
  writeState({
    ...state,
    messagesBySessionId: {
      ...state.messagesBySessionId,
      [sessionId]: [...current, ...newMessages],
    },
  });
};

export const hydrateGuestStoredMessages = (
  sessionId: string,
  storedMessages: GuestStoredMessage[],
): ChatMessage[] =>
  storedMessages.map((message, index) => ({
    id: createMessageId() + index,
    sessionId,
    role: message.role,
    content: message.content,
    metadata: { ...(message.metadata ?? {}), guest: true },
    createdAt: message.createdAt || nowIso(),
  }));

export const replaceGuestChatMessages = (
  sessionId: string,
  nextMessages: ChatMessage[],
) => {
  const state = readState();
  writeState({
    ...state,
    messagesBySessionId: {
      ...state.messagesBySessionId,
      [sessionId]: nextMessages,
    },
  });
};


const GUEST_HISTORY_METADATA_KEYS = [
  "intent",
  "intentSource",
  "requiresHistory",
  "detectedConsumptionContext",
  "detectedReadingMode",
  "consumptionContextType",
  "visualAttentionLimited",
  "handsFreePreferred",
  "requiresVisualReference",
  "topicQuery",
  "retrievalQuery",
  "rerankerQuery",
  "contextPolicyApplied",
  "multiTurnContextInherited",
  "multiTurnContextSource",
  "multiTurnContextReason",
  "inheritedReadingMode",
  "inheritedConsumptionContext",
  "inheritedRequestedAudienceGroup",
  "pipeline",
] as const;

const buildGuestHistoryMetadata = (
  metadata: ChatMessage["metadata"],
): Record<string, unknown> => {
  if (!metadata) return {};
  const result: Record<string, unknown> = {};
  GUEST_HISTORY_METADATA_KEYS.forEach((key) => {
    const value = metadata[key];
    if (value !== undefined && value !== null) {
      result[key] = value;
    }
  });
  // 수정 포인트: guestProfile 전체를 history에 싣지 않고, 멀티턴 복원용 metadata subset만 전달합니다.
  return result;
};

export const buildGuestHistory = (
  messages: ChatMessage[],
): GuestChatHistoryItem[] => {
  return messages
    .filter(
      (message) => message.role === "USER" || message.role === "ASSISTANT",
    )
    .slice(-GUEST_HISTORY_MESSAGE_LIMIT)
    .map((message) => ({
      role: message.role === "ASSISTANT" ? "assistant" : "user",
      content: message.content.slice(0, 1200),
      createdAt: message.createdAt,
      candidates:
        message.role === "ASSISTANT" && Array.isArray(message.metadata?.candidates)
          ? message.metadata.candidates.slice(0, 5)
          : [],
      metadata:
        message.role === "ASSISTANT"
          ? buildGuestHistoryMetadata(message.metadata)
          : {},
    }));
};

export const buildGuestProfileSnapshot = (
  _messages: ChatMessage[],
): GuestProfileSnapshot => ({
  preferredGenres: [],
  dislikedGenres: [],
  preferredMoods: [],
  dislikedMoods: [],
  readingLevel: null,
  summary: "",
});

export const updateGuestAssistantMessageByRequestId = (
  sessionId: string,
  requestId: string,
  updater: (message: ChatMessage) => ChatMessage,
) => {
  const state = readState();
  const current = state.messagesBySessionId[sessionId] ?? [];
  let changed = false;
  const nextMessages = current.map((message) => {
    const messageRequestId =
      typeof message.metadata?.requestId === "string"
        ? message.metadata.requestId
        : typeof message.metadata?.request_id === "string"
          ? message.metadata.request_id
          : null;
    if (message.role !== "ASSISTANT" || messageRequestId !== requestId) {
      return message;
    }
    changed = true;
    return updater(message);
  });
  if (!changed) return current;
  writeState({
    ...state,
    messagesBySessionId: {
      ...state.messagesBySessionId,
      [sessionId]: nextMessages,
    },
  });
  return nextMessages;
};
