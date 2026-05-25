from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, List

from app.services.intent.query_intent_parser import QueryIntent


_HANGUL_RUN_PATTERN = re.compile(r"[가-힣]{4,}")
_SPACE_PATTERN = re.compile(r"\s+")


@dataclass(frozen=True)
class QueryVariantResult:
    variants: List[str] = field(default_factory=list)
    normalized_variants: List[str] = field(default_factory=list)
    generated_by: str = "ALGORITHMIC_COMPOUND_SPACING"


class QueryVariantBuilder:
    """Build generic spacing variants without domain keyword mappings."""

    def build(self, *, query: str, query_intent: QueryIntent, limit: int = 6) -> QueryVariantResult:
        values: List[str] = []

        def add(value: Any) -> None:
            text = self._normalize_space(value)
            if text and text not in values:
                values.append(text)

        has_consumption_context = bool(getattr(query_intent, "consumption_context", None))

        if not has_consumption_context:
            add(query)
        add(query_intent.retrieval_query)
        if not has_consumption_context:
            add(query_intent.raw_query)

        variant_sources = [query_intent.retrieval_query]
        if not has_consumption_context:
            variant_sources.append(query)
            variant_sources.append(query_intent.raw_query)
        for source in variant_sources:
            for variant in self._compound_spacing_variants(source, max_variants=4):
                add(variant)

        for term in [*query_intent.genres, *query_intent.soft_genres]:
            add(term)

        joined_terms = " ".join(
            term for term in [*query_intent.genres, *query_intent.soft_genres] if str(term or "").strip()
        )
        add(joined_terms)

        return QueryVariantResult(
            variants=values[:limit],
            normalized_variants=values[1:limit],
        )

    @classmethod
    def _compound_spacing_variants(cls, value: Any, *, max_variants: int) -> List[str]:
        text = cls._normalize_space(value)
        if not text:
            return []

        variants: List[str] = []
        seen = {text}
        for match in _HANGUL_RUN_PATTERN.finditer(text):
            token = match.group(0)
            if len(token) > 14:
                continue
            for split_index in cls._split_positions(token):
                spaced_token = token[:split_index] + " " + token[split_index:]
                candidate = text[: match.start()] + spaced_token + text[match.end() :]
                candidate = cls._normalize_space(candidate)
                if candidate and candidate not in seen:
                    seen.add(candidate)
                    variants.append(candidate)
                    if len(variants) >= max_variants:
                        return variants
        return variants

    @staticmethod
    def _split_positions(token: str) -> List[int]:
        length = len(token)
        positions = [index for index in range(2, length - 1) if length - index >= 2]
        target = (length + 1) // 2
        return sorted(positions, key=lambda index: (abs(index - target), index))

    @staticmethod
    def _normalize_space(value: Any) -> str:
        return _SPACE_PATTERN.sub(" ", str(value or "")).strip()
