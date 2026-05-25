package com.taeo.bookcuration.admin.character.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import java.time.OffsetDateTime;

public final class AdminCharacterDtos {

    private AdminCharacterDtos() {
    }

    public record CharacterRequest(
            // 수정 포인트: 온보딩 독자 유형 카드와 연결되는 내부 키입니다. 삭제 없이 수정만 허용합니다.
            @NotBlank
            @Size(max = 50)
            @Pattern(regexp = "^[A-Za-z0-9_-]+$", message = "characterKey는 영문, 숫자, _, -만 사용할 수 있습니다.")
            String characterKey,
            @NotBlank
            @Size(max = 30)
            String defaultName,
            // 수정 포인트: 성장형 캐릭터 발급을 위해 레벨 1~4 이미지는 모두 필수로 받습니다.
            @Valid @NotNull CharacterLevelImageRequest level1Image,
            @Valid @NotNull CharacterLevelImageRequest level2Image,
            @Valid @NotNull CharacterLevelImageRequest level3Image,
            @Valid @NotNull CharacterLevelImageRequest level4Image
    ) {
    }

    public record CharacterLevelImageRequest(
            @NotBlank
            @Size(max = 500)
            String imageUrl,
            @Size(max = 255)
            String originalFilename,
            @Size(max = 100)
            String contentType,
            Long sizeBytes
    ) {
    }

    public record CharacterResponse(
            Long id,
            String characterKey,
            String defaultName,
            CharacterLevelImageResponse level1Image,
            CharacterLevelImageResponse level2Image,
            CharacterLevelImageResponse level3Image,
            CharacterLevelImageResponse level4Image,
            OffsetDateTime createdAt,
            OffsetDateTime updatedAt
    ) {
    }

    public record CharacterLevelImageResponse(
            int level,
            String imageUrl,
            String originalFilename,
            String contentType,
            Long sizeBytes
    ) {
    }

    public record CharacterImageUploadResponse(
            String imageUrl,
            String originalFilename,
            String contentType,
            long sizeBytes,
            int width,
            int height
    ) {
    }
}
