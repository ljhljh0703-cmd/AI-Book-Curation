package com.taeo.bookcuration.auth.oauth2;

import com.taeo.bookcuration.auth.service.SocialLoginService;
import lombok.RequiredArgsConstructor;
import org.springframework.security.oauth2.client.userinfo.DefaultOAuth2UserService;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserRequest;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class SocialOAuth2UserService extends DefaultOAuth2UserService {

    // 수정 포인트: OAuth2 어댑터가 AuthService 전체를 의존하지 않도록 소셜 로그인 전용 서비스로 분리합니다.
    private final SocialLoginService socialLoginService;

    @Override
    public OAuth2User loadUser(OAuth2UserRequest userRequest) throws OAuth2AuthenticationException {
        OAuth2User oauth2User = super.loadUser(userRequest);
        String registrationId = userRequest.getClientRegistration().getRegistrationId();
        SocialOAuth2Profile profile = SocialOAuth2Profile.from(registrationId, oauth2User.getAttributes());

        try {
            // 수정 포인트: OAuth access_token/refresh_token은 저장하지 않고 provider 고유 ID만 계정 연결에 사용합니다.
            return socialLoginService.loginWithSocial(profile, oauth2User.getAttributes());
        } catch (OAuth2AuthenticationException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            // 수정 포인트: 소셜 계정 연결/저장 실패를 OAuth2 실패 핸들러가 처리할 수 있는 예외로 변환합니다.
            throw new OAuth2AuthenticationException(
                    new OAuth2Error("social_login_failed"),
                    exception.getMessage(),
                    exception
            );
        }
    }
}
