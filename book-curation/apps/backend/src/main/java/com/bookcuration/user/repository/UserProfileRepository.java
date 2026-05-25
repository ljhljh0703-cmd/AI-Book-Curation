package com.taeo.bookcuration.user.repository;

import com.taeo.bookcuration.user.entity.UserProfileEntity;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.UUID;

public interface UserProfileRepository extends JpaRepository<UserProfileEntity, UUID> {
}
