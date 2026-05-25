package com.taeo.bookcuration.auth.service;

import com.taeo.bookcuration.auth.dto.AuthDtos.DormantReleaseConfirmRequest;
import com.taeo.bookcuration.auth.dto.AuthDtos.EmailAvailabilityResponse;
import com.taeo.bookcuration.auth.dto.AuthDtos.DormantReleaseSendCodeRequest;
import com.taeo.bookcuration.auth.dto.AuthDtos.MeResponse;
import com.taeo.bookcuration.auth.dto.AuthDtos.MessageResponse;
import com.taeo.bookcuration.auth.dto.AuthDtos.PasswordResetConfirmRequest;
import com.taeo.bookcuration.auth.dto.AuthDtos.PasswordResetSendCodeRequest;
import com.taeo.bookcuration.auth.dto.AuthDtos.SignupRequest;
import com.taeo.bookcuration.auth.dto.AuthDtos.SocialSignupCompleteRequest;
import com.taeo.bookcuration.auth.dto.AuthDtos.UpdateNicknameRequest;
import com.taeo.bookcuration.auth.entity.DormantReleaseVerificationEntity;
import com.taeo.bookcuration.auth.entity.PasswordResetVerificationEntity;
import com.taeo.bookcuration.auth.entity.UserCredentialEntity;
import com.taeo.bookcuration.auth.entity.UserEntity;
import com.taeo.bookcuration.auth.entity.UserSocialAccountEntity;
import com.taeo.bookcuration.auth.repository.DormantReleaseVerificationRepository;
import com.taeo.bookcuration.auth.repository.PasswordResetVerificationRepository;
import com.taeo.bookcuration.auth.repository.UserCredentialRepository;
import com.taeo.bookcuration.auth.repository.UserRepository;
import com.taeo.bookcuration.auth.repository.UserSocialAccountRepository;
import com.taeo.bookcuration.user.entity.UserCharacterEntity;
import com.taeo.bookcuration.user.entity.UserProfileEntity;
import com.taeo.bookcuration.user.repository.UserCharacterRepository;
import com.taeo.bookcuration.user.repository.UserProfileRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.dao.DataAccessException;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.security.SecureRandom;
import java.sql.ResultSet;
import java.time.OffsetDateTime;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.UUID;
import java.util.regex.Pattern;

@Slf4j
@Service
@RequiredArgsConstructor
public class AuthService {

    private static final String PASSWORD_RESET_INVALID_MESSAGE = "이메일 인증정보가 올바르지 않거나 만료되었습니다.";
    private static final String DORMANT_RELEASE_INVALID_MESSAGE = "휴면 해제 인증정보가 올바르지 않거나 만료되었습니다.";
    private static final Pattern SIGNUP_EMAIL_PATTERN = Pattern.compile(
            "^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\\.)+[A-Za-z]{2,63}$"
    );
    private static final Set<String> ALLOWED_SIGNUP_EMAIL_DOMAINS = Set.of(
            "gmail.com",
            "nate.com",
            "kakao.com",
            "naver.com",
            "daum.net"
    );
    private static final SecureRandom SECURE_RANDOM = new SecureRandom();

    private final UserRepository userRepository;
    private final UserCredentialRepository userCredentialRepository;
    private final UserSocialAccountRepository userSocialAccountRepository;
    private final UserProfileRepository userProfileRepository;
    private final UserCharacterRepository userCharacterRepository;
    private final PasswordResetVerificationRepository passwordResetVerificationRepository;
    private final DormantReleaseVerificationRepository dormantReleaseVerificationRepository;
    private final PasswordResetMailService passwordResetMailService;
    private final DormantReleaseMailService dormantReleaseMailService;
    private final PasswordEncoder passwordEncoder;
    private final JdbcTemplate jdbcTemplate;

    @Value("${app.auth.password-reset.code-expire-minutes:10}")
    private long passwordResetCodeExpireMinutes;

    @Value("${app.auth.password-reset.max-verify-attempts:5}")
    private int passwordResetMaxVerifyAttempts;

    @Value("${app.auth.dormant-release.code-expire-minutes:10}")
    private long dormantReleaseCodeExpireMinutes;

    @Value("${app.auth.dormant-release.max-verify-attempts:5}")
    private int dormantReleaseMaxVerifyAttempts;


