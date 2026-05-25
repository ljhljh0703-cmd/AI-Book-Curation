package com.taeo.bookcuration.admin.onboarding.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.OffsetDateTime;

@Getter
@Entity
@Table(
        name = "onboarding_options",
        schema = "book",
        uniqueConstraints = {
                @UniqueConstraint(name = "uk_onboarding_options_group_key", columnNames = {"option_group", "option_key"})
        }
)
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class OnboardingOptionEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "option_group", nullable = false, length = 50)
    private String optionGroup;

    @Column(name = "option_key", nullable = false, length = 100)
    private String optionKey;

    @Column(nullable = false, length = 100)
    private String label;

    @Column(length = 300)
    private String description;

    @Column(name = "character_group_code", length = 50)
    private String characterGroupCode;

    @Column(name = "display_order", nullable = false)
    private Integer displayOrder;

    @Column(nullable = false)
    private Boolean active;

    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;

    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt;

    public static OnboardingOptionEntity create(
            String optionGroup,
            String optionKey,
            String label,
            String description,
            String characterGroupCode,
            Integer displayOrder,
            Boolean active
    ) {
        OnboardingOptionEntity entity = new OnboardingOptionEntity();
        entity.optionGroup = optionGroup;
        entity.optionKey = optionKey;
        entity.update(label, description, characterGroupCode, active);
        entity.changeDisplayOrder(displayOrder);
        return entity;
    }

    public void update(String label, String description, String characterGroupCode, Boolean active) {
        // 수정 포인트: 관리자는 온보딩 노출 문구, 기획 설명, 캐릭터 구분값, 사용 여부를 관리합니다.
        this.label = label;
        this.description = description;
        this.characterGroupCode = characterGroupCode;
        this.active = active == null || active;
    }

    public void changeDisplayOrder(Integer displayOrder) {
        // 수정 포인트: 노출 순서는 숫자 입력이 아니라 드래그앤드랍 결과를 저장합니다.
        this.displayOrder = displayOrder == null || displayOrder < 1 ? 1 : displayOrder;
    }

    @PrePersist
    void prePersist() {
        OffsetDateTime now = OffsetDateTime.now();
        this.createdAt = now;
        this.updatedAt = now;
    }

    @PreUpdate
    void preUpdate() {
        this.updatedAt = OffsetDateTime.now();
    }
}
