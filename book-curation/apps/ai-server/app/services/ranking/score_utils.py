from __future__ import annotations

from typing import Any, Iterable, List


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_min_max(values: Iterable[float], default: float = 0.5) -> List[float]:
    numbers = [safe_float(value) for value in values]
    if not numbers:
        return []
    min_value = min(numbers)
    max_value = max(numbers)
    if max_value <= min_value:
        return [default for _ in numbers]
    return [(value - min_value) / (max_value - min_value) for value in numbers]


def candidate_item_key(candidate: dict[str, Any], field_names: Iterable[str]) -> str:
    for field_name in field_names:
        value = candidate.get(field_name)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""
