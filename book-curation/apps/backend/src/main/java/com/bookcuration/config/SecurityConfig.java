package com.taeo.bookcuration.config;

import com.taeo.bookcuration.auth.oauth2.OAuth2LoginFailureHandler;
import com.taeo.bookcuration.auth.oauth2.OAuth2LoginSuccessHandler;
import com.taeo.bookcuration.auth.oauth2.SocialOAuth2UserService;
import com.taeo.bookcuration.auth.oauth2.SocialOidcUserService;
import com.taeo.bookcuration.security.ratelimit.ApplicationRateLimitFilter;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.SecurityContextHolderFilter;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;

import java.io.IOException;
import java.util.List;
import java.util.Locale;

@Configuration
@EnableMethodSecurity
@RequiredArgsConstructor
public class SecurityConfig {

    private final CorsProperties corsProperties;
    private final OAuth2LoginSuccessHandler oauth2LoginSuccessHandler;
    private final OAuth2LoginFailureHandler oauth2LoginFailureHandler;
    private final ObjectProvider<ClientRegistrationRepository> clientRegistrationRepositoryProvider;
    private final ObjectProvider<SocialOAuth2UserService> socialOAuth2UserServiceProvider;
    private final ObjectProvider<SocialOidcUserService> socialOidcUserServiceProvider;
    private final Environment environment;
    private final ApplicationRateLimitFilter applicationRateLimitFilter;

