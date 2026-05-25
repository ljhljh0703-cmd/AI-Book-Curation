package com.taeo.bookcuration.config;

import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

import java.util.ArrayList;
import java.util.List;

@Configuration(proxyBeanMethods = false)
public class SocialOAuth2ClientConfig {

    private static final String DEFAULT_GOOGLE_REDIRECT_URI = "{baseUrl}/login/oauth2/code/google";
    private static final String DEFAULT_KAKAO_REDIRECT_URI = "{baseUrl}/login/oauth2/code/kakao";

    @Bean
    @ConditionalOnMissingBean(ClientRegistrationRepository.class)
    @Conditional(SocialOAuth2ClientsConfiguredCondition.class)
    public ClientRegistrationRepository clientRegistrationRepository(Environment environment) {
        List<ClientRegistration> registrations = new ArrayList<>();

        ClientRegistration google = buildGoogleRegistration(environment);
        if (google != null) {
            registrations.add(google);
        }

        ClientRegistration kakao = buildKakaoRegistration(environment);
        if (kakao != null) {
            registrations.add(kakao);
        }

        return new InMemoryClientRegistrationRepository(registrations);
    }

    private ClientRegistration buildGoogleRegistration(Environment environment) {
        String clientId = environment.getProperty("GOOGLE_CLIENT_ID");
        String clientSecret = environment.getProperty("GOOGLE_CLIENT_SECRET");
        if (isBlank(clientId) || isBlank(clientSecret)) {
            return null;
        }

        // 수정: K3s/Ingress/Cloudflare Tunnel 뒤에서 {baseUrl}이 http로 계산되는 문제를 피하기 위해
        // GOOGLE_REDIRECT_URI 또는 Spring Boot 표준 환경변수 값을 우선 사용합니다.
        String redirectUri = firstNonBlank(
                environment.getProperty("GOOGLE_REDIRECT_URI"),
                environment.getProperty("SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_GOOGLE_REDIRECT_URI"),
                DEFAULT_GOOGLE_REDIRECT_URI
        );

        return ClientRegistration.withRegistrationId("google")
                .clientId(clientId)
                .clientSecret(clientSecret)
                .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
                .redirectUri(redirectUri)
                .scope("openid", "profile", "email")
                .authorizationUri("https://accounts.google.com/o/oauth2/v2/auth")
                .tokenUri("https://oauth2.googleapis.com/token")
                .jwkSetUri("https://www.googleapis.com/oauth2/v3/certs")
                .issuerUri("https://accounts.google.com")
                .userInfoUri("https://www.googleapis.com/oauth2/v3/userinfo")
                .userNameAttributeName("sub")
                .clientName("Google")
                .build();
    }

    private ClientRegistration buildKakaoRegistration(Environment environment) {
        String clientId = environment.getProperty("KAKAO_CLIENT_ID");
        String clientSecret = environment.getProperty("KAKAO_CLIENT_SECRET", "");
        if (isBlank(clientId)) {
            return null;
        }

        ClientAuthenticationMethod authenticationMethod = isBlank(clientSecret)
                ? ClientAuthenticationMethod.NONE
                : ClientAuthenticationMethod.CLIENT_SECRET_POST;

        // 수정: K3s/Ingress/Cloudflare Tunnel 뒤에서 {baseUrl}이 http로 계산되는 문제를 피하기 위해
        // KAKAO_REDIRECT_URI 또는 Spring Boot 표준 환경변수 값을 우선 사용합니다.
        String redirectUri = firstNonBlank(
                environment.getProperty("KAKAO_REDIRECT_URI"),
                environment.getProperty("SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KAKAO_REDIRECT_URI"),
                DEFAULT_KAKAO_REDIRECT_URI
        );

        return ClientRegistration.withRegistrationId("kakao")
                .clientId(clientId)
                .clientSecret(clientSecret)
                .clientAuthenticationMethod(authenticationMethod)
                .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
                .redirectUri(redirectUri)
                .scope("profile_nickname", "account_email")
                .authorizationUri("https://kauth.kakao.com/oauth/authorize")
                .tokenUri("https://kauth.kakao.com/oauth/token")
                .userInfoUri("https://kapi.kakao.com/v2/user/me")
                .userNameAttributeName("id")
                .clientName("Kakao")
                .build();
    }

    private String firstNonBlank(String... values) {
        if (values == null) {
            return "";
        }

        for (String value : values) {
            if (!isBlank(value)) {
                return value.trim();
            }
        }

        return "";
    }

    private boolean isBlank(String value) {
        return value == null || value.trim().isEmpty();
    }
}