    @Transactional(readOnly = true)
    public EmailAvailabilityResponse checkSignupEmailAvailability(String rawEmail) {
        String email = normalizeEmail(rawEmail);
        return getSignupEmailAvailability(email);
    }

    @Transactional
    public AuthUser signup(SignupRequest request) {
        String email = normalizeEmail(request.email());
        validateSignupEmailAvailable(email);

        UserEntity savedUser = userRepository.save(UserEntity.createLocalUser(email, request.nickname()));

        String passwordHash = passwordEncoder.encode(request.password());
        userCredentialRepository.save(UserCredentialEntity.create(savedUser, email, passwordHash));

        createProfileIfAbsent(savedUser);
        createCharacterIfAbsent(savedUser);
        savedUser.markLoggedIn();
        // 수정 포인트: 가입 직후 자동 로그인도 접속회원 수에 포함되도록 로그인 이벤트를 남깁니다.
        userRepository.flush();
        recordLoginEvent(savedUser.getId(), "SIGNUP");

        return AuthUser.from(
                savedUser,
                email,
                passwordHash,
                List.of(new SimpleGrantedAuthority("ROLE_" + savedUser.getRole()))
        );
    }

    @Transactional
    public AuthUser completeSocialSignup(SocialSignupCompleteRequest request, PendingSocialSignupSessionData pendingSignup) {
        String email = normalizeEmail(request.email());
        validateSignupEmailAvailable(email);

        userSocialAccountRepository.findByProviderAndProviderUserIdAndUser_StatusNot(
                        pendingSignup.provider(),
                        pendingSignup.providerUserId(),
                        "DELETED"
                )
                .ifPresent(account -> {
                    throw new IllegalArgumentException("이미 연동된 소셜 계정입니다. 기존 계정으로 로그인해 주세요.");
                });

        UserEntity savedUser = userRepository.save(UserEntity.createLocalUser(email, request.nickname()));
        String passwordHash = passwordEncoder.encode(request.password());
        userCredentialRepository.save(UserCredentialEntity.create(savedUser, email, passwordHash));
        userSocialAccountRepository.save(UserSocialAccountEntity.create(
                savedUser,
                pendingSignup.provider(),
                pendingSignup.providerUserId(),
                pendingSignup.providerEmail()
        ));

        createProfileIfAbsent(savedUser);
        createCharacterIfAbsent(savedUser);
        savedUser.markLoggedIn();
        // 수정 포인트: 소셜 가입 완료 후 자동 로그인도 접속회원 수에 포함되도록 로그인 이벤트를 남깁니다.
        userRepository.flush();
        recordLoginEvent(savedUser.getId(), "SOCIAL_SIGNUP");

        return AuthUser.from(
                savedUser,
                email,
                passwordHash,
                List.of(new SimpleGrantedAuthority("ROLE_" + savedUser.getRole()))
        );
    }

    @Transactional
    public MessageResponse sendPasswordResetCode(PasswordResetSendCodeRequest request) {
        String email = normalizeEmail(request.email());

        userCredentialRepository.findByEmailIgnoreCaseAndUser_StatusNot(email, "DELETED")
                .ifPresent(credential -> {
                    expireActivePasswordResetVerifications(credential.getUserId());

                    String verificationCode = generateVerificationCode();
                    OffsetDateTime expiresAt = OffsetDateTime.now().plusMinutes(passwordResetCodeExpireMinutes);

                    passwordResetVerificationRepository.save(PasswordResetVerificationEntity.create(
                            credential.getUser(),
                            email,
                            passwordEncoder.encode(verificationCode),
                            expiresAt
                    ));

                    passwordResetMailService.sendPasswordResetCode(
                            email,
                            credential.getUser().getNickname(),
                            verificationCode,
                            expiresAt
                    );
                });

        return new MessageResponse("입력한 이메일로 인증번호를 전송했습니다. 메일이 보이지 않으면 스팸함도 확인해 주세요.");
    }