    @Bean
    public SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            DaoAuthenticationProvider daoAuthenticationProvider,
            SecurityContextRepository securityContextRepository
    ) throws Exception {
        http
                .cors(cors -> cors.configurationSource(corsConfigurationSource()))
                .csrf(csrf -> csrf
                        .csrfTokenRepository(cookieCsrfTokenRepository())
                        // 수정 포인트: 로그인 전 JSON POST는 세션 CSRF 토큰이 아직 없거나 브라우저 저장소가 초기화된 상태에서
                        // Spring Security의 CSRF 필터가 컨트롤러 진입 전 403("권한이 없거나 요청이 거부되었습니다.")을 반환할 수 있습니다.
                        // 공개 인증/비로그인 API만 예외 처리하고, 로그인 이후 상태 변경 API는 CSRF 보호를 유지합니다.
                        .ignoringRequestMatchers(
                                new AntPathRequestMatcher("/api/auth/signup", "POST"),
                                new AntPathRequestMatcher("/api/auth/social-signup/complete", "POST"),
                                new AntPathRequestMatcher("/api/auth/login", "POST"),
                                new AntPathRequestMatcher("/api/auth/password-reset/send-code", "POST"),
                                new AntPathRequestMatcher("/api/auth/password-reset/confirm", "POST"),
                                new AntPathRequestMatcher("/api/auth/dormant/send-code", "POST"),
                                new AntPathRequestMatcher("/api/auth/dormant/confirm", "POST"),
                                new AntPathRequestMatcher("/api/public/chats/recommend", "POST")
                        ))
                .securityContext(context -> context.securityContextRepository(securityContextRepository))
                .authenticationProvider(daoAuthenticationProvider)
                // 수정 포인트: Cloudflare Free의 rate limiting 한계를 보완하기 위해 Spring Security 체인에서 주요 API 요청 수를 제한합니다.
                .addFilterAfter(applicationRateLimitFilter, SecurityContextHolderFilter.class)
                .exceptionHandling(exceptions -> exceptions
                        .authenticationEntryPoint((request, response, authException) -> writeJsonError(
                                response,
                                HttpServletResponse.SC_UNAUTHORIZED,
                                "로그인이 필요하거나 세션이 만료되었습니다. 다시 로그인해 주세요."
                        ))
                        .accessDeniedHandler((request, response, accessDeniedException) -> writeJsonError(
                                response,
                                HttpServletResponse.SC_FORBIDDEN,
                                "권한이 없거나 요청이 거부되었습니다."
                        ))
                )
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/auth/csrf").permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/auth/oauth2/providers").permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/auth/social-signup/pending").permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/auth/signup/email-availability").permitAll()
                        .requestMatchers(HttpMethod.POST, "/api/auth/signup").permitAll()
                        .requestMatchers(HttpMethod.POST, "/api/auth/password-reset/send-code").permitAll()
                        .requestMatchers(HttpMethod.POST, "/api/auth/password-reset/confirm").permitAll()
                        .requestMatchers(HttpMethod.POST, "/api/auth/dormant/send-code").permitAll()
                        .requestMatchers(HttpMethod.POST, "/api/auth/dormant/confirm").permitAll()
                        .requestMatchers(HttpMethod.POST, "/api/auth/login").permitAll()
                        .requestMatchers(HttpMethod.POST, "/api/auth/social-signup/complete").permitAll()
                        // 수정 포인트: 비로그인 추천 채팅은 기존 로그인 채팅(/api/chats/**)과 분리된 public API만 허용합니다.
                        .requestMatchers(HttpMethod.POST, "/api/public/chats/recommend").permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/public/chats/*/rooms/*/messages").permitAll()
                        // 수정 포인트: 비로그인 추천 이유 polling도 public API입니다.
                        // 추천 카드 생성 후 reason job이 완료되어도 이 경로가 401이면 화면이 계속 "추천 이유 생성 중"에 머뭅니다.
                        .requestMatchers(HttpMethod.GET, "/api/public/chats/recommendation-reasons/**").permitAll()
                        .requestMatchers("/oauth2/**", "/login/oauth2/**").permitAll()
                        // 수정 포인트: NAS에 저장된 캐릭터 이미지는 로그인 없이 브라우저에서 표시되어야 하므로 GET 공개합니다.
                        .requestMatchers(HttpMethod.GET, "/uploads/**").permitAll()
                        .requestMatchers(HttpMethod.HEAD, "/uploads/**").permitAll()
                        .requestMatchers("/api/admin/**").hasRole("ADMIN")
                        .anyRequest().authenticated()
                )
                .formLogin(form -> form.disable())
                .httpBasic(basic -> basic.disable())
                .logout(logout -> logout
                        .logoutUrl("/api/auth/logout")
                        .deleteCookies("JSESSIONID", "XSRF-TOKEN")
                        .invalidateHttpSession(true)
                        .clearAuthentication(true)
                        .logoutSuccessHandler((request, response, authentication) -> response.setStatus(HttpStatus.NO_CONTENT.value()))
                );

        SocialOAuth2UserService socialOAuth2UserService = socialOAuth2UserServiceProvider.getIfAvailable();
        SocialOidcUserService socialOidcUserService = socialOidcUserServiceProvider.getIfAvailable();
        ClientRegistrationRepository clientRegistrationRepository = clientRegistrationRepositoryProvider.getIfAvailable();

        if (clientRegistrationRepository != null && socialOAuth2UserService != null) {
            http.oauth2Login(oauth2 -> oauth2
                    .userInfoEndpoint(userInfo -> userInfo
                            .userService(socialOAuth2UserService)
                            .oidcUserService(socialOidcUserService)
                    )
                    .successHandler(oauth2LoginSuccessHandler)
                    .failureHandler(oauth2LoginFailureHandler)
            );
        }

        return http.build();
    }

    private CookieCsrfTokenRepository cookieCsrfTokenRepository() {
        CookieCsrfTokenRepository repository = CookieCsrfTokenRepository.withHttpOnlyFalse();
        repository.setCookieName("XSRF-TOKEN");
        repository.setHeaderName("X-XSRF-TOKEN");
        repository.setCookiePath("/");
        repository.setCookieCustomizer(cookie -> cookie
                .path("/")
                .sameSite(csrfCookieSameSite())
                .secure(csrfCookieSecure())
        );
        return repository;
    }

    private String csrfCookieSameSite() {
        String value = environment.getProperty("app.security.csrf.cookie.same-site", "lax");
        return switch (value.trim().toLowerCase(Locale.ROOT)) {
            case "none" -> "None";
            case "strict" -> "Strict";
            default -> "Lax";
        };
    }

    private boolean csrfCookieSecure() {
        return Boolean.parseBoolean(environment.getProperty("app.security.csrf.cookie.secure", "false"));
    }

    private void writeJsonError(HttpServletResponse response, int status, String message) throws IOException {
        response.setStatus(status);
        response.setContentType("application/json;charset=UTF-8");
        response.getWriter().write("{\"message\":\"" + message + "\"}");
    }

    @Bean
    public CorsConfigurationSource corsConfigurationSource() {
        return request -> {
            CorsConfiguration config = new CorsConfiguration();
            config.setAllowedOrigins(corsProperties.safeAllowedOrigins());
            config.setAllowedMethods(List.of("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"));
            config.setAllowedHeaders(List.of(
                    "Content-Type",
                    "X-XSRF-TOKEN",
                    "X-CSRF-TOKEN",
                    "Authorization"
            ));
            config.setAllowCredentials(true);
            config.setExposedHeaders(List.of("X-XSRF-TOKEN", "X-CSRF-TOKEN"));
            config.setMaxAge(3600L);
            return config;
        };
    }
}
