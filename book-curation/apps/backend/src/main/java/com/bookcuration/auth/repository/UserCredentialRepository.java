package com.taeo.bookcuration.auth.repository;

import com.taeo.bookcuration.auth.entity.UserCredentialEntity;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;
import java.util.UUID;

public interface UserCredentialRepository extends JpaRepository<UserCredentialEntity, UUID> {

    boolean existsByEmailIgnoreCase(String email);

    boolean existsByEmailIgnoreCaseAndUser_StatusNot(String email, String status);

    Optional<UserCredentialEntity> findByEmailIgnoreCase(String email);

    Optional<UserCredentialEntity> findByEmailIgnoreCaseAndUser_StatusNot(String email, String status);
}
