package com.taeo.bookcuration.security.ratelimit;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

import java.time.Duration;

@Component
@ConfigurationProperties(prefix = "app.security.rate-limit")
public class RateLimitProperties {

    /** 수정 포인트: 운영 기본값은 request 제한을 켠 상태입니다. 장애 대응 시 RATE_LIMIT_ENABLED=false로 임시 해제할 수 있습니다. */
    private boolean enabled = true;

    /** 수정 포인트: Cloudflare Tunnel 뒤에서는 CF-Connecting-IP를 실제 사용자 IP로 신뢰합니다. */
    private boolean trustProxyHeaders = true;

    /** 수정 포인트: login/reset 요청의 email 기준 제한을 위해 작은 JSON body만 캐시합니다. */
    private int maxCachedRequestBodyBytes = 8 * 1024;

    /** 수정 포인트: 만료된 rate limit counter를 주기적으로 정리해 NAS 메모리 누수를 방지합니다. */
    private Duration cleanupInterval = Duration.ofMinutes(5);

    private EndpointLimit login = new EndpointLimit(5, Duration.ofMinutes(1));
    private EndpointLimit signup = new EndpointLimit(3, Duration.ofMinutes(10));
    private EndpointLimit emailAvailability = new EndpointLimit(30, Duration.ofMinutes(1));
    private EndpointLimit verificationSend = new EndpointLimit(3, Duration.ofMinutes(10));
    private EndpointLimit verificationConfirm = new EndpointLimit(10, Duration.ofMinutes(10));
    private EndpointLimit socialSignupComplete = new EndpointLimit(3, Duration.ofMinutes(10));
    private EndpointLimit onboardingBookSearch = new EndpointLimit(20, Duration.ofMinutes(1));
    private EndpointLimit chatSessionCreate = new EndpointLimit(20, Duration.ofMinutes(1));
    private EndpointLimit chatMessage = new EndpointLimit(10, Duration.ofMinutes(1));
    private EndpointLimit guestChatMessage = new EndpointLimit(8, Duration.ofMinutes(1));
    private EndpointLimit guestChatDaily = new EndpointLimit(40, Duration.ofDays(1));
    private EndpointLimit bookAvailability = new EndpointLimit(10, Duration.ofMinutes(1));
    private EndpointLimit adminImageUpload = new EndpointLimit(5, Duration.ofMinutes(1));

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public boolean isTrustProxyHeaders() {
        return trustProxyHeaders;
    }

    public void setTrustProxyHeaders(boolean trustProxyHeaders) {
        this.trustProxyHeaders = trustProxyHeaders;
    }

    public int getMaxCachedRequestBodyBytes() {
        return maxCachedRequestBodyBytes;
    }

    public void setMaxCachedRequestBodyBytes(int maxCachedRequestBodyBytes) {
        this.maxCachedRequestBodyBytes = Math.max(1024, maxCachedRequestBodyBytes);
    }

    public Duration getCleanupInterval() {
        return cleanupInterval;
    }

    public void setCleanupInterval(Duration cleanupInterval) {
        this.cleanupInterval = cleanupInterval == null ? Duration.ofMinutes(5) : cleanupInterval;
    }

    public EndpointLimit getLogin() {
        return login;
    }

    public void setLogin(EndpointLimit login) {
        this.login = normalize(login, 5, Duration.ofMinutes(1));
    }

    public EndpointLimit getSignup() {
        return signup;
    }

    public void setSignup(EndpointLimit signup) {
        this.signup = normalize(signup, 3, Duration.ofMinutes(10));
    }

    public EndpointLimit getEmailAvailability() {
        return emailAvailability;
    }

    public void setEmailAvailability(EndpointLimit emailAvailability) {
        this.emailAvailability = normalize(emailAvailability, 30, Duration.ofMinutes(1));
    }

    public EndpointLimit getVerificationSend() {
        return verificationSend;
    }

    public void setVerificationSend(EndpointLimit verificationSend) {
        this.verificationSend = normalize(verificationSend, 3, Duration.ofMinutes(10));
    }

    public EndpointLimit getVerificationConfirm() {
        return verificationConfirm;
    }

    public void setVerificationConfirm(EndpointLimit verificationConfirm) {
        this.verificationConfirm = normalize(verificationConfirm, 10, Duration.ofMinutes(10));
    }

    public EndpointLimit getSocialSignupComplete() {
        return socialSignupComplete;
    }

    public void setSocialSignupComplete(EndpointLimit socialSignupComplete) {
        this.socialSignupComplete = normalize(socialSignupComplete, 3, Duration.ofMinutes(10));
    }

    public EndpointLimit getOnboardingBookSearch() {
        return onboardingBookSearch;
    }

    public void setOnboardingBookSearch(EndpointLimit onboardingBookSearch) {
        this.onboardingBookSearch = normalize(onboardingBookSearch, 20, Duration.ofMinutes(1));
    }

    public EndpointLimit getChatSessionCreate() {
        return chatSessionCreate;
    }

    public void setChatSessionCreate(EndpointLimit chatSessionCreate) {
        this.chatSessionCreate = normalize(chatSessionCreate, 20, Duration.ofMinutes(1));
    }

    public EndpointLimit getChatMessage() {
        return chatMessage;
    }

    public void setChatMessage(EndpointLimit chatMessage) {
        this.chatMessage = normalize(chatMessage, 10, Duration.ofMinutes(1));
    }

    public EndpointLimit getGuestChatMessage() {
        return guestChatMessage;
    }

    public void setGuestChatMessage(EndpointLimit guestChatMessage) {
        this.guestChatMessage = normalize(guestChatMessage, 8, Duration.ofMinutes(1));
    }

    public EndpointLimit getGuestChatDaily() {
        return guestChatDaily;
    }

    public void setGuestChatDaily(EndpointLimit guestChatDaily) {
        this.guestChatDaily = normalize(guestChatDaily, 40, Duration.ofDays(1));
    }

    public EndpointLimit getBookAvailability() {
        return bookAvailability;
    }

    public void setBookAvailability(EndpointLimit bookAvailability) {
        this.bookAvailability = normalize(bookAvailability, 10, Duration.ofMinutes(1));
    }

    public EndpointLimit getAdminImageUpload() {
        return adminImageUpload;
    }

    public void setAdminImageUpload(EndpointLimit adminImageUpload) {
        this.adminImageUpload = normalize(adminImageUpload, 5, Duration.ofMinutes(1));
    }

    private EndpointLimit normalize(EndpointLimit value, int defaultCapacity, Duration defaultWindow) {
        if (value == null) {
            return new EndpointLimit(defaultCapacity, defaultWindow);
        }
        value.normalize(defaultCapacity, defaultWindow);
        return value;
    }

    public static class EndpointLimit {
        private int capacity;
        private Duration window;

        public EndpointLimit() {
        }

        public EndpointLimit(int capacity, Duration window) {
            this.capacity = capacity;
            this.window = window;
            normalize(capacity, window);
        }

        public int getCapacity() {
            return capacity;
        }

        public void setCapacity(int capacity) {
            this.capacity = capacity;
        }

        public Duration getWindow() {
            return window;
        }

        public void setWindow(Duration window) {
            this.window = window;
        }

        public long windowMillis() {
            return Math.max(1000L, window.toMillis());
        }

        private void normalize(int defaultCapacity, Duration defaultWindow) {
            if (capacity <= 0) {
                capacity = defaultCapacity;
            }
            if (window == null || window.isZero() || window.isNegative()) {
                window = defaultWindow;
            }
        }
    }
}
