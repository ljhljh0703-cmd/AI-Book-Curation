package com.taeo.bookcuration.auth.service;

import com.taeo.bookcuration.auth.oauth2.SocialOAuth2Profile;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

import java.util.Optional;
import java.util.UUID;

@Service
@RequiredArgsConstructor
public class SocialAuthSessionService {

    public static final String PENDING_SOCIAL_SIGNUP_KEY = "BOOK_PENDING_SOCIAL_SIGNUP";
    public static final String SOCIAL_LINK_INTENT_KEY = "BOOK_SOCIAL_LINK_INTENT";

    private final ObjectProvider<HttpServletRequest> requestProvider;

    public void storePendingSignup(SocialOAuth2Profile profile) {
        HttpSession session = getRequiredSession();
        session.setAttribute(PENDING_SOCIAL_SIGNUP_KEY, new PendingSocialSignupSessionData(
                profile.provider(),
                profile.providerUserId(),
                profile.email(),
                profile.nickname()
        ));
    }

    public Optional<PendingSocialSignupSessionData> getPendingSignup() {
        HttpSession session = getSession(false);
        if (session == null) {
            return Optional.empty();
        }
        Object value = session.getAttribute(PENDING_SOCIAL_SIGNUP_KEY);
        return value instanceof PendingSocialSignupSessionData data
                ? Optional.of(data)
                : Optional.empty();
    }

    public void clearPendingSignup() {
        HttpSession session = getSession(false);
        if (session != null) {
            session.removeAttribute(PENDING_SOCIAL_SIGNUP_KEY);
        }
    }

    public void storeLinkIntent(UUID userId, String provider) {
        HttpSession session = getRequiredSession();
        session.setAttribute(SOCIAL_LINK_INTENT_KEY, new SocialLinkSessionData(userId, provider));
    }

    public Optional<SocialLinkSessionData> getLinkIntent() {
        HttpSession session = getSession(false);
        if (session == null) {
            return Optional.empty();
        }
        Object value = session.getAttribute(SOCIAL_LINK_INTENT_KEY);
        return value instanceof SocialLinkSessionData data
                ? Optional.of(data)
                : Optional.empty();
    }

    public void clearLinkIntent() {
        HttpSession session = getSession(false);
        if (session != null) {
            session.removeAttribute(SOCIAL_LINK_INTENT_KEY);
        }
    }

    private HttpSession getRequiredSession() {
        HttpSession session = getSession(true);
        if (session == null) {
            throw new IllegalStateException("세션을 생성할 수 없습니다.");
        }
        return session;
    }

    private HttpSession getSession(boolean create) {
        HttpServletRequest request = requestProvider.getIfAvailable();
        if (request == null) {
            return null;
        }
        return request.getSession(create);
    }
}
