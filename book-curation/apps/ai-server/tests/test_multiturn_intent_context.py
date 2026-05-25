import os

os.environ.setdefault("CLOVA_API_KEY", "test-key")

from app.services.context.multiturn_intent_context import MultiturnIntentContextResolver
from app.services.intent.query_intent_parser import QueryIntent
from app.services.intent.reading_mode_policy import ReadingModePolicy


def test_inherits_listening_context_from_previous_response_metadata():
    resolver = MultiturnIntentContextResolver()
    current = QueryIntent(
        raw_query="내가 재미있어할 딱 한권만 추천해줘",
        retrieval_query="재미있게 읽을 책",
        general_recommendation=True,
        requested_recommendation_count=1,
    )
    history = [
        {
            "role": "assistant",
            "content": "추천 결과입니다.",
            "detected_reading_mode": ReadingModePolicy.MODE_LISTENING_FRIENDLY,
            "detected_consumption_context": "운전 중",
            "query_target_reader": "SELF",
            "query_requested_audience_group": "GENERAL",
        }
    ]

    inheritance = resolver.resolve(history=history, current_intent=current)
    inherited = resolver.apply(current_intent=current, inheritance=inheritance)

    assert inheritance.applied is True
    assert inherited.multiturn_context_inherited is True
    assert inherited.reading_mode == ReadingModePolicy.MODE_LISTENING_FRIENDLY
    assert inherited.consumption_context == "운전 중"
    assert inherited.target_reader == "SELF"
    assert inherited.requested_audience_group == "GENERAL"


def test_infers_listening_context_from_previous_audiobook_cards_when_metadata_missing():
    resolver = MultiturnIntentContextResolver()
    current = QueryIntent(
        raw_query="내가 재미있어할 딱 한권만 추천해줘",
        retrieval_query="재미있는 책",
        general_recommendation=True,
        requested_recommendation_count=1,
    )
    history = [
        {
            "role": "assistant",
            "content": "추천 결과입니다.",
            "candidates": [
                {"rank": 1, "title": "[오디오북] 오늘도 좋은 날이 될 거야"},
                {"rank": 2, "title": "[오디오북] 짧은 이야기 모음"},
            ],
        }
    ]

    inheritance = resolver.resolve(history=history, current_intent=current)
    inherited = resolver.apply(current_intent=current, inheritance=inheritance)

    assert inheritance.applied is True
    assert inheritance.source == "PREVIOUS_RECOMMENDATION_FORMAT_EVIDENCE"
    assert inherited.reading_mode == ReadingModePolicy.MODE_LISTENING_FRIENDLY
    assert inherited.requested_audience_group == "GENERAL"


def test_does_not_inherit_when_current_query_has_explicit_audience():
    resolver = MultiturnIntentContextResolver()
    current = QueryIntent(
        raw_query="아이에게 들려줄 책 한 권만 추천해줘",
        retrieval_query="아이에게 들려줄 책",
        general_recommendation=True,
        requested_recommendation_count=1,
        requested_audience_group="CHILD",
        target_reader="OTHER",
    )
    history = [
        {
            "role": "assistant",
            "content": "추천 결과입니다.",
            "detected_reading_mode": ReadingModePolicy.MODE_LISTENING_FRIENDLY,
            "detected_consumption_context": "운전 중",
        }
    ]

    inheritance = resolver.resolve(history=history, current_intent=current)

    assert inheritance.applied is False
    assert inheritance.reason == "current_query_has_explicit_constraints"
