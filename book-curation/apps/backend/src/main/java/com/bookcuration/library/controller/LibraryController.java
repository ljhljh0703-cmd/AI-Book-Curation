package com.taeo.bookcuration.library.controller;

import com.taeo.bookcuration.library.dto.LibraryDtos.LibraryPageResponse;
import com.taeo.bookcuration.library.dto.LibraryDtos.LibrarySearchResponse;
import com.taeo.bookcuration.library.dto.LibraryDtos.NearbyLibraryResponse;
import com.taeo.bookcuration.library.repository.LibraryJdbcRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/libraries")
@RequiredArgsConstructor
public class LibraryController {

    // 수정 포인트: 일반 사용자 도서관 검색은 limit 요청값을 받지 않고 10개 단위 페이지네이션으로 고정합니다.
    private static final int LIBRARY_PAGE_SIZE = 10;

    private final LibraryJdbcRepository libraryJdbcRepository;

    @GetMapping("/nearby")
    public LibraryPageResponse<NearbyLibraryResponse> nearby(
            @RequestParam double latitude,
            @RequestParam double longitude,
            @RequestParam(defaultValue = "5000") int radiusMeters,
            @RequestParam(defaultValue = "0") int page
    ) {
        // 수정 포인트: 너무 큰 반경 요청으로 DB 부하가 커지는 것을 방지합니다.
        int safeRadiusMeters = Math.min(Math.max(radiusMeters, 100), 50_000);
        int safePage = Math.max(page, 0);

        return libraryJdbcRepository.findNearby(latitude, longitude, safeRadiusMeters, safePage, LIBRARY_PAGE_SIZE);
    }

    @GetMapping("/search")
    public LibraryPageResponse<LibrarySearchResponse> search(
            @RequestParam String keyword,
            @RequestParam(defaultValue = "0") int page
    ) {
        // 수정 포인트: 일반 사용자용 도서관 검색은 도서관명/주소만 대상으로 하며 libCode 직접 검색은 제외합니다.
        int safePage = Math.max(page, 0);
        return libraryJdbcRepository.searchByKeyword(keyword, safePage, LIBRARY_PAGE_SIZE);
    }
}
