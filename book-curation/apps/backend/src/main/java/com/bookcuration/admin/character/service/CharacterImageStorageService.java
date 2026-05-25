package com.taeo.bookcuration.admin.character.service;

import com.taeo.bookcuration.admin.character.dto.AdminCharacterDtos.CharacterImageUploadResponse;
import com.taeo.bookcuration.config.FileStorageProperties;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;

@Service
@RequiredArgsConstructor
public class CharacterImageStorageService {

    private static final Map<String, String> EXTENSIONS_BY_CONTENT_TYPE = Map.of(
            "image/png", "png",
            "image/jpeg", "jpg",
            "image/gif", "gif"
    );

    private final FileStorageProperties fileStorageProperties;

    public CharacterImageUploadResponse store(MultipartFile file) {
        validateBasicFile(file);

        String contentType = normalizeContentType(file.getContentType());
        String extension = EXTENSIONS_BY_CONTENT_TYPE.get(contentType);
        if (extension == null) {
            throw new IllegalArgumentException("캐릭터 이미지는 PNG, JPG, GIF 파일만 업로드할 수 있습니다.");
        }

        ImageSize imageSize = readAndValidateImageSize(file);
        String storedFileName = UUID.randomUUID().toString().replace("-", "") + "." + extension;
        Path targetDirectory = fileStorageProperties.getRootPath().resolve("characters").normalize();
        Path targetFile = targetDirectory.resolve(storedFileName).normalize();

        try {
            Files.createDirectories(targetDirectory);
            try (InputStream inputStream = file.getInputStream()) {
                Files.copy(inputStream, targetFile, StandardCopyOption.REPLACE_EXISTING);
            }
        } catch (IOException e) {
            throw new IllegalStateException("캐릭터 이미지 저장 중 오류가 발생했습니다.", e);
        }

        String imageUrl = normalizePublicPrefix(fileStorageProperties.getPublicUrlPrefix()) + "/characters/" + storedFileName;
        return new CharacterImageUploadResponse(
                imageUrl,
                sanitizeOriginalFilename(file.getOriginalFilename()),
                contentType,
                file.getSize(),
                imageSize.width(),
                imageSize.height()
        );
    }

    private void validateBasicFile(MultipartFile file) {
        if (file == null || file.isEmpty()) {
            throw new IllegalArgumentException("업로드할 캐릭터 이미지를 선택해 주세요.");
        }

        long maxSizeBytes = fileStorageProperties.getCharacterImage().getMaxSizeBytes();
        if (file.getSize() > maxSizeBytes) {
            throw new IllegalArgumentException("캐릭터 이미지 용량은 최대 2MB까지 업로드할 수 있습니다.");
        }
    }

    private ImageSize readAndValidateImageSize(MultipartFile file) {
        BufferedImage image;
        try (InputStream inputStream = file.getInputStream()) {
            image = ImageIO.read(inputStream);
        } catch (IOException e) {
            throw new IllegalArgumentException("이미지 파일을 읽을 수 없습니다.", e);
        }

        if (image == null) {
            throw new IllegalArgumentException("손상되었거나 지원하지 않는 이미지 파일입니다.");
        }

        int width = image.getWidth();
        int height = image.getHeight();
        FileStorageProperties.CharacterImage policy = fileStorageProperties.getCharacterImage();

        if (width < policy.getMinWidth() || height < policy.getMinHeight()) {
            throw new IllegalArgumentException("캐릭터 이미지는 최소 128x128px 이상이어야 합니다.");
        }
        if (width > policy.getMaxWidth() || height > policy.getMaxHeight()) {
            throw new IllegalArgumentException("캐릭터 이미지는 최대 1024x1024px 이하만 업로드할 수 있습니다.");
        }

        double aspectRatio = (double) width / (double) height;
        if (aspectRatio < policy.getMinAspectRatio() || aspectRatio > policy.getMaxAspectRatio()) {
            throw new IllegalArgumentException("캐릭터 이미지는 정사각형에 가까운 비율이어야 합니다. 권장 비율은 1:1입니다.");
        }

        return new ImageSize(width, height);
    }

    private static String normalizeContentType(String contentType) {
        return contentType == null ? "" : contentType.trim().toLowerCase(Locale.ROOT);
    }

    private static String normalizePublicPrefix(String value) {
        if (value == null || value.isBlank()) {
            return "/uploads";
        }
        String normalized = value.trim();
        if (!normalized.startsWith("/")) {
            normalized = "/" + normalized;
        }
        return normalized.replaceAll("/+$", "");
    }

    private static String sanitizeOriginalFilename(String originalFilename) {
        if (originalFilename == null || originalFilename.isBlank()) {
            return null;
        }
        return Path.of(originalFilename).getFileName().toString();
    }

    private record ImageSize(int width, int height) {
    }
}
