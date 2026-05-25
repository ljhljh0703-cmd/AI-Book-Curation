package com.taeo.bookcuration.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

import java.nio.file.Path;
import java.util.Set;

@Component
@ConfigurationProperties(prefix = "app.file-storage")
public class FileStorageProperties {

    /** 수정 포인트: K3s/NAS에서는 이 경로를 hostPath 또는 PVC로 마운트해 업로드 파일을 영구 보관합니다. */
    private Path rootPath = Path.of("/app/uploads");

    /** 수정 포인트: 브라우저가 접근할 공개 URL prefix입니다. SecurityConfig와 WebMvc 설정에서 /uploads/**를 공개합니다. */
    private String publicUrlPrefix = "/uploads";

    private CharacterImage characterImage = new CharacterImage();

    public Path getRootPath() {
        return rootPath;
    }

    public void setRootPath(Path rootPath) {
        this.rootPath = rootPath;
    }

    public String getPublicUrlPrefix() {
        return publicUrlPrefix;
    }

    public void setPublicUrlPrefix(String publicUrlPrefix) {
        this.publicUrlPrefix = publicUrlPrefix;
    }

    public CharacterImage getCharacterImage() {
        return characterImage;
    }

    public void setCharacterImage(CharacterImage characterImage) {
        this.characterImage = characterImage;
    }

    public static class CharacterImage {
        private long maxSizeBytes = 2L * 1024L * 1024L;
        private int minWidth = 128;
        private int minHeight = 128;
        private int maxWidth = 1024;
        private int maxHeight = 1024;
        private double minAspectRatio = 0.8;
        private double maxAspectRatio = 1.25;
        private Set<String> allowedContentTypes = Set.of("image/png", "image/jpeg", "image/gif");

        public long getMaxSizeBytes() {
            return maxSizeBytes;
        }

        public void setMaxSizeBytes(long maxSizeBytes) {
            this.maxSizeBytes = maxSizeBytes;
        }

        public int getMinWidth() {
            return minWidth;
        }

        public void setMinWidth(int minWidth) {
            this.minWidth = minWidth;
        }

        public int getMinHeight() {
            return minHeight;
        }

        public void setMinHeight(int minHeight) {
            this.minHeight = minHeight;
        }

        public int getMaxWidth() {
            return maxWidth;
        }

        public void setMaxWidth(int maxWidth) {
            this.maxWidth = maxWidth;
        }

        public int getMaxHeight() {
            return maxHeight;
        }

        public void setMaxHeight(int maxHeight) {
            this.maxHeight = maxHeight;
        }

        public double getMinAspectRatio() {
            return minAspectRatio;
        }

        public void setMinAspectRatio(double minAspectRatio) {
            this.minAspectRatio = minAspectRatio;
        }

        public double getMaxAspectRatio() {
            return maxAspectRatio;
        }

        public void setMaxAspectRatio(double maxAspectRatio) {
            this.maxAspectRatio = maxAspectRatio;
        }

        public Set<String> getAllowedContentTypes() {
            return allowedContentTypes;
        }

        public void setAllowedContentTypes(Set<String> allowedContentTypes) {
            this.allowedContentTypes = allowedContentTypes;
        }
    }
}
