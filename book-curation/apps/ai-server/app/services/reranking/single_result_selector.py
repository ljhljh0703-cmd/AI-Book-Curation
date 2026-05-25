from __future__ import annotations

from typing import Any, Dict, List


def prioritize_single_result_by_reranker(
    candidates: List[Dict[str, Any]],
    *,
    request_id: str | None = None,
) -> List[Dict[str, Any]]:
    """사용자가 1권만 요청했을 때 외부 reranker 1순위를 최종 후보로 고정합니다."""
    rows = [dict(candidate) for candidate in (candidates or [])]
    if not rows:
        return []

    def score_of(candidate: Dict[str, Any]) -> float:
        try:
            return float(candidate.get("rerankerScore"))
        except (TypeError, ValueError):
            return -1.0

    if max(score_of(candidate) for candidate in rows) < 0:
        return rows

    rows.sort(key=score_of, reverse=True)
    for index, item in enumerate(rows):
        reranker_score = score_of(item)
        if reranker_score >= 0:
            item["finalScore"] = reranker_score
            item["score_detail"] = {
                **dict(item.get("score_detail") or {}),
                "single_result_selection_policy": "RERANKER_SCORE_FIRST",
                "single_result_reranker_rank": index + 1,
                "single_result_reranker_score": round(reranker_score, 6),
            }
    print(
        f"[SINGLE RESULT SELECTION][{request_id or '-'}] "
        f"policy=RERANKER_SCORE_FIRST candidate_count={len(rows)} "
        f"top_title={rows[0].get('title')!r} top_reranker_score={score_of(rows[0]):.6f}"
    )
    return rows
