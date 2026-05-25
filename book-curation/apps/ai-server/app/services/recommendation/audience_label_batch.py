from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List

from app.schemas.audience_label import (
    AudienceLabelBatchRequest,
    AudienceLabelBatchResponse,
    AudienceLabelBook,
    AudienceLabelResult,
)
from app.services.clients.clova_client import ClovaClient
from app.services.common.config_loader import load_text_resource


class AudienceLabelBatchClassifier:
    VALID_AUDIENCE_GROUPS = {
        "INFANT",
        "CHILD",
        "ELEMENTARY",
        "MIDDLE_SCHOOL",
        "HIGH_SCHOOL",
        "YOUNG_ADULT",
        "ADULT",
        "GENERAL",
        "UNKNOWN",
    }
    VALID_DIFFICULTY_LEVELS = {"EASY", "NORMAL", "HARD", "UNKNOWN"}
    MAX_BATCH_SIZE = 500
    # 수정 포인트: 50권을 한 번의 LLM 요청에 모두 넣으면 prompt가 과도하게 커져 CLOVA 응답이 비거나
    # JSON 파싱이 실패할 수 있습니다. 내부적으로 작은 chunk로 나누어 안정적으로 처리합니다.
    LLM_CHUNK_SIZE = 5

    def __init__(self, llm_client: ClovaClient | None = None) -> None:
        self.llm_client = llm_client or ClovaClient()

    def classify(self, request: AudienceLabelBatchRequest) -> AudienceLabelBatchResponse:
        books = [book for book in (request.books or []) if str(book.isbn or "").strip()]
        if not books:
            return AudienceLabelBatchResponse(items=[])

        books = books[: self.MAX_BATCH_SIZE]
        results: List[AudienceLabelResult] = []
        for chunk in self._chunks(books, self.LLM_CHUNK_SIZE):
            results.extend(self._classify_chunk(chunk))
        return AudienceLabelBatchResponse(items=results)

    def _classify_chunk(self, books: List[AudienceLabelBook]) -> List[AudienceLabelResult]:
        payload = {"books": [self._stable_payload(book) for book in books]}

        try:
            raw = self.llm_client.chat_completion(
                system_prompt=load_text_resource("prompts/book_audience_label_system.md"),
                user_prompt=load_text_resource("prompts/book_audience_label_user.md").replace(
                    "{{payload_json}}",
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
            parsed = self._parse_json(raw)
        except Exception as exc:
            return [
                AudienceLabelResult(
                    isbn=book.isbn,
                    status="FAILED",
                    audience_group="UNKNOWN",
                    difficulty_level="UNKNOWN",
                    confidence=0.0,
                    error_message=f"LLM audience label call failed: {exc}",
                )
                for book in books
            ]

        raw_items = self._extract_items(parsed)
        result_by_isbn: Dict[str, AudienceLabelResult] = {}
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            isbn = str(item.get("isbn") or "").strip()
            if not isbn:
                continue
            result_by_isbn[isbn] = self._normalize_result(isbn, item)

        results: List[AudienceLabelResult] = []
        for book in books:
            results.append(
                result_by_isbn.get(
                    book.isbn,
                    AudienceLabelResult(
                        isbn=book.isbn,
                        status="FAILED",
                        audience_group="UNKNOWN",
                        difficulty_level="UNKNOWN",
                        confidence=0.0,
                        error_message="LLM response did not include this ISBN.",
                    ),
                )
            )
        return results

    def _normalize_result(self, isbn: str, item: Dict[str, Any]) -> AudienceLabelResult:
        status = self._normalize_status(item.get("status"))
        audience_group = self._normalize_enum(item.get("audience_group"), self.VALID_AUDIENCE_GROUPS)
        difficulty_level = self._normalize_enum(item.get("difficulty_level"), self.VALID_DIFFICULTY_LEVELS)
        confidence = self._normalize_confidence(item.get("confidence"))
        error_message = self._trim(item.get("error_message"), 600)

        if status == "FAILED":
            return AudienceLabelResult(
                isbn=isbn,
                status="FAILED",
                audience_group="UNKNOWN",
                difficulty_level="UNKNOWN",
                confidence=0.0,
                reason=self._trim(item.get("reason"), 600),
                error_message=error_message or "LLM returned FAILED status.",
            )

        # 수정 포인트: UNKNOWN/UNKNOWN/confidence=0도 유효한 구조화 결과입니다.
        # 이전 로직은 이 값을 FAILED로 바꿔 label 배치가 전부 실패할 수 있었습니다.
        # 추천 리랭킹에서는 UNKNOWN/label 없음이 중립 처리되므로 READY로 저장해도 안전합니다.
        audience_min_age = self._normalize_age(item.get("audience_min_age"))
        audience_max_age = self._normalize_age(item.get("audience_max_age"))
        audience_group, audience_min_age, audience_max_age = self._normalize_group_age_policy(
            audience_group, audience_min_age, audience_max_age
        )

        return AudienceLabelResult(
            isbn=isbn,
            status="READY",
            audience_group=audience_group,
            audience_min_age=audience_min_age,
            audience_max_age=audience_max_age,
            difficulty_level=difficulty_level,
            confidence=confidence,
            reason=self._trim(item.get("reason"), 600),
        )

    def _stable_payload(self, book: AudienceLabelBook) -> Dict[str, Any]:
        return {
            "isbn": book.isbn,
            "title": self._trim(book.title, 160),
            "author": self._trim(book.author, 120),
            "publisher": self._trim(book.publisher, 120),
            "publish_date": self._trim(book.publish_date, 40),
            "page": book.page,
            "description": self._trim(book.description, 500),
            "simple_intro": self._trim(book.simple_intro, 500),
            "book_intro": self._trim(book.book_intro, 700),
            "categories": self._list(book.categories, 12),
            "cate_depth1": self._list(book.cate_depth1, 12),
            "kcid": self._list(book.kcid, 12),
            "author_intro": self._trim(book.author_intro, 300),
            "book_index": self._trim(book.book_index, 700),
            "pub_review": self._trim(book.pub_review, 700),
        }

    @classmethod
    def _normalize_group_age_policy(
        cls, audience_group: str, min_age: int | None, max_age: int | None
    ) -> tuple[str, int | None, int | None]:
        # 수정 포인트: LLM이 ADULT/17/99처럼 enum과 연령대를 모순되게 반환할 수 있습니다.
        # 특정 장르/문구 기반 if 하드코딩이 아니라 enum-연령 일관성만 후처리합니다.
        if min_age is not None and max_age is not None and min_age > max_age:
            min_age, max_age = max_age, min_age

        if audience_group == "UNKNOWN":
            return "UNKNOWN", None, None

        if audience_group == "ADULT":
            if min_age is not None and min_age < 19:
                if max_age is not None and max_age <= 35:
                    return "YOUNG_ADULT", max(17, min_age), max_age
                normalized_max = None if max_age in (None, 99) else max_age
                return "GENERAL", min_age, normalized_max
            return "ADULT", max(19, min_age or 19), max_age

        if audience_group == "YOUNG_ADULT":
            normalized_min = max(17, min_age or 17)
            if max_age is not None and max_age > 35:
                return "GENERAL", min_age, None if max_age == 99 else max_age
            return "YOUNG_ADULT", normalized_min, max_age or 29

        if audience_group == "GENERAL":
            return "GENERAL", min_age, None if max_age == 99 else max_age

        age_defaults = {
            "INFANT": (0, 5),
            "CHILD": (4, 8),
            "ELEMENTARY": (7, 12),
            "MIDDLE_SCHOOL": (13, 15),
            "HIGH_SCHOOL": (16, 18),
        }
        default_range = age_defaults.get(audience_group)
        if default_range is None:
            return audience_group, min_age, max_age
        default_min, default_max = default_range
        return audience_group, min_age if min_age is not None else default_min, max_age if max_age is not None else default_max

    @classmethod
    def _chunks(cls, books: List[AudienceLabelBook], size: int) -> Iterable[List[AudienceLabelBook]]:
        chunk_size = max(1, size)
        for index in range(0, len(books), chunk_size):
            yield books[index : index + chunk_size]

    @classmethod
    def _extract_items(cls, parsed: Any) -> List[Any]:
        if isinstance(parsed, dict):
            items = parsed.get("items")
            return items if isinstance(items, list) else []
        if isinstance(parsed, list):
            return parsed
        return []

    @staticmethod
    def _parse_json(text: str) -> Dict[str, Any] | List[Any]:
        value = str(text or "").strip()
        if not value:
            raise ValueError("LLM returned an empty response. Check CLOVA chat URL/model/API key and ai-server logs.")

        if value.startswith("```"):
            value = re.sub(r"^```(?:json)?", "", value, flags=re.IGNORECASE).strip()
            value = re.sub(r"```$", "", value).strip()

        if not value.startswith("{") and not value.startswith("["):
            match = re.search(r"(\{.*\}|\[.*\])", value, flags=re.DOTALL)
            value = match.group(0) if match else value

        parsed = json.loads(value)
        return parsed if isinstance(parsed, (dict, list)) else {}

    @staticmethod
    def _normalize_status(value: Any) -> str:
        normalized = str(value or "READY").strip().upper()
        if normalized in {"FAILED", "FAIL", "ERROR"}:
            return "FAILED"
        return "READY"

    @staticmethod
    def _normalize_enum(value: Any, allowed: set[str]) -> str:
        normalized = str(value or "UNKNOWN").strip().upper()
        return normalized if normalized in allowed else "UNKNOWN"

    @staticmethod
    def _normalize_confidence(value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, number))

    @staticmethod
    def _normalize_age(value: Any) -> int | None:
        try:
            number = int(value)
        except (TypeError, ValueError):
            return None
        return max(0, min(99, number))

    @staticmethod
    def _trim(value: Any, limit: int) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        return text[:limit]

    @staticmethod
    def _list(values: List[Any] | None, limit: int) -> List[str]:
        output: List[str] = []
        for value in values or []:
            text = str(value or "").strip()
            if text and text not in output:
                output.append(text[:120])
            if len(output) >= limit:
                break
        return output
