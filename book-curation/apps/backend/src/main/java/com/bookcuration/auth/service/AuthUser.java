package com.taeo.bookcuration.auth.service;

import com.taeo.bookcuration.auth.entity.UserEntity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.core.oidc.OidcUserInfo;
import org.springframework.security.oauth2.core.user.OAuth2User;

import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.UUID;

public record AuthUser(
        UUID id,
        String email,
        String nickname,
        String role,
        String passwordHash,
        Collection<? extends GrantedAuthority> authorities,
        Map<String, Object> attributes,
        OidcIdToken idToken,
        OidcUserInfo userInfo
) implements UserDetails, OAuth2User, OidcUser {

    public static AuthUser from(
            UserEntity user,
            String loginEmail,
            String passwordHash,
            Collection<? extends GrantedAuthority> authorities
    ) {
        return new AuthUser(
                user.getId(),
                loginEmail,
                user.getNickname(),
                user.getRole(),
                passwordHash,
                authorities,
                Map.of(),
                null,
                null
        );
    }

    public static AuthUser fromSocial(
            UserEntity user,
            String loginEmail,
            Collection<? extends GrantedAuthority> authorities,
            Map<String, Object> attributes
    ) {
        return fromSocial(user, loginEmail, authorities, attributes, null, null);
    }

    public static AuthUser fromSocial(
            UserEntity user,
            String loginEmail,
            Collection<? extends GrantedAuthority> authorities,
            Map<String, Object> attributes,
            OidcIdToken idToken,
            OidcUserInfo userInfo
    ) {
        return new AuthUser(
                user.getId(),
                loginEmail,
                user.getNickname(),
                user.getRole(),
                "",
                authorities,
                attributes == null ? Map.of() : Map.copyOf(attributes),
                idToken,
                userInfo
        );
    }

    public static AuthUser pendingSocial(
            String email,
            String nickname,
            Map<String, Object> attributes,
            OidcIdToken idToken,
            OidcUserInfo userInfo
    ) {
        return new AuthUser(
                UUID.randomUUID(),
                email,
                nickname,
                "PENDING_SOCIAL",
                "",
                List.of(),
                attributes == null ? Map.of() : Map.copyOf(attributes),
                idToken,
                userInfo
        );
    }

    @Override
    public Collection<? extends GrantedAuthority> getAuthorities() {
        return authorities;
    }

    @Override
    public String getPassword() {
        return passwordHash;
    }

    @Override
    public String getUsername() {
        return email == null ? id.toString() : email;
    }

    @Override
    public Map<String, Object> getAttributes() {
        return attributes;
    }

    @Override
    public Map<String, Object> getClaims() {
        if (userInfo != null) {
            return userInfo.getClaims();
        }
        return attributes;
    }

    @Override
    public OidcUserInfo getUserInfo() {
        return userInfo;
    }

    @Override
    public OidcIdToken getIdToken() {
        return idToken;
    }

    @Override
    public String getName() {
        return id.toString();
    }
}
