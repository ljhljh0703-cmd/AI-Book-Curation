from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List

from app.core.config import settings
from app.services.common.json_utils import extract_json_object

from app.services.common.config_loader import load_text_resource
from app.services.context.conversation_context import ConversationContext
from app.services.context.profile_context import ProfileContextBuilder
from app.services.common.text_utils import normalize_text, safe_join
from app.services.common.source_format_policy import SourceFormatPolicy


class RecommendationPromptBuilder:
    """추천/서비스 답변용 프롬프트와 deterministic 추천 이유 생성을 전담합니다."""

    def __init__(self, profile_context: ProfileContextBuilder | None = None) -> None:
        self.profile_context = profile_context or ProfileContextBuilder()
        self.reason_templates = self._load_reason_templates()

    @staticmethod
    def _load_reason_templates() -> Dict[str, Any]:
        raw = load_text_resource("prompts/recommendation_reason_fallbacks.json")
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _render(template: str, **values: str) -> str:
        rendered = template
        for key, value in values.items():
            rendered = rendered.replace("{{" + key + "}}", value)
        return rendered

    def recommendation_system_prompt(self) -> str:
        return load_text_resource("prompts/recommendation_system.md")

    def general_system_prompt(self) -> str:
        return load_text_resource("prompts/general_system.md")

    def reason_generation_system_prompt(self) -> str:
        return load_text_resource("prompts/recommendation_reason_system.md")

    def build_recommendation_reason_user_prompt(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        personalization_mode: str = "DISABLED",
    ) -> str:
        normalized_mode = self._resolve_mode(personalization_mode=personalization_mode, candidates=candidates)
        payload: List[Dict[str, Any]] = []
        for idx, book in enumerate(candidates, start=1):
            evidence = book.get("personalization_evidence") or (book.get("score_detail") or {}).get("personalization_evidence") or {}
            score_detail = book.get("score_detail") or {}
            payload.append(
                {
                    "book_id": self._candidate_reason_id(idx, book),
                    "rank": idx,
                    "title": str(book.get("title") or "").strip(),
                    "author": str(book.get("author") or "").strip(),
                    "isbn": str(book.get("isbn") or book.get("isbn13") or "").strip(),
                    "publisher": str(book.get("publisher") or "").strip(),
                    "publish_date": str(book.get("publish_date") or "").strip(),
                    "format": str(book.get("format") or book.get("book_format") or book.get("media_type") or book.get("content_format") or "").strip(),
                    "is_audio_book": book.get("is_audio_book"),
                    "source_format": book.get("source_format"),
                    "source_format_evidence": book.get("source_format_evidence"),
                    "is_ebook": book.get("is_ebook"),
                    "categories": self._as_texts(book.get("categories") or book.get("cate_depth1") or []),
                    "match_type": str(book.get("match_type") or "").strip(),
                    "score_detail": self._reason_score_payload(score_detail),
                    "personalization_evidence": self._reason_evidence_payload(evidence),
                    "reason_hint": self._make_fallback_recommendation_reason(
                        book=book,
                        personalization_mode=normalized_mode,
                    ),
                    "book_context": self._book_context_excerpt(book),
                }
            )

        template = load_text_resource("prompts/recommendation_reason_user.md")
        return self._render(
            template,
            query=query,
            personalization_mode=normalized_mode,
            candidate_json=json.dumps(payload, ensure_ascii=False, indent=2),
        )

    def make_recommendation_answer_from_reason_schema(
        self,
        llm_response: str,
        candidates: List[Dict[str, Any]],
        personalization_mode: str = "DISABLED",
    ) -> str:
        reasons = self._extract_valid_reason_schema(llm_response=llm_response, candidates=candidates)
        normalized_mode = self._resolve_mode(personalization_mode=personalization_mode, candidates=candidates)
        answer_blocks: List[str] = []
        for idx, book in enumerate(candidates, start=1):
            candidate_id = self._candidate_reason_id(idx, book)
            if self._should_force_format_reason(book):
                reason = self._make_fallback_recommendation_reason(
                    book=book,
                    personalization_mode=normalized_mode,
                )
                reason_source = "FALLBACK_FORMAT"
            else:
                reason = reasons.get(candidate_id) or self._make_fallback_recommendation_reason(
                    book=book,
                    personalization_mode=normalized_mode,
                )
                reason_source = "LLM" if candidate_id in reasons else "FALLBACK"
            book["recommendation_reason"] = reason
            book["recommendation_reason_source"] = reason_source
            title = str(book.get("title") or "제목 정보 없음").strip()
            author = str(book.get("author") or "저자 정보 없음").strip()
            answer_blocks.append(
                f"{idx}. {title}\n\n"
                f"저자: {author}\n"
                f"추천 이유: {reason}"
            )
        return "\n\n".join(answer_blocks)

    def count_valid_reason_schema(self, llm_response: str, candidates: List[Dict[str, Any]]) -> int:
        return len(self._extract_valid_reason_schema(llm_response=llm_response, candidates=candidates))

    def has_complete_reason_schema(self, llm_response: str, candidates: List[Dict[str, Any]]) -> bool:
        return self.count_valid_reason_schema(llm_response=llm_response, candidates=candidates) == len(candidates)

    def build_general_user_prompt(self, query: str, history: List[Dict[str, Any]] | None = None) -> str:
        history_text = ConversationContext.make_history_text(history)
        history_block = f"이전 대화 내역:\n{history_text}\n\n" if history_text else ""
        template = load_text_resource("prompts/general_user.md")
        return self._render(template, history_block=history_block, query=query)

    def build_recommendation_user_prompt(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        history: List[Dict[str, Any]] | None = None,
        personalization_mode: str = "DISABLED",
    ) -> str:
        history_text = ConversationContext.make_history_text(history)
        history_block = f"이전 대화 내역:\n{history_text}\n\n" if history_text else ""
        normalized_mode = self._resolve_mode(personalization_mode=personalization_mode, candidates=candidates)
        candidate_block = self._make_candidate_block(candidates, personalization_mode=normalized_mode)
        recommend_count = len(candidates)
        template = load_text_resource("prompts/recommendation_user.md")
        return self._render(
            template,
            history_block=history_block,
            query=query,
            candidate_block=candidate_block,
            recommend_count=str(recommend_count),
            next_number=str(recommend_count + 1),
            example_block=self._make_example_block(recommend_count),
            reason_instruction=self._make_reason_instruction(),
        )

    def attach_profile_to_prompt(
        self,
        user_prompt: str,
        profile: Dict[str, Any] | None = None,
        guest: bool = False,
    ) -> str:
        profile_text = self.profile_context.make_profile_text(profile=profile, guest=guest)
        if not profile_text:
            return user_prompt

        template = load_text_resource("prompts/profile_context.md")
        return self._render(template, profile_text=profile_text, user_prompt=user_prompt)

    def make_pending_recommendation_answer(self, candidates: List[Dict[str, Any]]) -> str:
        template = self._template("pending_recommendation_answer", "")
        if not template:
            return ""
        return template.replace("{count}", str(len(candidates or [])))

    def make_pending_recommendation_reason(self) -> str:
        return self._template("pending_recommendation_reason", self._empty_reason())

    def make_fallback_recommendation_answer(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        personalization_mode: str = "DISABLED",
    ) -> str:
        """최종 후보와 score_detail/evidence만 사용해 사용자 노출 답변을 생성합니다."""
        _ = query
        if not candidates:
            return self._template("empty_recommendation", "")

        normalized_mode = self._resolve_mode(personalization_mode=personalization_mode, candidates=candidates)
        answer_blocks: List[str] = []
        for idx, book in enumerate(candidates, start=1):
            title = str(book.get("title") or "제목 정보 없음").strip()
            author = str(book.get("author") or "저자 정보 없음").strip()
            reason = self._make_fallback_recommendation_reason(
                book=book,
                personalization_mode=normalized_mode,
            )
            answer_blocks.append(
                f"{idx}. {title}\n\n"
                f"저자: {author}\n"
                f"추천 이유: {reason}"
            )

        return "\n\n".join(answer_blocks)

    def is_low_quality_recommendation_answer(
        self,
        answer: str,
        query: str,
        personalization_mode: str = "DISABLED",
    ) -> bool:
        """LLM 답변을 사용하는 경로의 최소 구조 검증입니다."""
        _ = query, personalization_mode
        if not answer or not answer.strip():
            return True

        reason_lines = self._extract_reason_lines(answer)
        if len(reason_lines) >= 2:
            normalized_reasons = [normalize_text(line) for line in reason_lines if normalize_text(line)]
            if normalized_reasons and len(set(normalized_reasons)) <= 1:
                return True
        return False

    def _make_fallback_recommendation_reason(
        self,
        book: Dict[str, Any],
        personalization_mode: str,
    ) -> str:
        normalized_mode = self._normalize_mode(personalization_mode)
        evidence_phrases = self._personalization_evidence_phrases(book)
        score_phrases = self._score_evidence_phrases(book)
        category_text = self._candidate_category_text(book)
        context_text = self._context_keyword(book)
        match_type = str(book.get("match_type") or "").strip()

        source_format_reason = self._source_format_reason(book=book, category_text=category_text, context_text=context_text)
        if source_format_reason:
            return source_format_reason

        if evidence_phrases:
            secondary = score_phrases[0] if score_phrases else self._category_phrase(category_text, context_text)
            return self._join_reason_parts([evidence_phrases[0], secondary])

        if normalized_mode != "DISABLED" and score_phrases:
            return self._join_reason_parts(score_phrases[:2])

        if category_text:
            primary = self._category_phrase(category_text, context_text)
            return self._join_reason_parts([primary, score_phrases[0] if score_phrases else ""])

        if context_text:
            return self._format_template("generic_context_reason", context=context_text)

        if match_type:
            return self._template("match_type_reason", "") or self._empty_reason()

        return self._empty_reason()

    def _source_format_reason(self, *, book: Dict[str, Any], category_text: str, context_text: str) -> str:
        if not self._has_audiobook_format_evidence(book):
            return ""

        format_phrase = "원천 데이터에서 오디오북 형식으로 확인됩니다"
        if context_text:
            return self._join_reason_parts([
                format_phrase,
                f"소개 정보의 '{context_text}' 흐름을 눈으로 읽기 어려운 상황에서 청취로 따라가기 좋습니다",
            ])
        if category_text:
            return self._join_reason_parts([
                format_phrase,
                f"분류가 '{category_text}'로 확인되어 종이책 대신 청취 가능한 후보로 우선 추천합니다",
            ])
        return self._join_reason_parts([
            format_phrase,
            "운전이나 이동처럼 시각적 독서가 어려운 상황에는 일반 종이책보다 형식 조건이 더 잘 맞습니다",
        ])

    @staticmethod
    def _should_force_format_reason(book: Dict[str, Any]) -> bool:
        score_detail = book.get("score_detail") if isinstance(book.get("score_detail"), dict) else {}
        reading_mode = str(score_detail.get("reading_mode") or "").strip().upper()
        return bool(reading_mode == "LISTENING_FRIENDLY" and RecommendationPromptBuilder._has_audiobook_format_evidence(book))

    @staticmethod
    def _has_audiobook_format_evidence(book: Dict[str, Any]) -> bool:
        evidence = book.get("source_format_evidence")
        if not isinstance(evidence, dict) or not evidence.get("matched"):
            score_detail = book.get("score_detail") if isinstance(book.get("score_detail"), dict) else {}
            evidence = score_detail.get("listening_format_evidence")
        if isinstance(evidence, dict) and evidence.get("matched"):
            normalized_format = str(evidence.get("normalized_format") or "").strip().upper()
            if normalized_format == SourceFormatPolicy.AUDIOBOOK:
                return True
        return SourceFormatPolicy.is_audiobook_payload(book)

    def _join_reason_parts(self, parts: List[str]) -> str:
        cleaned = [part.strip().rstrip(".") for part in parts if part and part.strip()]
        if not cleaned:
            return self._empty_reason()
        sentences = [part if part.endswith(("다", "요", "함", "음", "습니다")) else part + "입니다" for part in cleaned[:2]]
        return " ".join(sentence.rstrip(".") + "." for sentence in sentences)

    def _category_phrase(self, category_text: str, context_text: str = "") -> str:
        if category_text and context_text:
            return self._format_template("category_context_reason", category=category_text, context=context_text)
        if category_text:
            return self._format_template("category_reason", category=category_text)
        return self._empty_reason()

    def _score_evidence_phrases(self, book: Dict[str, Any]) -> List[str]:
        score_detail = book.get("score_detail") or {}
        if not isinstance(score_detail, dict):
            return []

        fields = [
            "explicit_filter_match",
            "intent_relevance_score",
            "purpose_match_score",
            "listening_format_score",
            "consumption_mode_score",
            "raw_consumption_mode_score",
            "consumption_negative_score",
            "consumption_negative_penalty",
            "consumption_mode_mismatch_penalty",
            "reading_mode",
            "profile_match_score",
            "purpose_score",
            "genre_score",
            "preferred_book_score",
            "reading_book_score",
            "read_book_score",
            "review_rating_positive_score",
            "user_profile_vector_score",
            "audience_match_score",
            "final_rerank_score",
        ]
        phrases: List[str] = []
        score_templates = self.reason_templates.get("score_phrases") if isinstance(self.reason_templates, dict) else {}
        if not isinstance(score_templates, dict):
            score_templates = {}
        for key in fields:
            value = RecommendationPromptBuilder._safe_float(score_detail.get(key))
            threshold = 0.55 if key != "final_rerank_score" else 0.65
            phrase = str(score_templates.get(key) or "").strip()
            if value >= threshold and phrase:
                phrases.append(phrase)
        return RecommendationPromptBuilder._dedupe_texts(phrases, limit=3)

    def _personalization_evidence_phrases(self, book: Dict[str, Any]) -> List[str]:
        evidence = book.get("personalization_evidence") or (book.get("score_detail") or {}).get("personalization_evidence") or {}
        if not isinstance(evidence, dict):
            return []

        phrases: List[str] = []
        matched_genres = RecommendationPromptBuilder._as_texts(
            evidence.get("matched_genres") or evidence.get("matched_genre_signal")
        )
        if matched_genres:
            phrases.append(self._format_evidence_template("matched_genres", value=matched_genres[0]))

        purpose_terms = RecommendationPromptBuilder._as_texts(evidence.get("matched_purpose_terms"))
        purpose_summary = str(evidence.get("reading_purpose_summary") or evidence.get("purpose") or "").strip()
        if purpose_terms:
            template_key = "matched_purpose_terms_with_summary" if purpose_summary else "matched_purpose_terms"
            phrases.append(self._format_evidence_template(template_key, value=purpose_terms[0], summary=purpose_summary))

        reading_titles = RecommendationPromptBuilder._as_titles(evidence.get("matched_reading_books"))
        if reading_titles:
            phrases.append(self._format_evidence_template("matched_reading_books", value=reading_titles[0]))

        read_titles = RecommendationPromptBuilder._as_titles(evidence.get("matched_read_books"))
        if read_titles:
            phrases.append(self._format_evidence_template("matched_read_books", value=read_titles[0]))

        preferred_titles = RecommendationPromptBuilder._as_titles(evidence.get("matched_preferred_books"))
        if preferred_titles:
            phrases.append(self._format_evidence_template("matched_preferred_books", value=preferred_titles[0]))

        high_rated_titles = RecommendationPromptBuilder._as_titles(evidence.get("matched_high_rated_books"))
        review_positive_terms = RecommendationPromptBuilder._as_texts(
            evidence.get("matched_review_positive_terms") or evidence.get("review_positive_terms")
        )
        if high_rated_titles and review_positive_terms:
            phrases.append(
                self._format_evidence_template(
                    "matched_high_rated_books_with_terms",
                    title=high_rated_titles[0],
                    term=review_positive_terms[0],
                )
            )
        elif high_rated_titles:
            phrases.append(self._format_evidence_template("matched_high_rated_books", value=high_rated_titles[0]))
        elif review_positive_terms:
            phrases.append(self._format_evidence_template("matched_review_positive_terms", value=review_positive_terms[0]))

        if evidence.get("profile_vector"):
            phrases.append(self._format_evidence_template("profile_vector"))
        if evidence.get("audience"):
            phrases.append(self._format_evidence_template("audience"))

        return RecommendationPromptBuilder._dedupe_texts(phrases, limit=3)

    def _empty_reason(self) -> str:
        return self._template("empty_reason", "")

    def _template(self, key: str, default: str = "") -> str:
        value = self.reason_templates.get(key) if isinstance(self.reason_templates, dict) else None
        text = str(value or "").strip()
        return text or default

    def _format_template(self, key: str, **values: str) -> str:
        template = self._template(key, "")
        if not template:
            return self._empty_reason()
        for name, value in values.items():
            template = template.replace("{" + name + "}", str(value or "").strip())
        return template

    def _format_evidence_template(self, key: str, **values: str) -> str:
        evidence_templates = self.reason_templates.get("evidence_phrases") if isinstance(self.reason_templates, dict) else {}
        if not isinstance(evidence_templates, dict):
            evidence_templates = {}
        template = str(evidence_templates.get(key) or "").strip()
        if not template:
            return ""
        for name, value in values.items():
            template = template.replace("{" + name + "}", str(value or "").strip())
        return template

    @staticmethod
    def _context_keyword(book: Dict[str, Any]) -> str:
        context = RecommendationPromptBuilder._book_context_excerpt(book)
        if not context:
            return ""
        text = re.sub(r"\s+", " ", context).strip()
        if not text:
            return ""
        return text[:48].rstrip()

    @staticmethod
    def _score_detail_summary(score_detail: Dict[str, Any]) -> str:
        if not isinstance(score_detail, dict) or not score_detail:
            return "없음"

        label_by_key = {
            "semantic_score": "semantic",
            "explicit_filter_match": "explicit_filter",
            "intent_relevance_score": "intent_relevance",
            "audience_match_score": "audience_match",
            "purpose_match_score": "purpose_match",
            "consumption_mode_score": "consumption_mode",
            "consumption_negative_penalty": "consumption_negative_penalty",
            "consumption_mode_mismatch_penalty": "consumption_mode_mismatch_penalty",
            "profile_match_score": "profile_match",
            "off_intent_penalty": "off_intent_penalty",
            "specialized_content_penalty": "specialized_penalty",
            "final_rerank_score": "final_rerank",
        }
        parts: List[str] = []
        for key, label in label_by_key.items():
            value = score_detail.get(key)
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if abs(number) < 0.0001:
                continue
            parts.append(f"{label}={number:.3f}")

        return ", ".join(parts[:10]) if parts else "없음"

    @staticmethod
    def _candidate_reason_id(idx: int, book: Dict[str, Any]) -> str:
        isbn = str(book.get("isbn") or book.get("isbn13") or "").strip()
        if isbn:
            return f"isbn:{isbn}"
        title = normalize_text(str(book.get("title") or ""))
        author = normalize_text(str(book.get("author") or ""))
        if title or author:
            return f"book:{title}|{author}"
        return f"candidate:{idx}"

    @staticmethod
    def _reason_score_payload(score_detail: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(score_detail, dict):
            return {}
        keys = [
            "semantic_score",
            "explicit_filter_match",
            "intent_relevance_score",
            "audience_match_score",
            "purpose_match_score",
            "listening_format_score",
            "listening_format_evidence",
            "consumption_mode_score",
            "raw_consumption_mode_score",
            "consumption_negative_score",
            "consumption_negative_penalty",
            "consumption_mode_mismatch_penalty",
            "reading_mode",
            "profile_match_score",
            "purpose_score",
            "genre_score",
            "preferred_book_score",
            "reading_book_score",
            "read_book_score",
            "review_rating_positive_score",
            "user_profile_vector_score",
            "off_intent_penalty",
            "specialized_content_penalty",
            "candidate_relevance_score",
            "confidence",
            "final_rerank_score",
        ]
        result: Dict[str, Any] = {}
        for key in keys:
            if key in score_detail:
                result[key] = score_detail.get(key)
        return result

    @staticmethod
    def _reason_evidence_payload(evidence: Any) -> Dict[str, Any]:
        if not isinstance(evidence, dict):
            return {}
        result: Dict[str, Any] = {}
        for key in [
            "matched_genres",
            "matched_preferred_books",
            "matched_reading_books",
            "matched_read_books",
            "matched_high_rated_books",
            "matched_review_positive_terms",
            "matched_purpose_terms",
            "reading_purpose_summary",
        ]:
            values = RecommendationPromptBuilder._as_texts(evidence.get(key))
            if values:
                result[key] = values[:4]
        return result

    @staticmethod
    def _book_context_excerpt(book: Dict[str, Any]) -> str:
        values: List[str] = []
        for key in ["simple_intro", "book_intro", "description", "book_index", "pub_review"]:
            text = str(book.get(key) or "").strip()
            if text:
                values.append(text)
        joined = " ".join(values).strip()
        return joined[:420].rstrip()

    def _extract_valid_reason_schema(self, llm_response: str, candidates: List[Dict[str, Any]]) -> Dict[str, str]:
        data = extract_json_object(llm_response)
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            return {}

        candidate_by_id = {self._candidate_reason_id(idx, book): book for idx, book in enumerate(candidates, start=1)}
        valid_reasons: Dict[str, str] = {}
        max_chars = max(60, int(settings.RECOMMENDATION_REASON_MAX_CHARS))

        for item in items:
            if not isinstance(item, dict):
                continue
            candidate_id = str(item.get("book_id") or "").strip()
            if candidate_id not in candidate_by_id or candidate_id in valid_reasons:
                continue
            reason = self._clean_reason_text(item.get("reason"), max_chars=max_chars)
            if not reason:
                continue
            if not self._is_reason_structurally_grounded(reason, candidate_by_id[candidate_id]):
                continue
            valid_reasons[candidate_id] = reason

        return valid_reasons

    @staticmethod
    def _clean_reason_text(value: Any, max_chars: int) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        # 수정 포인트: LLM이 score_detail의 내부 enum명(AUDIENCE_MATCH 등)을 그대로 노출하면
        # 사용자에게 어색하게 보입니다. 괄호 안/독립 토큰으로 나온 내부 식별자는 제거하고,
        # 남은 문장만 추천 이유로 사용합니다.
        text = re.sub(r"\((?:[A-Z][A-Z0-9]*_){1,}[A-Z0-9]+\)", "", text)
        text = re.sub(r"\b(?:[A-Z][A-Z0-9]*_){1,}[A-Z0-9]+\b", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        text = re.sub(r"\s+([,.;:!?])", r"\1", text).strip(" ,;:/")
        if not text:
            return ""
        if len(text) > max_chars:
            text = text[:max_chars].rstrip()
        if text and text[-1] not in ".!?。！？다요함음됨됨니다습니다":
            text += "."
        return text

    @staticmethod
    def _is_reason_structurally_grounded(reason: str, book: Dict[str, Any]) -> bool:
        if re.search(r"\b(?:[A-Z][A-Z0-9]*_){1,}[A-Z0-9]+\b", str(reason or "")):
            return False
        normalized_reason = normalize_text(reason)
        if len(normalized_reason) < 8:
            return False

        for key in ["description", "simple_intro", "book_intro", "pub_review"]:
            source = normalize_text(str(book.get(key) or ""))
            if len(source) < 40:
                continue
            if normalized_reason and normalized_reason in source:
                return False
            similarity = SequenceMatcher(None, normalized_reason[:180], source[:260]).ratio()
            if similarity >= 0.86:
                return False
        return True

    @staticmethod
    def _candidate_category_text(book: Dict[str, Any]) -> str:
        categories = book.get("categories") or book.get("cate_depth1") or []
        category_text = safe_join(categories).strip()
        if not category_text:
            return ""
        return category_text[:60].rstrip()

    def _make_candidate_block(
        self,
        candidates: List[Dict[str, Any]],
        personalization_mode: str,
    ) -> str:
        candidate_texts: List[str] = []
        for idx, book in enumerate(candidates, start=1):
            categories = book.get("categories") or book.get("cate_depth1") or []
            evidence = book.get("personalization_evidence") or (book.get("score_detail") or {}).get("personalization_evidence") or {}
            score_detail = book.get("score_detail") or {}
            reason_hint = self._make_fallback_recommendation_reason(
                book=book,
                personalization_mode=personalization_mode,
            )
            candidate_texts.append(
                f"[candidate {idx}]\n"
                f"- title: {book.get('title', '')}\n"
                f"- author: {book.get('author', '')}\n"
                f"- isbn: {book.get('isbn', '')}\n"
                f"- publisher: {book.get('publisher', '')}\n"
                f"- publishDate: {book.get('publish_date', '')}\n"
                f"- format: {book.get('format') or book.get('book_format') or book.get('media_type') or book.get('content_format') or ''}\n"
                f"- isAudioBook: {book.get('is_audio_book', '')}\n"
                f"- sourceFormat: {book.get('source_format', '')}\n"
                f"- sourceFormatEvidence: {book.get('source_format_evidence', '')}\n"
                f"- isEbook: {book.get('is_ebook', '')}\n"
                f"- categories: {safe_join(categories)}\n"
                f"- matchType: {book.get('match_type', '')}\n"
                f"- searchScore: {book.get('score', 0)}\n"
                f"- rerankScore: {book.get('rerank_score', '')}\n"
                f"- scoreDetail: {RecommendationPromptBuilder._score_detail_summary(score_detail)}\n"
                f"- personalizationEvidence: {RecommendationPromptBuilder._evidence_summary(evidence)}\n"
                f"- reasonHint: {reason_hint}\n"
            )
        return "\n".join(candidate_texts)

    @staticmethod
    def _make_reason_instruction() -> str:
        return "- Use only candidate fields, scoreDetail, personalizationEvidence, and reasonHint. Do not add books or change order."

    @staticmethod
    def _evidence_summary(evidence: Any) -> str:
        if not isinstance(evidence, dict) or not evidence:
            return "없음"
        parts: List[str] = []
        for key in [
            "signal_labels",
            "matched_genres",
            "matched_preferred_books",
            "matched_reading_books",
            "matched_read_books",
            "matched_high_rated_books",
            "matched_review_positive_terms",
            "matched_purpose_terms",
        ]:
            values = RecommendationPromptBuilder._as_texts(evidence.get(key))
            if values:
                parts.append(f"{key}=" + ", ".join(values[:3]))
        return " / ".join(parts) if parts else "없음"

    @staticmethod
    def _extract_reason_lines(answer: str) -> List[str]:
        result: List[str] = []
        for line in answer.splitlines():
            if "추천 이유" not in line:
                continue
            _, _, reason = line.partition(":")
            result.append(reason.strip() or line.strip())
        return result

    @staticmethod
    def _as_texts(value: Any) -> List[str]:
        if not value:
            return []
        if isinstance(value, list):
            result: List[str] = []
            for item in value:
                result.extend(RecommendationPromptBuilder._as_texts(item))
            return RecommendationPromptBuilder._dedupe_texts(result, limit=8)
        if isinstance(value, dict):
            for key in ["label", "name", "title", "category", "categoryName", "categoryCode", "genre"]:
                if value.get(key):
                    return [str(value.get(key)).strip()]
            return []
        text = str(value).strip()
        return [text] if text else []

    @staticmethod
    def _as_titles(value: Any) -> List[str]:
        if not value:
            return []
        if isinstance(value, list):
            result: List[str] = []
            for item in value:
                result.extend(RecommendationPromptBuilder._as_titles(item))
            return RecommendationPromptBuilder._dedupe_texts(result, limit=8)
        if isinstance(value, dict):
            for key in ["title", "bookTitle", "name", "bookName", "label"]:
                if value.get(key):
                    return [str(value.get(key)).strip()]
            return []
        text = str(value).strip()
        return [text] if text else []

    @staticmethod
    def _make_example_block(recommend_count: int) -> str:
        example_blocks: List[str] = []
        for idx in range(1, recommend_count + 1):
            example_blocks.append(
                f"{idx}. title\n"
                "author: author\n"
                "reason: candidate-grounded reason"
            )
        return "\n\n".join(example_blocks)

    @classmethod
    def _resolve_mode(cls, personalization_mode: str, candidates: List[Dict[str, Any]]) -> str:
        normalized = cls._normalize_mode(personalization_mode)
        if normalized != "DISABLED":
            return normalized
        for book in candidates:
            mode = (book.get("score_detail") or {}).get("personalization_mode")
            normalized = cls._normalize_mode(str(mode or ""))
            if normalized != "DISABLED":
                return normalized
        return "DISABLED"

    @staticmethod
    def _normalize_mode(personalization_mode: str) -> str:
        normalized = str(personalization_mode or "DISABLED").strip().upper()
        if normalized not in {"QUERY_FIRST", "PROFILE_FIRST", "HYBRID", "DISABLED"}:
            return "DISABLED"
        return normalized

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _dedupe_texts(values: List[str], limit: int = 10) -> List[str]:
        seen = set()
        result: List[str] = []
        for value in values:
            text = str(value or "").strip()
            normalized = normalize_text(text)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            result.append(text)
            if len(result) >= limit:
                break
        return result
