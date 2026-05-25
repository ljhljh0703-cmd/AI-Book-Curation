package com.taeo.bookcuration.chat.controller;

import com.taeo.bookcuration.auth.service.AuthUser;
import com.taeo.bookcuration.chat.dto.ChatDtos.*;
import com.taeo.bookcuration.chat.service.ChatService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;
import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/chats")
@RequiredArgsConstructor
public class ChatController {
    private final ChatService chatService;

    @GetMapping
    public ChatSessionListResponse listSessions(@AuthenticationPrincipal AuthUser authUser) {
        return chatService.listSessions(authUser.id());
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public ChatSessionResponse createSession(@AuthenticationPrincipal AuthUser authUser, @Valid @RequestBody(required = false) CreateChatSessionRequest request) {
        return chatService.createSession(authUser.id(), request == null ? null : request.title());
    }


    @PostMapping("/messages")
    public SendChatMessageResponse sendMessageToNewSession(
            @AuthenticationPrincipal AuthUser authUser,
            @Valid @RequestBody SendChatMessageRequest request
    ) {
        // 수정 포인트: 빈 채팅방이 목록에 남지 않도록 첫 메시지를 보낼 때만 채팅방을 생성합니다.
        return chatService.sendMessageToNewSession(authUser.id(), request.content());
    }

    @GetMapping("/{sessionId}/messages")
    public List<ChatMessageResponse> listMessages(@AuthenticationPrincipal AuthUser authUser, @PathVariable UUID sessionId) {
        return chatService.listMessages(authUser.id(), sessionId);
    }

    @PostMapping("/{sessionId}/messages")
    public SendChatMessageResponse sendMessage(@AuthenticationPrincipal AuthUser authUser, @PathVariable UUID sessionId, @Valid @RequestBody SendChatMessageRequest request) {
        return chatService.sendMessage(authUser.id(), sessionId, request.content());
    }

    @GetMapping("/recommendation-reasons/{requestId}")
    public RecommendationReasonPollResponse pollRecommendationReasons(@AuthenticationPrincipal AuthUser authUser, @PathVariable UUID requestId) {
        return chatService.pollRecommendationReasons(authUser.id(), requestId);
    }

    @DeleteMapping("/{sessionId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void deleteSession(@AuthenticationPrincipal AuthUser authUser, @PathVariable UUID sessionId) {
        chatService.deleteSession(authUser.id(), sessionId);
    }
}
