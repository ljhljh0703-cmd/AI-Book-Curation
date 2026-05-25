from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class RankingResult:
    """모델 랭킹 단계의 결과와 fallback 정보를 함께 전달합니다."""

    candidates: List[Dict[str, Any]]
    requested_model: str
    applied_model: str
    applied: bool
    fallback: bool = False
    fallback_reason: str | None = None
    artifact_version: str | None = None
    elapsed_ms: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_metadata(self) -> Dict[str, Any]:
        return {
            "requestedModel": self.requested_model,
            "appliedModel": self.applied_model,
            "applied": self.applied,
            "fallback": self.fallback,
            "fallbackReason": self.fallback_reason,
            "artifactVersion": self.artifact_version,
            "elapsedMs": self.elapsed_ms,
            **dict(self.metadata or {}),
        }
