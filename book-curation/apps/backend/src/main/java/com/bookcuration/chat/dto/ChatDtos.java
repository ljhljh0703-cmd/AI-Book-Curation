package com.taeo.bookcuration.chat.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;

public class ChatDtos {
    public record ChatSessionResponse(String id, String title, String status, OffsetDateTime createdAt, OffsetDateTime updatedAt) {}

    // 수정 포인트: assistant 메시지에 저장한 AI 추천 원문(candidates, cover 등)을 프론트에서 카드 UI로 렌더링할 수 있도록 metadata를 함께 반환합니다.
    public record ChatMessageResponse(Long id, String sessionId, String role, String content, Map<String, Object> metadata, OffsetDateTime createdAt) {}

    public record ChatSessionListResponse(int maxActiveChatCount, int maxUserMessageCount, List<ChatSessionResponse> sessions) {}
    public record CreateChatSessionRequest(@Size(max = 200, message = "채팅방 제목은 200자 이하여야 합니다.") String title) {}
    public record SendChatMessageRequest(@NotBlank(message = "메시지를 입력해주세요.") @Size(max = 4000, message = "메시지는 4000자 이하여야 합니다.") String content) {}
    public record SendChatMessageResponse(ChatSessionResponse session, ChatMessageResponse userMessage, ChatMessageResponse assistantMessage, int maxUserMessageCount) {}
    public record RecommendationReasonPollResponse(String status, ChatMessageResponse assistantMessage, String errorMessage) {}
}
