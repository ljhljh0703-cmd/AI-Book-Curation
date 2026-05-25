package com.taeo.bookcuration.chat.dto;

import com.taeo.bookcuration.chat.client.AiRecommendationClient.BookCandidate;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;

public class GuestChatDtos {
    public record GuestChatHistoryItem(
            @NotBlank(message = "대화 역할이 비어 있습니다.")
            @Pattern(regexp = "user|assistant", message = "대화 역할은 user 또는 assistant만 허용됩니다.")
            String role,

            @NotBlank(message = "대화 내용이 비어 있습니다.")
            @Size(max = 1200, message = "대화 이력은 항목당 1200자 이하여야 합니다.")
            String content,

            OffsetDateTime createdAt,

            @Size(max = 5)
            List<BookCandidate> candidates,

            // 수정 포인트: 비로그인 멀티턴 승계용 최소 metadata입니다.
            // raw profile이 아니라 intent/context/debug subset만 허용합니다.
            Map<String, Object> metadata
    ) {}

    public record GuestProfileSnapshot(
            @Size(max = 12, message = "선호 장르는 최대 12개까지만 전달할 수 있습니다.")
            List<@Size(max = 40, message = "장르명은 40자 이하여야 합니다.") String> preferredGenres,

            @Size(max = 12, message = "비선호 장르는 최대 12개까지만 전달할 수 있습니다.")
            List<@Size(max = 40, message = "장르명은 40자 이하여야 합니다.") String> dislikedGenres,

            @Size(max = 12, message = "선호 분위기는 최대 12개까지만 전달할 수 있습니다.")
            List<@Size(max = 40, message = "분위기명은 40자 이하여야 합니다.") String> preferredMoods,

            @Size(max = 12, message = "비선호 분위기는 최대 12개까지만 전달할 수 있습니다.")
            List<@Size(max = 40, message = "분위기명은 40자 이하여야 합니다.") String> dislikedMoods,

            @Size(max = 40, message = "독서 레벨은 40자 이하여야 합니다.")
            String readingLevel,

            @Size(max = 1000, message = "게스트 프로필 요약은 1000자 이하여야 합니다.")
            String summary
    ) {}

    public record GuestRecommendRequest(
            @NotBlank(message = "guestSessionId가 필요합니다.")
            @Size(max = 120, message = "guestSessionId는 120자 이하여야 합니다.")
            String guestSessionId,

            @NotBlank(message = "guestRoomId가 필요합니다.")
            @Size(max = 120, message = "guestRoomId는 120자 이하여야 합니다.")
            String guestRoomId,

            @NotBlank(message = "메시지를 입력해주세요.")
            @Size(max = 1500, message = "비로그인 메시지는 1500자 이하여야 합니다.")
            String content,

            @Valid
            @Size(max = 6, message = "비로그인 대화 이력은 최근 6개 메시지만 전달할 수 있습니다.")
            List<GuestChatHistoryItem> history,

            @Valid
            GuestProfileSnapshot guestProfile
    ) {}

    public record GuestAssistantMessage(
            String role,
            String content,
            Map<String, Object> metadata,
            OffsetDateTime createdAt
    ) {}

    public record GuestRecommendResponse(
            boolean guest,
            boolean personalized,
            int maxGuestChatCount,
            int maxGuestUserMessageCount,
            String loginPrompt,
            GuestAssistantMessage assistantMessage
    ) {}

    public record GuestStoredMessage(
            String role,
            String content,
            Map<String, Object> metadata,
            OffsetDateTime createdAt
    ) {}

    public record GuestChatMessagesResponse(
            String guestSessionId,
            String guestRoomId,
            List<GuestStoredMessage> messages
    ) {}
}
