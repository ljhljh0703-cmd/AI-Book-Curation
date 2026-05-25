from __future__ import annotations

import json
import re
from typing import Any, Dict, List


def extract_json_object(text: str) -> Dict[str, Any]:
    """LLM 응답에서 첫 번째 JSON object만 안전하게 추출합니다."""
    if not text:
        return {}
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        value = json.loads(stripped)
        return value if isinstance(value, dict) else {}
    except Exception:
        pass

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        value = json.loads(stripped[start : end + 1])
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def to_string_list(value: Any, limit: int = 12) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parsed = None
        text = value.strip()
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except Exception:
                parsed = None
        if isinstance(parsed, list):
            value = parsed
        elif text:
            value = [text]
        else:
            value = []
    if not isinstance(value, list):
        return []
    result: List[str] = []
    seen = set()
    for item in value:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text[:80])
        if len(result) >= limit:
            break
    return result


def clamp_float(value: Any, minimum: float, maximum: float, default: float = 0.0) -> float:
    try:
        number = float(value)
    except Exception:
        return default
    if number != number or number in {float("inf"), float("-inf")}:
        return default
    return max(minimum, min(maximum, number))
