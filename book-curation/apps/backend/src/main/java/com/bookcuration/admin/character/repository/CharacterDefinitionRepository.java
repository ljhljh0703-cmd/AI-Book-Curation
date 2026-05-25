package com.taeo.bookcuration.admin.character.repository;

import com.taeo.bookcuration.admin.character.entity.CharacterDefinitionEntity;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface CharacterDefinitionRepository extends JpaRepository<CharacterDefinitionEntity, Long> {

    List<CharacterDefinitionEntity> findAllByOrderByIdAsc();

    boolean existsByCharacterKey(String characterKey);

    boolean existsByCharacterKeyAndIdNot(String characterKey, Long id);

    Optional<CharacterDefinitionEntity> findByCharacterKey(String characterKey);
}
