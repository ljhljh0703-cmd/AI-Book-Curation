package com.taeo.bookcuration.auth.controller;

import com.taeo.bookcuration.auth.dto.AuthDtos.CsrfResponse;
import com.taeo.bookcuration.auth.dto.AuthDtos.DormantReleaseConfirmRequest;
import com.taeo.bookcuration.auth.dto.AuthDtos.EmailAvailabilityResponse;
import com.taeo.bookcuration.auth.dto.AuthDtos.DormantReleaseSendCodeRequest;
import com.taeo.bookcuration.auth.dto.AuthDtos.LoginRequest;
import com.taeo.bookcuration.auth.dto.AuthDtos.MeResponse;
import com.taeo.bookcuration.auth.dto.AuthDtos.MessageResponse;
import com.taeo.bookcuration.auth.dto.AuthDtos.OAuth2ProviderItem;
import com.taeo.bookcuration.auth.dto.AuthDtos.OAuth2ProviderResponse;
import com.taeo.bookcuration.auth.dto.AuthDtos.PasswordResetConfirmRequest;
import com.taeo.bookcuration.auth.dto.AuthDtos.PasswordResetSendCodeRequest;
import com.taeo.bookcuration.auth.dto.AuthDtos.PendingSocialSignupResponse;
import com.taeo.bookcuration.auth.dto.AuthDtos.SignupRequest;
import com.taeo.bookcuration.auth.dto.AuthDtos.SocialLinkStartResponse;
import com.taeo.bookcuration.auth.dto.AuthDtos.SocialSignupCompleteRequest;
import com.taeo.bookcuration.auth.dto.AuthDtos.UpdateNicknameRequest;
import com.taeo.bookcuration.auth.service.AuthService;
import com.taeo.bookcuration.auth.service.AuthUser;
import com.taeo.bookcuration.auth.service.PendingSocialSignupSessionData;
import com.taeo.bookcuration.auth.service.SocialAuthSessionService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import org.springframework.validation.annotation.Validated;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

@RestController
@RequestMapping("/api/auth")
@RequiredArgsConstructor
@Validated
public class AuthController {

    private final AuthService authService;
    private final AuthenticationManager authenticationManager;
    private final SecurityContextRepository securityContextRepository;
    private final ObjectProvider<ClientRegistrationRepository> clientRegistrationRepositoryProvider;
    private final SocialAuthSessionService socialAuthSessionService;

    @GetMapping("/csrf")
    public CsrfResponse csrf(CsrfToken csrfToken) {
        return new CsrfResponse(
                csrfToken.getHeaderName(),
                csrfToken.getParameterName(),
                csrfToken.getToken()
        );
    }

    @GetMapping("/oauth2/providers")
    public OAuth2ProviderResponse oauth2Providers() {
        return new OAuth2ProviderResponse(listProviders());
    }

    @GetMapping("/social-signup/pending")
    public ResponseEntity<PendingSocialSignupResponse> pendingSocialSignup() {
        return socialAuthSessionService.getPendingSignup()
                .map(data -> ResponseEntity.ok(new PendingSocialSignupResponse(
                        data.provider(),
                        data.providerEmail(),
                        data.nickname()
                )))
                .orElseGet(() -> ResponseEntity.noContent().build());
    }

    @GetMapping("/signup/email-availability")
    public EmailAvailabilityResponse checkSignupEmailAvailability(
            @RequestParam @NotBlank @Email String email
    ) {
        return authService.checkSignupEmailAvailability(email);
    }

    @PostMapping("/signup")
    @ResponseStatus(HttpStatus.CREATED)
    public MeResponse signup(
            @Valid @RequestBody SignupRequest request,
            HttpServletRequest httpServletRequest,
            HttpServletResponse httpServletResponse
    ) {
        AuthUser authUser = authService.signup(request);
        saveAuthenticatedUser(authUser, httpServletRequest, httpServletResponse);
        return authService.toMeResponse(authUser);
    }

    @PostMapping("/social-signup/complete")
    @ResponseStatus(HttpStatus.CREATED)
    public MeResponse completeSocialSignup(
            @Valid @RequestBody SocialSignupCompleteRequest request,
            HttpServletRequest httpServletRequest,
            HttpServletResponse httpServletResponse
    ) {
        PendingSocialSignupSessionData pendingSignup = socialAuthSessionService.getPendingSignup()
                .orElseThrow(() -> new IllegalArgumentException("완료할 소셜 회원가입 정보가 없습니다. 다시 소셜 로그인을 진행해 주세요."));

        AuthUser authUser = authService.completeSocialSignup(request, pendingSignup);
        saveAuthenticatedUser(authUser, httpServletRequest, httpServletResponse);
        socialAuthSessionService.clearPendingSignup();
        return authService.toMeResponse(authUser);
    }

    @PostMapping("/password-reset/send-code")
    public MessageResponse sendPasswordResetCode(@Valid @RequestBody PasswordResetSendCodeRequest request) {
        return authService.sendPasswordResetCode(request);
    }

    @PostMapping("/password-reset/confirm")
    public MessageResponse confirmPasswordReset(@Valid @RequestBody PasswordResetConfirmRequest request) {
        return authService.confirmPasswordReset(request);
    }

