package com.taeo.bookcuration.security.ratelimit;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.taeo.bookcuration.auth.service.AuthUser;
import com.taeo.bookcuration.cache.RedisKeyService;
import com.taeo.bookcuration.cache.RedisRateLimitService;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.lang.NonNull;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;

@Slf4j
@Component
@RequiredArgsConstructor
public class ApplicationRateLimitFilter extends OncePerRequestFilter {

    private static final String TOO_MANY_REQUESTS_BODY = "{\"message\":\"요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.\"}";

    private final RateLimitProperties properties;
    private final ObjectMapper objectMapper;
    private final RedisKeyService redisKeyService;
    private final RedisRateLimitService redisRateLimitService;
    private final Clock clock = Clock.systemUTC();
    private final Map<String, WindowCounter> counters = new ConcurrentHashMap<>();

    private volatile long nextCleanupAtMillis = 0L;

    @Override
    protected void doFilterInternal(
            @NonNull HttpServletRequest request,
            @NonNull HttpServletResponse response,
            @NonNull FilterChain filterChain
    ) throws ServletException, IOException {
        if (!properties.isEnabled() || "OPTIONS".equalsIgnoreCase(request.getMethod())) {
            filterChain.doFilter(request, response);
            return;
        }

        List<MatchedRule> matchedRules = matchRules(request);
        if (matchedRules.isEmpty()) {
            filterChain.doFilter(request, response);
            return;
        }

        HttpServletRequest requestToUse = request;
        String email = extractEmailFromQuery(request);
        boolean shouldInspectBodyEmail = matchedRules.stream().anyMatch(MatchedRule::usesBodyEmail);

        if (shouldInspectBodyEmail && email == null && mayContainJsonBody(request)) {
            try {
                CachedBodyHttpServletRequest wrappedRequest = new CachedBodyHttpServletRequest(
                        request,
                        properties.getMaxCachedRequestBodyBytes()
                );
                requestToUse = wrappedRequest;
                email = extractEmailFromBody(wrappedRequest.getCachedBody()).orElse(null);
            } catch (IOException e) {
                // 수정 포인트: 비정상적으로 큰 인증 요청 본문은 인증 로직까지 보내지 않고 429로 조기 차단합니다.
                MatchedRule rule = matchedRules.getFirst();
                log.warn("Rate limit body inspection failed: method={}, path={}, ip={}, reason={}",
                        request.getMethod(), normalizedPath(request), clientIp(request), e.getMessage());
                writeRateLimitResponse(response, rule.limit(), rule.name());
                return;
            }
        }

        for (MatchedRule rule : matchedRules) {
            String key = buildKey(rule, request, email);
            RateLimitDecision decision = tryConsumeDistributedFirst(key, rule.limit());
            if (!decision.allowed()) {
                log.warn("Rate limit exceeded: rule={}, method={}, path={}, key={}, retryAfterSeconds={}",
                        rule.name(), request.getMethod(), normalizedPath(request), safeLogKey(key), decision.retryAfterSeconds());
                writeRateLimitResponse(response, rule.limit(), rule.name());
                return;
            }

            response.setHeader("X-RateLimit-" + rule.name() + "-Limit", String.valueOf(rule.limit().getCapacity()));
            response.setHeader("X-RateLimit-" + rule.name() + "-Window-Seconds", String.valueOf(rule.limit().windowMillis() / 1000L));
        }

        filterChain.doFilter(requestToUse, response);
    }

