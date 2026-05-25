package com.taeo.bookcuration.auth.oauth2;

import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;

import java.util.Locale;
import java.util.Map;

public record SocialOAuth2Profile(
        String provider,
        String providerUserId,
        String email,
        String nickname
) {

    public static SocialOAuth2Profile from(String registrationId, Map<String, Object> attributes) {
        String provider = registrationId.toUpperCase(Locale.ROOT);

        return switch (provider) {
            case "GOOGLE" -> fromGoogle(attributes);
            case "KAKAO" -> fromKakao(attributes);
            default -> throw invalidProvider(provider);
        };
    }

    private static SocialOAuth2Profile fromGoogle(Map<String, Object> attributes) {
        String id = stringValue(attributes.get("sub"));
        String email = normalizeEmail(stringValue(attributes.get("email")));
        String nickname = firstNonBlank(
                stringValue(attributes.get("name")),
                emailPrefix(email),
                "google_user"
        );

        return create("GOOGLE", id, email, nickname);
    }

    @SuppressWarnings("unchecked")
    private static SocialOAuth2Profile fromKakao(Map<String, Object> attributes) {
        String id = stringValue(attributes.get("id"));

        Map<String, Object> kakaoAccount = asMap(attributes.get("kakao_account"));
        Map<String, Object> profile = asMap(kakaoAccount.get("profile"));

        String email = normalizeEmail(stringValue(kakaoAccount.get("email")));
        String nickname = firstNonBlank(
                stringValue(profile.get("nickname")),
                emailPrefix(email),
                "kakao_user"
        );

        return create("KAKAO", id, email, nickname);
    }

    private static SocialOAuth2Profile create(String provider, String providerUserId, String email, String nickname) {
        if (providerUserId == null || providerUserId.isBlank()) {
            throw new OAuth2AuthenticationException(
                    new OAuth2Error("invalid_social_profile"),
                    provider + " provider_user_id를 찾을 수 없습니다."
            );
        }

        return new SocialOAuth2Profile(
                provider,
                providerUserId,
                email,
                truncate(nickname, 50)
        );
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> asMap(Object value) {
        if (value instanceof Map<?, ?> map) {
            return (Map<String, Object>) map;
        }
        return Map.of();
    }

    private static String stringValue(Object value) {
        return value == null ? null : String.valueOf(value);
    }

    private static String normalizeEmail(String email) {
        if (email == null || email.isBlank()) {
            return null;
        }
        return email.trim().toLowerCase(Locale.ROOT);
    }

    private static String emailPrefix(String email) {
        if (email == null || email.isBlank() || !email.contains("@")) {
            return null;
        }
        return email.substring(0, email.indexOf('@'));
    }

    private static String firstNonBlank(String... values) {
        for (String value : values) {
            if (value != null && !value.isBlank()) {
                return value.trim();
            }
        }
        return null;
    }

    private static String truncate(String value, int maxLength) {
        if (value == null || value.length() <= maxLength) {
            return value;
        }
        return value.substring(0, maxLength);
    }

    private static OAuth2AuthenticationException invalidProvider(String provider) {
        return new OAuth2AuthenticationException(
                new OAuth2Error("unsupported_provider"),
                "지원하지 않는 소셜 로그인 provider입니다: " + provider
        );
    }
}
