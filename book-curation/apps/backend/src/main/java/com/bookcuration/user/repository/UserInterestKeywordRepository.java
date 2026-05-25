package com.taeo.bookcuration.user.repository;

import com.taeo.bookcuration.user.entity.UserInterestKeywordEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;
import java.util.UUID;

public interface UserInterestKeywordRepository extends JpaRepository<UserInterestKeywordEntity, Long> {

    List<UserInterestKeywordEntity> findByUserIdOrderByKeywordAsc(UUID userId);

    // 수정 포인트: 관심 키워드 교체 저장도 장르와 동일하게 bulk delete로 중복 insert 위험을 제거합니다.
    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("delete from UserInterestKeywordEntity k where k.userId = :userId")
    void deleteByUserId(@Param("userId") UUID userId);
}
