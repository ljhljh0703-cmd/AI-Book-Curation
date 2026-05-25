import { api } from "./authApi";
import type {
  ChatMessage,
  ChatSession,
  ChatSessionListResponse,
  GuestChatMessagesResponse,
  GuestRecommendRequest,
  GuestRecommendResponse,
  RecommendationReasonStatusResponse,
  SendChatMessageResponse,
} from "../types/chat";

const API_PREFIX = "/api";

export const fetchChatSessions = async (): Promise<ChatSessionListResponse> => {
  const res = await api.get<ChatSessionListResponse>(`${API_PREFIX}/chats`);
  return res.data;
};

export const createChatSession = async (): Promise<ChatSession> => {
  // 수정 포인트: 새 채팅 버튼 클릭 시 서버에 채팅방을 먼저 생성해서 새로고침 후에도 목록이 유지되도록 한다.
  const res = await api.post<ChatSession>(`${API_PREFIX}/chats`, {});
  return res.data;
};

export const fetchChatMessages = async (
  sessionId: string,
): Promise<ChatMessage[]> => {
  const res = await api.get<ChatMessage[]>(
    `${API_PREFIX}/chats/${sessionId}/messages`,
  );
  return res.data;
};

export const sendNewChatMessage = async (
  content: string,
): Promise<SendChatMessageResponse> => {
  // 수정 포인트: 빈 채팅방 생성을 막기 위해 첫 메시지 전송 시점에 채팅방을 함께 생성합니다.
  const res = await api.post<SendChatMessageResponse>(
    `${API_PREFIX}/chats/messages`,
    { content },
  );
  return res.data;
};

export const sendChatMessage = async (
  sessionId: string,
  content: string,
): Promise<SendChatMessageResponse> => {
  const res = await api.post<SendChatMessageResponse>(
    `${API_PREFIX}/chats/${sessionId}/messages`,
    { content },
  );
  return res.data;
};

export const deleteChatSession = async (sessionId: string): Promise<void> => {
  // 수정 포인트: 채팅방 삭제는 서버에서 실제 삭제가 아니라 DELETED 상태로 바꾸는 soft delete API를 호출한다.
  await api.delete(`${API_PREFIX}/chats/${sessionId}`);
};

export const sendGuestChatMessage = async (
  payload: GuestRecommendRequest,
): Promise<GuestRecommendResponse> => {
  // 수정 포인트: 비로그인 추천은 기존 로그인 채팅 API와 분리된 public API를 호출합니다.
  const res = await api.post<GuestRecommendResponse>(
    `${API_PREFIX}/public/chats/recommend`,
    payload,
  );
  return res.data;
};

export const fetchGuestChatMessages = async (
  guestSessionId: string,
  guestRoomId: string,
): Promise<GuestChatMessagesResponse> => {
  // 수정 포인트: 비로그인 채팅 새로고침 복원은 Valkey TTL 임시 저장소를 보조 저장소로 사용합니다.
  const res = await api.get<GuestChatMessagesResponse>(
    `${API_PREFIX}/public/chats/${guestSessionId}/rooms/${guestRoomId}/messages`,
  );
  return res.data;
};

export const fetchRecommendationReasons = async (
  requestId: string,
): Promise<RecommendationReasonStatusResponse> => {
  const res = await api.get<RecommendationReasonStatusResponse>(
    `${API_PREFIX}/chats/recommendation-reasons/${requestId}`,
  );
  return res.data;
};

export const fetchGuestRecommendationReasons = async (
  requestId: string,
): Promise<RecommendationReasonStatusResponse> => {
  const res = await api.get<RecommendationReasonStatusResponse>(
    `${API_PREFIX}/public/chats/recommendation-reasons/${requestId}`,
  );
  return res.data;
};
