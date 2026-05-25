package com.taeo.bookcuration.security.ratelimit;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RateLimitFilterRegistrationConfig {

    @Bean
    public FilterRegistrationBean<ApplicationRateLimitFilter> applicationRateLimitFilterRegistration(ApplicationRateLimitFilter filter) {
        FilterRegistrationBean<ApplicationRateLimitFilter> registration = new FilterRegistrationBean<>(filter);
        // 수정 포인트: 해당 필터는 Spring Security 체인에만 명시적으로 추가하고, 서블릿 컨테이너 필터로 중복 실행되지 않게 막습니다.
        registration.setEnabled(false);
        return registration;
    }
}
