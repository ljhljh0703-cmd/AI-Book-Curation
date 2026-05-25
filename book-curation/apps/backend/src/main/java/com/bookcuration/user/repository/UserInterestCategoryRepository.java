package com.taeo.bookcuration.user.repository;

import com.taeo.bookcuration.user.entity.UserInterestCategoryEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;
import java.util.UUID;

public interface UserInterestCategoryRepository extends JpaRepository<UserInterestCategoryEntity, Long> {

    List<UserInterestCategoryEntity> findByUserIdOrderByCategoryCodeAsc(UUID userId);

    // 수정 포인트: 마이페이지 희망 장르 교체 저장 시 JPA delete/insert flush 순서로 unique key가 터지지 않도록 bulk delete를 사용합니다.
    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("delete from UserInterestCategoryEntity c where c.userId = :userId")
    void deleteByUserId(@Param("userId") UUID userId);
}
