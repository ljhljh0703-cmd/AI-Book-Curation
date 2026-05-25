package com.taeo.bookcuration.library.controller;

import com.taeo.bookcuration.config.Data4LibraryProperties;
import com.taeo.bookcuration.library.dto.LibraryDtos.LibrarySyncConfigResponse;
import com.taeo.bookcuration.library.dto.LibraryDtos.LibrarySyncResponse;
import com.taeo.bookcuration.library.service.LibrarySyncService;
import lombok.RequiredArgsConstructor;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/admin/libraries")
@RequiredArgsConstructor
public class AdminLibraryController {

    private final LibrarySyncService librarySyncService;
    private final Data4LibraryProperties data4LibraryProperties;

    @GetMapping("/sync/config")
    @PreAuthorize("hasRole('ADMIN')")
    public LibrarySyncConfigResponse syncConfig() {
        // 수정 포인트: 관리자 화면에서 API 토큰 존재 여부만 확인하고 실제 토큰 값은 절대 내려주지 않습니다.
        return new LibrarySyncConfigResponse(
                data4LibraryProperties.hasAuthKey(),
                data4LibraryProperties.baseUrl(),
                data4LibraryProperties.safePageSize()
        );
    }

    @PostMapping("/sync")
    @PreAuthorize("hasRole('ADMIN')")
    public LibrarySyncResponse syncLibraries() {
        return librarySyncService.syncLibraries();
    }
}
