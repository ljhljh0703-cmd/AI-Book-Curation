package com.taeo.bookcuration.auth.repository;

import com.taeo.bookcuration.auth.entity.UserEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.OffsetDateTime;
import java.util.Optional;
import java.util.UUID;

public interface UserRepository extends JpaRepository<UserEntity, UUID> {

    Optional<UserEntity> findByPrimaryEmailIgnoreCase(String primaryEmail);

    Optional<UserEntity> findByPrimaryEmailIgnoreCaseAndStatusNot(String primaryEmail, String status);

    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query("""
            update UserEntity u
               set u.status = 'INACTIVE',
                   u.dormantAt = CURRENT_TIMESTAMP
             where u.status = 'ACTIVE'
               and coalesce(u.lastLoginAt, u.createdAt) <= :threshold
            """)
    int markDormantUsers(@Param("threshold") OffsetDateTime threshold);
}
