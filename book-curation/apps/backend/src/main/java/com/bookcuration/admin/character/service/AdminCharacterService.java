package com.taeo.bookcuration.admin.character.service;

import com.taeo.bookcuration.admin.character.dto.AdminCharacterDtos.CharacterLevelImageRequest;
import com.taeo.bookcuration.admin.character.dto.AdminCharacterDtos.CharacterLevelImageResponse;
import com.taeo.bookcuration.admin.character.dto.AdminCharacterDtos.CharacterRequest;
import com.taeo.bookcuration.admin.character.dto.AdminCharacterDtos.CharacterResponse;
import com.taeo.bookcuration.admin.character.entity.CharacterDefinitionEntity;
import com.taeo.bookcuration.admin.character.entity.CharacterDefinitionEntity.CharacterImageValues;
import com.taeo.bookcuration.admin.character.repository.CharacterDefinitionRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Locale;

@Service
@RequiredArgsConstructor
public class AdminCharacterService {

    private final CharacterDefinitionRepository characterDefinitionRepository;

    @Transactional(readOnly = true)
    public List<CharacterResponse> getCharacters() {
        return characterDefinitionRepository.findAllByOrderByIdAsc().stream()
                .map(this::toResponse)
                .toList();
    }

    @Transactional
    public CharacterResponse createCharacter(CharacterRequest request) {
        String characterKey = normalizeCharacterKey(request.characterKey());
        validateUniqueCharacterKey(characterKey, null);

        CharacterDefinitionEntity saved = characterDefinitionRepository.save(CharacterDefinitionEntity.create(
                characterKey,
                normalizeRequired(request.defaultName(), "캐릭터 기본 이름을 입력해 주세요."),
                toImageValues(request.level1Image(), 1),
                toImageValues(request.level2Image(), 2),
                toImageValues(request.level3Image(), 3),
                toImageValues(request.level4Image(), 4)
        ));
        return toResponse(saved);
    }

    @Transactional
    public CharacterResponse updateCharacter(Long id, CharacterRequest request) {
        CharacterDefinitionEntity entity = characterDefinitionRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("캐릭터를 찾을 수 없습니다."));

        String characterKey = normalizeCharacterKey(request.characterKey());
        validateUniqueCharacterKey(characterKey, id);

        // 수정 포인트: 삭제/비활성화 없이 키, 기본 이름, 레벨별 이미지 4개만 수정합니다.
        entity.update(
                characterKey,
                normalizeRequired(request.defaultName(), "캐릭터 기본 이름을 입력해 주세요."),
                toImageValues(request.level1Image(), 1),
                toImageValues(request.level2Image(), 2),
                toImageValues(request.level3Image(), 3),
                toImageValues(request.level4Image(), 4)
        );
        return toResponse(entity);
    }

    private CharacterResponse toResponse(CharacterDefinitionEntity entity) {
        return new CharacterResponse(
                entity.getId(),
                entity.getCharacterKey(),
                entity.getDefaultName(),
                new CharacterLevelImageResponse(1, entity.getLevel1ImageUrl(), entity.getLevel1ImageOriginalFilename(), entity.getLevel1ImageContentType(), entity.getLevel1ImageSizeBytes()),
                new CharacterLevelImageResponse(2, entity.getLevel2ImageUrl(), entity.getLevel2ImageOriginalFilename(), entity.getLevel2ImageContentType(), entity.getLevel2ImageSizeBytes()),
                new CharacterLevelImageResponse(3, entity.getLevel3ImageUrl(), entity.getLevel3ImageOriginalFilename(), entity.getLevel3ImageContentType(), entity.getLevel3ImageSizeBytes()),
                new CharacterLevelImageResponse(4, entity.getLevel4ImageUrl(), entity.getLevel4ImageOriginalFilename(), entity.getLevel4ImageContentType(), entity.getLevel4ImageSizeBytes()),
                entity.getCreatedAt(),
                entity.getUpdatedAt()
        );
    }

    private CharacterImageValues toImageValues(CharacterLevelImageRequest image, int level) {
        if (image == null || image.imageUrl() == null || image.imageUrl().isBlank()) {
            throw new IllegalArgumentException("레벨 " + level + " 캐릭터 이미지를 업로드해 주세요.");
        }
        return new CharacterImageValues(
                image.imageUrl().trim(),
                blankToNull(image.originalFilename()),
                blankToNull(image.contentType()),
                image.sizeBytes()
        );
    }

    private void validateUniqueCharacterKey(String characterKey, Long currentId) {
        boolean duplicated = currentId == null
                ? characterDefinitionRepository.existsByCharacterKey(characterKey)
                : characterDefinitionRepository.existsByCharacterKeyAndIdNot(characterKey, currentId);
        if (duplicated) {
            throw new IllegalArgumentException("이미 사용 중인 캐릭터 키입니다.");
        }
    }

    private static String normalizeCharacterKey(String characterKey) {
        if (characterKey == null || characterKey.isBlank()) {
            throw new IllegalArgumentException("캐릭터 키를 입력해 주세요.");
        }
        return characterKey.trim().toUpperCase(Locale.ROOT);
    }

    private static String normalizeRequired(String value, String message) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(message);
        }
        return value.trim();
    }

    private static String blankToNull(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        return value.trim();
    }
}