    @PostMapping("/dormant/send-code")
    public MessageResponse sendDormantReleaseCode(@Valid @RequestBody DormantReleaseSendCodeRequest request) {
        return authService.sendDormantReleaseCode(request);
    }

    @PostMapping("/dormant/confirm")
    public MessageResponse confirmDormantRelease(@Valid @RequestBody DormantReleaseConfirmRequest request) {
        return authService.confirmDormantRelease(request);
    }

    @PostMapping("/login")
    public MeResponse login(
            @Valid @RequestBody LoginRequest request,
            HttpServletRequest httpServletRequest,
            HttpServletResponse httpServletResponse
    ) {
        Authentication authentication = authenticationManager.authenticate(
                new UsernamePasswordAuthenticationToken(
                        request.email().toLowerCase(),
                        request.password()
                )
        );

        var securityContext = SecurityContextHolder.createEmptyContext();
        securityContext.setAuthentication(authentication);
        SecurityContextHolder.setContext(securityContext);
        securityContextRepository.saveContext(securityContext, httpServletRequest, httpServletResponse);

        AuthUser authUser = (AuthUser) authentication.getPrincipal();
        authService.markLoginSuccess(authUser.id());
        return authService.toMeResponse(authUser);
    }

    @PostMapping("/withdraw")
    public MessageResponse withdraw(
            @AuthenticationPrincipal AuthUser authUser,
            HttpServletRequest request,
            HttpServletResponse response
    ) {
        if (authUser == null) {
            throw new IllegalArgumentException("로그인한 사용자만 회원탈퇴를 진행할 수 있습니다.");
        }

        MessageResponse result = authService.withdraw(authUser);
        clearSession(request, response);
        return result;
    }

    @PostMapping("/social-link/{provider}/start")
    public SocialLinkStartResponse startSocialLink(
            @AuthenticationPrincipal AuthUser authUser,
            @PathVariable String provider
    ) {
        if (authUser == null) {
            throw new IllegalArgumentException("로그인한 사용자만 소셜 계정을 연동할 수 있습니다.");
        }

        String normalizedProvider = provider.trim().toUpperCase(Locale.ROOT);
        OAuth2ProviderItem providerItem = listProviders().stream()
                .filter(item -> item.provider().equals(normalizedProvider))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("사용할 수 없는 소셜 로그인 제공자입니다."));

        socialAuthSessionService.storeLinkIntent(authUser.id(), normalizedProvider);
        socialAuthSessionService.clearPendingSignup();
        return new SocialLinkStartResponse(providerItem.authorizationUrl());
    }

    @DeleteMapping("/social-link/{provider}")
    public MeResponse unlinkSocialProvider(
            @AuthenticationPrincipal AuthUser authUser,
            @PathVariable String provider
    ) {
        if (authUser == null) {
            throw new IllegalArgumentException("로그인한 사용자만 소셜 계정 연동을 해제할 수 있습니다.");
        }

        return authService.unlinkSocialProvider(authUser, provider);
    }

    @GetMapping("/me")
    public MeResponse me(@AuthenticationPrincipal AuthUser authUser) {
        return authService.toMeResponse(authUser);
    }

    @PutMapping("/me/nickname")
    public MeResponse updateNickname(
            @AuthenticationPrincipal AuthUser authUser,
            @Valid @RequestBody UpdateNicknameRequest request
    ) {
        // 수정 포인트: 아이디/이메일은 변경하지 않고 닉네임만 수정하는 전용 API입니다.
        return authService.updateNickname(authUser, request);
    }

    private List<OAuth2ProviderItem> listProviders() {
        ClientRegistrationRepository repository = clientRegistrationRepositoryProvider.getIfAvailable();
        if (!(repository instanceof Iterable<?> iterable)) {
            return List.of();
        }

        List<OAuth2ProviderItem> providers = new ArrayList<>();
        for (Object candidate : iterable) {
            if (candidate instanceof ClientRegistration registration) {
                String registrationId = registration.getRegistrationId();
                providers.add(new OAuth2ProviderItem(
                        registrationId.toUpperCase(Locale.ROOT),
                        "/oauth2/authorization/" + registrationId
                ));
            }
        }
        return providers;
    }

    private void saveAuthenticatedUser(
            AuthUser authUser,
            HttpServletRequest request,
            HttpServletResponse response
    ) {
        Authentication authentication = UsernamePasswordAuthenticationToken.authenticated(
                authUser,
                null,
                authUser.getAuthorities()
        );
        var securityContext = SecurityContextHolder.createEmptyContext();
        securityContext.setAuthentication(authentication);
        SecurityContextHolder.setContext(securityContext);
        securityContextRepository.saveContext(securityContext, request, response);
    }

    private void clearSession(HttpServletRequest request, HttpServletResponse response) {
        SecurityContextHolder.clearContext();
        HttpSession session = request.getSession(false);
        if (session != null) {
            session.invalidate();
        }
        response.setHeader("Clear-Site-Data", "\"cache\", \"cookies\", \"storage\"");
    }
}
