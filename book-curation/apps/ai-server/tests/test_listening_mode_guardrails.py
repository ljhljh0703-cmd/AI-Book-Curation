import os

os.environ.setdefault("CLOVA_API_KEY", "test-key")

from app.services.intent.query_intent_parser import QueryIntent
from app.services.intent.reading_mode_policy import ReadingModePolicy
from app.services.recommendation.recommendation_guardrails import RecommendationGuardrails


def _intent() -> QueryIntent:
    return QueryIntent(
        raw_query="운전 중 들을 책 추천해줘",
        retrieval_query="오디오북 낭독 음성 청취",
        general_recommendation=True,
        consumption_context="병행 활동",
        reading_mode=ReadingModePolicy.MODE_LISTENING_FRIENDLY,
        consumption_positive_terms=["청취", "음성", "낭독"],
        target_reader="SELF",
    )


def test_listening_mode_filters_to_actual_audio_metadata_when_available():
    guardrails = RecommendationGuardrails()
    candidates = [
        {
            "title": "일반 종이책",
            "score": 0.99,
            "description": "쉬운 이야기",
            "score_detail": {},
        },
        {
            "title": "실제 오디오북",
            "score": 0.50,
            "format": "오디오북",
            "score_detail": {},
        },
    ]

    result = guardrails.apply_relevance_gate(candidates=candidates, query_intent=_intent(), min_remaining=5)

    assert [item["title"] for item in result.candidates] == ["실제 오디오북"]
    assert "listening_format_source_required" in result.applied_rules


def test_listening_mode_does_not_treat_title_listening_as_audio_format():
    guardrails = RecommendationGuardrails()
    candidates = [
        {
            "title": "TOEIC SMART YELLOW BOOK LISTENING - TEXT BOOK",
            "score": 0.99,
            "description": "영어 듣기 교재",
            "score_detail": {},
        },
        {
            "title": "오디오 메타데이터가 있는 책",
            "score": 0.40,
            "is_audio_book": True,
            "score_detail": {},
        },
    ]

    result = guardrails.apply_relevance_gate(candidates=candidates, query_intent=_intent(), min_remaining=5)

    assert [item["title"] for item in result.candidates] == ["오디오 메타데이터가 있는 책"]


def test_self_listening_mode_filters_child_audience_when_non_child_candidate_exists():
    guardrails = RecommendationGuardrails()
    candidates = [
        {
            "title": "유아용 오디오북",
            "score": 0.99,
            "is_audio_book": True,
            "audience_profile": {"target_age_group": "CHILD", "education_stage": "PRESCHOOL", "confidence": 0.9},
            "score_detail": {},
        },
        {
            "title": "일반 독자 오디오북",
            "score": 0.50,
            "is_audio_book": True,
            "audience_profile": {"target_age_group": "GENERAL", "education_stage": "GENERAL", "confidence": 0.9},
            "score_detail": {},
        },
    ]

    result = guardrails.apply_relevance_gate(candidates=candidates, query_intent=_intent(), min_remaining=5)

    assert [item["title"] for item in result.candidates] == ["일반 독자 오디오북"]
    assert "self_listening_audience_guardrail" in result.applied_rules


def test_listening_mode_accepts_source_catalog_title_marker_as_format_evidence():
    guardrails = RecommendationGuardrails()
    candidates = [
        {
            "title": "일반 종이책",
            "score": 0.99,
            "description": "쉬운 이야기",
            "score_detail": {},
        },
        {
            "title": "[오디오북] 오늘은 좋은 날이 될 거야",
            "score": 0.50,
            "score_detail": {},
        },
    ]

    result = guardrails.apply_relevance_gate(candidates=candidates, query_intent=_intent(), min_remaining=5)

    assert [item["title"] for item in result.candidates] == ["[오디오북] 오늘은 좋은 날이 될 거야"]
    evidence = result.candidates[0]["score_detail"].get("listening_format_evidence")
    assert evidence["matched"] is True
    assert "source_title_marker" in evidence["sources"]

from app.services.recommendation.recommendation_prompt_builder import RecommendationPromptBuilder


def test_listening_mode_format_reason_is_grounded_in_source_format():
    builder = RecommendationPromptBuilder()
    book = {
        "title": "[오디오북] 오늘도 좋은 날이 될 거야",
        "author": "슬라미 오디오 공편",
        "source_format": "AUDIOBOOK",
        "source_format_evidence": {
            "matched": True,
            "normalized_format": "AUDIOBOOK",
            "fields": ["title"],
            "sources": ["source_title_marker"],
        },
        "score_detail": {"reading_mode": ReadingModePolicy.MODE_LISTENING_FRIENDLY},
        "book_intro": "긍정적인 메시지를 전하는 짧은 글을 모은 도서",
    }

    reason = builder._make_fallback_recommendation_reason(book=book, personalization_mode="DISABLED")

    assert "오디오북" in reason
    assert "원천 데이터" in reason
    assert "운전 중에 편안한 마음" not in reason