    private List<MatchedRule> matchRules(HttpServletRequest request) {
        String method = request.getMethod().toUpperCase(Locale.ROOT);
        String path = normalizedPath(request);

        if ("POST".equals(method) && "/api/auth/login".equals(path)) {
            return List.of(new MatchedRule("login", properties.getLogin(), KeyScope.EMAIL_AND_IP, true));
        }
        if ("POST".equals(method) && "/api/auth/signup".equals(path)) {
            return List.of(new MatchedRule("signup", properties.getSignup(), KeyScope.EMAIL_AND_IP, true));
        }
        if ("GET".equals(method) && "/api/auth/signup/email-availability".equals(path)) {
            return List.of(new MatchedRule("emailAvailability", properties.getEmailAvailability(), KeyScope.EMAIL_AND_IP, false));
        }
        if ("POST".equals(method) && ("/api/auth/password-reset/send-code".equals(path) || "/api/auth/dormant/send-code".equals(path))) {
            return List.of(new MatchedRule("verificationSend", properties.getVerificationSend(), KeyScope.EMAIL_AND_IP, true));
        }
        if ("POST".equals(method) && ("/api/auth/password-reset/confirm".equals(path) || "/api/auth/dormant/confirm".equals(path))) {
            return List.of(new MatchedRule("verificationConfirm", properties.getVerificationConfirm(), KeyScope.EMAIL_AND_IP, true));
        }
        if ("POST".equals(method) && "/api/auth/social-signup/complete".equals(path)) {
            return List.of(new MatchedRule("socialSignupComplete", properties.getSocialSignupComplete(), KeyScope.EMAIL_AND_IP, true));
        }
        if ("GET".equals(method) && "/api/onboarding/books/search".equals(path)) {
            return List.of(new MatchedRule("onboardingBookSearch", properties.getOnboardingBookSearch(), KeyScope.USER_OR_IP, false));
        }
        if ("POST".equals(method) && "/api/chats".equals(path)) {
            return List.of(new MatchedRule("chatSessionCreate", properties.getChatSessionCreate(), KeyScope.USER_OR_IP, false));
        }
        if ("POST".equals(method) && ("/api/chats/messages".equals(path) || isChatSessionMessagePath(path))) {
            return List.of(new MatchedRule("chatMessage", properties.getChatMessage(), KeyScope.USER_OR_IP, false));
        }
        if ("POST".equals(method) && "/api/public/chats/recommend".equals(path)) {
            // 수정 포인트: 비로그인 추천은 분당 제한과 일일 제한을 동시에 적용해 CLOVA/Qdrant 남용을 줄입니다.
            return List.of(
                    new MatchedRule("guestChatMessage", properties.getGuestChatMessage(), KeyScope.IP_ONLY, false),
                    new MatchedRule("guestChatDaily", properties.getGuestChatDaily(), KeyScope.IP_ONLY, false)
            );
        }
        if ("POST".equals(method) && "/api/users/me/book-availability".equals(path)) {
            return List.of(new MatchedRule("bookAvailability", properties.getBookAvailability(), KeyScope.USER_OR_IP, false));
        }
        if ("POST".equals(method) && "/api/admin/characters/images".equals(path)) {
            return List.of(new MatchedRule("adminImageUpload", properties.getAdminImageUpload(), KeyScope.USER_OR_IP, false));
        }
        return List.of();
    }

    private boolean isChatSessionMessagePath(String path) {
        return path.startsWith("/api/chats/") && path.endsWith("/messages") && path.length() > "/api/chats//messages".length();
    }

    private String normalizedPath(HttpServletRequest request) {
        String requestUri = request.getRequestURI();
        String contextPath = request.getContextPath();
        if (contextPath != null && !contextPath.isBlank() && requestUri.startsWith(contextPath)) {
            return requestUri.substring(contextPath.length());
        }
        return requestUri;
    }

    private boolean mayContainJsonBody(HttpServletRequest request) {
        String contentType = request.getContentType();
        return contentType == null || contentType.toLowerCase(Locale.ROOT).contains(MediaType.APPLICATION_JSON_VALUE);
    }

    private String extractEmailFromQuery(HttpServletRequest request) {
        String email = request.getParameter("email");
        return normalizeEmail(email).orElse(null);
    }

    private Optional<String> extractEmailFromBody(byte[] body) {
        if (body.length == 0) {
            return Optional.empty();
        }
        try {
            JsonNode node = objectMapper.readTree(body);
            if (node == null || !node.hasNonNull("email")) {
                return Optional.empty();
            }
            return normalizeEmail(node.get("email").asText());
        } catch (Exception e) {
            return Optional.empty();
        }
    }

    private Optional<String> normalizeEmail(String value) {
        if (value == null || value.isBlank()) {
            return Optional.empty();
        }
        return Optional.of(value.trim().toLowerCase(Locale.ROOT));
    }

    private String buildKey(MatchedRule rule, HttpServletRequest request, String email) {
        String ip = clientIp(request);
        return switch (rule.keyScope()) {
            case EMAIL_AND_IP -> rule.name() + ":email:" + (email == null ? "unknown" : email) + ":ip:" + ip;
            case USER_OR_IP -> rule.name() + ":" + currentUserKey().orElse("ip:" + ip);
            case IP_ONLY -> rule.name() + ":ip:" + ip;
        };
    }

