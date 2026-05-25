package com.taeo.bookcuration.auth.oauth2;

import com.taeo.bookcuration.auth.exception.AccountStatusAuthenticationException;
import com.taeo.bookcuration.auth.service.SocialAuthSessionService;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.web.authentication.AuthenticationFailureHandler;
import org.springframework.stereotype.Component;
import org.springframework.web.util.UriComponentsBuilder;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

@Slf4j
@Component
public class OAuth2LoginFailureHandler implements AuthenticationFailureHandler {

    private final String failureRedirectUrl;
    private final SocialAuthSessionService socialAuthSessionService;

    public OAuth2LoginFailureHandler(
            @Value("${app.oauth2.failure-redirect-url:http://localhost:5173/login?socialError=true}") String failureRedirectUrl,
            SocialAuthSessionService socialAuthSessionService
    ) {
        this.failureRedirectUrl = failureRedirectUrl;
        this.socialAuthSessionService = socialAuthSessionService;
    }

    @Override
    public void onAuthenticationFailure(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException exception
    ) throws IOException, ServletException {
        log.warn("OAuth2 login failed: {}", exception.getMessage(), exception);
        socialAuthSessionService.clearLinkIntent();

        UriComponentsBuilder builder = UriComponentsBuilder.fromUriString(failureRedirectUrl)
                .queryParam("message", exception.getMessage())
                .queryParam("socialError", "true");

        AccountStatusAuthenticationException statusException = extractAccountStatusException(exception);
        if (statusException != null) {
            builder.queryParam("errorCode", statusException.getCode());
            if (statusException.getEmail() != null && !statusException.getEmail().isBlank()) {
                builder.queryParam("email", statusException.getEmail());
            }
        }

        response.sendRedirect(builder.build().encode(StandardCharsets.UTF_8).toUriString());
    }

    private AccountStatusAuthenticationException extractAccountStatusException(AuthenticationException exception) {
        if (exception instanceof AccountStatusAuthenticationException direct) {
            return direct;
        }

        if (exception instanceof OAuth2AuthenticationException oauth2Exception
                && oauth2Exception.getCause() instanceof AccountStatusAuthenticationException cause) {
            return cause;
        }

        if (exception.getCause() instanceof AccountStatusAuthenticationException cause) {
            return cause;
        }

        return null;
    }
}
