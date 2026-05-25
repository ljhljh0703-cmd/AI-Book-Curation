package com.taeo.bookcuration.auth.dto;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import java.util.List;
import java.util.UUID;

public final class AuthDtos {

    private AuthDtos() {
    }

    public record SignupRequest(
            @Email
            @NotBlank
            @Size(max = 254)
            String email,

            @NotBlank
            @Size(min = 8, max = 72)
            String password,

            @NotBlank
            @Size(min = 2, max = 30)
            String nickname
    ) {
    }

    public record SocialSignupCompleteRequest(
            @Email
            @NotBlank
            @Size(max = 254)
            String email,

            @NotBlank
            @Size(min = 8, max = 72)
            String password,

            @NotBlank
            @Size(min = 2, max = 30)
            String nickname
    ) {
    }

    public record LoginRequest(
            @Email
            @NotBlank
            String email,

            @NotBlank
            String password
    ) {
    }

    public record PasswordResetSendCodeRequest(
            @Email
            @NotBlank
            String email
    ) {
    }

    public record PasswordResetConfirmRequest(
            @Email
            @NotBlank
            String email,

            @NotBlank
            @Pattern(regexp = "^\\d{6}$")
            String code,

            @NotBlank
            @Size(min = 8, max = 72)
            String newPassword
    ) {
    }


    public record DormantReleaseSendCodeRequest(
            @Email
            @NotBlank
            String email
    ) {
    }

    public record DormantReleaseConfirmRequest(
            @Email
            @NotBlank
            String email,

            @NotBlank
            @Pattern(regexp = "^\\d{6}$")
            String code
    ) {
    }

    public record MessageResponse(
            String message
    ) {
    }

    public record EmailAvailabilityResponse(
            boolean available,
            String message
    ) {
    }

    public record UpdateNicknameRequest(
            @NotBlank
            @Size(min = 2, max = 30)
            String nickname
    ) {
    }

    public record MeResponse(
            UUID id,
            String email,
            String nickname,
            String role,
            boolean onboardingCompleted,
            List<String> linkedProviders
    ) {
    }

    public record PendingSocialSignupResponse(
            String provider,
            String email,
            String nickname
    ) {
    }

    public record SocialLinkStartResponse(
            String authorizationUrl
    ) {
    }

    public record CsrfResponse(
            String headerName,
            String parameterName,
            String token
    ) {
    }

    public record OAuth2ProviderResponse(
            List<OAuth2ProviderItem> providers
    ) {
    }

    public record OAuth2ProviderItem(
            String provider,
            String authorizationUrl
    ) {
    }
}
