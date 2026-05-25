package com.taeo.bookcuration.user.repository;

import com.taeo.bookcuration.user.entity.UserBookShelfEntity;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface UserBookShelfRepository extends JpaRepository<UserBookShelfEntity, Long> {

    List<UserBookShelfEntity> findByUserIdOrderByUpdatedAtDesc(UUID userId);

    List<UserBookShelfEntity> findByUserIdAndShelfTypeOrderByUpdatedAtDesc(UUID userId, String shelfType);

    Optional<UserBookShelfEntity> findByUserIdAndBookIdAndShelfType(UUID userId, Long bookId, String shelfType);

    Optional<UserBookShelfEntity> findByIdAndUserId(Long id, UUID userId);

    long countByUserIdAndShelfType(UUID userId, String shelfType);

    void deleteByUserIdAndBookIdAndShelfType(UUID userId, Long bookId, String shelfType);
}
