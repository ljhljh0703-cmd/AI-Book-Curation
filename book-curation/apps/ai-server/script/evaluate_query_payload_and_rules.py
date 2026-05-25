#!/usr/bin/env python3
"""
Evaluate how query payload composition and rule-based weights affect retrieval candidates.

This script is intentionally isolated from the production FastAPI route. It calls the
ai-server retrieval/reranking modules directly so that evaluation can inspect candidate
pools before final answer generation, external rerankers, and LLM reason generation hide
where quality changed.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import sys
import time
import warnings
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# Allow running from repository root without installing the ai-server package.
SCRIPT_PATH = Path(__file__).resolve()
AI_SERVER_ROOT = SCRIPT_PATH.parents[1]
if str(AI_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_SERVER_ROOT))

# 수정 포인트: local runner 평가에서는 Qdrant NodePort를 http로 호출할 수밖에 없어
# qdrant_client가 api-key/http 조합을 UserWarning으로 출력합니다. 평가 실패가 아니므로
# 관리자 화면 stderr에 에러처럼 노출되지 않도록 해당 경고만 명시적으로 숨깁니다.
warnings.filterwarnings(
    "ignore",
    message=r"Api key is used with an insecure connection\.",
    category=UserWarning,
    module=r"qdrant_client\..*",
)


LLM_REQUIRED_QUERY_VARIANTS = {
    "llm_search_query",
    "retrieval_query",
    "retrieval_plus_context",
    "retrieval_plus_profile",
}


def elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def log_eval_event(stage: str, status: str = "INFO", **fields: Any) -> None:
    """Emit structured evaluation progress logs for local-runner/NAS log inspection."""
    payload: Dict[str, Any] = {"stage": stage, "status": status}
    for key, value in fields.items():
        if value is None:
            continue
        if key == "query_text":
            value = str(value)[:240]
        if key == "error_message":
            value = str(value)[:500]
        payload[key] = value
    print("[EVAL] " + json.dumps(payload, ensure_ascii=False, default=str), flush=True)


class EvaluationClovaCompletionClient:
    """Lazy Clova wrapper used only by LLM-based evaluation query variants."""

    def __init__(self, timeout_seconds: float) -> None:
        self.timeout_seconds = max(1.0, float(timeout_seconds or 1.0))
        self._client: Any | None = None

    def _client_instance(self) -> Any:
        if self._client is None:
            # 평가에서 original/dense만 실행할 때는 이 import/초기화 자체가 발생하지 않도록 lazy 처리합니다.
            from app.services.clients.clova_client import ClovaClient

            self._client = ClovaClient()
        return self._client

    def chat_completion(self, system_prompt: str, user_prompt: str) -> str:
        # 평가 전용 timeout/fallback입니다. 운영 추천 API의 ClovaClient 설정은 변경하지 않습니다.
        from app.core.config import settings

        previous_timeout = getattr(settings, "CLOVA_CHAT_TIMEOUT_SECONDS", None)
        previous_retries = getattr(settings, "CLOVA_MAX_RETRIES", None)
        try:
            if previous_timeout is not None:
                settings.CLOVA_CHAT_TIMEOUT_SECONDS = min(float(previous_timeout), self.timeout_seconds)
            if previous_retries is not None:
                settings.CLOVA_MAX_RETRIES = min(int(previous_retries), 1)
            return self._client_instance().chat_completion(system_prompt=system_prompt, user_prompt=user_prompt)
        except Exception as exc:
            log_eval_event("clova_call", "FALLBACK", fallback=True, error_message=exc)
            return ""
        finally:
            if previous_timeout is not None:
                settings.CLOVA_CHAT_TIMEOUT_SECONDS = previous_timeout
            if previous_retries is not None:
                settings.CLOVA_MAX_RETRIES = previous_retries


@dataclass(frozen=True)
class EvalCase:
    id: str
    query: str
    category: str = "general"
    personalized: bool = False
    profile: Dict[str, Any] | None = None
    expected: Dict[str, Any] | None = None
    intent_override: Dict[str, Any] | None = None


@dataclass(frozen=True)
class RetrievalResult:
    candidates: List[Dict[str, Any]]
    latency_ms: int
    extra: Dict[str, Any]


class Tokenizer:
    _TOKEN_PATTERN = re.compile(r"[0-9A-Za-z가-힣]+")
    _HANGUL_PATTERN = re.compile(r"^[가-힣]+$")

    @classmethod
    def tokens(cls, value: Any) -> List[str]:
        text = str(value or "").lower()
        base_tokens = cls._TOKEN_PATTERN.findall(text)
        output: List[str] = []
        seen: set[str] = set()
        for token in base_tokens:
            if not token:
                continue
            cls._add(output, seen, token)
            # 평가용 BM25/lookup 보강: 한국어 복합명사·붙여쓰기 query가 많은 편이라
            # 운영 로직이 아니라 offline lexical 평가에서만 짧은 character n-gram을 추가합니다.
            if cls._HANGUL_PATTERN.match(token) and 3 <= len(token) <= 16:
                for n in (2, 3):
                    for index in range(0, max(0, len(token) - n + 1)):
                        cls._add(output, seen, token[index : index + n])
        return output

    @staticmethod
    def _add(output: List[str], seen: set[str], token: str) -> None:
        if token and token not in seen:
            seen.add(token)
            output.append(token)


class CandidateKey:
    @staticmethod
    def key(candidate: Dict[str, Any]) -> str:
        isbn = str(candidate.get("isbn") or candidate.get("isbn13") or "").strip()
        if isbn:
            return f"isbn:{isbn}"
        title = CandidateKey._normalize(candidate.get("title"))
        author = CandidateKey._normalize(candidate.get("author"))
        return f"title_author:{title}:{author}"

    @staticmethod
    def _normalize(value: Any) -> str:
        text = str(value or "").lower().strip()
        text = re.sub(r"\s+", "", text)
        return text


class QdrantCorpus:
    """Qdrant payload cache used only for evaluation BM25/lookup variants."""

    def __init__(self, retriever: Any, cache_path: Path | None, max_docs: int) -> None:
        self.retriever = retriever
        self.cache_path = cache_path
        self.max_docs = max(1, int(max_docs or 1))
        self._docs: Optional[List[Dict[str, Any]]] = None

    def docs(self) -> List[Dict[str, Any]]:
        if self._docs is not None:
            return self._docs
        if self.cache_path and self.cache_path.exists():
            self._docs = self._load_cache(self.cache_path)
            return self._docs
        self._docs = self._load_from_qdrant()
        if self.cache_path:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with self.cache_path.open("w", encoding="utf-8") as out:
                for doc in self._docs:
                    out.write(json.dumps(doc, ensure_ascii=False) + "\n")
        return self._docs

    @staticmethod
    def _load_cache(path: Path) -> List[Dict[str, Any]]:
        docs: List[Dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                docs.append(json.loads(line))
        return docs

    def _load_from_qdrant(self) -> List[Dict[str, Any]]:
        docs: List[Dict[str, Any]] = []
        offset = None
        while len(docs) < self.max_docs:
            batch_limit = min(512, self.max_docs - len(docs))
            points, offset = self.retriever.client.scroll(
                collection_name=self.retriever.collection_name,
                limit=batch_limit,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            if not points:
                break
            # _format_points keeps the same payload shape used by the current ai-server retrieval path.
            docs.extend(self.retriever._format_points(points, match_type="bm25_corpus", default_score=0.0))
            if offset is None:
                break
        return docs


class Bm25Index:
    def __init__(self, docs: Sequence[Dict[str, Any]]) -> None:
        self.docs = list(docs)
        self.doc_tokens: List[List[str]] = [Tokenizer.tokens(self._doc_text(doc)) for doc in self.docs]
        self.doc_len = [len(tokens) for tokens in self.doc_tokens]
        self.avgdl = sum(self.doc_len) / len(self.doc_len) if self.doc_len else 0.0
        self.df: Counter[str] = Counter()
        for tokens in self.doc_tokens:
            self.df.update(set(tokens))
        self.N = len(self.docs)

    def search(self, query: str, limit: int) -> List[Dict[str, Any]]:
        query_tokens = Tokenizer.tokens(query)
        if not query_tokens or not self.docs:
            return []
        scores: List[Tuple[float, int]] = []
        qtf = Counter(query_tokens)
        k1 = 1.5
        b = 0.75
        for index, tokens in enumerate(self.doc_tokens):
            if not tokens:
                continue
            tf = Counter(tokens)
            score = 0.0
            for token, query_count in qtf.items():
                freq = tf.get(token, 0)
                if freq <= 0:
                    continue
                df = self.df.get(token, 0)
                idf = math.log(1 + (self.N - df + 0.5) / (df + 0.5))
                denom = freq + k1 * (1 - b + b * (self.doc_len[index] / (self.avgdl or 1.0)))
                score += idf * ((freq * (k1 + 1)) / denom) * min(1.0 + math.log1p(query_count), 2.0)
            if score > 0:
                scores.append((score, index))
        scores.sort(reverse=True)
        max_score = scores[0][0] if scores else 1.0
        result: List[Dict[str, Any]] = []
        for rank, (score, index) in enumerate(scores[:limit], start=1):
            item = dict(self.docs[index])
            item["score"] = round(score / max_score, 6) if max_score else 0.0
            item["match_type"] = "bm25"
            item["retrieval_rank"] = rank
            result.append(item)
        return result

    @staticmethod
    def _doc_text(doc: Dict[str, Any]) -> str:
        fields = [
            doc.get("title"),
            doc.get("author"),
            doc.get("publisher"),
            doc.get("description"),
            doc.get("simple_intro"),
            doc.get("book_intro"),
            doc.get("categoryName"),
            doc.get("category_name"),
            doc.get("category_full_name"),
            doc.get("category_path"),
            doc.get("genre"),
            " ".join(str(x) for x in doc.get("genres") or []),
            " ".join(str(x) for x in doc.get("categories") or []),
            " ".join(str(x) for x in doc.get("cate_depth1") or []),
            " ".join(str(x) for x in doc.get("cate_depth2") or []),
            " ".join(str(x) for x in doc.get("cate_depth3") or []),
            " ".join(str(x) for x in doc.get("kcid") or []),
            doc.get("book_index"),
            doc.get("pub_review"),
        ]
        return " ".join(str(field or "") for field in fields)


class LookupIndex:
    def __init__(self, docs: Sequence[Dict[str, Any]]) -> None:
        self.docs = list(docs)

    def search(self, query: str, limit: int) -> List[Dict[str, Any]]:
        query_tokens = Tokenizer.tokens(query)
        if not query_tokens:
            return []
        scored: List[Tuple[float, int]] = []
        for index, doc in enumerate(self.docs):
            score = self._score_doc(query_tokens, doc)
            if score > 0:
                scored.append((score, index))
        scored.sort(reverse=True)
        max_score = scored[0][0] if scored else 1.0
        result: List[Dict[str, Any]] = []
        for rank, (score, index) in enumerate(scored[:limit], start=1):
            item = dict(self.docs[index])
            item["score"] = round(score / max_score, 6) if max_score else 0.0
            item["match_type"] = "lookup_payload_text"
            item["retrieval_rank"] = rank
            result.append(item)
        return result

    @staticmethod
    def _score_doc(query_tokens: Sequence[str], doc: Dict[str, Any]) -> float:
        title = str(doc.get("title") or "").lower()
        author = str(doc.get("author") or "").lower()
        categories = " ".join(
            str(x or "")
            for x in [
                doc.get("categoryName"),
                doc.get("category_name"),
                doc.get("category_full_name"),
                doc.get("category_path"),
                doc.get("genre"),
                *(doc.get("genres") or []),
                *(doc.get("categories") or []),
                *(doc.get("cate_depth1") or []),
                *(doc.get("cate_depth2") or []),
                *(doc.get("cate_depth3") or []),
            ]
        ).lower()
        description = " ".join(
            str(x or "") for x in [doc.get("description"), doc.get("simple_intro"), doc.get("book_intro")]
        ).lower()
        score = 0.0
        for token in query_tokens:
            if token in title:
                score += 3.0
            if token in author:
                score += 2.5
            if token in categories:
                score += 2.0
            if token in description:
                score += 0.75
        return score / math.sqrt(max(1, len(query_tokens)))


class QueryPayloadBuilder:
    def __init__(self, intent_parser: Any, *, llm_timeout_seconds: float) -> None:
        self.intent_parser = intent_parser
        self.llm_timeout_seconds = llm_timeout_seconds
        self._intent_classifier: Any | None = None

    def build_requested_variants(
        self,
        *,
        case: EvalCase,
        requested_variants: Sequence[str],
    ) -> Tuple[Dict[str, str], Dict[str, Any]]:
        """Build only the query variants requested by the evaluation run.

        수정 포인트:
        - original variant는 입력 query를 그대로 반환하고 LLM/Clova 초기화도 하지 않습니다.
        - LLM 기반 query가 필요한 variant가 요청된 경우에만 ChatIntentClassifier/ClovaClient를 lazy 초기화합니다.
        - 평가용 LLM 호출 실패/timeout은 전체 job 실패가 아니라 original query fallback으로 기록합니다.
        """
        normalized_requested = [str(item or "").strip() for item in requested_variants if str(item or "").strip()]
        variants: Dict[str, str] = {"original": case.query}
        metadata = self._base_metadata(fallback=False)

        llm_requested = any(item in LLM_REQUIRED_QUERY_VARIANTS for item in normalized_requested)
        if not llm_requested:
            for item in normalized_requested:
                variants.setdefault(item, case.query)
            metadata["query_variant_source"] = "original_only_or_non_llm_requested"
            return {key: value for key, value in variants.items() if str(value or "").strip()}, metadata

        try:
            intent, query_intent = self.classify_and_parse(case)
            variants.update(self._variants_from_intent(case, intent, query_intent))
            metadata = self._intent_metadata(intent, query_intent, fallback=False)
            return {key: value for key, value in variants.items() if str(value or "").strip()}, metadata
        except Exception as exc:
            log_eval_event(
                "query variant generation",
                "FALLBACK",
                case_id=case.id,
                query_text=case.query,
                fallback=True,
                error_message=exc,
            )
            for item in normalized_requested:
                variants[item] = case.query
            metadata = self._base_metadata(fallback=True, error_message=str(exc))
            return {key: value for key, value in variants.items() if str(value or "").strip()}, metadata

    def classify_and_parse(self, case: EvalCase) -> Tuple[Any, Any]:
        if case.intent_override:
            from app.services.intent.chat_intent_classifier import ChatIntent

            defaults = {
                "name": "recommend_book",
                "query_type": "recommend",
                "requires_history": False,
                "source": "eval_case_override",
                "reason": "provided by evaluation case",
            }
            defaults.update(case.intent_override)
            intent = ChatIntent(**defaults)
        else:
            intent = self._classifier().classify(
                query=case.query,
                history=[],
                history_text="",
                profile_context="",
            )
        return intent, self.intent_parser.parse(case.query, chat_intent=intent)

    def _classifier(self) -> Any:
        if self._intent_classifier is None:
            from app.services.intent.chat_intent_classifier import ChatIntentClassifier

            # ClovaClient는 EvaluationClovaCompletionClient 안에서 실제 chat_completion 시점에만 생성됩니다.
            self._intent_classifier = ChatIntentClassifier(
                EvaluationClovaCompletionClient(timeout_seconds=self.llm_timeout_seconds)
            )
        return self._intent_classifier

    def _variants_from_intent(self, case: EvalCase, intent: Any, query_intent: Any) -> Dict[str, str]:
        profile = case.profile or {}
        variants = {
            "original": case.query,
            "llm_search_query": getattr(intent, "recommendation_search_query", None) or case.query,
            "retrieval_query": getattr(query_intent, "retrieval_query", None) or case.query,
            "topic_query": getattr(query_intent, "topic_query", None) or getattr(query_intent, "retrieval_query", None) or case.query,
            "reranker_query": getattr(query_intent, "reranker_query", None) or getattr(query_intent, "retrieval_query", None) or case.query,
        }
        variants["retrieval_plus_genre"] = self._join(
            variants["retrieval_query"],
            *(getattr(query_intent, "genres", []) or []),
            *(getattr(query_intent, "soft_genres", []) or []),
        )
        variants["retrieval_plus_purpose"] = self._join(
            variants["retrieval_query"],
            getattr(query_intent, "requested_purpose", None),
            *(getattr(query_intent, "purpose_terms", []) or []),
        )
        variants["retrieval_plus_context"] = self._join(
            variants["retrieval_query"],
            getattr(query_intent, "consumption_context", None),
            *(getattr(query_intent, "consumption_positive_terms", []) or []),
        )
        variants["retrieval_plus_profile"] = self._join(
            variants["retrieval_query"],
            *self._profile_terms(profile),
        )
        return variants

    @staticmethod
    def _base_metadata(*, fallback: bool, error_message: str | None = None) -> Dict[str, Any]:
        return {
            "intent": None,
            "intent_source": None,
            "llm_search_query": None,
            "llm_topic_query": None,
            "llm_reranker_query": None,
            "retrieval_query": None,
            "topic_query": None,
            "reranker_query": None,
            "reading_mode": None,
            "consumption_context": None,
            "requested_audience_group": None,
            "requested_recommendation_count": None,
            "query_variant_fallback": fallback,
            "query_variant_error": error_message or "",
        }

    @classmethod
    def _intent_metadata(cls, intent: Any, query_intent: Any, *, fallback: bool, error_message: str | None = None) -> Dict[str, Any]:
        metadata = cls._base_metadata(fallback=fallback, error_message=error_message)
        metadata.update(
            {
                "intent": getattr(intent, "name", None),
                "intent_source": getattr(intent, "source", None),
                "llm_search_query": getattr(intent, "recommendation_search_query", None),
                "llm_topic_query": getattr(intent, "recommendation_topic_query", None),
                "llm_reranker_query": getattr(intent, "recommendation_reranker_query", None),
                "retrieval_query": getattr(query_intent, "retrieval_query", None),
                "topic_query": getattr(query_intent, "topic_query", None),
                "reranker_query": getattr(query_intent, "reranker_query", None),
                "reading_mode": getattr(query_intent, "reading_mode", None),
                "consumption_context": getattr(query_intent, "consumption_context", None),
                "requested_audience_group": getattr(query_intent, "requested_audience_group", None),
                "requested_recommendation_count": getattr(query_intent, "requested_recommendation_count", None),
            }
        )
        return metadata

    @staticmethod
    def _join(*values: Any) -> str:
        output: List[str] = []
        seen: set[str] = set()
        for value in values:
            if isinstance(value, list):
                parts = value
            else:
                parts = [value]
            for part in parts:
                text = str(part or "").strip()
                if not text:
                    continue
                normalized = re.sub(r"\s+", "", text.lower())
                if normalized in seen:
                    continue
                seen.add(normalized)
                output.append(text)
        return " ".join(output).strip()

    @staticmethod
    def _profile_terms(profile: Dict[str, Any]) -> List[str]:
        terms: List[str] = []
        for key in ["preferred_genres", "preferredGenres", "interestCategories", "genres", "categories"]:
            value = profile.get(key)
            if isinstance(value, list):
                terms.extend(str(item) for item in value if str(item or "").strip())
        purpose = profile.get("reading_purpose_profile") or profile.get("readingPurposeProfile") or {}
        if isinstance(purpose, dict):
            for key in ["summary", "positive_terms", "positiveTerms"]:
                value = purpose.get(key)
                if isinstance(value, list):
                    terms.extend(str(item) for item in value if str(item or "").strip())
                elif value:
                    terms.append(str(value))
        return terms[:12]


class RetrievalEvaluator:
    def __init__(
        self,
        *,
        retriever: Any,
        corpus: QdrantCorpus,
        top_k: int,
        dense_limit_multiplier: int = 3,
    ) -> None:
        self.retriever = retriever
        self.corpus = corpus
        self.top_k = max(1, int(top_k or 10))
        self.dense_limit_multiplier = max(1, int(dense_limit_multiplier or 1))
        self._bm25_index: Bm25Index | None = None
        self._lookup_index: LookupIndex | None = None

    def retrieve(self, *, variant: str, query: str, log_context: Dict[str, Any] | None = None) -> RetrievalResult:
        # log_context may already contain retrieval_variant.
        # Keep the field in one place to avoid duplicate keyword arguments in structured logs.
        context = dict(log_context or {})
        context.setdefault("retrieval_variant", variant)
        started = time.perf_counter()
        log_eval_event("retrieval", "START", query_text=query, **context)
        if variant == "dense":
            candidates = self._dense(query, log_context=context)
        elif variant == "lookup":
            candidates = self._lookup(query, log_context=context)
        elif variant == "bm25":
            candidates = self._bm25(query, log_context=context)
        elif variant == "dense_lookup":
            candidates = self._rrf_merge([self._dense(query, log_context=context), self._lookup(query, log_context=context)], ["dense", "lookup"])
        elif variant == "dense_bm25_rrf":
            candidates = self._dense_bm25_rrf(query, log_context=context)
        elif variant == "lookup_dense_bm25_rrf":
            candidates = self._rrf_merge(
                [self._lookup(query, log_context=context), self._dense_bm25_rrf(query, log_context=context)],
                ["lookup", "dense_bm25_rrf"],
            )
        elif variant == "dense_bm25":
            candidates = self._rrf_merge([self._dense(query, log_context=context), self._bm25(query, log_context=context)], ["dense", "bm25"])
        elif variant == "dense_bm25_lookup":
            candidates = self._rrf_merge(
                [self._dense(query, log_context=context), self._bm25(query, log_context=context), self._lookup(query, log_context=context)],
                ["dense", "bm25", "lookup"],
            )
        else:
            raise ValueError(f"Unsupported retrieval variant: {variant}")
        latency_ms = elapsed_ms(started)
        log_eval_event("retrieval", "COMPLETE", elapsed_ms=latency_ms, candidate_count=len(candidates), **context)
        return RetrievalResult(candidates=candidates[: self.top_k], latency_ms=latency_ms, extra={})

    def _dense(self, query: str, *, log_context: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        # 평가 목적상 dense는 precise lookup auto-routing을 우회하고 벡터 검색만 호출합니다.
        context = log_context or {}
        started = time.perf_counter()
        log_eval_event("embedding", "START", query_text=query, **context)
        log_eval_event("qdrant search", "START", query_text=query, **context)
        candidates = self.retriever.search_vector_only(query, limit=self.top_k * self.dense_limit_multiplier)
        duration = elapsed_ms(started)
        log_eval_event("qdrant search", "COMPLETE", elapsed_ms=duration, candidate_count=len(candidates), **context)
        log_eval_event("embedding", "COMPLETE", elapsed_ms=duration, candidate_count=len(candidates), **context)
        return candidates

    def _dense_bm25_rrf(self, query: str, *, log_context: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        context = log_context or {}
        started = time.perf_counter()
        log_eval_event("hybrid dense_bm25_rrf search", "START", query_text=query, **context)
        hybrid_search = getattr(self.retriever, "search_dense_bm25_rrf", None)
        if callable(hybrid_search):
            candidates = hybrid_search(query, limit=self.top_k * self.dense_limit_multiplier)
        else:
            candidates = self._rrf_merge([self._dense(query, log_context=context), self._bm25(query, log_context=context)], ["dense", "bm25"])
        log_eval_event(
            "hybrid dense_bm25_rrf search",
            "COMPLETE",
            elapsed_ms=elapsed_ms(started),
            candidate_count=len(candidates),
            **context,
        )
        return candidates

    def _bm25(self, query: str, *, log_context: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        context = log_context or {}
        started = time.perf_counter()
        log_eval_event("bm25 search", "START", query_text=query, **context)
        if self._bm25_index is None:
            self._bm25_index = Bm25Index(self.corpus.docs())
        candidates = self._bm25_index.search(query, limit=self.top_k * self.dense_limit_multiplier)
        log_eval_event("bm25 search", "COMPLETE", elapsed_ms=elapsed_ms(started), candidate_count=len(candidates), **context)
        return candidates

    def _lookup(self, query: str, *, log_context: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        context = log_context or {}
        started = time.perf_counter()
        log_eval_event("lookup search", "START", query_text=query, **context)
        if self._lookup_index is None:
            self._lookup_index = LookupIndex(self.corpus.docs())
        candidates = self._lookup_index.search(query, limit=self.top_k * self.dense_limit_multiplier)
        log_eval_event("lookup search", "COMPLETE", elapsed_ms=elapsed_ms(started), candidate_count=len(candidates), **context)
        return candidates

    def _rrf_merge(self, candidate_lists: Sequence[List[Dict[str, Any]]], names: Sequence[str]) -> List[Dict[str, Any]]:
        rrf_k = 60.0
        merged: Dict[str, Dict[str, Any]] = {}
        scores: Dict[str, float] = defaultdict(float)
        sources: Dict[str, List[str]] = defaultdict(list)
        for candidates, name in zip(candidate_lists, names):
            for rank, candidate in enumerate(candidates or [], start=1):
                key = CandidateKey.key(candidate)
                if key not in merged:
                    merged[key] = dict(candidate)
                scores[key] += 1.0 / (rrf_k + rank)
                if name not in sources[key]:
                    sources[key].append(name)
        rows = []
        max_score = max(scores.values()) if scores else 1.0
        for key, candidate in merged.items():
            item = dict(candidate)
            item["score"] = round(scores[key] / max_score, 6) if max_score else 0.0
            item["match_type"] = "rrf_hybrid"
            item["retrieval_sources"] = sources[key]
            rows.append(item)
        rows.sort(key=lambda row: float(row.get("score") or 0.0), reverse=True)
        return rows


class RuleVariantRunner:
    def __init__(self, profile_reranker: Any) -> None:
        self.profile_reranker = profile_reranker
        self.base_presets = json.loads(json.dumps(profile_reranker.weight_presets, ensure_ascii=False))

    def apply(self, *, variant: str, candidates: List[Dict[str, Any]], profile: Dict[str, Any], mode: str) -> List[Dict[str, Any]]:
        rows = [dict(candidate) for candidate in candidates]
        normalized_variant = variant.strip().lower()
        if normalized_variant in {"none", "rule_off", "semantic_only"}:
            return self.profile_reranker.rerank(rows, profile={}, personalized=False, mode="DISABLED")

        self.profile_reranker.weight_presets = self._presets_for_variant(normalized_variant)
        try:
            return self.profile_reranker.rerank(rows, profile=profile, personalized=bool(profile), mode=mode)
        finally:
            self.profile_reranker.weight_presets = json.loads(json.dumps(self.base_presets, ensure_ascii=False))

    def _presets_for_variant(self, variant: str) -> Dict[str, Dict[str, float]]:
        presets = json.loads(json.dumps(self.base_presets, ensure_ascii=False))
        if variant in {"current", "current_rules"}:
            return presets
        if variant in {"query_first", "hybrid", "profile_first", "disabled"}:
            return presets
        groups = {
            "no_genre": ["genre"],
            "no_purpose": ["purpose", "purpose_penalty"],
            "no_review": ["review_positive", "review_negative"],
            "no_bookshelf": ["preferred_book", "reading_book", "read_book"],
            "no_negative": ["purpose_penalty", "review_negative", "disliked_penalty"],
            "no_audience": ["audience_bonus", "audience_penalty"],
            "half_personalization": [
                "profile_vector",
                "genre",
                "purpose",
                "preferred_book",
                "reading_book",
                "read_book",
                "review_positive",
                "audience_bonus",
            ],
            "strong_personalization": [
                "profile_vector",
                "genre",
                "purpose",
                "preferred_book",
                "reading_book",
                "read_book",
                "review_positive",
                "audience_bonus",
            ],
        }
        if variant not in groups:
            return presets
        for mode, weights in presets.items():
            for key in groups[variant]:
                if key not in weights:
                    continue
                if variant == "half_personalization":
                    weights[key] *= 0.5
                elif variant == "strong_personalization":
                    weights[key] *= 1.5
                else:
                    weights[key] = 0.0
            self._renormalize_positive_weights(weights)
        return presets

    @staticmethod
    def _renormalize_positive_weights(weights: Dict[str, float]) -> None:
        positive_keys = [
            "semantic",
            "profile_vector",
            "genre",
            "purpose",
            "preferred_book",
            "reading_book",
            "read_book",
            "review_positive",
            "audience_bonus",
        ]
        total = sum(max(0.0, float(weights.get(key) or 0.0)) for key in positive_keys)
        if total <= 0:
            weights["semantic"] = 1.0
            for key in positive_keys:
                if key != "semantic":
                    weights[key] = 0.0
            return
        for key in positive_keys:
            weights[key] = float(weights.get(key) or 0.0) / total


def read_cases(path: Path) -> List[EvalCase]:
    cases: List[EvalCase] = []
    with path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            data = json.loads(line)
            cases.append(
                EvalCase(
                    id=str(data.get("id") or f"case-{line_number}"),
                    query=str(data.get("query") or ""),
                    category=str(data.get("category") or "general"),
                    personalized=bool(data.get("personalized", False)),
                    profile=data.get("profile") if isinstance(data.get("profile"), dict) else {},
                    expected=data.get("expected") if isinstance(data.get("expected"), dict) else {},
                    intent_override=data.get("intent_override") if isinstance(data.get("intent_override"), dict) else None,
                )
            )
    return cases


def candidate_preview(candidate: Dict[str, Any]) -> str:
    category = candidate.get("category_full_name") or candidate.get("categoryName") or candidate.get("category_name")
    if not category:
        values = []
        for field in ["cate_depth1", "categories", "kcid"]:
            value = candidate.get(field)
            if isinstance(value, list):
                values.extend(str(item) for item in value[:3])
            elif value:
                values.append(str(value))
        category = " / ".join(values[:4])
    return " | ".join(
        str(x or "")
        for x in [candidate.get("title"), candidate.get("author"), category, candidate.get("description") or candidate.get("simple_intro")]
    )[:700]


def expected_flags(case: EvalCase, query_variant_text: str, candidates: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    expected = case.expected or {}
    forbidden = [str(value) for value in expected.get("query_should_not_contain", []) or []]
    query_contamination = any(term and term in query_variant_text for term in forbidden)
    audio_required = bool(expected.get("audio_evidence_required"))
    audio_evidence_count = 0
    if audio_required:
        for candidate in candidates:
            evidence = candidate.get("source_format_evidence") or {}
            if candidate.get("is_audio_book") or evidence.get("matched"):
                audio_evidence_count += 1
    return {
        "query_contamination": query_contamination,
        "audio_evidence_required": audio_required,
        "audio_evidence_rate": round(audio_evidence_count / len(candidates), 4) if candidates else 0.0,
    }


def write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as out:
        for row in rows:
            out.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def run_evaluation(args: argparse.Namespace) -> None:
    from app.services.intent.query_intent_parser import QueryIntentParser
    from app.services.recommendation.profile_reranker import ProfileReranker
    from app.services.retrieval.qdrant_kure_search import BookKureQdrantSearcher
    from app.services.retrieval.qdrant_search import BookQdrantSearcher

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    case_load_started = time.perf_counter()
    log_eval_event("case load", "START", cases_path=str(args.cases))
    cases = read_cases(Path(args.cases))
    log_eval_event("case load", "COMPLETE", elapsed_ms=elapsed_ms(case_load_started), case_count=len(cases))

    log_eval_event(
        "evaluation config",
        "INFO",
        embedding_model=args.embedding_model.upper(),
        top_k=args.top_k,
        max_corpus_docs=args.max_corpus_docs,
        qdrant_url=os.getenv("QDRANT_URL"),
        qdrant_host=os.getenv("QDRANT_HOST"),
        qdrant_port=os.getenv("QDRANT_PORT"),
        kure_embedding_base_url=os.getenv("KURE_EMBEDDING_BASE_URL") or os.getenv("KURE_EMBEDDING_URL"),
        out_dir=str(out_dir),
    )

    from app.core.config import settings

    requested_retrieval_variants = [item.strip() for item in args.retrieval_variants.split(",") if item.strip()]
    requires_hybrid_collection = any("bm25_rrf" in variant for variant in requested_retrieval_variants)

    if args.embedding_model.upper() == "KURE":
        retriever = BookKureQdrantSearcher(
            collection_name=(getattr(settings, "QDRANT_KURE_HYBRID_COLLECTION", "books_kure_hybrid") if requires_hybrid_collection else None),
            hybrid_enabled=requires_hybrid_collection,
            fallback_collection_name=getattr(settings, "QDRANT_KURE_COLLECTION", "books_kure"),
        )
    else:
        retriever = BookQdrantSearcher(
            collection_name=(getattr(settings, "QDRANT_HYBRID_COLLECTION", "books_hybrid") if requires_hybrid_collection else None),
            hybrid_enabled=requires_hybrid_collection,
            fallback_collection_name=getattr(settings, "QDRANT_COLLECTION", "books"),
        )

    corpus = QdrantCorpus(
        retriever=retriever,
        cache_path=Path(args.corpus_cache) if args.corpus_cache else out_dir / "qdrant_payload_corpus.jsonl",
        max_docs=args.max_corpus_docs,
    )
    payload_builder = QueryPayloadBuilder(QueryIntentParser(), llm_timeout_seconds=args.llm_timeout_seconds)
    retrieval_evaluator = RetrievalEvaluator(retriever=retriever, corpus=corpus, top_k=args.top_k)
    rule_runner = RuleVariantRunner(ProfileReranker())

    query_variants = [item.strip() for item in args.query_variants.split(",") if item.strip()]
    retrieval_variants = requested_retrieval_variants
    rule_variants = [item.strip() for item in args.rule_variants.split(",") if item.strip()]

    raw_rows: List[Dict[str, Any]] = []
    label_rows: List[Dict[str, Any]] = []
    auto_summary_rows: List[Dict[str, Any]] = []

    for case in cases:
        log_eval_event("case", "START", case_id=case.id, query_text=case.query)
        variant_started = time.perf_counter()
        log_eval_event("query variant generation", "START", case_id=case.id, query_text=case.query, query_variants=",".join(query_variants))
        variant_map, intent_metadata = payload_builder.build_requested_variants(
            case=case,
            requested_variants=query_variants,
        )
        log_eval_event(
            "query variant generation",
            "COMPLETE",
            case_id=case.id,
            elapsed_ms=elapsed_ms(variant_started),
            candidate_count=len(variant_map),
            fallback=bool(intent_metadata.get("query_variant_fallback")),
            error_message=intent_metadata.get("query_variant_error"),
        )

        for query_variant in query_variants:
            query_text = variant_map.get(query_variant)
            if not query_text:
                log_eval_event("query variant generation", "SKIP", case_id=case.id, query_variant=query_variant, error_message="empty query variant")
                continue
            for retrieval_variant in retrieval_variants:
                log_context = {
                    "case_id": case.id,
                    "query_variant": query_variant,
                    "retrieval_variant": retrieval_variant,
                }
                try:
                    retrieval_result = retrieval_evaluator.retrieve(
                        variant=retrieval_variant,
                        query=query_text,
                        log_context=log_context,
                    )
                except Exception as exc:
                    log_eval_event(
                        "retrieval",
                        "ERROR",
                        case_id=case.id,
                        query_variant=query_variant,
                        retrieval_variant=retrieval_variant,
                        query_text=query_text,
                        error_message=exc,
                    )
                    continue
                for rule_variant in rule_variants:
                    rule_started = time.perf_counter()
                    log_eval_event(
                        "rule scoring",
                        "START",
                        case_id=case.id,
                        query_variant=query_variant,
                        retrieval_variant=retrieval_variant,
                        rule_variant=rule_variant,
                        candidate_count=len(retrieval_result.candidates),
                    )
                    mode = "PROFILE_FIRST"
                    if rule_variant.lower() in {"query_first", "hybrid", "profile_first", "disabled"}:
                        mode = rule_variant.upper()
                    ranked = rule_runner.apply(
                        variant=rule_variant,
                        candidates=retrieval_result.candidates,
                        profile=case.profile or {},
                        mode=mode,
                    )[: args.top_k]
                    log_eval_event(
                        "rule scoring",
                        "COMPLETE",
                        case_id=case.id,
                        query_variant=query_variant,
                        retrieval_variant=retrieval_variant,
                        rule_variant=rule_variant,
                        elapsed_ms=elapsed_ms(rule_started),
                        candidate_count=len(ranked),
                    )
                    flags = expected_flags(case, query_text, ranked)
                    run_key = f"{case.id}__{query_variant}__{retrieval_variant}__{rule_variant}"
                    auto_summary_rows.append(
                        {
                            "run_id": run_key,
                            "query_id": case.id,
                            "category": case.category,
                            "query": case.query,
                            "query_variant": query_variant,
                            "query_text": query_text,
                            "retrieval_variant": retrieval_variant,
                            "rule_variant": rule_variant,
                            "result_count": len(ranked),
                            "latency_ms": retrieval_result.latency_ms,
                            **intent_metadata,
                            **flags,
                        }
                    )
                    for rank, candidate in enumerate(ranked, start=1):
                        score_detail = candidate.get("score_detail") or {}
                        row = {
                            "run_id": run_key,
                            "query_id": case.id,
                            "category": case.category,
                            "query": case.query,
                            "query_variant": query_variant,
                            "query_text": query_text,
                            "retrieval_variant": retrieval_variant,
                            "rule_variant": rule_variant,
                            "latency_ms": retrieval_result.latency_ms,
                            "query_variant_fallback": intent_metadata.get("query_variant_fallback"),
                            "query_variant_error": intent_metadata.get("query_variant_error"),
                            "query_contamination": flags.get("query_contamination"),
                            "audio_evidence_rate": flags.get("audio_evidence_rate"),
                            "rank": rank,
                            "isbn": candidate.get("isbn"),
                            "title": candidate.get("title"),
                            "author": candidate.get("author"),
                            "match_type": candidate.get("match_type"),
                            "retrieval_sources": ";".join(candidate.get("retrieval_sources") or []),
                            "score": candidate.get("score"),
                            "rerank_score": candidate.get("rerank_score"),
                            "semantic_score": score_detail.get("semantic_score"),
                            "genre_score": score_detail.get("genre_score"),
                            "purpose_score": score_detail.get("purpose_score"),
                            "review_rating_positive_score": score_detail.get("review_rating_positive_score"),
                            "review_rating_negative_penalty": score_detail.get("review_rating_negative_penalty"),
                            "disliked_book_penalty": score_detail.get("disliked_book_penalty"),
                            "audience_match_score": score_detail.get("audience_match_score"),
                            "off_audience_penalty": score_detail.get("off_audience_penalty"),
                            "source_format": candidate.get("source_format"),
                            "is_audio_book": candidate.get("is_audio_book"),
                            "preview": candidate_preview(candidate),
                            "human_relevance_0_2": "",
                            "human_memo": "",
                        }
                        label_rows.append(row)
                        raw_rows.append({**row, "candidate": candidate, "intent_metadata": intent_metadata, "expected_flags": flags})
        log_eval_event("case", "COMPLETE", case_id=case.id)

    raw_path = out_dir / "raw_results.jsonl"
    label_path = out_dir / "candidate_label_template.csv"
    summary_path = out_dir / "auto_summary.csv"

    started = time.perf_counter()
    log_eval_event("csv write", "START", file_name=label_path.name, row_count=len(label_rows))
    write_csv(label_path, label_rows)
    log_eval_event("csv write", "COMPLETE", file_name=label_path.name, elapsed_ms=elapsed_ms(started), row_count=len(label_rows))

    started = time.perf_counter()
    log_eval_event("summary write", "START", file_name=summary_path.name, row_count=len(auto_summary_rows))
    write_csv(summary_path, auto_summary_rows)
    log_eval_event("summary write", "COMPLETE", file_name=summary_path.name, elapsed_ms=elapsed_ms(started), row_count=len(auto_summary_rows))

    started = time.perf_counter()
    log_eval_event("raw write", "START", file_name=raw_path.name, row_count=len(raw_rows))
    write_jsonl(raw_path, raw_rows)
    log_eval_event("raw write", "COMPLETE", file_name=raw_path.name, elapsed_ms=elapsed_ms(started), row_count=len(raw_rows))

    print(f"[EVAL] wrote {raw_path}")
    print(f"[EVAL] wrote {label_path}")
    print(f"[EVAL] wrote {summary_path}")


def write_csv(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: List[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def summarize_labeled_results(args: argparse.Namespace) -> None:
    input_path = Path(args.labels)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_eval_event("summary read", "START", file_name=str(input_path))
    rows: List[Dict[str, Any]] = []
    with input_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                row["human_relevance_0_2"] = int(str(row.get("human_relevance_0_2") or "").strip())
            except ValueError:
                continue
            rows.append(row)
    log_eval_event("summary read", "COMPLETE", row_count=len(rows))

    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("run_id") or "")].append(row)

    summary: List[Dict[str, Any]] = []
    for run_id, group in grouped.items():
        group.sort(key=lambda value: int(value.get("rank") or 9999))
        top_k = group[: args.top_k]
        rels = [int(row["human_relevance_0_2"]) for row in top_k]
        precision_at_k = sum(1 for rel in rels if rel >= 1) / len(rels) if rels else 0.0
        bad_rate = sum(1 for rel in rels if rel == 0) / len(rels) if rels else 0.0
        avg_rel = sum(rels) / len(rels) if rels else 0.0
        strong_hit = any(rel == 2 for rel in rels)
        first = top_k[0] if top_k else group[0]
        summary.append(
            {
                "run_id": run_id,
                "query_id": first.get("query_id"),
                "category": first.get("category"),
                "query": first.get("query"),
                "query_variant": first.get("query_variant"),
                "query_text": first.get("query_text"),
                "retrieval_variant": first.get("retrieval_variant"),
                "rule_variant": first.get("rule_variant"),
                f"avg_rel_at_{args.top_k}": round(avg_rel, 4),
                f"precision_at_{args.top_k}": round(precision_at_k, 4),
                f"bad_rate_at_{args.top_k}": round(bad_rate, 4),
                f"strong_hit_at_{args.top_k}": int(strong_hit),
                "labeled_count": len(rels),
                "latency_ms": first.get("latency_ms"),
                "query_contamination": first.get("query_contamination"),
                "audio_evidence_rate": first.get("audio_evidence_rate"),
            }
        )
    started = time.perf_counter()
    log_eval_event("summary write", "START", file_name="labeled_summary.csv", row_count=len(summary))
    write_csv(out_dir / "labeled_summary.csv", summary)
    log_eval_event("summary write", "COMPLETE", file_name="labeled_summary.csv", elapsed_ms=elapsed_ms(started), row_count=len(summary))
    print(f"[EVAL] wrote {out_dir / 'labeled_summary.csv'}")

    # 수정 포인트: 화면에서 query 구성 요소와 retrieval 방식별 점수를 바로 비교할 수 있도록
    # 후보 row가 아니라 실험 차원별 집계 파일을 별도로 생성합니다.
    dimension_summary = build_dimension_summary(summary, args.top_k)
    started = time.perf_counter()
    log_eval_event("summary write", "START", file_name="dimension_summary.csv", row_count=len(dimension_summary))
    write_csv(out_dir / "dimension_summary.csv", dimension_summary)
    log_eval_event("summary write", "COMPLETE", file_name="dimension_summary.csv", elapsed_ms=elapsed_ms(started), row_count=len(dimension_summary))
    print(f"[EVAL] wrote {out_dir / 'dimension_summary.csv'}")


def _float_value(row: Dict[str, Any], key: str) -> float:
    try:
        return float(row.get(key) or 0)
    except (TypeError, ValueError):
        return 0.0


def build_dimension_summary(summary: Sequence[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
    avg_key = f"avg_rel_at_{top_k}"
    precision_key = f"precision_at_{top_k}"
    bad_key = f"bad_rate_at_{top_k}"
    hit_key = f"strong_hit_at_{top_k}"

    grouped: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)
    grouped_query_retrieval: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for row in summary:
        grouped[(str(row.get("query_variant") or ""), str(row.get("retrieval_variant") or ""), str(row.get("rule_variant") or ""))].append(row)
        grouped_query_retrieval[(str(row.get("query_variant") or ""), str(row.get("retrieval_variant") or ""))].append(row)

    rows: List[Dict[str, Any]] = []
    for (query_variant, retrieval_variant, rule_variant), group in grouped.items():
        rows.append(_dimension_row("query_retrieval_rule", query_variant, retrieval_variant, rule_variant, group, top_k, avg_key, precision_key, bad_key, hit_key))
    for (query_variant, retrieval_variant), group in grouped_query_retrieval.items():
        rows.append(_dimension_row("query_retrieval", query_variant, retrieval_variant, "ALL", group, top_k, avg_key, precision_key, bad_key, hit_key))
    rows.sort(key=lambda row: (_float_value(row, f"avg_rel_at_{top_k}"), _float_value(row, f"precision_at_{top_k}")), reverse=True)
    return rows


def _dimension_row(
    dimension: str,
    query_variant: str,
    retrieval_variant: str,
    rule_variant: str,
    group: Sequence[Dict[str, Any]],
    top_k: int,
    avg_key: str,
    precision_key: str,
    bad_key: str,
    hit_key: str,
) -> Dict[str, Any]:
    count = len(group)
    if count <= 0:
        count = 1
    return {
        "dimension": dimension,
        "query_variant": query_variant,
        "retrieval_variant": retrieval_variant,
        "rule_variant": rule_variant,
        "run_count": len(group),
        f"avg_rel_at_{top_k}": round(sum(_float_value(row, avg_key) for row in group) / count, 4),
        f"precision_at_{top_k}": round(sum(_float_value(row, precision_key) for row in group) / count, 4),
        f"bad_rate_at_{top_k}": round(sum(_float_value(row, bad_key) for row in group) / count, 4),
        f"strong_hit_rate_at_{top_k}": round(sum(_float_value(row, hit_key) for row in group) / count, 4),
        "avg_latency_ms": round(sum(_float_value(row, "latency_ms") for row in group) / count, 2),
        "query_contamination_rate": round(sum(1 for row in group if str(row.get("query_contamination") or "").lower() == "true") / count, 4),
        "avg_audio_evidence_rate": round(sum(_float_value(row, "audio_evidence_rate") for row in group) / count, 4),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate query payload and rule-based ranking effects.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="Run retrieval/rule evaluation and create label CSV.")
    run.add_argument("--cases", required=True, help="JSONL evaluation cases.")
    run.add_argument("--out-dir", default="apps/ai-server/script/evaluation/results/query_payload_rules")
    run.add_argument("--embedding-model", choices=["CLOVA", "KURE"], default=os.getenv("EVAL_EMBEDDING_MODEL", "CLOVA"))
    run.add_argument("--top-k", type=int, default=10)
    run.add_argument("--max-corpus-docs", type=int, default=int(os.getenv("EVAL_MAX_CORPUS_DOCS", "50000")))
    run.add_argument("--corpus-cache", default=os.getenv("EVAL_CORPUS_CACHE", ""))
    run.add_argument("--llm-timeout-seconds", type=float, default=float(os.getenv("EVAL_CLOVA_TIMEOUT_SECONDS", "8.0")))
    run.add_argument(
        "--query-variants",
        default="original,llm_search_query,retrieval_query,retrieval_plus_genre,retrieval_plus_purpose,retrieval_plus_context,retrieval_plus_profile",
    )
    run.add_argument(
        "--retrieval-variants",
        default="dense,dense_bm25_rrf,lookup_dense_bm25_rrf",
    )
    run.add_argument(
        "--rule-variants",
        default="rule_off,current,no_genre,no_purpose,no_review,no_bookshelf,no_negative,no_audience,half_personalization,strong_personalization",
    )
    run.set_defaults(func=run_evaluation)

    summarize = subparsers.add_parser("summarize", help="Aggregate manually labeled candidate CSV.")
    summarize.add_argument("--labels", required=True, help="Filled candidate_label_template.csv")
    summarize.add_argument("--out-dir", default="apps/ai-server/script/evaluation/results/query_payload_rules")
    summarize.add_argument("--top-k", type=int, default=10)
    summarize.set_defaults(func=summarize_labeled_results)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

