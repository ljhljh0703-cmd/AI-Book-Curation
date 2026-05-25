package com.taeo.bookcuration.admin.onboarding.repository;

import com.taeo.bookcuration.admin.onboarding.entity.OnboardingOptionEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;

public interface OnboardingOptionRepository extends JpaRepository<OnboardingOptionEntity, Long> {

    List<OnboardingOptionEntity> findByOptionGroupOrderByDisplayOrderAscIdAsc(String optionGroup);

    // 수정 포인트: 프론트 온보딩 화면에는 active=true 항목만 노출합니다.
    List<OnboardingOptionEntity> findByActiveTrueOrderByOptionGroupAscDisplayOrderAscIdAsc();

    // 수정 포인트: 특정 온보딩 단계의 active=true 항목만 순서대로 조회합니다.
    List<OnboardingOptionEntity> findByOptionGroupAndActiveTrueOrderByDisplayOrderAscIdAsc(String optionGroup);

    boolean existsByOptionGroupAndOptionKey(String optionGroup, String optionKey);

    @Query("""
            select coalesce(max(option.displayOrder), 0)
            from OnboardingOptionEntity option
            where option.optionGroup = :optionGroup
            """)
    int findMaxDisplayOrderByOptionGroup(@Param("optionGroup") String optionGroup);
}
