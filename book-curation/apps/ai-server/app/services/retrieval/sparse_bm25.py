from __future__ import annotations

import hashlib
import math
import re
from collections import Counter, defaultdict
from typing import Any, Dict, List, Sequence

from app.core.config import settings


class SparseTextVectorizer:
    """BM25 sparse vector query adapter used by the hybrid Qdrant collections.

    색인 스크립트와 동일한 입력 정규화 원칙을 운영 검색에서도 재사용합니다.
    tokenizer는 일반 토큰 + 한국어 2/3-gram 보조 토큰을 만들고, token hash index는
    운영/색인이 같은 방식으로 맞춰져야 하므로 env로만 교체할 수 있게 했습니다.
    """

    _TOKEN_PATTERN = re.compile(r"[0-9A-Za-z가-힣]+")
    _HANGUL_PATTERN = re.compile(r"^[가-힣]+$")

    def __init__(self, hash_method: str | None = None) -> None:
        self.hash_method = (
            hash_method
            or getattr(settings, "QDRANT_BM25_HASH_METHOD", "blake2b_64_mod_2000000000")
        ).strip().lower()
        self.hash_mod = int(getattr(settings, "QDRANT_BM25_HASH_MOD", 2_000_000_000))

    def tokenize(self, text: Any) -> List[str]:
        value = str(text or "").lower()
        output: List[str] = []
        seen = set()
        for match in self._TOKEN_PATTERN.findall(value):
            token = match.strip()
            if not token:
                continue
            self._append_unique(output, seen, token)
            # 수정 포인트: 한국어 단어는 색인 시 사용한 2/3-gram 보조 토큰을 query에도 동일하게 적용합니다.
            if self._HANGUL_PATTERN.match(token) and 2 <= len(token) <= 32:
                for ngram_size in (2, 3):
                    if len(token) < ngram_size:
                        continue
                    for index in range(0, len(token) - ngram_size + 1):
                        self._append_unique(output, seen, token[index : index + ngram_size])
        return output

    def vector(self, text: Any) -> Dict[str, List[float] | List[int]]:
        counter = Counter(self.tokenize(text))
        index_values: Dict[int, float] = defaultdict(float)
        for token, count in counter.items():
            index_values[self.token_hash_index(token)] += 1.0 + math.log1p(float(count))

        ordered = sorted(index_values.items(), key=lambda item: item[0])
        return {
            "indices": [int(index) for index, _ in ordered],
            "values": [float(value) for _, value in ordered],
        }

    def token_hash_index(self, token: str) -> int:
        encoded = str(token or "").encode("utf-8")
        if self.hash_method in {"blake2b_64_mod_2000000000", "blake2b_64_mod", "blake2b_mod"}:
            # 수정 포인트: NAS에서 hybrid collection을 생성할 때 사용한 sparse token index와 동일하게 맞춥니다.
            # Qdrant sparse 검색은 query/index hash가 1이라도 다르면 lexical hit가 거의 사라지므로 기본값도 운영 색인 기준으로 둡니다.
            digest = hashlib.blake2b(encoded, digest_size=8).digest()
            return int.from_bytes(digest, "little") % self.hash_mod
        if self.hash_method == "md5_32":
            return int(hashlib.md5(encoded).hexdigest()[:8], 16)
        if self.hash_method == "sha1_32":
            return int(hashlib.sha1(encoded).hexdigest()[:8], 16)
        if self.hash_method == "sha256_32":
            return int(hashlib.sha256(encoded).hexdigest()[:8], 16)
        raise ValueError(f"Unsupported QDRANT_BM25_HASH_METHOD: {self.hash_method}")

    @staticmethod
    def _append_unique(output: List[str], seen: set[str], token: str) -> None:
        if token in seen:
            return
        seen.add(token)
        output.append(token)


class CandidateKey:
    @staticmethod
    def key(candidate: Dict[str, Any]) -> str:
        qdrant_id = candidate.get("qdrant_id") or candidate.get("point_id")
        if qdrant_id not in (None, ""):
            return f"qdrant:{qdrant_id}"
        isbn = str(candidate.get("isbn") or candidate.get("isbn13") or "").strip().lower()
        if isbn:
            return f"isbn:{isbn}"
        title = str(candidate.get("title") or "").strip().lower()
        author = str(candidate.get("author") or "").strip().lower()
        return f"title_author:{title}:{author}"


def rrf_fuse(
    candidate_lists: Sequence[Sequence[Dict[str, Any]]],
    names: Sequence[str],
    *,
    limit: int | None = None,
    rrf_k: float = 60.0,
) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    scores: Dict[str, float] = defaultdict(float)
    sources: Dict[str, List[str]] = defaultdict(list)
    source_scores: Dict[str, Dict[str, float]] = defaultdict(dict)

    for candidates, source_name in zip(candidate_lists, names):
        for rank, candidate in enumerate(candidates or [], start=1):
            key = CandidateKey.key(candidate)
            if key not in merged:
                merged[key] = dict(candidate)
            scores[key] += 1.0 / (float(rrf_k) + float(rank))
            if source_name not in sources[key]:
                sources[key].append(source_name)
            try:
                source_scores[key][f"{source_name}_score"] = float(candidate.get("score") or 0.0)
            except (TypeError, ValueError):
                source_scores[key][f"{source_name}_score"] = 0.0

    max_score = max(scores.values()) if scores else 1.0
    rows: List[Dict[str, Any]] = []
    for key, candidate in merged.items():
        item = dict(candidate)
        normalized_score = round(scores[key] / max_score, 6) if max_score else 0.0
        item["score"] = normalized_score
        item["rrf_score"] = normalized_score
        item["match_type"] = "dense_bm25_rrf"
        item["retrieval_sources"] = sources[key]
        score_detail = dict(item.get("score_detail") or {})
        score_detail.update(source_scores[key])
        score_detail["rrf_score"] = normalized_score
        item["score_detail"] = score_detail
        rows.append(item)

    rows.sort(key=lambda row: float(row.get("score") or 0.0), reverse=True)
    if limit is not None:
        return rows[: max(1, int(limit))]
    return rows
