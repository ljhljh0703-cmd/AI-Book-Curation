package com.taeo.bookcuration.auth.oauth2;

import com.taeo.bookcuration.auth.service.AuthUser;
import com.taeo.bookcuration.auth.service.SocialLoginService;
import lombok.RequiredArgsConstructor;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class SocialOidcUserService extends OidcUserService {

    private final SocialLoginService socialLoginService;

    @Override
    public OidcUser loadUser(OidcUserRequest userRequest) throws OAuth2AuthenticationException {
        OidcUser oidcUser = super.loadUser(userRequest);
        String registrationId = userRequest.getClientRegistration().getRegistrationId();
        SocialOAuth2Profile profile = SocialOAuth2Profile.from(registrationId, oidcUser.getClaims());

        try {
            // 수정 포인트: OIDC(provider 예: Google) 로그인도 AuthUser로 통일해 세션 principal 타입을 일관되게 유지합니다.
            AuthUser authUser = socialLoginService.loginWithSocial(
                    profile,
                    oidcUser.getAttributes(),
                    oidcUser.getIdToken(),
                    oidcUser.getUserInfo()
            );
            return authUser;
        } catch (OAuth2AuthenticationException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            throw new OAuth2AuthenticationException(
                    new OAuth2Error("social_login_failed"),
                    exception.getMessage(),
                    exception
            );
        }
    }
}
