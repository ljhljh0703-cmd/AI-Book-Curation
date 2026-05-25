package com.taeo.bookcuration.auth.service;

import com.taeo.bookcuration.auth.entity.UserCredentialEntity;
import com.taeo.bookcuration.auth.entity.UserEntity;
import com.taeo.bookcuration.auth.exception.AccountStatusAuthenticationException;
import com.taeo.bookcuration.auth.repository.UserCredentialRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
@RequiredArgsConstructor
public class CustomUserDetailsService implements UserDetailsService {

    private final UserCredentialRepository userCredentialRepository;

    @Override
    public UserDetails loadUserByUsername(String email) throws UsernameNotFoundException {
        UserCredentialEntity credential = userCredentialRepository
                .findByEmailIgnoreCaseAndUser_StatusNot(email.trim().toLowerCase(), "DELETED")
                .orElseThrow(() -> new UsernameNotFoundException("사용자를 찾을 수 없습니다."));

        UserEntity user = credential.getUser();

        if ("INACTIVE".equals(user.getStatus())) {
            throw new AccountStatusAuthenticationException(
                    "DORMANT_ACCOUNT",
                    "휴면회원입니다. 이메일 인증 후 휴면을 해제해 주세요.",
                    user.getPrimaryEmail()
            );
        }

        if ("DELETED".equals(user.getStatus())) {
            throw new AccountStatusAuthenticationException(
                    "WITHDRAWN_ACCOUNT",
                    "탈퇴한 계정입니다.",
                    user.getPrimaryEmail()
            );
        }

        if (!"ACTIVE".equals(user.getStatus())) {
            throw new DisabledException("비활성화된 계정입니다.");
        }

        return AuthUser.from(
                user,
                credential.getEmail(),
                credential.getPasswordHash(),
                List.of(new SimpleGrantedAuthority("ROLE_" + user.getRole()))
        );
    }
}
