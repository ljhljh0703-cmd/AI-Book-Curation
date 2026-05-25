package com.taeo.bookcuration.chat.controller;

import com.taeo.bookcuration.chat.dto.GuestChatDtos.GuestChatMessagesResponse;
import com.taeo.bookcuration.chat.dto.GuestChatDtos.GuestRecommendRequest;
import com.taeo.bookcuration.chat.dto.GuestChatDtos.GuestRecommendResponse;
import com.taeo.bookcuration.chat.client.AiRecommendationClient.RecommendationReasonStatusResponse;
import com.taeo.bookcuration.chat.service.PublicChatService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/public/chats")
@RequiredArgsConstructor
public class PublicChatController {
    private final PublicChatService publicChatService;

    @PostMapping("/recommend")
    public GuestRecommendResponse recommend(@Valid @RequestBody GuestRecommendRequest request) {
        // 수정 포인트: 기존 /api/chats/** 로그인 채팅과 분리된 비로그인 전용 추천 API입니다.
        return publicChatService.recommend(request);
    }

    @GetMapping("/{guestSessionId}/rooms/{guestRoomId}/messages")
    public GuestChatMessagesResponse messages(
            @PathVariable String guestSessionId,
            @PathVariable String guestRoomId
    ) {
        // 수정 포인트: 비로그인 채팅은 Valkey TTL 임시 저장소 기준으로만 복원하며 로그인 DB로 이관하지 않습니다.
        return publicChatService.loadMessages(guestSessionId, guestRoomId);
    }

    @GetMapping("/recommendation-reasons/{requestId}")
    public RecommendationReasonStatusResponse pollRecommendationReasons(@PathVariable String requestId) {
        return publicChatService.pollRecommendationReasons(requestId);
    }
}
