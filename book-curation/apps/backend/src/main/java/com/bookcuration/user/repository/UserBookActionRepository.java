package com.taeo.bookcuration.user.repository;

import com.taeo.bookcuration.user.entity.UserBookActionEntity;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.UUID;

public interface UserBookActionRepository extends JpaRepository<UserBookActionEntity, Long> {

    List<UserBookActionEntity> findTop50ByUserIdOrderByCreatedAtDesc(UUID userId);
}
