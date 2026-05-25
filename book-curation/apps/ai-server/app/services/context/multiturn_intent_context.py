from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Dict, Iterable, List

from app.services.common.source_format_policy import SourceFormatPolicy
from app.services.context.conversation_context import ConversationContext
from app.services.intent.query_intent_parser import QueryIntent
from app.services.intent.reading_mode_policy import ReadingModePolicy


@dataclass(frozen=True)
class MultiturnIntentContextResult:
    """Result of carrying structured recommendation constraints across turns."""

    applied: bool = False
    source: str = "NONE"
    reason: str = ""
    inherited_consumption_context: str | None = None
    inherited_consumption_context_type: str | None = None
    inherited_visual_attention_limited: bool | None = None
    inherited_hands_free_preferred: bool | None = None
    inherited_requires_visual_reference: bool | None = None
    inherited_reading_mode: str | None = None
    inherited_target_reader: str | None = None
    inherited_requested_audience_group: str | None = None

    def metadata(self) -> Dict[str, Any]:
        return {
            "multiTurnContextInherited": self.applied,
            "multiTurnContextSource": self.source,
            "multiTurnContextReason": self.reason,
            "inheritedConsumptionContext": self.inherited_consumption_context,
            "inheritedConsumptionContextType": self.inherited_consumption_context_type,
            "inheritedVisualAttentionLimited": self.inherited_visual_attention_limited,
            "inheritedHandsFreePreferred": self.inherited_hands_free_preferred,
            "inheritedRequiresVisualReference": self.inherited_requires_visual_reference,
            "inheritedReadingMode": self.inherited_reading_mode,
            "inheritedTargetReader": self.inherited_target_reader,
            "inheritedRequestedAudienceGroup": self.inherited_requested_audience_group,
        }


