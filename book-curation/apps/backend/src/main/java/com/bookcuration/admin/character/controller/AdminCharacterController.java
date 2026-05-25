package com.taeo.bookcuration.admin.character.controller;

import com.taeo.bookcuration.admin.character.dto.AdminCharacterDtos.CharacterImageUploadResponse;
import com.taeo.bookcuration.admin.character.dto.AdminCharacterDtos.CharacterRequest;
import com.taeo.bookcuration.admin.character.dto.AdminCharacterDtos.CharacterResponse;
import com.taeo.bookcuration.admin.character.service.AdminCharacterService;
import com.taeo.bookcuration.admin.character.service.CharacterImageStorageService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import java.util.List;

@RestController
@RequestMapping("/api/admin/characters")
@PreAuthorize("hasRole('ADMIN')")
@RequiredArgsConstructor
public class AdminCharacterController {

    private final AdminCharacterService adminCharacterService;
    private final CharacterImageStorageService characterImageStorageService;

    @GetMapping
    public List<CharacterResponse> getCharacters() {
        return adminCharacterService.getCharacters();
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public CharacterResponse createCharacter(@Valid @RequestBody CharacterRequest request) {
        return adminCharacterService.createCharacter(request);
    }

    @PutMapping("/{id}")
    public CharacterResponse updateCharacter(
            @PathVariable Long id,
            @Valid @RequestBody CharacterRequest request
    ) {
        return adminCharacterService.updateCharacter(id, request);
    }

    @PostMapping("/images")
    @ResponseStatus(HttpStatus.CREATED)
    public CharacterImageUploadResponse uploadCharacterImage(@RequestParam("file") MultipartFile file) {
        // 수정 포인트: 캐릭터 등록/수정 전 이미지 파일만 먼저 업로드하고, 반환된 imageUrl을 캐릭터 저장 API에 사용합니다.
        return characterImageStorageService.store(file);
    }
}
