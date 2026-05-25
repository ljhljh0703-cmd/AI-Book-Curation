from __future__ import annotations

import json
from typing import Any, Dict

from app.schemas.preference import ReviewPreferenceAnalysisRequest, ReviewPreferenceAnalysisResponse
from app.services.clients.clova_client import ClovaClient
from app.services.common.config_loader import load_text_resource
from app.services.common.json_utils import clamp_float, extract_json_object, to_string_list


class ReviewPreferenceAnalyzer:
    """리뷰 원문을 추천 점수로 직접 쓰지 않고 저장 가능한 취향 신호 JSON으로 구조화합니다."""

    def __init__(self) -> None:
        self.llm = ClovaClient()

    def analyze(self, request: ReviewPreferenceAnalysisRequest) -> ReviewPreferenceAnalysisResponse:
        if not request.review_content or not request.review_content.strip():
            return ReviewPreferenceAnalysisResponse(
                analysis_status="SKIPPED",
                analysis_error_message="review content is empty",
            )

        system_prompt = self._system_prompt()
        user_prompt = self._user_prompt(request)

        try:
            content = self.llm.chat_completion(system_prompt, user_prompt)
            payload = extract_json_object(content)
            if not payload:
                return self._fallback_from_rating(request, "LLM JSON parse failed")
            return self._normalize_response(payload, request)
        except Exception as exc:
            return self._fallback_from_rating(request, str(exc))


    def _system_prompt(self) -> str:
        # 수정 포인트: 리뷰 취향 분석 prompt를 파일로 분리해 추천 pipeline 코드와 prompt 문서를 분리합니다.
        # 파일 로딩이 실패하면 기존 inline prompt와 동일한 fallback을 사용해 운영 동작을 깨뜨리지 않습니다.
        return load_text_resource("prompts/review_preference_system.md") or """
당신은 도서 리뷰에서 사용자의 취향 신호를 구조화하는 분석기입니다.
반드시 JSON object만 반환하세요.
규칙:
- 리뷰 원문과 평점, 도서 메타데이터에서 근거가 있는 취향만 추출합니다.
- 추천 후보를 만들거나 책을 지어내지 않습니다.
- overall_sentiment는 positive, negative, mixed, neutral 중 하나입니다.
- 평점과 리뷰 내용이 충돌하면 mixed 또는 confidence를 낮게 설정합니다.
- liked_aspects와 disliked_aspects를 반드시 분리합니다.
- sentiment_score는 -1.0~1.0, confidence는 0.0~1.0입니다.
- 배열 필드는 짧은 한국어 명사구로 제한합니다.
""".strip()

    def _user_prompt(self, request: ReviewPreferenceAnalysisRequest) -> str:
        payload = {
            "rating": request.rating,
            "review_content": request.review_content[:2000],
            "book_metadata": request.book_metadata,
            "expected_json_schema": {
                "overall_sentiment": "positive|negative|mixed|neutral",
                "sentiment_score": 0.0,
                "confidence": 0.0,
                "liked_aspects": ["문체", "몰입감"],
                "disliked_aspects": ["느린 전개"],
                "preference_terms": ["흡입력 있는 전개"],
                "avoid_terms": ["지루한 구성"],
                "preferred_mood": ["편안한"],
                "avoid_mood": ["답답한"],
                "summary": "리뷰에서 드러난 취향 요약",
            },
        }
        template = load_text_resource("prompts/review_preference_user.md")
        if template:
            return template.replace("{{payload_json}}", json.dumps(payload, ensure_ascii=False))
        return json.dumps(payload, ensure_ascii=False)

    def _normalize_response(self, payload: Dict[str, Any], request: ReviewPreferenceAnalysisRequest) -> ReviewPreferenceAnalysisResponse:
        sentiment = str(payload.get("overall_sentiment") or "neutral").strip().lower()
        if sentiment not in {"positive", "negative", "mixed", "neutral"}:
            sentiment = self._sentiment_from_rating(request.rating)

        return ReviewPreferenceAnalysisResponse(
            overall_sentiment=sentiment,
            sentiment_score=clamp_float(payload.get("sentiment_score"), -1.0, 1.0, self._score_from_rating(request.rating)),
            confidence=clamp_float(payload.get("confidence"), 0.0, 1.0, 0.55),
            liked_aspects=to_string_list(payload.get("liked_aspects"), 12),
            disliked_aspects=to_string_list(payload.get("disliked_aspects"), 12),
            preference_terms=to_string_list(payload.get("preference_terms"), 12),
            avoid_terms=to_string_list(payload.get("avoid_terms"), 12),
            preferred_mood=to_string_list(payload.get("preferred_mood"), 8),
            avoid_mood=to_string_list(payload.get("avoid_mood"), 8),
            summary=str(payload.get("summary") or "").strip()[:500] or None,
            analysis_status="SUCCEEDED",
        )

    def _fallback_from_rating(self, request: ReviewPreferenceAnalysisRequest, reason: str) -> ReviewPreferenceAnalysisResponse:
        sentiment = self._sentiment_from_rating(request.rating)
        return ReviewPreferenceAnalysisResponse(
            overall_sentiment=sentiment,
            sentiment_score=self._score_from_rating(request.rating),
            confidence=0.25,
            summary="LLM 분석 실패로 평점 기반 최소 신호만 저장했습니다.",
            analysis_status="FAILED",
            analysis_error_message=reason[:500],
        )

    @staticmethod
    def _sentiment_from_rating(rating: float) -> str:
        if rating >= 4.0:
            return "positive"
        if rating <= 2.0:
            return "negative"
        return "mixed"

    @staticmethod
    def _score_from_rating(rating: float) -> float:
        return max(-1.0, min(1.0, (float(rating) - 3.0) / 2.0))
