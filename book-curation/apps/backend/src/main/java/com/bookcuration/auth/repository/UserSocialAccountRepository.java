package com.taeo.bookcuration.auth.repository;

import com.taeo.bookcuration.auth.entity.UserSocialAccountEntity;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface UserSocialAccountRepository extends JpaRepository<UserSocialAccountEntity, Long> {

    Optional<UserSocialAccountEntity> findByProviderAndProviderUserId(String provider, String providerUserId);

    Optional<UserSocialAccountEntity> findByProviderAndProviderUserIdAndUser_StatusNot(
            String provider,
            String providerUserId,
            String status
    );

    boolean existsByUser_IdAndProvider(UUID userId, String provider);

    long countByUser_Id(UUID userId);

    void deleteByUser_IdAndProvider(UUID userId, String provider);

    List<UserSocialAccountEntity> findAllByUser_Id(UUID userId);
}