    @Transactional
    public MessageResponse confirmPasswordReset(PasswordResetConfirmRequest request) {
        String email = normalizeEmail(request.email());
        UserCredentialEntity credential = userCredentialRepository.findByEmailIgnoreCaseAndUser_StatusNot(email, "DELETED")
                .orElseThrow(() -> new IllegalArgumentException(PASSWORD_RESET_INVALID_MESSAGE));

        PasswordResetVerificationEntity verification = passwordResetVerificationRepository
                .findFirstByUser_IdAndEmailIgnoreCaseAndConsumedAtIsNullOrderByCreatedAtDesc(
                        credential.getUserId(),
                        email
                )
                .orElseThrow(() -> new IllegalArgumentException(PASSWORD_RESET_INVALID_MESSAGE));

        if (verification.isExpired()) {
            verification.consume();
            throw new IllegalArgumentException("인증번호가 만료되었습니다. 다시 요청해 주세요.");
        }

        if (verification.isMaxAttemptsReached(passwordResetMaxVerifyAttempts)) {
            verification.consume();
            throw new IllegalArgumentException("인증번호 입력 횟수를 초과했습니다. 다시 요청해 주세요.");
        }

        if (!passwordEncoder.matches(request.code(), verification.getCodeHash())) {
            verification.increaseAttemptCount();
            if (verification.isMaxAttemptsReached(passwordResetMaxVerifyAttempts)) {
                verification.consume();
            }
            throw new IllegalArgumentException("인증번호가 올바르지 않습니다.");
        }

        credential.changePassword(passwordEncoder.encode(request.newPassword()));
        verification.consume();

        return new MessageResponse("비밀번호가 변경되었습니다. 새 비밀번호로 로그인해 주세요.");
    }

    @Transactional
    public MessageResponse sendDormantReleaseCode(DormantReleaseSendCodeRequest request) {
        String email = normalizeEmail(request.email());

        userRepository.findByPrimaryEmailIgnoreCaseAndStatusNot(email, "DELETED")
                .filter(user -> "INACTIVE".equals(user.getStatus()))
                .ifPresent(user -> {
                    expireActiveDormantReleaseVerifications(user.getId());

                    String verificationCode = generateVerificationCode();
                    OffsetDateTime expiresAt = OffsetDateTime.now().plusMinutes(dormantReleaseCodeExpireMinutes);

                    dormantReleaseVerificationRepository.save(DormantReleaseVerificationEntity.create(
                            user,
                            email,
                            passwordEncoder.encode(verificationCode),
                            expiresAt
                    ));

                    dormantReleaseMailService.sendDormantReleaseCode(
                            email,
                            user.getNickname(),
                            verificationCode,
                            expiresAt
                    );
                });

        return new MessageResponse("입력한 이메일로 휴면 해제 인증번호를 전송했습니다. 메일이 보이지 않으면 스팸함도 확인해 주세요.");
    }

    @Transactional
    public MessageResponse confirmDormantRelease(DormantReleaseConfirmRequest request) {
        String email = normalizeEmail(request.email());
        UserEntity user = userRepository.findByPrimaryEmailIgnoreCaseAndStatusNot(email, "DELETED")
                .orElseThrow(() -> new IllegalArgumentException(DORMANT_RELEASE_INVALID_MESSAGE));

        if ("DELETED".equals(user.getStatus())) {
            throw new IllegalArgumentException("탈퇴한 계정은 휴면 해제를 진행할 수 없습니다.");
        }

        if (!"INACTIVE".equals(user.getStatus())) {
            throw new IllegalArgumentException("이미 활성화된 계정입니다. 로그인해 주세요.");
        }

        DormantReleaseVerificationEntity verification = dormantReleaseVerificationRepository
                .findFirstByUser_IdAndEmailIgnoreCaseAndConsumedAtIsNullOrderByCreatedAtDesc(
                        user.getId(),
                        email
                )
                .orElseThrow(() -> new IllegalArgumentException(DORMANT_RELEASE_INVALID_MESSAGE));

        if (verification.isExpired()) {
            verification.consume();
            throw new IllegalArgumentException("인증번호가 만료되었습니다. 다시 요청해 주세요.");
        }

        if (verification.isMaxAttemptsReached(dormantReleaseMaxVerifyAttempts)) {
            verification.consume();
            throw new IllegalArgumentException("인증번호 입력 횟수를 초과했습니다. 다시 요청해 주세요.");
        }

        if (!passwordEncoder.matches(request.code(), verification.getCodeHash())) {
            verification.increaseAttemptCount();
            if (verification.isMaxAttemptsReached(dormantReleaseMaxVerifyAttempts)) {
                verification.consume();
            }
            throw new IllegalArgumentException("인증번호가 올바르지 않습니다.");
        }

        user.releaseDormant();
        verification.consume();

        return new MessageResponse("휴면 해제가 완료되었습니다. 다시 로그인해 주세요.");
    }


