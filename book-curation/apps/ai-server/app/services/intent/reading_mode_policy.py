from __future__ import annotations

from typing import Any


class ReadingModePolicy:
    """Normalize LLM-structured reading mode fields.

    Natural-language detection belongs to the intent classifier prompt/model. Runtime
    recommendation code only consumes the structured fields returned by that classifier.
    """

    MODE_UNKNOWN = "UNKNOWN"
    MODE_ANY = "ANY"
    MODE_LISTENING_FRIENDLY = "LISTENING_FRIENDLY"
    MODE_VISUAL_READING = "VISUAL_READING"
    VALID_MODES = {MODE_UNKNOWN, MODE_ANY, MODE_LISTENING_FRIENDLY, MODE_VISUAL_READING}

    def normalize_mode(self, value: Any) -> str:
        mode = str(value or self.MODE_UNKNOWN).strip().upper()
        return mode if mode in self.VALID_MODES else self.MODE_UNKNOWN

    @staticmethod
    def normalize_weight(value: Any, *, upper: float = 0.2) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(float(upper), number))

    def is_listening_friendly(self, value: Any) -> bool:
        return self.normalize_mode(value) == self.MODE_LISTENING_FRIENDLY

    @classmethod
    def listening_format_query(cls) -> str:
        # 수정 포인트: 소비 상황형 질의에서 활동명/난이도 표현이 검색어를 오염시키지 않도록,
        # 런타임은 LLM이 반환한 structured reading mode를 실제 format 후보 검색용 seed로만 변환합니다.
        return "오디오북 낭독 음성 청취"
