package com.taeo.bookcuration.common;

import com.taeo.bookcuration.auth.exception.AccountStatusAuthenticationException;
import lombok.extern.slf4j.Slf4j;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.multipart.MaxUploadSizeExceededException;

import java.util.LinkedHashMap;
import java.util.Map;

@Slf4j
@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(IllegalArgumentException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public Map<String, String> handleIllegalArgument(IllegalArgumentException e) {
        log.warn("IllegalArgumentException: {}", e.getMessage(), e);
        return Map.of("message", e.getMessage());
    }

    @ExceptionHandler(IllegalStateException.class)
    @ResponseStatus(HttpStatus.INTERNAL_SERVER_ERROR)
    public Map<String, String> handleIllegalState(IllegalStateException e) {
        if (isExpectedVerificationMailFailure(e)) {
            // 수정 포인트: 인증번호 메일 설정/전송 실패는 운영 설정 문제로 분류해 사용자에게는 안전한 메시지를 반환하고 로그에는 원인만 남깁니다.
            log.warn("Verification mail failure: {}", e.getMessage());
            return Map.of("message", e.getMessage());
        }

        log.error("IllegalStateException: {}", e.getMessage(), e);
        return Map.of("message", e.getMessage());
    }


    private static boolean isExpectedVerificationMailFailure(IllegalStateException e) {
        String message = e.getMessage();
        return message != null && message.startsWith("인증번호 메일");
    }

    @ExceptionHandler(AccountStatusAuthenticationException.class)
    @ResponseStatus(HttpStatus.UNAUTHORIZED)
    public Map<String, Object> handleAccountStatusAuthentication(AccountStatusAuthenticationException e) {
        log.warn("AccountStatusAuthenticationException: code={}, message={}, email={}", e.getCode(), e.getMessage(), e.getEmail(), e);
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("code", e.getCode());
        response.put("message", e.getMessage());
        if (e.getEmail() != null && !e.getEmail().isBlank()) {
            response.put("email", e.getEmail());
        }
        return response;
    }

    @ExceptionHandler(BadCredentialsException.class)
    @ResponseStatus(HttpStatus.UNAUTHORIZED)
    public Map<String, String> handleBadCredentials(BadCredentialsException e) {
        // 수정 포인트: 잘못된 비밀번호 입력은 예상 가능한 인증 실패이므로 스택트레이스 없이 경고만 남깁니다.
        log.warn("BadCredentialsException: {}", e.getMessage());
        return Map.of("message", "이메일 또는 비밀번호가 올바르지 않습니다.");
    }

    @ExceptionHandler(DisabledException.class)
    @ResponseStatus(HttpStatus.UNAUTHORIZED)
    public Map<String, String> handleDisabled(DisabledException e) {
        log.warn("DisabledException: {}", e.getMessage(), e);
        return Map.of("message", e.getMessage());
    }

    @ExceptionHandler(DataIntegrityViolationException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public Map<String, String> handleDataIntegrity(DataIntegrityViolationException e) {
        log.error("DataIntegrityViolationException", e);
        return Map.of("message", "요청 데이터가 DB 제약조건과 맞지 않습니다.");
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public Map<String, String> handleValidation(MethodArgumentNotValidException e) {
        String message = e.getBindingResult().getFieldErrors().stream()
                .findFirst()
                .map(error -> error.getField() + ": " + error.getDefaultMessage())
                .orElse("요청값이 올바르지 않습니다.");

        log.warn("MethodArgumentNotValidException: {}", message, e);
        return Map.of("message", message);
    }

    @ExceptionHandler(Exception.class)
    @ResponseStatus(HttpStatus.INTERNAL_SERVER_ERROR)
    public Map<String, String> handleUnknown(Exception e) {
        log.error("Unhandled exception", e);
        return Map.of("message", "서버 오류가 발생했습니다.");
    }

    @ExceptionHandler(MaxUploadSizeExceededException.class)
    @ResponseStatus(HttpStatus.PAYLOAD_TOO_LARGE)
    public Map<String, String> handleMaxUploadSizeExceeded(MaxUploadSizeExceededException e) {
        // 수정 포인트: multipart 제한 초과를 서버 오류 500이 아니라 413으로 응답해 프론트에서 사용자에게 정확히 안내합니다.
        log.warn("MaxUploadSizeExceededException: {}", e.getMessage(), e);
        return Map.of("message", "캐릭터 이미지 용량은 최대 2MB까지 업로드할 수 있습니다.");
    }
}
