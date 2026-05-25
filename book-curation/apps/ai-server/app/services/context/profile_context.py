from __future__ import annotations

from typing import Any, Dict, List

from app.services.common.text_utils import coerce_profile_values, dedupe_texts, normalize_text


class ProfileContextBuilder:
    """로그인 사용자 프로필을 검색어/프롬프트/필터링에 사용할 형태로 변환합니다."""

    POSITIVE_SHELF_TYPES = ["INTERESTED", "READING", "FAVORITE", "WANT_TO_READ"]
    WEAK_POSITIVE_SHELF_TYPES = ["READ"]
    NEGATIVE_SHELF_TYPES = ["NOT_INTERESTED"]

    def extract_shelf_books_by_type(self, value: Any, shelf_types: List[str], identity_only: bool = False) -> List[str]:
        if not value:
            return []

        normalized_target_types = {normalize_text(shelf_type) for shelf_type in shelf_types if normalize_text(shelf_type)}
        if not normalized_target_types:
            return []

        if isinstance(value, list):
            result: List[str] = []
            for item in value:
                result.extend(self.extract_shelf_books_by_type(item, shelf_types, identity_only=identity_only))
            return result

        if not isinstance(value, dict):
            return []

        current_shelf_type = normalize_text(value.get("shelfType"))
        if current_shelf_type not in normalized_target_types:
            return []

        keys = [
            "title",
            "bookTitle",
            "name",
            "bookName",
        ]
        if identity_only:
            keys.extend(["isbn", "isbn13"])
        if not identity_only:
            keys.extend([
                "author",
                "publisher",
                "category",
                "categoryCode",
                "genre",
                "keyword",
            ])
        return coerce_profile_values(
            value,
            preferred_keys=keys,
            include_identifier_values=identity_only,
        )

    def extract_positive_profile_terms(self, profile: Dict[str, Any] | None = None, guest: bool = False) -> List[str]:
        if not profile or guest:
            return []

        review_profile = self._review_rating_profile(profile)
        candidate_values = [
            self.extract_reading_purpose(profile),
            profile.get("interestCategories"),
            profile.get("interestKeywords"),
            profile.get("preferred_genres"),
            profile.get("preferredGenres"),
            profile.get("preferredMoods"),
            profile.get("readingLevel"),
            profile.get("preferred_books"),
            profile.get("preferredBooks"),
            profile.get("reading_books"),
            profile.get("readingBooks"),
            profile.get("high_rated_books"),
            profile.get("highRatedBooks"),
            review_profile.get("high_rating_positive_terms"),
            review_profile.get("liked_aspects"),
            review_profile.get("preferred_mood"),
        ]

        terms: List[str] = []
        for value in candidate_values:
            terms.extend(coerce_profile_values(value))

        terms.extend(
            self.extract_shelf_books_by_type(
                profile.get("shelfBooks"),
                self.POSITIVE_SHELF_TYPES,
            )
        )

        return dedupe_texts(terms, limit=14)


    def extract_weak_positive_profile_terms(self, profile: Dict[str, Any] | None = None, guest: bool = False) -> List[str]:
        if not profile or guest:
            return []

        preferred_keys = [
            "title",
            "bookTitle",
            "name",
            "bookName",
            "author",
            "publisher",
            "category",
            "categoryName",
            "categoryCode",
            "genre",
            "keyword",
        ]
        terms: List[str] = []
        for value in [profile.get("read_books"), profile.get("readBooks")]:
            terms.extend(
                coerce_profile_values(
                    value,
                    preferred_keys=preferred_keys,
                    include_identifier_values=False,
                )
            )

        terms.extend(
            self.extract_shelf_books_by_type(
                profile.get("shelfBooks"),
                self.WEAK_POSITIVE_SHELF_TYPES,
            )
        )
        return dedupe_texts(terms, limit=8)

    def has_positive_search_signal(self, profile: Dict[str, Any] | None = None, guest: bool = False) -> bool:
        if not profile or guest:
            return False
        explicit_flag = profile.get("positiveProfileSignalAvailable")
        if isinstance(explicit_flag, bool):
            return explicit_flag
        return bool(
            self.extract_positive_profile_terms(profile=profile, guest=guest)
            or self.extract_weak_positive_profile_terms(profile=profile, guest=guest)
        )

    def extract_negative_profile_terms(self, profile: Dict[str, Any] | None = None, guest: bool = False) -> List[str]:
        if not profile or guest:
            return []

        negative_values = [
            profile.get("disliked_genres"),
            profile.get("dislikedGenres"),
            profile.get("dislikedMoods"),
            profile.get("disliked_books"),
            profile.get("dislikedBooks"),
            profile.get("low_rated_books"),
            profile.get("lowRatedBooks"),
            profile.get("dislikeBooks"),
            profile.get("negativeBooks"),
            profile.get("hateBooks"),
            profile.get("blockedBooks"),
            profile.get("avoidBooks"),
        ]

        terms: List[str] = []
        for value in negative_values:
            terms.extend(
                coerce_profile_values(
                    value,
                    preferred_keys=["isbn", "isbn13", "title", "bookTitle", "name", "bookName"],
                    include_identifier_values=True,
                )
            )

        terms.extend(
            self.extract_shelf_books_by_type(
                profile.get("shelfBooks"),
                self.NEGATIVE_SHELF_TYPES,
                identity_only=True,
            )
        )
        return dedupe_texts(terms, limit=50)

    def extract_negative_review_terms(self, value: Any) -> List[str]:
        if not value:
            return []

        if isinstance(value, list):
            result: List[str] = []
            for item in value:
                result.extend(self.extract_negative_review_terms(item))
            return result

        if not isinstance(value, dict):
            return []

        negative = False

        for key in ["liked", "isLiked", "like", "favorite"]:
            if key in value and value.get(key) is False:
                negative = True

        for key in ["negative", "isNegative"]:
            if key in value and value.get(key) is True:
                negative = True

        for key in ["rating", "score", "star", "stars", "reviewRating"]:
            if key not in value:
                continue
            try:
                score = float(value.get(key))
                if score <= 2:
                    negative = True
            except (TypeError, ValueError):
                pass

        if not negative:
            return []

        return coerce_profile_values(
            value,
            preferred_keys=[
                "title",
                "bookTitle",
                "name",
                "bookName",
                "isbn",
                "isbn13",
                "author",
                "category",
                "categoryName",
                "genre",
                "keyword",
            ],
            include_identifier_values=True,
        )

    def build_profile_search_query(self, query: str, profile: Dict[str, Any] | None = None, guest: bool = False) -> str:
        strong_positive_terms = self.extract_positive_profile_terms(profile=profile, guest=guest)
        positive_terms = strong_positive_terms or self.extract_weak_positive_profile_terms(profile=profile, guest=guest)
        negative_terms = self.extract_negative_profile_terms(profile=profile, guest=guest)

        if not positive_terms:
            return query

        normalized_negative_terms = {normalize_text(term) for term in negative_terms if normalize_text(term)}
        filtered_positive_terms: List[str] = []

        for term in positive_terms:
            normalized_term = normalize_text(term)
            if not normalized_term:
                continue
            if normalized_term in normalized_negative_terms:
                continue
            if any(normalized_term in negative_term or negative_term in normalized_term for negative_term in normalized_negative_terms):
                continue
            filtered_positive_terms.append(term)

        if not filtered_positive_terms:
            return query

        profile_hint = " ".join(filtered_positive_terms[:8])
        return f"{query} {profile_hint}".strip()

    def build_profile_focused_search_query(self, query: str, profile: Dict[str, Any] | None = None, guest: bool = False) -> str:
        if not profile or guest:
            return query

        strong_positive_terms = self.extract_positive_profile_terms(profile=profile, guest=guest)
        positive_terms = strong_positive_terms or self.extract_weak_positive_profile_terms(profile=profile, guest=guest)
        negative_terms = self.extract_negative_profile_terms(profile=profile, guest=guest)

        if not positive_terms:
            return query

        normalized_negative_terms = {normalize_text(term) for term in negative_terms if normalize_text(term)}
        filtered_terms: List[str] = []

        for term in positive_terms:
            normalized_term = normalize_text(term)
            if not normalized_term:
                continue
            if normalized_term in normalized_negative_terms:
                continue
            if any(normalized_term in negative_term or negative_term in normalized_term for negative_term in normalized_negative_terms):
                continue
            filtered_terms.append(term)

        if not filtered_terms:
            return query

        profile_hint = " ".join(filtered_terms[:8])
        return f"{profile_hint} {query}".strip()

    def extract_reading_purpose(self, profile: Dict[str, Any] | None = None) -> str:
        """backend user_profile에서 독서 목적 자유 텍스트를 안전하게 추출합니다."""
        if not profile:
            return ""

        direct_keys = ["readingPurpose", "reading_purpose", "purpose", "readingGoal", "readingGoals"]
        for key in direct_keys:
            value = profile.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        onboarding = profile.get("onboarding")
        if isinstance(onboarding, dict):
            for key in direct_keys:
                value = onboarding.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

        return ""

    def make_intent_profile_text(self, profile: Dict[str, Any] | None = None, guest: bool = False) -> str:
        """intent classifier LLM에 넘길 압축 프로필입니다."""
        if not profile or guest:
            return ""

        lines: List[str] = []
        reading_purpose = self.extract_reading_purpose(profile)
        if reading_purpose:
            lines.append(f"- 독서 목적: {reading_purpose}")

        summary = str(profile.get("summary") or "").strip()
        if summary:
            lines.append(f"- 프로필 요약: {summary[:450]}")

        compact_keys = [
            ("선호 장르", profile.get("preferred_genres") or profile.get("preferredGenres") or profile.get("interestCategories")),
            ("관심 키워드", profile.get("interestKeywords")),
            ("관심 도서", profile.get("preferred_books") or profile.get("preferredBooks")),
            ("읽는 중", profile.get("reading_books") or profile.get("readingBooks")),
            ("읽은 책", profile.get("read_books") or profile.get("readBooks")),
            ("비선호 도서", profile.get("disliked_books") or profile.get("dislikedBooks")),
        ]
        for label, value in compact_keys:
            values = dedupe_texts(coerce_profile_values(value), limit=6)
            if values:
                lines.append(f"- {label}: {', '.join(values)}")

        review_lines = self._make_review_rating_lines(profile, limit=6)
        if review_lines:
            lines.append("- 리뷰/평점 대표 신호:")
            lines.extend(review_lines)

        if not lines:
            return ""
        return "\n".join(lines)[:2400]

    def build_diverse_profile_search_queries(
        self,
        query: str,
        profile: Dict[str, Any] | None = None,
        guest: bool = False,
        max_queries: int = 6,
    ) -> List[str]:
        """프로필 검색어를 하나의 긴 문장으로 합치지 않고 여러 검색어로 분리합니다."""
        if not profile or guest:
            return []

        queries: List[str] = []
        base_query = str(query or "").strip()

        purpose_profile = profile.get("readingPurposeProfile") if isinstance(profile.get("readingPurposeProfile"), dict) else {}
        purpose_terms = coerce_profile_values(purpose_profile.get("positive_terms"))
        if purpose_terms:
            queries.append(f"{base_query} {' '.join(dedupe_texts(purpose_terms, limit=5))}".strip())

        review_profile = self._review_rating_profile(profile)
        review_terms = []
        review_terms.extend(coerce_profile_values(review_profile.get("high_rating_positive_terms")))
        review_terms.extend(coerce_profile_values(review_profile.get("liked_aspects")))
        review_terms.extend(coerce_profile_values(review_profile.get("preferred_mood")))
        if review_terms:
            queries.append(f"{base_query} {' '.join(dedupe_texts(review_terms, limit=5))}".strip())

        grouped_values = [
            profile.get("interestCategories"),
            profile.get("interestKeywords"),
            profile.get("preferred_books") or profile.get("preferredBooks"),
            profile.get("reading_books") or profile.get("readingBooks"),
            profile.get("high_rated_books") or profile.get("highRatedBooks"),
        ]
        for value in grouped_values:
            terms = dedupe_texts(coerce_profile_values(value), limit=5)
            if not terms:
                continue
            queries.append(f"{base_query} {' '.join(terms)}".strip())

        if not queries:
            weak_terms = self.extract_weak_positive_profile_terms(profile=profile, guest=guest)
            if weak_terms:
                queries.append(f"{base_query} {' '.join(dedupe_texts(weak_terms, limit=5))}".strip())

        deduped = dedupe_texts([item for item in queries if item and item != base_query], limit=max_queries)
        return deduped

    def make_profile_text(self, profile: Dict[str, Any] | None = None, guest: bool = False) -> str:
        if not profile:
            return ""

        lines: List[str] = []
        summary = profile.get("summary")
        if summary:
            lines.append(f"- 요약: {summary}")

        reading_purpose = self.extract_reading_purpose(profile)
        if reading_purpose:
            lines.append(f"- 독서 목적: {reading_purpose}")

        profile_keys = [
            "preferred_genres",
            "preferredGenres",
            "disliked_genres",
            "dislikedGenres",
            "preferredMoods",
            "dislikedMoods",
            "readingLevel",
            "interestCategories",
            "interestKeywords",
            "preferred_books",
            "preferredBooks",
            "reading_books",
            "readingBooks",
            "read_books",
            "readBooks",
            "high_rated_books",
            "highRatedBooks",
            "low_rated_books",
            "lowRatedBooks",
        ]

        for key in profile_keys:
            value = profile.get(key)
            values = dedupe_texts(coerce_profile_values(value), limit=8)
            if values:
                lines.append(f"- {key}: {', '.join(values)}")

        review_profile = self._review_rating_profile(profile)
        review_terms = dedupe_texts(
            [
                *coerce_profile_values(review_profile.get("liked_aspects")),
                *coerce_profile_values(review_profile.get("disliked_aspects")),
                *coerce_profile_values(review_profile.get("preferred_mood")),
                *coerce_profile_values(review_profile.get("avoid_mood")),
            ],
            limit=12,
        )
        if review_terms:
            lines.append(f"- reviewRatingPreferenceProfile: {', '.join(review_terms)}")

        if not lines:
            values = dedupe_texts(coerce_profile_values(profile), limit=10)
            if values:
                lines.append(f"- 프로필 값: {', '.join(values)}")

        if not lines:
            return ""

        if guest:
            lines.append("- 참고: 이 프로필은 비로그인 사용자의 현재 브라우저 채팅방에서 임시로 파악한 정보입니다.")
        else:
            lines.append("- 참고: 이 프로필은 로그인 사용자의 온보딩, 서재, 리뷰, 평점 데이터를 기반으로 구성된 정보입니다.")

        return "\n".join(lines)

    @staticmethod
    def _review_rating_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
        value = profile.get("reviewRatingPreferenceProfile") or profile.get("review_rating_preference_profile")
        return value if isinstance(value, dict) else {}

    def _make_review_rating_lines(self, profile: Dict[str, Any], limit: int) -> List[str]:
        books = profile.get("review_rating_books") or profile.get("reviewRatingBooks") or profile.get("reviewedBooks") or []
        if not isinstance(books, list):
            return []

        result: List[str] = []
        for book in books:
            if not isinstance(book, dict):
                continue
            rating = str(book.get("reviewRating") or book.get("rating") or "").strip()
            review = str(book.get("reviewContent") or "").strip().replace("\n", " ")
            title = str(book.get("title") or book.get("bookTitle") or "").strip()
            author = str(book.get("author") or "").strip()
            category = str(book.get("categoryCode") or book.get("category") or "").strip()
            band = str(book.get("ratingBand") or "").strip()
            if not rating or not review:
                continue
            label_parts = [part for part in [title, author] if part]
            label = " / ".join(label_parts) if label_parts else "제목 정보 없음"
            pieces = [f"{label}", f"평점 {rating}"]
            if band:
                pieces.append(f"구간 {band}")
            if category:
                pieces.append(f"분류 {category}")
            pieces.append(f"리뷰 '{review[:220]}'")
            result.append("  - " + " / ".join(pieces))
            if len(result) >= limit:
                break
        return result