class MultiturnIntentContextResolver:
    """Carry stable structured constraints from recent recommendation turns.

    수정 포인트:
    - 직전 턴의 "운전하면서/듣기" 같은 소비 상황을 현재 턴이 명시적으로 바꾸지 않았으면
      raw history text가 아니라 이전 응답 metadata/추천 카드의 source format evidence에서 복원합니다.
    - "내가 재미있어할 한 권"처럼 현재 질의가 일반·자기 자신 추천이면 이전 LISTENING_FRIENDLY
      제약을 유지해 유아책/자동차책이 최종 1권으로 새어 나오는 것을 막습니다.
    """

    _UNKNOWN_MODES = {"", ReadingModePolicy.MODE_UNKNOWN, ReadingModePolicy.MODE_ANY}
    _UNKNOWN_AUDIENCE_GROUPS = {"", "UNKNOWN", "ANY"}
    _UNKNOWN_TARGET_READERS = {"", "UNKNOWN"}

    _METADATA_CONTEXT_KEYS = (
        "query_consumption_context",
        "detected_consumption_context",
        "consumption_context",
        "detectedConsumptionContext",
    )
    _METADATA_CONTEXT_TYPE_KEYS = (
        "query_consumption_context_type",
        "consumption_context_type",
        "consumptionContextType",
    )
    _METADATA_READING_MODE_KEYS = (
        "query_reading_mode",
        "detected_reading_mode",
        "reading_mode",
        "detectedReadingMode",
    )
    _METADATA_TARGET_READER_KEYS = (
        "query_target_reader",
        "target_reader",
        "targetReader",
    )
    _METADATA_AUDIENCE_GROUP_KEYS = (
        "query_requested_audience_group",
        "requested_audience_group",
        "requestedAudienceGroup",
    )

    def __init__(self, context: ConversationContext | None = None) -> None:
        self.context = context or ConversationContext()
        self.reading_mode_policy = ReadingModePolicy()

    def resolve(
        self,
        *,
        history: List[Dict[str, Any]] | None,
        current_intent: QueryIntent,
    ) -> MultiturnIntentContextResult:
        if not history:
            return MultiturnIntentContextResult(reason="no_history")
        if not self._is_safe_to_inherit(current_intent):
            return MultiturnIntentContextResult(reason="current_query_has_explicit_constraints")

        structured = self._latest_structured_context(history)
        if structured.applied:
            return structured

        inferred = self._infer_from_previous_candidates(history)
        if inferred.applied:
            return inferred

        return MultiturnIntentContextResult(reason="no_reusable_structured_context")

    def apply(
        self,
        *,
        current_intent: QueryIntent,
        inheritance: MultiturnIntentContextResult,
    ) -> QueryIntent:
        if not inheritance.applied:
            return current_intent

        reading_mode = current_intent.reading_mode
        if self._is_unknown_reading_mode(reading_mode) and inheritance.inherited_reading_mode:
            reading_mode = self.reading_mode_policy.normalize_mode(inheritance.inherited_reading_mode)

        consumption_context = current_intent.consumption_context or inheritance.inherited_consumption_context
        consumption_context_type = current_intent.consumption_context_type or inheritance.inherited_consumption_context_type
        visual_attention_limited = self._first_bool(
            current_intent.visual_attention_limited,
            inheritance.inherited_visual_attention_limited,
        )
        hands_free_preferred = self._first_bool(
            current_intent.hands_free_preferred,
            inheritance.inherited_hands_free_preferred,
        )
        requires_visual_reference = self._first_bool(
            current_intent.requires_visual_reference,
            inheritance.inherited_requires_visual_reference,
        )

        target_reader = current_intent.target_reader
        if self._is_unknown_target_reader(target_reader) and inheritance.inherited_target_reader:
            target_reader = inheritance.inherited_target_reader

        requested_audience_group = current_intent.requested_audience_group
        if self._is_unknown_audience_group(requested_audience_group) and inheritance.inherited_requested_audience_group:
            requested_audience_group = inheritance.inherited_requested_audience_group

        return replace(
            current_intent,
            consumption_context=consumption_context,
            consumption_context_type=consumption_context_type,
            visual_attention_limited=visual_attention_limited,
            hands_free_preferred=hands_free_preferred,
            requires_visual_reference=requires_visual_reference,
            reading_mode=reading_mode,
            target_reader=target_reader,
            requested_audience_group=requested_audience_group,
            multiturn_context_inherited=True,
            multiturn_context_source=inheritance.source,
            multiturn_context_reason=inheritance.reason,
            inherited_reading_mode=inheritance.inherited_reading_mode,
            inherited_consumption_context=inheritance.inherited_consumption_context,
            inherited_requested_audience_group=inheritance.inherited_requested_audience_group,
        )

    def _is_safe_to_inherit(self, current_intent: QueryIntent) -> bool:
        if current_intent.is_precise_lookup:
            return False
        if not current_intent.general_recommendation:
            return False
        if current_intent.consumption_context:
            return False
        if not self._is_unknown_reading_mode(current_intent.reading_mode):
            return False
        if not self._is_unknown_audience_group(current_intent.requested_audience_group):
            return False
        if current_intent.requested_audience:
            return False
        return True

    def _latest_structured_context(self, history: List[Dict[str, Any]]) -> MultiturnIntentContextResult:
        for item in reversed(self.context.recent_turn_messages(history, turn_limit=3)):
            contexts = list(self._metadata_sources(item))
            for metadata in contexts:
                reading_mode = self.reading_mode_policy.normalize_mode(
                    self._first_text(metadata, self._METADATA_READING_MODE_KEYS)
                )
                consumption_context = self._first_text(metadata, self._METADATA_CONTEXT_KEYS)
                if self._is_unknown_reading_mode(reading_mode) and not consumption_context:
                    continue

                target_reader = self._normalize_target_reader(
                    self._first_text(metadata, self._METADATA_TARGET_READER_KEYS)
                ) or "SELF"
                requested_audience_group = self._normalize_audience_group(
                    self._first_text(metadata, self._METADATA_AUDIENCE_GROUP_KEYS)
                ) or "GENERAL"
                return MultiturnIntentContextResult(
                    applied=True,
                    source="PREVIOUS_RESPONSE_METADATA",
                    reason="structured_context_found_in_recent_history",
                    inherited_consumption_context=consumption_context,
                    inherited_consumption_context_type=self._first_text(metadata, self._METADATA_CONTEXT_TYPE_KEYS),
                    inherited_visual_attention_limited=self._first_bool_from_mapping(
                        metadata,
                        ("query_visual_attention_limited", "visual_attention_limited", "visualAttentionLimited"),
                    ),
                    inherited_hands_free_preferred=self._first_bool_from_mapping(
                        metadata,
                        ("query_hands_free_preferred", "hands_free_preferred", "handsFreePreferred"),
                    ),
                    inherited_requires_visual_reference=self._first_bool_from_mapping(
                        metadata,
                        ("query_requires_visual_reference", "requires_visual_reference", "requiresVisualReference"),
                    ),
                    inherited_reading_mode=reading_mode,
                    inherited_target_reader=target_reader,
                    inherited_requested_audience_group=requested_audience_group,
                )
        return MultiturnIntentContextResult(reason="no_structured_history_metadata")

    def _infer_from_previous_candidates(self, history: List[Dict[str, Any]]) -> MultiturnIntentContextResult:
        candidates = self.context.extract_recent_recommendation_candidates(history, turn_limit=2, max_candidates=10)
        if not candidates:
            return MultiturnIntentContextResult(reason="no_recent_recommendation_candidates")

        source_backed_audio_count = 0
        for candidate in candidates[:5]:
            evidence = SourceFormatPolicy.audiobook_evidence(candidate)
            if evidence.get("matched"):
                source_backed_audio_count += 1

        if source_backed_audio_count <= 0:
            return MultiturnIntentContextResult(reason="recent_candidates_have_no_audio_format_evidence")

        return MultiturnIntentContextResult(
            applied=True,
            source="PREVIOUS_RECOMMENDATION_FORMAT_EVIDENCE",
            reason="recent_recommendation_cards_include_source_backed_audiobooks",
            inherited_consumption_context="이전 추천의 청취 친화 소비 상황",
            inherited_consumption_context_type="INHERITED_PARALLEL_ACTIVITY",
            inherited_visual_attention_limited=True,
            inherited_hands_free_preferred=True,
            inherited_requires_visual_reference=False,
            inherited_reading_mode=ReadingModePolicy.MODE_LISTENING_FRIENDLY,
            inherited_target_reader="SELF",
            inherited_requested_audience_group="GENERAL",
        )

    @classmethod
    def _metadata_sources(cls, item: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
        if isinstance(item, dict):
            yield item
            metadata = item.get("metadata")
            if isinstance(metadata, dict):
                yield metadata
            pipeline = item.get("pipeline")
            if isinstance(pipeline, dict):
                yield pipeline
            nested_pipeline = metadata.get("pipeline") if isinstance(metadata, dict) else None
            if isinstance(nested_pipeline, dict):
                yield nested_pipeline

    @staticmethod
    def _first_text(mapping: Dict[str, Any], keys: Iterable[str]) -> str | None:
        for key in keys:
            value = mapping.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _first_bool(*values: bool | None) -> bool | None:
        for value in values:
            if isinstance(value, bool):
                return value
        return None

    @classmethod
    def _first_bool_from_mapping(cls, mapping: Dict[str, Any], keys: Iterable[str]) -> bool | None:
        for key in keys:
            value = mapping.get(key)
            if isinstance(value, bool):
                return value
        return None

    @classmethod
    def _is_unknown_reading_mode(cls, value: Any) -> bool:
        return str(value or "").strip().upper() in cls._UNKNOWN_MODES

    @classmethod
    def _is_unknown_audience_group(cls, value: Any) -> bool:
        return str(value or "").strip().upper() in cls._UNKNOWN_AUDIENCE_GROUPS

    @classmethod
    def _is_unknown_target_reader(cls, value: Any) -> bool:
        return str(value or "").strip().upper() in cls._UNKNOWN_TARGET_READERS

    @classmethod
    def _normalize_audience_group(cls, value: Any) -> str | None:
        normalized = str(value or "").strip().upper()
        if cls._is_unknown_audience_group(normalized):
            return None
        allowed = {"CHILD", "TEEN", "YOUNG_ADULT", "ADULT", "SENIOR", "GENERAL"}
        return normalized if normalized in allowed else None

    @classmethod
    def _normalize_target_reader(cls, value: Any) -> str | None:
        normalized = str(value or "").strip().upper()
        if cls._is_unknown_target_reader(normalized):
            return None
        return normalized if normalized in {"SELF", "OTHER"} else None
