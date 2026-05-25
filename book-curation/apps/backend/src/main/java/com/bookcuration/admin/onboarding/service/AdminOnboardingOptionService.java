package com.taeo.bookcuration.admin.onboarding.service;

import com.taeo.bookcuration.admin.character.repository.CharacterDefinitionRepository;
import com.taeo.bookcuration.admin.onboarding.dto.AdminOnboardingOptionDtos.OnboardingOptionGroup;
import com.taeo.bookcuration.admin.onboarding.dto.AdminOnboardingOptionDtos.OnboardingOptionReorderRequest;
import com.taeo.bookcuration.admin.onboarding.dto.AdminOnboardingOptionDtos.OnboardingOptionRequest;
import com.taeo.bookcuration.admin.onboarding.dto.AdminOnboardingOptionDtos.OnboardingOptionResponse;
import com.taeo.bookcuration.admin.onboarding.entity.OnboardingOptionEntity;
import com.taeo.bookcuration.admin.onboarding.repository.OnboardingOptionRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
public class AdminOnboardingOptionService {

    private final OnboardingOptionRepository onboardingOptionRepository;
    private final CharacterDefinitionRepository characterDefinitionRepository;

    @Transactional(readOnly = true)
    public List<OnboardingOptionResponse> getOptions(OnboardingOptionGroup optionGroup) {
        String normalizedGroup = optionGroup.name();
        return onboardingOptionRepository.findByOptionGroupOrderByDisplayOrderAscIdAsc(normalizedGroup).stream()
                .map(this::toResponse)
                .toList();
    }

    @Transactional
    public OnboardingOptionResponse createOption(OnboardingOptionRequest request) {
        String normalizedGroup = request.optionGroup().name();
        int nextDisplayOrder = onboardingOptionRepository.findMaxDisplayOrderByOptionGroup(normalizedGroup) + 1;

        // 수정 포인트: optionKey는 사용자 선택값 저장용 내부 식별자이므로 관리자 입력을 받지 않고 서버에서 자동 생성합니다.
        OnboardingOptionEntity saved = onboardingOptionRepository.save(OnboardingOptionEntity.create(
                normalizedGroup,
                generateInternalOptionKey(normalizedGroup),
                request.label().trim(),
                blankToNull(request.description()),
                normalizeAndValidateCharacterGroupCode(normalizedGroup, request.characterGroupCode()),
                nextDisplayOrder,
                request.active()
        ));

        return toResponse(saved);
    }

    @Transactional
    public OnboardingOptionResponse updateOption(Long id, OnboardingOptionRequest request) {
        OnboardingOptionEntity entity = onboardingOptionRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("온보딩 선택지를 찾을 수 없습니다."));

        if (!entity.getOptionGroup().equals(request.optionGroup().name())) {
            throw new IllegalArgumentException("기존 선택지의 그룹은 변경할 수 없습니다. 다른 그룹으로 옮기려면 새로 등록해 주세요.");
        }

        // 수정 포인트: 기존 사용자 선택값과의 연결을 보존하기 위해 내부 optionKey는 수정하지 않습니다.
        entity.update(
                request.label().trim(),
                blankToNull(request.description()),
                normalizeAndValidateCharacterGroupCode(entity.getOptionGroup(), request.characterGroupCode()),
                request.active()
        );
        return toResponse(entity);
    }

    @Transactional
    public List<OnboardingOptionResponse> reorderOptions(OnboardingOptionReorderRequest request) {
        String normalizedGroup = request.optionGroup().name();
        List<OnboardingOptionEntity> entities = onboardingOptionRepository.findByOptionGroupOrderByDisplayOrderAscIdAsc(normalizedGroup);

        if (entities.size() != new HashSet<>(request.orderedIds()).size()) {
            throw new IllegalArgumentException("정렬 대상 항목 개수가 현재 항목 개수와 일치하지 않습니다. 새로고침 후 다시 시도해 주세요.");
        }

        Map<Long, OnboardingOptionEntity> entityById = entities.stream()
                .collect(Collectors.toMap(OnboardingOptionEntity::getId, Function.identity()));

        for (Long orderedId : request.orderedIds()) {
            if (!entityById.containsKey(orderedId)) {
                throw new IllegalArgumentException("현재 그룹에 속하지 않는 항목이 포함되어 있습니다. 새로고침 후 다시 시도해 주세요.");
            }
        }

        // 수정 포인트: 드래그앤드랍으로 넘어온 순서를 1부터 다시 매겨 숫자 간격 관리 문제를 없앱니다.
        for (int index = 0; index < request.orderedIds().size(); index++) {
            OnboardingOptionEntity entity = entityById.get(request.orderedIds().get(index));
            entity.changeDisplayOrder(index + 1);
        }

        return onboardingOptionRepository.findByOptionGroupOrderByDisplayOrderAscIdAsc(normalizedGroup).stream()
                .map(this::toResponse)
                .toList();
    }

    @Transactional
    public void deleteOption(Long id) {
        // 수정 포인트: 현재는 사용자 선택값과 FK로 묶지 않아 관리자 화면에서 항목 자체를 제거할 수 있습니다.
        onboardingOptionRepository.deleteById(id);
    }

    private OnboardingOptionResponse toResponse(OnboardingOptionEntity entity) {
        return new OnboardingOptionResponse(
                entity.getId(),
                entity.getOptionGroup(),
                entity.getLabel(),
                entity.getDescription(),
                entity.getCharacterGroupCode(),
                entity.getDisplayOrder(),
                entity.getActive(),
                entity.getCreatedAt(),
                entity.getUpdatedAt()
        );
    }

    private String generateInternalOptionKey(String optionGroup) {
        String key;
        do {
            key = optionGroup + "_" + UUID.randomUUID()
                    .toString()
                    .replace("-", "")
                    .substring(0, 12)
                    .toUpperCase(Locale.ROOT);
        } while (onboardingOptionRepository.existsByOptionGroupAndOptionKey(optionGroup, key));
        return key;
    }

    private static String blankToNull(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        return value.trim();
    }

    private String normalizeAndValidateCharacterGroupCode(String optionGroup, String value) {
        if (value == null || value.isBlank()) {
            return null;
        }

        String normalizedValue = value.trim();
        if (!"READER_TYPE".equals(optionGroup)) {
            return normalizedValue;
        }

        // 수정 포인트: 독자 유형 카드는 관리자 캐릭터 설정에 등록된 캐릭터만 연결할 수 있게 서버에서도 검증합니다.
        if (!characterDefinitionRepository.existsByCharacterKey(normalizedValue)) {
            throw new IllegalArgumentException("등록된 캐릭터만 독자 유형 카드에 연결할 수 있습니다.");
        }

        return normalizedValue;
    }
}
