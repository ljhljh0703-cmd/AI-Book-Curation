import os
os.environ.setdefault("CLOVA_API_KEY", "test-key")

from app.services.intent.chat_intent_classifier import ChatIntent
from app.services.intent.query_intent_parser import QueryIntentParser
from app.services.reranking.hcx_reranker_provider import HcxRerankerProvider
from app.services.reranking.single_result_selector import prioritize_single_result_by_reranker


def _resolve_final_limit(query_intent, configured_limit: int = 5) -> int:
    requested_count = getattr(query_intent, "requested_recommendation_count", None)
    try:
        requested_count_int = int(requested_count)
    except (TypeError, ValueError):
        return configured_limit
    if requested_count_int <= 0:
        return configured_limit
    return max(1, min(configured_limit, requested_count_int))


def test_query_intent_uses_llm_requested_recommendation_count() -> None:
    intent = ChatIntent(
        name="recommend_book",
        query_type="recommend",
        requires_history=False,
        source="test",
        recommendation_search_query="오디오북",
        recommendation_count=1,
    )

    query_intent = QueryIntentParser().parse("오디오북 한 권만 추천해줘", intent)

    assert query_intent.requested_recommendation_count == 1
    assert _resolve_final_limit(query_intent) == 1


def test_single_result_selection_prioritizes_reranker_score() -> None:
    candidates = [
        {"title": "rule score가 높은 책", "finalScore": 0.99, "rerankerScore": 0.1, "score_detail": {}},
        {"title": "reranker 1등 책", "finalScore": 0.50, "rerankerScore": 0.9, "score_detail": {}},
    ]

    result = prioritize_single_result_by_reranker(candidates)

    assert result[0]["title"] == "reranker 1등 책"
    assert result[0]["finalScore"] == 0.9
    assert result[0]["score_detail"]["single_result_selection_policy"] == "RERANKER_SCORE_FIRST"


def test_hcx_reranker_extracts_doc_citation_order() -> None:
    text = "추천 후보는 <doc3>이 가장 적합하고, 다음으로 <doc1>을 참고할 수 있습니다. <doc3> 반복."

    assert HcxRerankerProvider._extract_cited_positions(text, document_count=5) == [2, 0]
