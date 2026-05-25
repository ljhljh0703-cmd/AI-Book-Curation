from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class RerankDocument:
    index: int
    text: str
    candidate: Dict[str, Any]


@dataclass(frozen=True)
class RerankResult:
    candidates: List[Dict[str, Any]]
    provider: str
    applied: bool
    fallback: bool = False
    fallback_reason: str | None = None
    endpoint_role: str | None = None
    latency_ms: int = 0
    input_count: int = 0
    output_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_metadata(self) -> Dict[str, Any]:
        metadata = dict(self.metadata or {})
        # 수정 포인트: 운영 로그/응답 metadata에서 reranker 실행시간을 바로 확인할 수 있게
        # 공통 timing key를 항상 노출합니다. provider별 상세값은 metadata에 추가로 병합됩니다.
        return {
            "provider": self.provider,
            "applied": self.applied,
            "fallback": self.fallback,
            "fallbackReason": self.fallback_reason,
            "endpointRole": self.endpoint_role,
            "latencyMs": self.latency_ms,
            "inputCount": self.input_count,
            "outputCount": self.output_count,
            "primaryLatencyMs": int(metadata.get("primaryLatencyMs") or 0),
            "fallbackLatencyMs": int(metadata.get("fallbackLatencyMs") or 0),
            "totalLatencyMs": int(metadata.get("totalLatencyMs") or self.latency_ms or 0),
            **metadata,
        }
