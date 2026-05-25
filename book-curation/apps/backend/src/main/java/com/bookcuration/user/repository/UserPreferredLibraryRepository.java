package com.taeo.bookcuration.user.repository;

import com.taeo.bookcuration.user.entity.UserPreferredLibraryEntity;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface UserPreferredLibraryRepository extends JpaRepository<UserPreferredLibraryEntity, Long> {

    List<UserPreferredLibraryEntity> findByUserIdOrderByPriorityAscCreatedAtAsc(UUID userId);

    Optional<UserPreferredLibraryEntity> findByUserIdAndLibCode(UUID userId, String libCode);

    long countByUserId(UUID userId);

    void deleteByUserIdAndLibCode(UUID userId, String libCode);
}
