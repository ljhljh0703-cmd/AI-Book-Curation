from __future__ import annotations

import re
from typing import Any, List


_IDENTIFIER_KEY_NAMES = {
    "id",
    "bookid",
    "book_id",
    "isbn",
    "isbn10",
    "isbn13",
    "kcid",
    "vectorpointid",
    "vector_point_id",
}
_UUID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
_LONG_DIGIT_PATTERN = re.compile(r"^\d{10,}$")


def safe_join(values: Any) -> str:
    if isinstance(values, list):
        return ", ".join(str(v) for v in values if v)
    if values is None:
        return ""
    return str(values)


def normalize_text(value: Any) -> str:
    if value is None:
        return ""

    text = str(value).lower().strip()
    for token in [" ", "-", "_", "·", ".", ",", ":", ";", "!", "?", "'", '"']:
        text = text.replace(token, "")
    return text


def get_simple_intro(book: dict[str, Any]) -> str:
    for key in ["simple_intro", "description", "book_intro"]:
        value = book.get(key)
        if value:
            return str(value).strip()
    return "제공된 소개 정보가 없습니다."


def is_identifier_like(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    compact = text.replace("-", "")
    return bool(_UUID_PATTERN.match(text) or _LONG_DIGIT_PATTERN.match(compact))


def _is_identifier_key(key: Any) -> bool:
    normalized = str(key or "").strip().replace("-", "_").lower()
    return normalized in _IDENTIFIER_KEY_NAMES


def coerce_profile_values(
    value: Any,
    preferred_keys: List[str] | None = None,
    *,
    include_identifier_values: bool = False,
) -> List[str]:
    preferred_keys = preferred_keys or [
        "name",
        "label",
        "title",
        "keyword",
        "category",
        "categoryName",
        "genre",
        "mood",
        "value",
    ]

    if value is None:
        return []

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if not include_identifier_values and is_identifier_like(text):
            return []
        return [text]

    if isinstance(value, (int, float, bool)):
        text = str(value)
        if not include_identifier_values and is_identifier_like(text):
            return []
        return [text]

    if isinstance(value, list):
        result: List[str] = []
        for item in value:
            result.extend(
                coerce_profile_values(
                    item,
                    preferred_keys,
                    include_identifier_values=include_identifier_values,
                )
            )
        return result

    if isinstance(value, dict):
        result: List[str] = []
        for key in preferred_keys:
            if key in value:
                if not include_identifier_values and _is_identifier_key(key):
                    continue
                result.extend(
                    coerce_profile_values(
                        value.get(key),
                        preferred_keys,
                        include_identifier_values=include_identifier_values,
                    )
                )

        if not result:
            for nested_key, nested_value in value.items():
                if not include_identifier_values and _is_identifier_key(nested_key):
                    continue
                if isinstance(nested_value, (str, int, float, bool)):
                    result.extend(
                        coerce_profile_values(
                            nested_value,
                            preferred_keys,
                            include_identifier_values=include_identifier_values,
                        )
                    )

        return result

    return []


def dedupe_texts(values: List[str], limit: int = 12) -> List[str]:
    deduped: List[str] = []
    seen = set()

    for value in values:
        text = str(value).strip()
        if not text:
            continue

        normalized = normalize_text(text)
        if not normalized or normalized in seen:
            continue

        seen.add(normalized)
        deduped.append(text)

        if len(deduped) >= limit:
            break

    return deduped
