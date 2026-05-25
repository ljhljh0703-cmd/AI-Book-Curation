package com.taeo.bookcuration.auth.exception;

import org.springframework.security.authentication.DisabledException;

public class AccountStatusAuthenticationException extends DisabledException {

    private final String code;
    private final String email;

    public AccountStatusAuthenticationException(String code, String message, String email) {
        super(message);
        this.code = code;
        this.email = email;
    }

    public String getCode() {
        return code;
    }

    public String getEmail() {
        return email;
    }
}
