package com.taeo.bookcuration.user.repository;

import com.taeo.bookcuration.user.entity.UserCharacterEntity;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.UUID;

public interface UserCharacterRepository extends JpaRepository<UserCharacterEntity, UUID> {
}