    @Transactional
    public MeResponse updateNickname(AuthUser authUser, UpdateNicknameRequest request) {
        UserEntity user = userRepository.findById(authUser.id())
                .orElseThrow(() -> new IllegalArgumentException("사용자를 찾을 수 없습니다."));

        String nickname = request.nickname().trim();
        user.changeNickname(nickname);

        boolean onboardingCompleted = userProfileRepository.findById(user.getId())
                .map(UserProfileEntity::isOnboardingCompleted)
                .orElse(false);

        // 수정 포인트: 세션 인증 구조는 유지하고, 변경된 닉네임이 프론트 저장소에 즉시 반영되도록 MeResponse를 반환합니다.
        return toMeResponse(user.getId(), user.getPrimaryEmail(), user.getNickname(), user.getRole(), onboardingCompleted);
    }

    @Transactional
    public MessageResponse withdraw(AuthUser authUser) {
        UserEntity user = userRepository.findById(authUser.id())
                .orElseThrow(() -> new IllegalArgumentException("사용자를 찾을 수 없습니다."));

        if ("DELETED".equals(user.getStatus())) {
            return new MessageResponse("이미 탈퇴 처리된 계정입니다.");
        }

        // 수정 포인트: 탈퇴 사용자의 인증/소셜/프로필/개인화/채팅 데이터를 먼저 정리해
        // 같은 이메일·소셜 식별자로 재가입하더라도 기존 데이터가 새 계정에 붙지 않게 합니다.
        deleteUserRelatedData(user.getId());
        user.markWithdrawn("USER_REQUESTED");
        userRepository.save(user);

        return new MessageResponse("회원탈퇴가 완료되었습니다.");
    }

    @Transactional
    public MeResponse unlinkSocialProvider(AuthUser authUser, String rawProvider) {
        UUID userId = authUser.id();
        String provider = normalizeProvider(rawProvider);

        UserEntity user = userRepository.findById(userId)
                .orElseThrow(() -> new IllegalArgumentException("사용자를 찾을 수 없습니다."));

        if ("DELETED".equals(user.getStatus())) {
            throw new IllegalArgumentException("탈퇴한 계정은 소셜 연동을 해제할 수 없습니다.");
        }

        if (!userSocialAccountRepository.existsByUser_IdAndProvider(userId, provider)) {
            throw new IllegalArgumentException("연동되지 않은 소셜 로그인 제공자입니다.");
        }

        boolean hasLocalLogin = userCredentialRepository.existsById(userId);
        long linkedProviderCount = userSocialAccountRepository.countByUser_Id(userId);

        if (!hasLocalLogin && linkedProviderCount <= 1) {
            throw new IllegalArgumentException("마지막 로그인 수단은 해제할 수 없습니다. 다른 로그인 수단을 먼저 연동해 주세요.");
        }

        userSocialAccountRepository.deleteByUser_IdAndProvider(userId, provider);
        return toMeResponse(authUser);
    }

    @Transactional
    public void markLoginSuccess(UUID userId) {
        UserEntity user = userRepository.findById(userId)
                .orElseThrow(() -> new IllegalArgumentException("사용자를 찾을 수 없습니다."));
        user.markLoggedIn();
        recordLoginEvent(userId, "LOCAL");
    }

    @Transactional(readOnly = true)
    public MeResponse toMeResponse(AuthUser authUser) {
        UserEntity user = userRepository.findById(authUser.id())
                .orElseThrow(() -> new IllegalArgumentException("사용자를 찾을 수 없습니다."));

        boolean onboardingCompleted = userProfileRepository.findById(user.getId())
                .map(UserProfileEntity::isOnboardingCompleted)
                .orElse(false);

        // 수정 포인트: 소셜 연동·소셜 로그인 직후에도 화면의 기본 이메일은 users.primary_email 기준으로 내려줍니다.
        return toMeResponse(
                user.getId(),
                user.getPrimaryEmail(),
                user.getNickname(),
                user.getRole(),
                onboardingCompleted
        );
    }

    private void validateSignupEmailAvailable(String email) {
        EmailAvailabilityResponse availability = getSignupEmailAvailability(email);
        if (!availability.available()) {
            throw new IllegalArgumentException(availability.message());
        }
    }

