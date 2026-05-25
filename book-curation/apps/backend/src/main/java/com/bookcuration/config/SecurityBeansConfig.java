package com.taeo.bookcuration.config;

import com.taeo.bookcuration.auth.service.CustomUserDetailsService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.authentication.configuration.AuthenticationConfiguration;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.web.client.RestClient;

@Configuration
public class SecurityBeansConfig {

    @Bean
    public PasswordEncoder passwordEncoder() {
        // 수정 포인트: PasswordEncoder를 SecurityConfig에서 분리하여 AuthService -> SecurityConfig 간접 의존을 제거합니다.
        return new BCryptPasswordEncoder();
    }

    @Bean
    public DaoAuthenticationProvider daoAuthenticationProvider(
            CustomUserDetailsService customUserDetailsService,
            PasswordEncoder passwordEncoder
    ) {
        // 수정 포인트: DaoAuthenticationProvider는 UserDetailsService와 PasswordEncoder만 조합하는 독립 Bean으로 둡니다.
        DaoAuthenticationProvider provider = new DaoAuthenticationProvider(customUserDetailsService);
        provider.setPasswordEncoder(passwordEncoder);
        return provider;
    }

    @Bean
    public SecurityContextRepository securityContextRepository() {
        // 수정 포인트: JSON 로그인 후 세션 저장에 필요한 Bean을 SecurityConfig에서 분리합니다.
        return new HttpSessionSecurityContextRepository();
    }

    @Bean
    public AuthenticationManager authenticationManager(AuthenticationConfiguration authenticationConfiguration) throws Exception {
        // 수정 포인트: AuthController는 SecurityConfig가 아니라 AuthenticationManager Bean만 사용합니다.
        return authenticationConfiguration.getAuthenticationManager();
    }

    @Bean
    public RestClient.Builder restClientBuilder() {
        // 수정 포인트: 외부 API 호출용 RestClient.Builder는 보안 필터 설정과 무관하므로 독립 Bean으로 둡니다.
        return RestClient.builder();
    }
}
