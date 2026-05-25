package com.taeo.bookcuration.library.dto;

import java.math.BigDecimal;
import java.util.List;

public final class LibraryDtos {

    private LibraryDtos() {
    }

    public record LibrarySyncResponse(
            int totalCount,
            int savedCount,
            int pageCount
    ) {
    }

    public record LibrarySyncConfigResponse(
            boolean configured,
            String baseUrl,
            int pageSize
    ) {
    }

    public record LibraryPageResponse<T>(
            List<T> content,
            int page,
            int size,
            long totalElements,
            int totalPages,
            boolean hasNext,
            boolean hasPrevious
    ) {
        public static <T> LibraryPageResponse<T> of(List<T> content, int page, int size, long totalElements) {
            int safePage = Math.max(page, 0);
            int safeSize = Math.max(size, 1);
            int totalPages = totalElements == 0 ? 0 : (int) Math.ceil((double) totalElements / safeSize);
            return new LibraryPageResponse<>(
                    content,
                    safePage,
                    safeSize,
                    totalElements,
                    totalPages,
                    safePage + 1 < totalPages,
                    safePage > 0
            );
        }

        public static <T> LibraryPageResponse<T> empty(int page, int size) {
            return of(List.of(), page, size, 0);
        }
    }

    public record NearbyLibraryResponse(
            String libCode,
            String libName,
            String address,
            BigDecimal latitude,
            BigDecimal longitude,
            BigDecimal distanceMeters
    ) {
    }

    public record LibrarySearchResponse(
            String libCode,
            String libName,
            String address,
            BigDecimal latitude,
            BigDecimal longitude
    ) {
    }
}