    private EmailAvailabilityResponse getSignupEmailAvailability(String email) {
        String validationMessage = getSignupEmailValidationMessage(email);

        if (!validationMessage.isBlank()) {
            return new EmailAvailabilityResponse(false, validationMessage);
        }

        if (userCredentialRepository.existsByEmailIgnoreCaseAndUser_StatusNot(email, "DELETED")) {
            return new EmailAvailabilityResponse(false, "이미 가입된 이메일입니다.");
        }

        return userRepository.findByPrimaryEmailIgnoreCaseAndStatusNot(email, "DELETED")
                .map(existingUser -> new EmailAvailabilityResponse(false, "이미 가입된 이메일입니다. 로그인 후 마이페이지에서 소셜 계정을 연동하세요."))
                .orElseGet(() -> new EmailAvailabilityResponse(true, "사용 가능한 이메일입니다."));
    }

    private static String getSignupEmailValidationMessage(String email) {
        String normalizedEmail = email == null ? "" : email.trim().toLowerCase(Locale.ROOT);

        if (normalizedEmail.isBlank()) {
            return "이메일을 입력해 주세요.";
        }

        if (normalizedEmail.length() > 254) {
            return "이메일은 254자 이하로 입력해 주세요.";
        }

        int atIndex = normalizedEmail.indexOf('@');
        int lastAtIndex = normalizedEmail.lastIndexOf('@');

        if (
                atIndex <= 0 ||
                atIndex != lastAtIndex ||
                !SIGNUP_EMAIL_PATTERN.matcher(normalizedEmail).matches()
        ) {
            return "올바른 이메일 형식으로 입력해 주세요.";
        }

        String localPart = normalizedEmail.substring(0, atIndex);
        String domainPart = normalizedEmail.substring(atIndex + 1);

        if (
                localPart.length() > 64 ||
                localPart.startsWith(".") ||
                localPart.endsWith(".") ||
                localPart.contains("..") ||
                domainPart.contains("..")
        ) {
            return "올바른 이메일 형식으로 입력해 주세요.";
        }

        if (!ALLOWED_SIGNUP_EMAIL_DOMAINS.contains(domainPart)) {
            // 수정 포인트: 실제 이메일 인증은 하지 않되, 가입 가능한 이메일 도메인을 서비스 정책상 허용 목록으로 제한합니다.
            return "가입 가능한 이메일 도메인은 gmail.com, nate.com, kakao.com, naver.com, daum.net입니다.";
        }

        return "";
    }

    private void createProfileIfAbsent(UserEntity user) {
        if (!userProfileRepository.existsById(user.getId())) {
            userProfileRepository.save(UserProfileEntity.createEmpty(user));
        }
    }

    private void createCharacterIfAbsent(UserEntity user) {
        if (!userCharacterRepository.existsById(user.getId())) {
            // 수정 포인트: 기존 프로필 생성 흐름은 유지하고, 신규 회원에게 기본 알 캐릭터만 추가 발급합니다.
            userCharacterRepository.save(UserCharacterEntity.createDefault(user));
        }
    }

    private void expireActivePasswordResetVerifications(UUID userId) {
        passwordResetVerificationRepository.findAllByUser_IdAndConsumedAtIsNull(userId)
                .forEach(PasswordResetVerificationEntity::consume);
    }

    private void expireActiveDormantReleaseVerifications(UUID userId) {
        dormantReleaseVerificationRepository.findAllByUser_IdAndConsumedAtIsNull(userId)
                .forEach(DormantReleaseVerificationEntity::consume);
    }

    private MeResponse toMeResponse(
            UUID id,
            String email,
            String nickname,
            String role,
            boolean onboardingCompleted
    ) {
        return new MeResponse(id, email, nickname, role, onboardingCompleted, findLinkedProviders(id));
    }

    private List<String> findLinkedProviders(UUID userId) {
        return userSocialAccountRepository.findAllByUser_Id(userId).stream()
                .map(UserSocialAccountEntity::getProvider)
                .sorted(Comparator.naturalOrder())
                .toList();
    }

    private void recordLoginEvent(UUID userId, String source) {
        try {
            if (!tableExists("user_login_events")) {
                return;
            }

            jdbcTemplate.update(
                    "INSERT INTO book.user_login_events (user_id, login_source) VALUES (?, ?)",
                    userId,
                    source
            );
        } catch (DataAccessException ex) {
            // 수정 포인트: 로그인 이벤트는 모니터링 보조 데이터이므로 기록 실패가 회원가입/로그인을 막지 않도록 분리합니다.
            log.warn("Login event recording skipped. userId={}, source={}, reason={}", userId, source, ex.getMessage());
        }
    }

