package com.taeo.bookcuration.auth.oauth2;

import com.taeo.bookcuration.auth.service.SocialAuthSessionService;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.stereotype.Component;

import java.io.IOException;

@Component
public class OAuth2LoginSuccessHandler implements AuthenticationSuccessHandler {

    private final String successRedirectUrl;
    private final String signupRedirectUrl;
    private final SocialAuthSessionService socialAuthSessionService;

    public OAuth2LoginSuccessHandler(
            @Value("${app.oauth2.success-redirect-url:http://localhost:5173/oauth/success}") String successRedirectUrl,
            @Value("${app.oauth2.signup-redirect-url:http://localhost:5173/signup?socialPending=true}") String signupRedirectUrl,
            SocialAuthSessionService socialAuthSessionService
    ) {
        this.successRedirectUrl = successRedirectUrl;
        this.signupRedirectUrl = signupRedirectUrl;
        this.socialAuthSessionService = socialAuthSessionService;
    }

    @Override
    public void onAuthenticationSuccess(
            HttpServletRequest request,
            HttpServletResponse response,
            Authentication authentication
    ) throws IOException, ServletException {
        if (socialAuthSessionService.getPendingSignup().isPresent()) {
            clearSecurityContext(request);
            response.sendRedirect(signupRedirectUrl);
            return;
        }

        response.sendRedirect(successRedirectUrl);
    }

    private void clearSecurityContext(HttpServletRequest request) {
        SecurityContextHolder.clearContext();
        HttpSession session = request.getSession(false);
        if (session != null) {
            session.removeAttribute(HttpSessionSecurityContextRepository.SPRING_SECURITY_CONTEXT_KEY);
        }
    }
}
