package com.taeo.bookcuration.config;

import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public class SocialOAuth2ClientsConfiguredCondition implements Condition {

    @Override
    public boolean matches(ConditionContext context, AnnotatedTypeMetadata metadata) {
        return hasGoogleConfig(context) || hasKakaoConfig(context);
    }

    private boolean hasGoogleConfig(ConditionContext context) {
        return hasText(context, "GOOGLE_CLIENT_ID") && hasText(context, "GOOGLE_CLIENT_SECRET");
    }

    private boolean hasKakaoConfig(ConditionContext context) {
        return hasText(context, "KAKAO_CLIENT_ID");
    }

    private boolean hasText(ConditionContext context, String key) {
        String value = context.getEnvironment().getProperty(key);
        return value != null && !value.trim().isEmpty();
    }
}