    private boolean tableExists(String tableName) {
        try {
            return Boolean.TRUE.equals(jdbcTemplate.execute((ConnectionCallback<Boolean>) connection -> {
                String normalized = tableName == null ? "" : tableName.trim();
                if (normalized.isBlank()) {
                    return false;
                }
                // 수정 포인트: 인증 흐름의 보조 테이블 존재 확인이 특정 DB 함수(to_regclass)에 의존하지 않도록 JDBC metadata를 사용합니다.
                return hasTable(connection.getMetaData().getTables(null, "book", normalized, new String[]{"TABLE"}))
                        || hasTable(connection.getMetaData().getTables(null, "BOOK", normalized.toUpperCase(Locale.ROOT), new String[]{"TABLE"}));
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

    private void deleteUserRelatedData(UUID userId) {
        deleteIfTableExists(
                "recommendation_items",
                """
                DELETE FROM book.recommendation_items item
                USING book.recommendation_requests request
                WHERE item.request_id = request.id
                  AND (
                      request.user_id = ?
                      OR request.session_id IN (SELECT id FROM book.chat_sessions WHERE user_id = ?)
                  )
                """,
                userId,
                userId
        );
        deleteIfTableExists(
                "recommendation_requests",
                """
                DELETE FROM book.recommendation_requests
                WHERE user_id = ?
                   OR session_id IN (SELECT id FROM book.chat_sessions WHERE user_id = ?)
                """,
                userId,
                userId
        );
        deleteIfTableExists(
                "chat_session_summaries",
                """
                DELETE FROM book.chat_session_summaries
                WHERE user_id = ?
                   OR session_id IN (SELECT id FROM book.chat_sessions WHERE user_id = ?)
                """,
                userId,
                userId
        );
        deleteIfTableExists(
                "chat_messages",
                "DELETE FROM book.chat_messages WHERE session_id IN (SELECT id FROM book.chat_sessions WHERE user_id = ?)",
                userId
        );
        deleteIfTableExists("chat_sessions", "DELETE FROM book.chat_sessions WHERE user_id = ?", userId);
        deleteIfTableExists("user_login_events", "DELETE FROM book.user_login_events WHERE user_id = ?", userId);
        deleteIfTableExists("user_book_actions", "DELETE FROM book.user_book_actions WHERE user_id = ?", userId);
        deleteIfTableExists("user_book_shelves", "DELETE FROM book.user_book_shelves WHERE user_id = ?", userId);
        deleteIfTableExists("user_interest_keywords", "DELETE FROM book.user_interest_keywords WHERE user_id = ?", userId);
        deleteIfTableExists("user_interest_categories", "DELETE FROM book.user_interest_categories WHERE user_id = ?", userId);
        deleteIfTableExists("user_preferred_libraries", "DELETE FROM book.user_preferred_libraries WHERE user_id = ?", userId);
        deleteIfTableExists("user_characters", "DELETE FROM book.user_characters WHERE user_id = ?", userId);
        deleteIfTableExists("user_profiles", "DELETE FROM book.user_profiles WHERE user_id = ?", userId);
        deleteIfTableExists("user_social_accounts", "DELETE FROM book.user_social_accounts WHERE user_id = ?", userId);
        deleteIfTableExists("user_credentials", "DELETE FROM book.user_credentials WHERE user_id = ?", userId);
        deleteIfTableExists("password_reset_verifications", "DELETE FROM book.password_reset_verifications WHERE user_id = ?", userId);
        deleteIfTableExists("dormant_release_verifications", "DELETE FROM book.dormant_release_verifications WHERE user_id = ?", userId);
    }

    private int deleteIfTableExists(String tableName, String sql, Object... args) {
        if (!tableExists(tableName)) {
            return 0;
        }

        return jdbcTemplate.update(sql, args);
    }

    private static String normalizeProvider(String provider) {
        if (provider == null || provider.isBlank()) {
            throw new IllegalArgumentException("소셜 로그인 제공자를 입력해 주세요.");
        }
        return provider.trim().toUpperCase(Locale.ROOT);
    }

    private static String normalizeEmail(String email) {
        return email == null ? "" : email.trim().toLowerCase(Locale.ROOT);
    }

    private static String generateVerificationCode() {
        return String.format("%06d", SECURE_RANDOM.nextInt(1_000_000));
    }
}
