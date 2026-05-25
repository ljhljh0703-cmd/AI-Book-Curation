from __future__ import annotations

import re
from typing import Any, Dict, List

from app.services.intent.query_intent_parser import QueryIntent, QueryIntentParser
from app.services.recommendation.recommendation_policy import RecommendationPolicy
from app.services.common.text_utils import normalize_text, safe_join


class CandidateFilter:
    """Qdrant 후보 필터링, 장르 필터링, 중복 제거를 담당합니다."""

    def __init__(self, policy: RecommendationPolicy | None = None) -> None:
        self.policy = policy or RecommendationPolicy()
        self.query_parser = QueryIntentParser()

    def dedupe_candidates(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        deduped: List[Dict[str, Any]] = []
        seen_isbns = set()
        seen_book_ids = set()
        seen_title_author = set()
        seen_title_publisher = set()
        for candidate in candidates:
            isbn_key = self._normalize_isbn(candidate.get("isbn") or candidate.get("isbn13") or candidate.get("isbn10"))
            book_id_key = normalize_text(candidate.get("book_id") or candidate.get("bookId") or candidate.get("id"))
            title_key = self._normalize_title(candidate.get("title"))
            title_core_key = self._canonical_title_key(candidate.get("title"))
            author_key = self._canonical_contributor_key(candidate.get("author"))
            publisher_key = normalize_text(candidate.get("publisher"))
            # 수정 포인트: 운영 안정성을 위해 중복 제거는 신뢰도 높은 키(ISBN/bookId/제목+저자/제목+출판사)에 한정합니다.
            # title-only 또는 cover-only dedupe는 후보를 과하게 줄여 첫 추천이 1권으로 축소될 수 있어 사용하지 않습니다.
            if isbn_key and isbn_key in seen_isbns:
                continue
            if book_id_key and book_id_key in seen_book_ids:
                continue
            if title_key and author_key and f"{title_key}|{author_key}" in seen_title_author:
                continue
            if title_key and publisher_key and f"{title_key}|{publisher_key}" in seen_title_publisher:
                continue
            if isbn_key:
                seen_isbns.add(isbn_key)
            if book_id_key:
                seen_book_ids.add(book_id_key)
            if title_key and author_key:
                seen_title_author.add(f"{title_key}|{author_key}")
            if title_key and publisher_key:
                seen_title_publisher.add(f"{title_key}|{publisher_key}")
            deduped.append(self.clean_display_candidate(candidate))
        return deduped

    def clean_display_candidate(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        cleaned = dict(candidate)
        cleaned_title = self._clean_numbered_title(cleaned.get("title"))
        if cleaned_title:
            cleaned["title"] = cleaned_title
        return cleaned

    @staticmethod
    def _normalize_isbn(value: Any) -> str:
        digits = re.sub(r"\D", "", str(value or ""))
        return digits if len(digits) >= 10 else ""

    @classmethod
    def _normalize_title(cls, value: Any) -> str:
        return normalize_text(cls._clean_numbered_title(value))

    @classmethod
    def _canonical_title_key(cls, value: Any) -> str:
        return normalize_text(cls._clean_numbered_title(value))

    @staticmethod
    def _canonical_contributor_key(value: Any) -> str:
        return normalize_text(value)

    @staticmethod
    def _clean_numbered_title(value: Any) -> str:
        title = str(value or "").strip()
        return re.sub(r"^\s*\d+[.)]\s+", "", title).strip()

    def filter_candidates_by_intent(self, query_intent: QueryIntent, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not candidates or not query_intent.has_required_filters:
            return candidates
        filtered = candidates
        if query_intent.isbn:
            isbn = self._normalize_isbn(query_intent.isbn)
            filtered = [book for book in filtered if isbn and isbn in self._normalize_isbn(book.get("isbn"))]
        if query_intent.title:
            title = normalize_text(query_intent.title)
            filtered = [book for book in filtered if title and title in normalize_text(book.get("title"))]
        if query_intent.author:
            filtered = [book for book in filtered if self._matches_primary_author(book, query_intent.author)]
        if query_intent.genres:
            filtered = [book for book in filtered if self._matches_any_genre(book, query_intent.genres)]
        # 수정 포인트: hard filter 후에도 같은 책의 다른 판형/중복 payload가 남을 수 있어 한 번 더 정리합니다.
        return self.dedupe_candidates(filtered)

    def filter_candidates_by_query(self, query: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        query_intent = self.query_parser.parse(query)
        if query_intent.has_required_filters:
            return self.filter_candidates_by_intent(query_intent=query_intent, candidates=candidates)
        return candidates

    def filter_candidates_by_recommendation_genre(self, query: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        query_intent = self.query_parser.parse(query)
        if not query_intent.genres:
            return candidates
        return [book for book in candidates if self._matches_any_genre(book, query_intent.genres)]

    def _matches_primary_author(self, candidate: Dict[str, Any], author: str) -> bool:
        expected = normalize_text(author)
        if not expected:
            return True
        for value in [candidate.get("primary_author"), candidate.get("main_author"), candidate.get("author_name"), candidate.get("author")]:
            if expected in normalize_text(value):
                return True
        return False

    def _matches_any_genre(self, candidate: Dict[str, Any], genres: List[str]) -> bool:
        if not genres:
            return True
        return any(self._matches_genre(candidate, genre) for genre in genres)

    def _matches_genre(self, candidate: Dict[str, Any], genre: str) -> bool:
        normalized_genre = normalize_text(genre)
        if not normalized_genre:
            return True

        normalized_category_text = normalize_text(self._candidate_category_text(candidate))

        # 수정 포인트: DB 카테고리 매칭은 intent parser가 내려준 구조화 값만 사용합니다.
        # LLM intent parser가 explicit_filters.genres/genre_terms에 DB 카테고리와 맞출 후보 용어를 내려주고,
        # hard filter는 후보의 실제 카테고리 payload와 그 용어의 직접 일치만 확인합니다.
        if normalized_category_text:
            return normalized_genre in normalized_category_text

        # 카테고리 payload가 없는 오래된 후보만 제목/소개 fallback을 허용합니다.
        intro_text = " ".join([
            str(candidate.get("title") or ""),
            str(candidate.get("description") or ""),
            str(candidate.get("simple_intro") or ""),
            str(candidate.get("book_intro") or ""),
            str(candidate.get("book_index") or ""),
            str(candidate.get("pub_review") or ""),
        ])
        return normalized_genre in normalize_text(intro_text)

    def _candidate_category_text(self, candidate: Dict[str, Any]) -> str:
        category_fields = [
            "categories",
            "cate_depth1",
            "cate_depth2",
            "cate_depth3",
            "kcid",
            "genre",
            "genres",
            "genre_normalized",
            "category",
            "categoryName",
            "category_name",
            "category_full_name",
            "category_path",
            "category_normalized",
            "aladin_category",
            "aladin_category_name",
            "className",
            "class_name",
        ]
        return " ".join(safe_join(candidate.get(field)) for field in category_fields if candidate.get(field))

    def exclude_previous_recommendations(self, candidates: List[Dict[str, Any]], previous_books: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        if not candidates or not previous_books:
            return candidates
        previous_isbns = {normalize_text(book.get("isbn")) for book in previous_books if normalize_text(book.get("isbn"))}
        previous_titles = {normalize_text(book.get("title")) for book in previous_books if normalize_text(book.get("title"))}
        filtered: List[Dict[str, Any]] = []
        for candidate in candidates:
            candidate_isbn = normalize_text(candidate.get("isbn"))
            candidate_title = normalize_text(candidate.get("title"))
            if candidate_isbn and candidate_isbn in previous_isbns:
                continue
            if candidate_title and candidate_title in previous_titles:
                continue
            filtered.append(candidate)
        return filtered


    def apply_previous_recommendation_penalty(self, candidates: List[Dict[str, Any]], previous_books: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not candidates or not previous_books:
            return candidates
        previous_by_isbn = {normalize_text(book.get("isbn")): book for book in previous_books if normalize_text(book.get("isbn"))}
        previous_by_title = {normalize_text(book.get("title")): book for book in previous_books if normalize_text(book.get("title"))}
        result: List[Dict[str, Any]] = []
        for candidate in candidates:
            candidate_isbn = normalize_text(candidate.get("isbn"))
            candidate_title = normalize_text(candidate.get("title"))
            previous = previous_by_isbn.get(candidate_isbn) if candidate_isbn else None
            previous = previous or (previous_by_title.get(candidate_title) if candidate_title else None)
            if not previous:
                result.append(candidate)
                continue
            decay_weight = self._safe_float(previous.get("decay_weight"))
            penalty = max(0.03, min(0.18, 0.18 * decay_weight))
            item = dict(candidate)
            item["policyPenalty"] = round(self._safe_float(item.get("policyPenalty")) + penalty, 6)
            score_detail = dict(item.get("score_detail") or {})
            penalties = list(score_detail.get("policy_penalties") or [])
            penalties.append({
                "type": "recent_multiturn_recommendation_decay",
                "penalty": round(penalty, 6),
                "age_minutes": previous.get("age_minutes"),
            })
            score_detail["policy_penalties"] = penalties
            item["score_detail"] = score_detail
            result.append(item)
        return result

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def filter_disliked_candidates_by_profile(self, candidates: List[Dict[str, Any]], negative_terms: List[str]) -> List[Dict[str, Any]]:
        if not candidates or not negative_terms:
            return candidates
        filtered = [candidate for candidate in candidates if not self._is_negative_candidate(candidate, negative_terms)]
        # 수정 포인트: 동일 ISBN/동일 제목 hard exclusion에 걸린 후보는
        # 최종 5권을 채우기 위해 되살리지 않습니다.
        return filtered

    def _is_negative_candidate(self, candidate: Dict[str, Any], negative_terms: List[str]) -> bool:
        normalized_terms = [normalize_text(term) for term in negative_terms if normalize_text(term)]
        if not normalized_terms:
            return False

        # 수정 포인트: 비선호 도서 20권의 저자/출판사/카테고리가 hard filter로 작동하면
        # 정상 후보까지 대량 제거될 수 있습니다. hard exclusion은 동일 ISBN 또는 동일/유사 제목만 적용하고,
        # 장르·저자·카테고리 유사도는 ProfileReranker의 soft penalty로만 반영합니다.
        candidate_isbn = self._normalize_isbn(candidate.get("isbn") or candidate.get("isbn13") or candidate.get("isbn10"))
        candidate_title = self._canonical_title_key(candidate.get("title"))

        for term in normalized_terms:
            term_isbn = self._normalize_isbn(term)
            if term_isbn and candidate_isbn and term_isbn == candidate_isbn:
                return True

            # 1~2글자 장르/분위기 단어가 제목에 우연히 포함되어 hard exclusion 되는 것을 방지합니다.
            if len(term) < 3 or not candidate_title:
                continue
            if term == candidate_title or term in candidate_title or candidate_title in term:
                return True

        return False
