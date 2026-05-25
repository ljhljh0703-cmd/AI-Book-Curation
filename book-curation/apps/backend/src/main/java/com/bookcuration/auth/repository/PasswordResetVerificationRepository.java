package com.taeo.bookcuration.auth.repository;

import com.taeo.bookcuration.auth.entity.PasswordResetVerificationEntity;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface PasswordResetVerificationRepository extends JpaRepository<PasswordResetVerificationEntity, Long> {

    List<PasswordResetVerificationEntity> findAllByUser_IdAndConsumedAtIsNull(UUID userId);

    Optional<PasswordResetVerificationEntity> findFirstByUser_IdAndEmailIgnoreCaseAndConsumedAtIsNullOrderByCreatedAtDesc(
            UUID userId,
            String email
    );
}
