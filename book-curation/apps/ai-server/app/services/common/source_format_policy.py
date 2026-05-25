from __future__ import annotations

from typing import Any, Dict, Iterable, List

from app.services.common.text_utils import normalize_text, safe_join


class SourceFormatPolicy:
    """Infer normalized book format signals from source-catalog fields.

    User intent detection must remain in the LLM intent classifier. This policy only
    normalizes book payload evidence that already exists in the source catalog, such as
    explicit format fields or catalog title markers used by the data provider.
    """

    AUDIOBOOK = "AUDIOBOOK"
    AUDIOBOOK_BOOLEAN_FIELDS = ("is_audio_book", "isAudioBook", "audiobook")
    AUDIOBOOK_FORMAT_FIELDS = ("format", "book_format", "media_type", "content_format")
    TITLE_MARKER_FIELDS = ("title", "subtitle")
    AUDIOBOOK_METADATA_MARKERS = ("audio", "audiobook", "오디오")
    AUDIOBOOK_TITLE_MARKERS = ("오디오북",)
    TRUTHY_VALUES = {"true", "1", "yes", "y"}

    @classmethod
    def audiobook_evidence(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        matched_fields: List[str] = []
        evidence_sources: List[str] = []

        for field in cls.AUDIOBOOK_BOOLEAN_FIELDS:
            value = payload.get(field)
            if isinstance(value, bool) and value:
                matched_fields.append(field)
                evidence_sources.append("metadata_boolean")
            elif str(value or "").strip().lower() in cls.TRUTHY_VALUES:
                matched_fields.append(field)
                evidence_sources.append("metadata_boolean")

        for field in cls.AUDIOBOOK_FORMAT_FIELDS:
            normalized = normalize_text(safe_join(payload.get(field))).lower()
            if not normalized:
                continue
            if any(marker in normalized for marker in cls.AUDIOBOOK_METADATA_MARKERS):
                matched_fields.append(field)
                evidence_sources.append("metadata_format")

        for field in cls.TITLE_MARKER_FIELDS:
            # 알라딘 원천 데이터의 제목 접두/표기처럼 source catalog가 제공한 형식 표식을 정규화합니다.
            # 사용자 질의 단어가 아니라 도서 payload 자체의 format evidence만 확인합니다.
            normalized = normalize_text(safe_join(payload.get(field))).lower()
            if not normalized:
                continue
            if any(marker in normalized for marker in cls.AUDIOBOOK_TITLE_MARKERS):
                matched_fields.append(field)
                evidence_sources.append("source_title_marker")

        return {
            "matched": bool(matched_fields),
            "normalized_format": cls.AUDIOBOOK if matched_fields else "UNKNOWN",
            "fields": sorted(set(matched_fields)),
            "sources": sorted(set(evidence_sources)),
        }

    @classmethod
    def is_audiobook_payload(cls, payload: Dict[str, Any]) -> bool:
        return bool(cls.audiobook_evidence(payload).get("matched"))

    @classmethod
    def title_marker_terms(cls) -> Iterable[str]:
        return cls.AUDIOBOOK_TITLE_MARKERS
