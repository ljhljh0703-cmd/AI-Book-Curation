from __future__ import annotations

import json
import math
import re
from typing import Any, Dict, List, Optional, Sequence

from qdrant_client import QdrantClient
from qdrant_client.http.models import FieldCondition, Filter, MatchValue

from app.core.config import settings
from app.services.common.json_utils import to_string_list


class ProfileReranker:
    """로그인 사용자 프로필 기반 deterministic reranker입니다."""

    def __init__(self) -> None:
        self.weight_presets = {
            "QUERY_FIRST": {
                "semantic": 0.74,
                "profile_vector": 0.04,
                "genre": 0.05,
                "purpose": 0.04,
                "preferred_book": 0.05,
                "reading_book": 0.03,
                "read_book": 0.01,
                "review_positive": 0.04,
                "purpose_penalty": 0.08,
                "review_negative": 0.08,
                "disliked_penalty": 0.12,
                "audience_bonus": 0.03,
                "audience_penalty": 0.28,
            },
            "HYBRID": {
                "semantic": 0.57,
                "profile_vector": 0.08,
                "genre": 0.10,
                "purpose": 0.07,
                "preferred_book": 0.08,
                "reading_book": 0.04,
                "read_book": 0.015,
                "review_positive": 0.08,
                "purpose_penalty": 0.10,
                "review_negative": 0.10,
                "disliked_penalty": 0.14,
                "audience_bonus": 0.05,
                "audience_penalty": 0.34,
            },
            "PROFILE_FIRST": {
                "semantic": 0.45,
                "profile_vector": 0.12,
                "genre": 0.14,
                "purpose": 0.09,
                "preferred_book": 0.09,
                "reading_book": 0.04,
                "read_book": 0.02,
                "review_positive": 0.10,
                "purpose_penalty": 0.12,
                "review_negative": 0.12,
                "disliked_penalty": 0.16,
                "audience_bonus": 0.08,
                "audience_penalty": 0.55,
            },
            "DISABLED": {
                "semantic": 1.0,
                "profile_vector": 0.0,
                "genre": 0.0,
                "purpose": 0.0,
                "preferred_book": 0.0,
                "reading_book": 0.0,
                "read_book": 0.0,
                "review_positive": 0.0,
                "purpose_penalty": 0.0,
                "review_negative": 0.0,
                "disliked_penalty": 0.0,
                "audience_bonus": 0.0,
                "audience_penalty": 0.0,
            },
        }
        self.max_negative_penalty = 0.35
        self._qdrant_client: Optional[QdrantClient] = None
        self._profile_vector_cache: Dict[str, Optional[List[float]]] = {}
        self._book_vector_cache: Dict[str, Optional[List[float]]] = {}

    def rerank(
        self,
        candidates: List[Dict[str, Any]],
        profile: Optional[Dict[str, Any]],
        personalized: bool = False,
        mode: str = "PROFILE_FIRST",
    ) -> List[Dict[str, Any]]:
        if not candidates:
            return []
        if not personalized or not profile:
            return self._sort_by_qdrant_score(candidates)

        normalized_profile = self._normalize_profile(profile)
        if not self._has_profile_signal(normalized_profile):
            return self._sort_by_qdrant_score(candidates)

        normalized_mode = self._normalize_mode(mode)
        weights = self._resolve_weight_preset(normalized_mode)
        excluded_isbns = normalized_profile["excluded_isbns"]
        reranked: List[Dict[str, Any]] = []

        for candidate in candidates:
            item = dict(candidate)
            candidate_isbn = self._normalize_isbn(item.get("isbn"))
            if candidate_isbn and candidate_isbn in excluded_isbns:
                continue

            semantic_score = self._normalize_semantic_score(item.get("score"))
            user_profile_vector_score = self._user_profile_vector_score(item, normalized_profile)
            genre_score = self._category_match_score(item, normalized_profile["preferred_genres"])
            purpose_score = self._term_match_score(item, normalized_profile["purpose_positive_terms"])
            purpose_penalty = self._term_match_score(item, normalized_profile["purpose_negative_terms"])
            preferred_book_score = self._book_similarity_score(item, normalized_profile["preferred_books"])
            reading_book_score = self._book_similarity_score(item, normalized_profile["reading_books"])
            read_book_score = self._book_similarity_score(item, normalized_profile["read_books"])
            review_rating_positive_score = max(
                self._term_match_score(item, normalized_profile["review_positive_terms"]),
                self._book_similarity_score(item, normalized_profile["high_rated_books"]),
            )
            review_rating_negative_penalty = max(
                self._term_match_score(item, normalized_profile["review_negative_terms"]),
                self._book_similarity_score(item, normalized_profile["low_rated_books"]),
            )
            disliked_book_penalty = min(
                self.max_negative_penalty,
                self._book_similarity_score(item, normalized_profile["disliked_books"]),
            )
            previous_recommendation_penalty = min(
                0.25,
                max(
                    0.0,
                    self._safe_float(item.get("previousRecommendationPenalty"))
                    or self._safe_float(item.get("policyPenalty")),
                ),
            )
            audience_result = self._audience_alignment(item, normalized_profile, normalized_mode)
            audience_match_score = audience_result["match_score"]
            off_audience_penalty = audience_result["penalty"]

            final_score = (
                weights["semantic"] * semantic_score
                + weights["profile_vector"] * user_profile_vector_score
                + weights["genre"] * genre_score
                + weights["purpose"] * purpose_score
                + weights["preferred_book"] * preferred_book_score
                + weights["reading_book"] * reading_book_score
                + weights["read_book"] * read_book_score
                + weights["review_positive"] * review_rating_positive_score
                + weights["audience_bonus"] * audience_match_score
                - weights["purpose_penalty"] * purpose_penalty
                - weights["review_negative"] * review_rating_negative_penalty
                - weights["disliked_penalty"] * disliked_book_penalty
                - weights["audience_penalty"] * off_audience_penalty
                - previous_recommendation_penalty
            )
            final_score = max(0.0, min(1.0, final_score))

            score_detail = {
                "personalization_mode": normalized_mode,
                "semantic_weight": round(weights["semantic"], 6),
                "user_profile_vector_weight": round(weights["profile_vector"], 6),
                "genre_weight": round(weights["genre"], 6),
                "purpose_weight": round(weights["purpose"], 6),
                "preferred_book_weight": round(weights["preferred_book"], 6),
                "reading_book_weight": round(weights["reading_book"], 6),
                "read_book_weight": round(weights["read_book"], 6),
                "review_rating_positive_weight": round(weights["review_positive"], 6),
                "purpose_penalty_weight": round(weights["purpose_penalty"], 6),
                "review_rating_negative_weight": round(weights["review_negative"], 6),
                "disliked_penalty_weight": round(weights["disliked_penalty"], 6),
                "audience_bonus_weight": round(weights["audience_bonus"], 6),
                "audience_penalty_weight": round(weights["audience_penalty"], 6),
                "semantic_score": round(semantic_score, 6),
                "user_profile_vector_score": round(user_profile_vector_score, 6),
                "purpose_score": round(purpose_score, 6),
                "purpose_penalty": round(purpose_penalty, 6),
                "genre_score": round(genre_score, 6),
                "preferred_book_score": round(preferred_book_score, 6),
                "reading_book_score": round(reading_book_score, 6),
                "read_book_score": round(read_book_score, 6),
                "review_rating_positive_score": round(review_rating_positive_score, 6),
                "review_rating_negative_penalty": round(review_rating_negative_penalty, 6),
                "disliked_book_penalty": round(disliked_book_penalty, 6),
                "previous_recommendation_penalty": round(previous_recommendation_penalty, 6),
                "audience_match_score": round(audience_match_score, 6),
                "off_audience_penalty": round(off_audience_penalty, 6),
                "audience_policy_source": audience_result["source"],
                "age_group_source": audience_result.get("age_group_source", "UNKNOWN"),
                "user_age_group": audience_result["user_age_group"],
                "requested_audience_group": audience_result["requested_audience_group"],
                "candidate_audience_group": audience_result["candidate_audience_group"],
                "already_read_or_disliked_excluded": False,
            }
            evidence = self._build_personalization_evidence(item, normalized_profile, score_detail)
            score_detail["personalization_evidence"] = evidence
            score_detail["final_rerank_score"] = round(final_score, 6)

            item["rerank_score"] = round(final_score, 6)
            item["profileVectorScore"] = round(user_profile_vector_score, 6)
            item["score_detail"] = score_detail
            item["personalization_evidence"] = evidence
            item["rerank_reason"] = self._make_reason(score_detail)
            reranked.append(item)

        if not reranked:
            return self._sort_by_qdrant_score(candidates)

        reranked = sorted(
            reranked,
            key=lambda row: self._safe_float(row.get("rerank_score", row.get("score", 0.0))),
            reverse=True,
        )
        return self._drop_audience_mismatches_when_safe(reranked, normalized_mode)

    def _sort_by_qdrant_score(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        for candidate in candidates:
            item = dict(candidate)
            base_score = self._normalize_semantic_score(item.get("score"))
            item.setdefault("rerank_score", round(base_score, 6))
            item.setdefault("rerank_reason", "SEMANTIC_BASELINE")
            item.setdefault(
                "score_detail",
                {
                    "personalization_mode": "DISABLED",
                    "semantic_score": round(base_score, 6),
                    "user_profile_vector_score": 0.0,
                    "purpose_score": 0.0,
                    "purpose_penalty": 0.0,
                    "review_rating_positive_score": 0.0,
                    "review_rating_negative_penalty": 0.0,
                    "preferred_book_score": 0.0,
                    "reading_book_score": 0.0,
                    "read_book_score": 0.0,
                    "disliked_book_penalty": 0.0,
                    "personalization_evidence": {},
                },
            )
            result.append(item)
        return sorted(result, key=lambda row: self._safe_float(row.get("rerank_score")), reverse=True)

    def _normalize_profile(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        preferred_books = self._collect_book_objects(profile, ["preferred_books", "preferredBooks", "high_rated_books", "highRatedBooks"])
        disliked_books = self._collect_book_objects(profile, ["disliked_books", "dislikedBooks", "low_rated_books", "lowRatedBooks"])
        reading_books = self._collect_book_objects(profile, ["reading_books", "readingBooks"])
        read_books = self._collect_book_objects(profile, ["read_books", "readBooks", "finished_books", "finishedBooks"])
        high_rated_books = self._collect_book_objects(profile, ["high_rated_books", "highRatedBooks"])
        low_rated_books = self._collect_book_objects(profile, ["low_rated_books", "lowRatedBooks"])

        for book in self._collect_book_objects(profile, ["shelfBooks"]):
            shelf_type = self._normalize_token(book.get("shelfType") or book.get("shelf_type"))
            rating = self._safe_float(book.get("reviewRating") or book.get("rating"))
            if shelf_type in {"interested", "favorite", "wanttoread"}:
                preferred_books.append(book)
            elif shelf_type == "reading":
                reading_books.append(book)
            elif shelf_type == "read":
                read_books.append(book)
            elif shelf_type in {"notinterested", "dislike", "disliked"}:
                disliked_books.append(book)
            if rating >= 4.0:
                high_rated_books.append(book)
                preferred_books.append(book)
            elif 0 < rating <= 2.0:
                low_rated_books.append(book)
                disliked_books.append(book)

        for book in self._collect_book_objects(profile, ["reviewedBooks", "ratings"]):
            rating = self._safe_float(book.get("reviewRating") or book.get("rating") or book.get("score"))
            if rating >= 4.0:
                high_rated_books.append(book)
                preferred_books.append(book)
            elif 0 < rating <= 2.0:
                low_rated_books.append(book)
                disliked_books.append(book)

        review_signals = self._collect_review_signals(profile)
        review_positive_terms: List[str] = []
        review_negative_terms: List[str] = []
        for signal in review_signals:
            rating = self._safe_float(signal.get("rating"))
            sentiment = self._normalize_token(signal.get("overallSentiment") or signal.get("overall_sentiment"))
            review_positive_terms.extend(self._normalize_any(signal.get("likedAspects") or signal.get("liked_aspects")))
            review_positive_terms.extend(self._normalize_any(signal.get("preferenceTerms") or signal.get("preference_terms")))
            review_positive_terms.extend(self._normalize_any(signal.get("preferredMood") or signal.get("preferred_mood")))
            review_negative_terms.extend(self._normalize_any(signal.get("dislikedAspects") or signal.get("disliked_aspects")))
            review_negative_terms.extend(self._normalize_any(signal.get("avoidTerms") or signal.get("avoid_terms")))
            review_negative_terms.extend(self._normalize_any(signal.get("avoidMood") or signal.get("avoid_mood")))
            if rating >= 4.0 or sentiment == "positive":
                high_rated_books.append(signal)
            elif 0 < rating <= 2.0 or sentiment == "negative":
                low_rated_books.append(signal)
                disliked_books.append(signal)

        preference_profile = self._preference_profile(profile)
        review_positive_terms.extend(self._normalize_any(preference_profile.get("positiveTerms") or preference_profile.get("positive_terms")))
        review_positive_terms.extend(self._normalize_any(preference_profile.get("likedAspects") or preference_profile.get("liked_aspects")))
        review_negative_terms.extend(self._normalize_any(preference_profile.get("negativeTerms") or preference_profile.get("negative_terms")))
        review_negative_terms.extend(self._normalize_any(preference_profile.get("dislikedAspects") or preference_profile.get("disliked_aspects")))

        purpose_profile = profile.get("reading_purpose_profile") or profile.get("readingPurposeProfile") or {}
        if not isinstance(purpose_profile, dict):
            purpose_profile = {}
        purpose_positive_terms = self._deduplicate(self._normalize_any(purpose_profile.get("positive_terms") or purpose_profile.get("positiveTerms")))
        purpose_negative_terms = self._deduplicate(self._normalize_any(purpose_profile.get("negative_terms") or purpose_profile.get("negativeTerms")))

        excluded_isbns = set(self._collect_isbns(profile, ["excluded_isbns", "excludedIsbns", "blocked_isbns", "blockedIsbns"]))
        excluded_isbns.update(self._book_isbns(read_books))
        excluded_isbns.update(self._book_isbns(disliked_books))
        excluded_isbns.update(self._book_isbns(low_rated_books))

        demographic_profile = profile.get("demographicProfile") or profile.get("demographic_profile") or {}
        if not isinstance(demographic_profile, dict):
            demographic_profile = {}

        requested_audience_group = self._normalize_audience_group(
            purpose_profile.get("requested_audience_group") or purpose_profile.get("requestedAudienceGroup")
        )
        requested_education_stage = self._normalize_education_stage(
            purpose_profile.get("requested_education_stage") or purpose_profile.get("requestedEducationStage")
        )
        target_reader = self._normalize_target_reader(
            purpose_profile.get("target_reader") or purpose_profile.get("targetReader")
        )

        return {
            "reading_purpose": self._extract_reading_purpose(profile),
            "purpose_summary": str(purpose_profile.get("summary") or "").strip(),
            "purpose_positive_terms": purpose_positive_terms,
            "purpose_negative_terms": purpose_negative_terms,
            "preferred_genres": self._collect_values(profile, ["preferred_genres", "preferredGenres", "interestCategories", "genres", "categories"]),
            "preferred_books": self._dedupe_books(preferred_books),
            "disliked_books": self._dedupe_books(disliked_books),
            "reading_books": self._dedupe_books(reading_books),
            "read_books": self._dedupe_books(read_books),
            "high_rated_books": self._dedupe_books(high_rated_books),
            "low_rated_books": self._dedupe_books(low_rated_books),
            "review_positive_terms": self._deduplicate(review_positive_terms),
            "review_negative_terms": self._deduplicate(review_negative_terms),
            "excluded_isbns": excluded_isbns,
            "user_age_group": self._normalize_audience_group(
                demographic_profile.get("userAgeGroup")
                or demographic_profile.get("user_age_group")
                or demographic_profile.get("ageGroup")
                or demographic_profile.get("age_group")
                or profile.get("userAgeGroup")
                or profile.get("user_age_group")
                or profile.get("ageGroup")
                or profile.get("age_group")
            ),
            "age_group_source": (
                demographic_profile.get("ageGroupSource")
                or demographic_profile.get("age_group_source")
                or profile.get("ageGroupSource")
                or profile.get("age_group_source")
                or "UNKNOWN"
            ),
            "requested_audience_group": requested_audience_group,
            "requested_education_stage": requested_education_stage,
            "target_reader": target_reader,
            "vector_collection_name": preference_profile.get("vectorCollectionName") or preference_profile.get("vector_collection_name"),
            "vector_point_id": preference_profile.get("vectorPointId") or preference_profile.get("vector_point_id"),
        }

    def _has_profile_signal(self, normalized_profile: Dict[str, Any]) -> bool:
        return bool(
            normalized_profile["preferred_genres"]
            or normalized_profile.get("reading_purpose")
            or normalized_profile["purpose_positive_terms"]
            or normalized_profile["purpose_negative_terms"]
            or normalized_profile["preferred_books"]
            or normalized_profile["disliked_books"]
            or normalized_profile["reading_books"]
            or normalized_profile["read_books"]
            or normalized_profile["high_rated_books"]
            or normalized_profile["low_rated_books"]
            or normalized_profile["review_positive_terms"]
            or normalized_profile["review_negative_terms"]
            or normalized_profile.get("vector_point_id")
            or normalized_profile.get("user_age_group") not in (None, "", "UNKNOWN", "ANY")
            or normalized_profile.get("requested_audience_group") not in (None, "", "UNKNOWN", "ANY")
            or normalized_profile.get("requested_education_stage") not in (None, "", "UNKNOWN")
            or normalized_profile.get("target_reader") not in (None, "", "UNKNOWN")
        )

    def _normalize_mode(self, mode: str) -> str:
        normalized = str(mode or "PROFILE_FIRST").strip().upper()
        return normalized if normalized in self.weight_presets else "PROFILE_FIRST"

    def _resolve_weight_preset(self, mode: str) -> Dict[str, float]:
        return dict(self.weight_presets.get(mode, self.weight_presets["PROFILE_FIRST"]))

    def _user_profile_vector_score(self, candidate: Dict[str, Any], profile: Dict[str, Any]) -> float:
        collection_name = str(profile.get("vector_collection_name") or "").strip()
        point_id = str(profile.get("vector_point_id") or "").strip()
        isbn = self._normalize_isbn(candidate.get("isbn"))
        if not collection_name or not point_id or not isbn:
            return 0.0
        profile_vector = self._load_profile_vector(collection_name, point_id)
        book_vector = self._load_book_vector(isbn)
        if not profile_vector or not book_vector:
            return 0.0
        return max(0.0, min(1.0, (self._cosine(profile_vector, book_vector) + 1.0) / 2.0))

    def _qdrant(self) -> QdrantClient:
        if self._qdrant_client is not None:
            return self._qdrant_client
        api_key = getattr(settings, "QDRANT_API_KEY", "")
        if api_key:
            self._qdrant_client = QdrantClient(url=getattr(settings, "QDRANT_URL", "http://qdrant:6333"), api_key=api_key)
        else:
            self._qdrant_client = QdrantClient(url=getattr(settings, "QDRANT_URL", "http://qdrant:6333"))
        return self._qdrant_client

    def _load_profile_vector(self, collection_name: str, point_id: str) -> Optional[List[float]]:
        cache_key = f"{collection_name}:{point_id}"
        if cache_key in self._profile_vector_cache:
            return self._profile_vector_cache[cache_key]
        try:
            points = self._qdrant().retrieve(collection_name=collection_name, ids=[point_id], with_vectors=True)
            if not points:
                self._profile_vector_cache[cache_key] = None
                return None
            vector = self._vector_from_point(points[0])
            self._profile_vector_cache[cache_key] = vector
            return vector
        except Exception:
            self._profile_vector_cache[cache_key] = None
            return None

    def _load_book_vector(self, isbn: str) -> Optional[List[float]]:
        if isbn in self._book_vector_cache:
            return self._book_vector_cache[isbn]
        try:
            result, _ = self._qdrant().scroll(
                collection_name=getattr(settings, "QDRANT_KURE_COLLECTION", "books_kure"),
                scroll_filter=Filter(must=[FieldCondition(key="isbn", match=MatchValue(value=isbn))]),
                limit=1,
                with_vectors=True,
                with_payload=False,
            )
            if not result:
                self._book_vector_cache[isbn] = None
                return None
            vector = self._vector_from_point(result[0])
            self._book_vector_cache[isbn] = vector
            return vector
        except Exception:
            self._book_vector_cache[isbn] = None
            return None

    @staticmethod
    def _vector_from_point(point: Any) -> Optional[List[float]]:
        vector = getattr(point, "vector", None)
        if isinstance(vector, dict):
            vector = next(iter(vector.values()), None)
        if not isinstance(vector, list):
            return None
        try:
            return [float(v) for v in vector]
        except Exception:
            return None

    @staticmethod
    def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
        if len(left) != len(right) or not left:
            return 0.0
        dot = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(a * a for a in left))
        right_norm = math.sqrt(sum(b * b for b in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return dot / (left_norm * right_norm)

    def _category_match_score(self, candidate: Dict[str, Any], preferred_categories: List[str]) -> float:
        if not preferred_categories:
            return 0.0
        candidate_terms = self._candidate_terms(candidate, include_long_text=False)
        category_terms = [self._normalize_text(term) for term in preferred_categories]
        return self._overlap_score(candidate_terms, category_terms)

    def _term_match_score(self, candidate: Dict[str, Any], terms: List[str]) -> float:
        if not terms:
            return 0.0
        candidate_terms = self._candidate_terms(candidate, include_long_text=True)
        return self._overlap_score(candidate_terms, [self._normalize_text(term) for term in terms])

    def _book_similarity_score(self, candidate: Dict[str, Any], books: List[Dict[str, Any]]) -> float:
        if not books:
            return 0.0
        candidate_terms = self._candidate_terms(candidate, include_long_text=True)
        best = 0.0
        for book in books:
            book_terms = self._candidate_terms(book, include_long_text=True)
            best = max(best, self._overlap_score(candidate_terms, book_terms))
        return best

    def _candidate_terms(self, candidate: Dict[str, Any], include_long_text: bool) -> List[str]:
        values: List[str] = []
        for key in ["title", "author", "publisher", "categoryCode", "category_code"]:
            values.extend(self._normalize_any(candidate.get(key)))
        for key in ["categories", "cate_depth1", "kcid"]:
            values.extend(self._normalize_any(candidate.get(key)))
        if include_long_text:
            for key in ["description", "simple_intro", "book_intro", "book_index", "pub_review", "document"]:
                values.extend(self._normalize_any(candidate.get(key)))
        return [self._normalize_text(v) for v in values if v]

    def _overlap_score(self, left_terms: List[str], right_terms: List[str]) -> float:
        left_blob = " ".join(left_terms)
        right = [term for term in right_terms if term]
        if not left_blob or not right:
            return 0.0
        hit = 0
        partial = 0
        for term in right:
            if term in left_blob:
                hit += 1
            elif any(token and token in left_blob for token in term.split()):
                partial += 1
        return max(0.0, min(1.0, (hit + 0.4 * partial) / max(3, len(right))))

    def _build_personalization_evidence(
        self,
        candidate: Dict[str, Any],
        normalized_profile: Dict[str, Any],
        score_detail: Dict[str, Any],
    ) -> Dict[str, Any]:
        evidence: Dict[str, Any] = {}
        signal_labels: List[str] = []

        if score_detail.get("purpose_score", 0.0) > 0:
            purpose_summary = normalized_profile.get("purpose_summary") or normalized_profile.get("reading_purpose")
            if purpose_summary:
                evidence["reading_purpose_summary"] = purpose_summary
            purpose_terms = normalized_profile.get("purpose_positive_terms", [])[:5]
            if purpose_terms:
                evidence["matched_purpose_terms"] = purpose_terms
            signal_labels.append("PURPOSE_MATCH")

        if score_detail.get("review_rating_positive_score", 0.0) > 0:
            positive_terms = normalized_profile.get("review_positive_terms", [])[:5]
            if positive_terms:
                evidence["matched_review_positive_terms"] = positive_terms
            high_rated_books = normalized_profile.get("high_rated_books", [])[:5]
            if high_rated_books:
                evidence["matched_high_rated_books"] = high_rated_books
            signal_labels.append("REVIEW_RATING_MATCH")

        if score_detail.get("review_rating_negative_penalty", 0.0) > 0:
            negative_terms = normalized_profile.get("review_negative_terms", [])[:5]
            if negative_terms:
                evidence["review_negative_terms"] = negative_terms

        if score_detail.get("genre_score", 0.0) > 0:
            matched_genres = normalized_profile.get("preferred_genres", [])[:5]
            if matched_genres:
                evidence["matched_genres"] = matched_genres
            signal_labels.append("GENRE_MATCH")

        if score_detail.get("preferred_book_score", 0.0) > 0:
            preferred_books = normalized_profile.get("preferred_books", [])[:5]
            if preferred_books:
                evidence["matched_preferred_books"] = preferred_books
            signal_labels.append("PREFERRED_BOOK_MATCH")

        if score_detail.get("reading_book_score", 0.0) > 0:
            reading_books = normalized_profile.get("reading_books", [])[:5]
            if reading_books:
                evidence["matched_reading_books"] = reading_books
            signal_labels.append("READING_BOOK_MATCH")

        if score_detail.get("read_book_score", 0.0) > 0:
            read_books = normalized_profile.get("read_books", [])[:5]
            if read_books:
                evidence["matched_read_books"] = read_books
            signal_labels.append("READ_BOOK_WEAK_MATCH")

        if score_detail.get("user_profile_vector_score", 0.0) > 0:
            evidence["profile_vector"] = "PROFILE_VECTOR_MATCH"
            signal_labels.append("PROFILE_VECTOR_MATCH")

        if score_detail.get("audience_match_score", 0.0) > 0:
            evidence["audience"] = "AUDIENCE_MATCH"
            signal_labels.append("AUDIENCE_MATCH")
        if score_detail.get("off_audience_penalty", 0.0) > 0:
            evidence["audience_penalty"] = "AUDIENCE_MISMATCH"

        if signal_labels:
            evidence["signal_labels"] = self._deduplicate(signal_labels)
        return evidence

    @staticmethod
    def _make_reason(score_detail: Dict[str, Any]) -> str:
        reasons = []
        if score_detail.get("review_rating_positive_score", 0.0) > 0:
            reasons.append("REVIEW_POSITIVE")
        if score_detail.get("purpose_score", 0.0) > 0:
            reasons.append("PURPOSE_MATCH")
        if score_detail.get("audience_match_score", 0.0) > 0:
            reasons.append("AUDIENCE_MATCH")
        if score_detail.get("read_book_score", 0.0) > 0:
            reasons.append("READ_HISTORY_WEAK_MATCH")
        if score_detail.get("user_profile_vector_score", 0.0) > 0:
            reasons.append("PROFILE_VECTOR_MATCH")
        if score_detail.get("review_rating_negative_penalty", 0.0) > 0 or score_detail.get("disliked_book_penalty", 0.0) > 0:
            reasons.append("NEGATIVE_SIGNAL_PENALTY")
        if score_detail.get("off_audience_penalty", 0.0) > 0:
            reasons.append("AUDIENCE_MISMATCH_PENALTY")
        return ",".join(reasons) if reasons else "SEMANTIC_BASELINE"

    def _audience_alignment(self, candidate: Dict[str, Any], profile: Dict[str, Any], mode: str) -> Dict[str, Any]:
        audience_profile = candidate.get("audience_profile") or candidate.get("audienceProfile") or {}
        if not isinstance(audience_profile, dict):
            audience_profile = {}
        candidate_group = self._normalize_audience_group(
            audience_profile.get("target_age_group") or audience_profile.get("targetAgeGroup")
        )
        confidence = self._safe_float(audience_profile.get("confidence"))
        if candidate_group == "ANY":
            candidate_group = "GENERAL"

        requested_group = self._normalize_audience_group(profile.get("requested_audience_group"))
        user_group = self._normalize_audience_group(profile.get("user_age_group"))
        age_group_source = str(profile.get("age_group_source") or "UNKNOWN").strip().upper()
        target_reader = self._normalize_target_reader(profile.get("target_reader"))

        if requested_group not in {"UNKNOWN", "ANY"}:
            match = self._group_match(candidate_group, requested_group, allow_unknown=True)
            return {
                "match_score": match,
                "penalty": 0.0 if match > 0 else min(0.25, max(0.0, confidence)),
                "source": "REQUESTED_AUDIENCE",
                "user_age_group": user_group,
                "requested_audience_group": requested_group,
                "candidate_audience_group": candidate_group,
                "age_group_source": age_group_source,
            }

        if target_reader == "OTHER":
            return {
                "match_score": 0.0 if candidate_group == "UNKNOWN" else 0.35,
                "penalty": 0.0,
                "source": "OTHER_READER",
                "user_age_group": user_group,
                "requested_audience_group": requested_group,
                "candidate_audience_group": candidate_group,
                "age_group_source": age_group_source,
            }

        if user_group == "UNKNOWN" or candidate_group == "UNKNOWN":
            return {
                "match_score": 0.0,
                "penalty": 0.0,
                "source": "UNKNOWN",
                "user_age_group": user_group,
                "requested_audience_group": requested_group,
                "candidate_audience_group": candidate_group,
                "age_group_source": age_group_source,
            }

        if candidate_group == "GENERAL":
            return {
                "match_score": 0.75,
                "penalty": 0.0,
                "source": "GENERAL_AUDIENCE",
                "user_age_group": user_group,
                "requested_audience_group": requested_group,
                "candidate_audience_group": candidate_group,
                "age_group_source": age_group_source,
            }

        match = self._group_match(candidate_group, user_group, allow_unknown=False)
        if match > 0:
            return {
                "match_score": match,
                "penalty": 0.0,
                "source": "USER_AGE_GROUP",
                "user_age_group": user_group,
                "requested_audience_group": requested_group,
                "candidate_audience_group": candidate_group,
                "age_group_source": age_group_source,
            }

        mode_factor = 1.0 if mode == "PROFILE_FIRST" else 0.78 if mode == "HYBRID" else 0.6
        confidence_factor = max(0.35, min(1.0, confidence or 0.0))
        return {
            "match_score": 0.0,
            "penalty": min(1.0, mode_factor * confidence_factor),
            "source": "USER_AGE_GROUP",
            "user_age_group": user_group,
            "requested_audience_group": requested_group,
            "candidate_audience_group": candidate_group,
            "age_group_source": age_group_source,
        }

    def _drop_audience_mismatches_when_safe(self, candidates: List[Dict[str, Any]], mode: str) -> List[Dict[str, Any]]:
        # 수정 포인트: audience label은 hard exclude가 아니라 soft reranking 신호로만 사용합니다.
        # 후보 부족을 만들지 않도록 명백한 mismatch도 점수 감점에만 반영합니다.
        return candidates

    @staticmethod
    def _group_match(candidate_group: str, target_group: str, allow_unknown: bool) -> float:
        if candidate_group == target_group:
            return 1.0
        if candidate_group == "GENERAL":
            return 0.75
        if allow_unknown and candidate_group == "UNKNOWN":
            return 0.0
        adjacent = {
            "INFANT": {"CHILD"},
            "CHILD": {"INFANT", "ELEMENTARY"},
            "ELEMENTARY": {"CHILD", "MIDDLE_SCHOOL"},
            "MIDDLE_SCHOOL": {"ELEMENTARY", "HIGH_SCHOOL", "TEEN"},
            "HIGH_SCHOOL": {"MIDDLE_SCHOOL", "TEEN", "YOUNG_ADULT"},
            "TEEN": {"MIDDLE_SCHOOL", "HIGH_SCHOOL", "YOUNG_ADULT"},
            "YOUNG_ADULT": {"HIGH_SCHOOL", "ADULT", "TEEN"},
            "ADULT": {"YOUNG_ADULT", "SENIOR"},
            "SENIOR": {"ADULT"},
        }
        if candidate_group in adjacent.get(target_group, set()):
            return 0.55
        return 0.0

    @staticmethod
    def _normalize_audience_group(value: Any) -> str:
        group = str(value or "UNKNOWN").strip().upper()
        return group if group in {"INFANT", "CHILD", "ELEMENTARY", "MIDDLE_SCHOOL", "HIGH_SCHOOL", "TEEN", "YOUNG_ADULT", "ADULT", "SENIOR", "GENERAL", "ANY", "UNKNOWN"} else "UNKNOWN"

    @staticmethod
    def _normalize_education_stage(value: Any) -> str:
        stage = str(value or "UNKNOWN").strip().upper()
        return stage if stage in {"PRESCHOOL", "ELEMENTARY", "MIDDLE", "HIGH", "COLLEGE", "GENERAL", "UNKNOWN"} else "UNKNOWN"

    @staticmethod
    def _normalize_target_reader(value: Any) -> str:
        reader = str(value or "UNKNOWN").strip().upper()
        return reader if reader in {"SELF", "OTHER", "UNKNOWN"} else "UNKNOWN"

    def _preference_profile(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        value = profile.get("preferenceProfile") or profile.get("preference_profile")
        return value if isinstance(value, dict) else {}

    def _collect_review_signals(self, profile: Dict[str, Any]) -> List[Dict[str, Any]]:
        raw = profile.get("reviewPreferenceSignals") or profile.get("review_preference_signals") or []
        if not isinstance(raw, list):
            return []
        return [row for row in raw if isinstance(row, dict)]

    def _collect_book_objects(self, profile: Dict[str, Any], keys: List[str]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for key in keys:
            value = profile.get(key)
            if isinstance(value, list):
                rows.extend([row for row in value if isinstance(row, dict)])
        return rows

    def _collect_values(self, profile: Dict[str, Any], keys: List[str]) -> List[str]:
        values: List[str] = []
        for key in keys:
            raw = profile.get(key)
            if isinstance(raw, list):
                for item in raw:
                    if isinstance(item, dict):
                        values.extend(self._normalize_any(item.get("label") or item.get("categoryName") or item.get("categoryCode") or item.get("name")))
                    else:
                        values.extend(self._normalize_any(item))
            else:
                values.extend(self._normalize_any(raw))
        return self._deduplicate(values)

    def _collect_isbns(self, profile: Dict[str, Any], keys: List[str]) -> List[str]:
        values: List[str] = []
        for key in keys:
            values.extend(self._normalize_any(profile.get(key)))
        return [isbn for isbn in (self._normalize_isbn(v) for v in values) if isbn]

    def _book_isbns(self, books: List[Dict[str, Any]]) -> set[str]:
        return {isbn for isbn in (self._normalize_isbn(book.get("isbn13") or book.get("isbn")) for book in books) if isbn}

    def _dedupe_books(self, books: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        result: List[Dict[str, Any]] = []
        for book in books:
            isbn = self._normalize_isbn(book.get("isbn13") or book.get("isbn"))
            title = self._normalize_text(book.get("title"))
            key = f"isbn:{isbn}" if isbn else f"title:{title}"
            if not key or key in seen:
                continue
            seen.add(key)
            result.append(book)
        return result

    def _normalize_any(self, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            if text.startswith("["):
                return to_string_list(text, 50)
            return [text]
        if isinstance(value, dict):
            return [str(v).strip() for v in value.values() if isinstance(v, (str, int, float)) and str(v).strip()]
        if isinstance(value, list):
            result: List[str] = []
            for item in value:
                result.extend(self._normalize_any(item))
            return result
        return [str(value).strip()] if str(value).strip() else []

    @staticmethod
    def _deduplicate(values: List[str]) -> List[str]:
        seen = set()
        result: List[str] = []
        for value in values:
            text = str(value or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            result.append(text)
        return result

    @staticmethod
    def _normalize_text(value: Any) -> str:
        text = str(value or "").strip().lower()
        text = re.sub(r"[^0-9a-z가-힣\s]", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _normalize_token(value: Any) -> str:
        return re.sub(r"[^0-9a-z가-힣]", "", str(value or "").strip().lower())

    @staticmethod
    def _normalize_isbn(value: Any) -> Optional[str]:
        if value is None:
            return None
        digits = re.sub(r"\D", "", str(value))
        return digits or None

    def _extract_reading_purpose(self, profile: Dict[str, Any]) -> str:
        onboarding = profile.get("onboarding") if isinstance(profile.get("onboarding"), dict) else {}
        value = profile.get("readingPurpose") or profile.get("reading_purpose") or onboarding.get("readingPurpose") or onboarding.get("reading_purpose")
        return str(value or "").strip()

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            number = float(value)
        except Exception:
            return 0.0
        if math.isnan(number) or math.isinf(number):
            return 0.0
        return number

    def _normalize_semantic_score(self, value: Any) -> float:
        score = self._safe_float(value)
        if score < 0:
            return 0.0
        if score > 1:
            return min(1.0, score / 100.0 if score > 10 else score)
        return score