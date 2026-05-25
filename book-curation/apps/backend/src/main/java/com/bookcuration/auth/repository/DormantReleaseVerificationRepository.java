package com.taeo.bookcuration.auth.repository;

import com.taeo.bookcuration.auth.entity.DormantReleaseVerificationEntity;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface DormantReleaseVerificationRepository extends JpaRepository<DormantReleaseVerificationEntity, Long> {

    List<DormantReleaseVerificationEntity> findAllByUser_IdAndConsumedAtIsNull(UUID userId);

    Optional<DormantReleaseVerificationEntity> findFirstByUser_IdAndEmailIgnoreCaseAndConsumedAtIsNullOrderByCreatedAtDesc(
            UUID userId,
            String email
    );
}
