package com.taeo.bookcuration.user.entity;

import com.taeo.bookcuration.auth.entity.UserEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.MapsId;
import jakarta.persistence.OneToOne;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.OffsetDateTime;
import java.util.UUID;

@Getter
@Entity
@Table(name = "user_characters", schema = "book")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class UserCharacterEntity {

    @Id
    @Column(name = "user_id", columnDefinition = "uuid")
    private UUID userId;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @MapsId
    @JoinColumn(name = "user_id", nullable = false)
    private UserEntity user;

    @Column(name = "character_key", nullable = false, length = 50)
    private String characterKey;

    @Column(name = "stage", nullable = false, length = 30)
    private String stage;

    @Column(name = "character_nickname", length = 30)
    private String characterNickname;

    @Column(name = "review_growth_count", nullable = false)
    private int reviewGrowthCount;

    @Column(name = "current_image_url", length = 500)
    private String currentImageUrl;

    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;

    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt;

    public static UserCharacterEntity createDefault(UserEntity user) {
        UserCharacterEntity character = new UserCharacterEntity();
        character.user = user;
        // 수정 포인트: 온보딩을 건너뛰는 사용자는 DB에 존재하는 DEFAULT_BOOKEMON을 기본 캐릭터로 받습니다.
        // BOOKEMON_EGG는 character_definitions에 없는 레거시 키라 FK 제약조건 오류가 발생할 수 있습니다.
        character.characterKey = "DEFAULT_BOOKEMON";
        character.stage = "EGG";
        // 수정 포인트: 기본 캐릭터는 사용자가 온보딩을 하지 않아도 마이페이지 카드에 바로 표시되어야 합니다.
        character.characterNickname = "북케몬";
        character.reviewGrowthCount = 0;
        character.currentImageUrl = "/bookemon.png";
        return character;
    }

    public void issueInitialCharacter(String characterKey, String defaultName, String currentImageUrl) {
        // 수정 포인트: 온보딩에서 배정된 캐릭터 또는 기존 가입자 기본 캐릭터를 사용자 캐릭터로 발급합니다.
        this.characterKey = characterKey;
        this.stage = "EGG";
        this.currentImageUrl = currentImageUrl;

        // 수정 포인트: 기본 캐릭터에서 독자유형 캐릭터로 최초 발급되는 경우에는
        // 기본 닉네임 "북케몬"을 보존하지 않고 캐릭터 마스터의 기본 이름으로 교체합니다.
        // 이미 사용자가 캐릭터 닉네임을 직접 수정한 경우에는 기존 이름을 유지합니다.
        boolean hasDefaultOrBlankNickname = this.characterNickname == null
                || this.characterNickname.isBlank()
                || "북케몬".equals(this.characterNickname)
                || "북케몬 알".equals(this.characterNickname);

        if (hasDefaultOrBlankNickname) {
            this.characterNickname = defaultName;
        }
    }

    public void changeCharacterNickname(String characterNickname) {
        // 수정 포인트: 캐릭터 성장 정보와 분리해 이름만 변경할 수 있게 합니다.
        this.characterNickname = characterNickname;
    }

    public void increaseReviewGrowthCount() {
        // 수정 포인트: 리뷰 작성 완료 이벤트마다 누적 리뷰 수를 증가시키고, 서비스 레이어에서 레벨/이미지를 다시 계산합니다.
        this.reviewGrowthCount += 1;
    }

    public void syncCharacterMasterInfo(String characterKey, String defaultName, String fallbackImageUrl) {
        // 수정 포인트: 캐릭터 마스터 정보 동기화 시 기존 성장 stage를 EGG로 되돌리지 않고 키/기본명/누락 이미지만 보정합니다.
        this.characterKey = characterKey;

        boolean hasDefaultOrBlankNickname = this.characterNickname == null
                || this.characterNickname.isBlank()
                || "북케몬".equals(this.characterNickname)
                || "북케몬 알".equals(this.characterNickname);

        if (hasDefaultOrBlankNickname) {
            this.characterNickname = defaultName;
        }

        if ((this.currentImageUrl == null || this.currentImageUrl.isBlank()) && fallbackImageUrl != null && !fallbackImageUrl.isBlank()) {
            this.currentImageUrl = fallbackImageUrl;
        }
    }

    public void changeStage(String stage, String characterKey, String currentImageUrl) {
        // 수정 포인트: 성장 조건 달성 시 stage와 이미지 경로만 교체하는 구조입니다.
        this.stage = stage;
        this.characterKey = characterKey;
        this.currentImageUrl = currentImageUrl;
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
