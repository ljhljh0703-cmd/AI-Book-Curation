package com.taeo.bookcuration.admin.character.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.OffsetDateTime;

@Getter
@Entity
@Table(name = "character_definitions", schema = "book")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class CharacterDefinitionEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "character_key", nullable = false, unique = true, length = 50)
    private String characterKey;

    @Column(name = "default_name", nullable = false, length = 30)
    private String defaultName;

    // 수정 포인트: 기존 단일 이미지 컬럼은 레벨 1 이미지와 동일하게 유지해 기존 조회/호환 흐름이 깨지지 않게 합니다.
    @Column(name = "image_url", nullable = false, length = 500)
    private String imageUrl;

    @Column(name = "level1_image_url", nullable = false, length = 500)
    private String level1ImageUrl;

    @Column(name = "level1_image_original_filename", length = 255)
    private String level1ImageOriginalFilename;

    @Column(name = "level1_image_content_type", length = 100)
    private String level1ImageContentType;

    @Column(name = "level1_image_size_bytes")
    private Long level1ImageSizeBytes;

    @Column(name = "level2_image_url", nullable = false, length = 500)
    private String level2ImageUrl;

    @Column(name = "level2_image_original_filename", length = 255)
    private String level2ImageOriginalFilename;

    @Column(name = "level2_image_content_type", length = 100)
    private String level2ImageContentType;

    @Column(name = "level2_image_size_bytes")
    private Long level2ImageSizeBytes;

    @Column(name = "level3_image_url", nullable = false, length = 500)
    private String level3ImageUrl;

    @Column(name = "level3_image_original_filename", length = 255)
    private String level3ImageOriginalFilename;

    @Column(name = "level3_image_content_type", length = 100)
    private String level3ImageContentType;

    @Column(name = "level3_image_size_bytes")
    private Long level3ImageSizeBytes;

    @Column(name = "level4_image_url", nullable = false, length = 500)
    private String level4ImageUrl;

    @Column(name = "level4_image_original_filename", length = 255)
    private String level4ImageOriginalFilename;

    @Column(name = "level4_image_content_type", length = 100)
    private String level4ImageContentType;

    @Column(name = "level4_image_size_bytes")
    private Long level4ImageSizeBytes;

    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;

    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt;

    public static CharacterDefinitionEntity create(
            String characterKey,
            String defaultName,
            CharacterImageValues level1Image,
            CharacterImageValues level2Image,
            CharacterImageValues level3Image,
            CharacterImageValues level4Image
    ) {
        CharacterDefinitionEntity entity = new CharacterDefinitionEntity();
        entity.update(characterKey, defaultName, level1Image, level2Image, level3Image, level4Image);
        return entity;
    }

    public void update(
            String characterKey,
            String defaultName,
            CharacterImageValues level1Image,
            CharacterImageValues level2Image,
            CharacterImageValues level3Image,
            CharacterImageValues level4Image
    ) {
        // 수정 포인트: 캐릭터 키는 온보딩 옵션 FK와 연결되므로 DB의 ON UPDATE CASCADE로 연결값까지 함께 변경됩니다.
        this.characterKey = characterKey;
        this.defaultName = defaultName;
        applyLevelImages(level1Image, level2Image, level3Image, level4Image);
    }

    private void applyLevelImages(
            CharacterImageValues level1Image,
            CharacterImageValues level2Image,
            CharacterImageValues level3Image,
            CharacterImageValues level4Image
    ) {
        this.imageUrl = level1Image.imageUrl();

        this.level1ImageUrl = level1Image.imageUrl();
        this.level1ImageOriginalFilename = level1Image.originalFilename();
        this.level1ImageContentType = level1Image.contentType();
        this.level1ImageSizeBytes = level1Image.sizeBytes();

        this.level2ImageUrl = level2Image.imageUrl();
        this.level2ImageOriginalFilename = level2Image.originalFilename();
        this.level2ImageContentType = level2Image.contentType();
        this.level2ImageSizeBytes = level2Image.sizeBytes();

        this.level3ImageUrl = level3Image.imageUrl();
        this.level3ImageOriginalFilename = level3Image.originalFilename();
        this.level3ImageContentType = level3Image.contentType();
        this.level3ImageSizeBytes = level3Image.sizeBytes();

        this.level4ImageUrl = level4Image.imageUrl();
        this.level4ImageOriginalFilename = level4Image.originalFilename();
        this.level4ImageContentType = level4Image.contentType();
        this.level4ImageSizeBytes = level4Image.sizeBytes();
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

    public record CharacterImageValues(
            String imageUrl,
            String originalFilename,
            String contentType,
            Long sizeBytes
    ) {
    }
}
