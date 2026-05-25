package com.taeo.bookcuration.auth.service;

import com.taeo.bookcuration.auth.entity.UserEntity;
import com.taeo.bookcuration.auth.entity.UserSocialAccountEntity;
import com.taeo.bookcuration.auth.exception.AccountStatusAuthenticationException;
import com.taeo.bookcuration.auth.oauth2.SocialOAuth2Profile;
import com.taeo.bookcuration.auth.repository.UserRepository;
import com.taeo.bookcuration.auth.repository.UserSocialAccountRepository;
import com.taeo.bookcuration.user.entity.UserProfileEntity;
import com.taeo.bookcuration.user.repository.UserProfileRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.dao.DataAccessException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.OidcUserInfo;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.sql.ResultSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;

@Slf4j
@Service
@RequiredArgsConstructor
public class SocialLoginService {

    private final UserRepository userRepository;
    private final UserSocialAccountRepository userSocialAccountRepository;
    private final UserProfileRepository userProfileRepository;
    private final SocialAuthSessionService socialAuthSessionService;
    private final JdbcTemplate jdbcTemplate;

    @Transactional
    public AuthUser loginWithSocial(SocialOAuth2Profile profile, Map<String, Object> attributes) {
        return loginWithSocial(profile, attributes, null, null);
    }

    @Transactional
    public AuthUser loginWithSocial(
            SocialOAuth2Profile profile,
            Map<String, Object> attributes,
            OidcIdToken idToken,
            OidcUserInfo userInfo
    ) {
        UserSocialAccountEntity socialAccount = userSocialAccountRepository
                .findByProviderAndProviderUserIdAndUser_StatusNot(
                        profile.provider(),
                        profile.providerUserId(),
                        "DELETED"
                )
                .map(account -> {
                    account.changeProviderEmail(profile.email());
                    return account;
                })
                .orElse(null);

        SocialLinkSessionData linkIntent = socialAuthSessionService.getLinkIntent().orElse(null);
        if (linkIntent != null) {
            try {
                return handleSocialLink(linkIntent, profile, socialAccount, attributes, idToken, userInfo);
            } finally {
                socialAuthSessionService.clearLinkIntent();
            }
        }

        if (socialAccount != null) {
            socialAuthSessionService.clearPendingSignup();
            return toAuthenticatedUser(socialAccount.getUser(), profile, attributes, idToken, userInfo);
        }

        socialAuthSessionService.storePendingSignup(profile);
        return AuthUser.pendingSocial(profile.email(), profile.nickname(), attributes, idToken, userInfo);
    }

    private AuthUser handleSocialLink(
            SocialLinkSessionData linkIntent,
            SocialOAuth2Profile profile,
            UserSocialAccountEntity socialAccount,
            Map<String, Object> attributes,
            OidcIdToken idToken,
            OidcUserInfo userInfo
    ) {
        if (!Objects.equals(linkIntent.provider(), profile.provider())) {
            throw new IllegalArgumentException("요청한 소셜 로그인 제공자와 연동 대상이 일치하지 않습니다.");
        }

        UserEntity user = userRepository.findById(linkIntent.userId())
                .orElseThrow(() -> new IllegalArgumentException("연동할 사용자를 찾을 수 없습니다."));

        if (socialAccount != null && !socialAccount.getUser().getId().equals(user.getId())) {
            throw new IllegalArgumentException(profile.provider() + " 계정이 이미 다른 회원에 연동되어 있습니다.");
        }

        if (socialAccount == null) {
            if (userSocialAccountRepository.existsByUser_IdAndProvider(user.getId(), profile.provider())) {
                throw new IllegalArgumentException("이미 같은 제공자의 소셜 로그인이 연동되어 있습니다.");
            }

            userSocialAccountRepository.save(UserSocialAccountEntity.create(
                    user,
                    profile.provider(),
                    profile.providerUserId(),
                    profile.email()
            ));
        }

        return toAuthenticatedUser(user, profile, attributes, idToken, userInfo);
    }

    private AuthUser toAuthenticatedUser(
            UserEntity user,
            SocialOAuth2Profile profile,
            Map<String, Object> attributes,
            OidcIdToken idToken,
            OidcUserInfo userInfo
    ) {
        if ("INACTIVE".equals(user.getStatus())) {
            throw new AccountStatusAuthenticationException(
                    "DORMANT_ACCOUNT",
                    "휴면회원입니다. 이메일 인증 후 휴면을 해제해 주세요.",
                    firstNonBlank(user.getPrimaryEmail(), profile.email())
            );
        }

        if ("DELETED".equals(user.getStatus())) {
            throw new AccountStatusAuthenticationException(
                    "WITHDRAWN_ACCOUNT",
                    "탈퇴한 계정입니다.",
                    firstNonBlank(user.getPrimaryEmail(), profile.email())
            );
        }

        if (!"ACTIVE".equals(user.getStatus())) {
            throw new DisabledException("비활성화된 계정입니다.");
        }

        user.markLoggedIn();
        recordLoginEvent(user.getId());
        createProfileIfAbsent(user);

        // 수정 포인트: 소셜 로그인으로 인증하더라도 세션/마이페이지 기본 이메일은 users.primary_email을 우선합니다.
        String loginEmail = firstNonBlank(user.getPrimaryEmail(), profile.email());
        return AuthUser.fromSocial(
                user,
                loginEmail,
                List.of(new SimpleGrantedAuthority("ROLE_" + user.getRole())),
                attributes,
                idToken,
                userInfo
        );
    }

    private void recordLoginEvent(java.util.UUID userId) {
        try {
            if (!tableExists("user_login_events")) {
                return;
            }

            jdbcTemplate.update(
                    "INSERT INTO book.user_login_events (user_id, login_source) VALUES (?, 'SOCIAL')",
                    userId
            );
        } catch (DataAccessException ex) {
            // 수정 포인트: 소셜 로그인 성공 자체가 모니터링 테이블 상태에 영향받지 않도록 이벤트 기록을 best-effort로 처리합니다.
            log.warn("Social login event recording skipped. userId={}, reason={}", userId, ex.getMessage());
        }
    }

    private boolean tableExists(String tableName) {
        try {
            return Boolean.TRUE.equals(jdbcTemplate.execute((ConnectionCallback<Boolean>) connection -> {
                String normalized = tableName == null ? "" : tableName.trim();
                if (normalized.isBlank()) {
                    return false;
                }
                // 수정 포인트: 소셜 로그인도 특정 DB 함수 대신 JDBC metadata로 보조 테이블 존재 여부를 판단합니다.
                return hasTable(connection.getMetaData().getTables(null, "book", normalized, new String[]{"TABLE"}))
                        || hasTable(connection.getMetaData().getTables(null, "BOOK", normalized.toUpperCase(java.util.Locale.ROOT), new String[]{"TABLE"}));
            }));
        } catch (DataAccessException ex) {
            log.warn("Table existence check failed. table={}, reason={}", tableName, ex.getMessage());
            return false;
        }
    }

    private static boolean hasTable(ResultSet resultSet) {
        try (resultSet) {
            return resultSet.next();
        } catch (Exception ex) {
            return false;
        }
    }

    private void createProfileIfAbsent(UserEntity user) {
        if (!userProfileRepository.existsById(user.getId())) {
            userProfileRepository.save(UserProfileEntity.createEmpty(user));
        }
    }

    private static String firstNonBlank(String... values) {
        for (String value : values) {
            if (value != null && !value.isBlank()) {
                return value;
            }
        }
        return null;
    }
}