    private Optional<String> currentUserKey() {
        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
        if (authentication == null || !authentication.isAuthenticated() || authentication.getPrincipal() == null) {
            return Optional.empty();
        }
        Object principal = authentication.getPrincipal();
        if (principal instanceof AuthUser authUser) {
            return Optional.of("user:" + authUser.id());
        }
        String name = authentication.getName();
        if (name == null || name.isBlank() || "anonymousUser".equals(name)) {
            return Optional.empty();
        }
        return Optional.of("user:" + name);
    }

    private String clientIp(HttpServletRequest request) {
        if (properties.isTrustProxyHeaders()) {
            String cfConnectingIp = firstHeaderValue(request.getHeader("CF-Connecting-IP"));
            if (cfConnectingIp != null) {
                return cfConnectingIp;
            }
            String xForwardedFor = firstHeaderValue(request.getHeader("X-Forwarded-For"));
            if (xForwardedFor != null) {
                return xForwardedFor;
            }
            String xRealIp = firstHeaderValue(request.getHeader("X-Real-IP"));
            if (xRealIp != null) {
                return xRealIp;
            }
        }
        return request.getRemoteAddr() == null ? "unknown" : request.getRemoteAddr();
    }

    private String firstHeaderValue(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        String first = value.split(",")[0].trim();
        return first.isBlank() ? null : first;
    }

    private RateLimitDecision tryConsumeDistributedFirst(String key, RateLimitProperties.EndpointLimit limit) {
        String redisKey = redisKeyService.key("rate-limit", "backend", key);
        return redisRateLimitService.consume(redisKey, limit)
                .map(decision -> new RateLimitDecision(decision.allowed(), decision.retryAfterSeconds()))
                .orElseGet(() -> tryConsume(key, limit));
    }

    private RateLimitDecision tryConsume(String key, RateLimitProperties.EndpointLimit limit) {
        long now = clock.millis();
        cleanupExpiredCounters(now);
        AtomicBoolean allowed = new AtomicBoolean(false);
        long[] retryAfterMillis = new long[]{limit.windowMillis()};

        counters.compute(key, (ignored, existing) -> {
            if (existing == null || now >= existing.windowEndsAtMillis()) {
                allowed.set(true);
                return new WindowCounter(1, now + limit.windowMillis());
            }
            retryAfterMillis[0] = Math.max(1000L, existing.windowEndsAtMillis() - now);
            if (existing.count() >= limit.getCapacity()) {
                allowed.set(false);
                return existing;
            }
            allowed.set(true);
            return new WindowCounter(existing.count() + 1, existing.windowEndsAtMillis());
        });

        return new RateLimitDecision(allowed.get(), Math.max(1L, (retryAfterMillis[0] + 999L) / 1000L));
    }

    private void cleanupExpiredCounters(long now) {
        if (now < nextCleanupAtMillis) {
            return;
        }
        nextCleanupAtMillis = now + properties.getCleanupInterval().toMillis();
        counters.entrySet().removeIf(entry -> now >= entry.getValue().windowEndsAtMillis());
    }

    private void writeRateLimitResponse(
            HttpServletResponse response,
            RateLimitProperties.EndpointLimit limit,
            String ruleName
    ) throws IOException {
        response.setStatus(429);
        response.setHeader(HttpHeaders.RETRY_AFTER, String.valueOf(Math.max(1L, limit.windowMillis() / 1000L)));
        response.setHeader("X-RateLimit-Rule", ruleName);
        response.setHeader("X-RateLimit-Limit", String.valueOf(limit.getCapacity()));
        response.setHeader("X-RateLimit-Window-Seconds", String.valueOf(limit.windowMillis() / 1000L));
        response.setContentType(MediaType.APPLICATION_JSON_VALUE + ";charset=UTF-8");
        response.getOutputStream().write(TOO_MANY_REQUESTS_BODY.getBytes(StandardCharsets.UTF_8));
    }

    private String safeLogKey(String key) {
        if (key.contains(":email:")) {
            return key.replaceAll("email:[^:]+", "email:***");
        }
        return key;
    }

    private enum KeyScope {
        EMAIL_AND_IP,
        USER_OR_IP,
        IP_ONLY
    }

    private record MatchedRule(
            String name,
            RateLimitProperties.EndpointLimit limit,
            KeyScope keyScope,
            boolean usesBodyEmail
    ) {
    }

    private record WindowCounter(int count, long windowEndsAtMillis) {
    }

    private record RateLimitDecision(boolean allowed, long retryAfterSeconds) {
    }
}
