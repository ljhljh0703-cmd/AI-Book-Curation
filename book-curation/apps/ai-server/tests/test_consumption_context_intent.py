from app.services.intent.chat_intent_classifier import ChatIntent
from app.services.intent.query_intent_parser import QueryIntentParser
from app.services.intent.query_variant_builder import QueryVariantBuilder
from app.services.intent.reading_mode_policy import ReadingModePolicy


def _intent(
    *,
    raw_query: str,
    topic_query: str | None = None,
    consumption_context: str | None = None,
    consumption_context_type: str | None = None,
    normalized_query: str | None = None,
    reranker_query: str | None = None,
    reading_mode: str = ReadingModePolicy.MODE_UNKNOWN,
) -> ChatIntent:
    positive_terms = ["청취 친화", "쉬운 문장 흐름", "짧은 에피소드", "시각 자료 의존도 낮음"] if consumption_context else []
    negative_terms = ["도표 중심", "시각 자료 의존"] if consumption_context else []
    return ChatIntent(
        name="recommend_book",
        query_type="recommend",
        requires_history=False,
        source="test",
        recommendation_personalization_mode="QUERY_FIRST",
        recommendation_topic_query=topic_query,
        recommendation_search_query=normalized_query,
        recommendation_normalized_query=normalized_query,
        recommendation_reranker_query=reranker_query,
        recommendation_consumption_context=consumption_context,
        recommendation_consumption_context_type=consumption_context_type,
        recommendation_visual_attention_limited=True if consumption_context else None,
        recommendation_hands_free_preferred=True if consumption_context else None,
        recommendation_requires_visual_reference=False if consumption_context else None,
        recommendation_reading_mode=reading_mode,
        recommendation_consumption_positive_terms=positive_terms,
        recommendation_consumption_negative_terms=negative_terms,
        recommendation_consumption_weight=0.2 if consumption_context else 0.0,
    )


def _parse(raw_query: str, **kwargs):
    return QueryIntentParser().parse(raw_query, _intent(raw_query=raw_query, **kwargs))


def _assert_consumption_query(raw_query: str, activity_term: str) -> None:
    query_intent = _parse(
        raw_query,
        consumption_context=activity_term,
        consumption_context_type="PARALLEL_ACTIVITY",
        normalized_query=raw_query,
        reranker_query=raw_query,
        reading_mode=ReadingModePolicy.MODE_LISTENING_FRIENDLY,
    )

    assert query_intent.topic_query is None
    assert query_intent.consumption_context == activity_term
    assert query_intent.reading_mode == ReadingModePolicy.MODE_LISTENING_FRIENDLY
    assert activity_term not in (query_intent.retrieval_query or "")
    assert activity_term not in (query_intent.reranker_query or "")
    assert "청취" in (query_intent.retrieval_query or "")
    assert query_intent.context_policy_applied is True

    variants = QueryVariantBuilder().build(query=raw_query, query_intent=query_intent).variants
    assert raw_query not in variants
    assert all(activity_term not in variant for variant in variants)


def test_parallel_activity_query_does_not_reuse_activity_as_topic() -> None:
    _assert_consumption_query("운전하면서 읽을 수 있는 책 추천해줘", "운전")


def test_topic_query_keeps_topic_for_about_query() -> None:
    query_intent = _parse(
        "운전에 대한 책 추천해줘",
        topic_query="운전",
        normalized_query="운전",
        reranker_query="운전",
        reading_mode=ReadingModePolicy.MODE_ANY,
    )

    assert query_intent.topic_query == "운전"
    assert query_intent.consumption_context is None
    assert query_intent.retrieval_query == "운전"
    assert query_intent.reranker_query == "운전"
    assert "운전에 대한 책 추천해줘" in QueryVariantBuilder().build(
        query="운전에 대한 책 추천해줘",
        query_intent=query_intent,
    ).variants


def test_walking_query_is_consumption_context() -> None:
    _assert_consumption_query("산책하면서 읽기 좋은 책 추천해줘", "산책")


def test_commute_listening_query_is_consumption_context() -> None:
    _assert_consumption_query("출퇴근하면서 들을 책 추천해줘", "출퇴근")


def test_housework_listening_query_is_consumption_context() -> None:
    _assert_consumption_query("집안일하면서 들을 책 추천해줘", "집안일")
