from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List


def _bootstrap_imports(artifact_dir: str) -> None:
    ai_server_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(ai_server_root))
    os.environ.setdefault("CLOVA_API_KEY", "local-lightfm-validation-placeholder")
    os.environ.setdefault("LIGHTFM_ENABLED", "true")
    os.environ["LIGHTFM_ARTIFACT_DIR"] = artifact_dir
    os.environ.setdefault("LIGHTFM_TOP_N", "20")
    os.environ.setdefault("LIGHTFM_CANDIDATE_LIMIT", "50")


def _load_mappings(artifact_dir: Path) -> Dict[str, Any]:
    mappings_path = artifact_dir / "mappings.json"
    if not mappings_path.exists():
        return {}
    with mappings_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _candidate(isbn: str, index: int) -> Dict[str, Any]:
    return {
        "isbn": isbn,
        "title": f"validation candidate {index}",
        "qdrantScore": float(100 - index),
        "ruleScore": float(100 - index),
        "preScore": float(100 - index),
    }


def _build_candidates(item_ids: List[str], total: int = 50) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for index in range(total):
        if index < len(item_ids):
            isbn = str(item_ids[index])
        else:
            isbn = f"unknown-validation-item-{index}"
        candidates.append(_candidate(isbn, index))
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate ai-server LightFM runtime loading and fallback behavior.")
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--expect-missing-artifact", action="store_true")
    args = parser.parse_args()

    _bootstrap_imports(args.artifact_dir)

    from app.services.ranking.lightfm_ranker import LightFmRanker

    artifact_dir = Path(args.artifact_dir).expanduser().resolve()
    mappings = _load_mappings(artifact_dir)
    user_ids = list(dict(mappings.get("user_id_to_index") or {}).keys())
    item_ids = list(dict(mappings.get("item_id_to_index") or {}).keys())[:45]
    candidates = _build_candidates(item_ids=item_ids, total=50)

    ranker = LightFmRanker(artifact_dir=str(artifact_dir))

    missing_or_unknown_result = ranker.rerank(
        user_id="unknown-validation-user",
        candidates=candidates,
        requested_model="LIGHTFM",
        limit=20,
        request_id="validate-unknown-user",
    )
    print("unknown_user_result=", missing_or_unknown_result.as_metadata())
    if not missing_or_unknown_result.fallback:
        raise SystemExit("unknown user must fallback")

    if args.expect_missing_artifact:
        if missing_or_unknown_result.fallback_reason and "ARTIFACT_LOAD_FAILED" in missing_or_unknown_result.fallback_reason:
            print("missing_artifact_fallback=ok")
            return 0
        raise SystemExit(f"expected missing artifact fallback, got {missing_or_unknown_result.fallback_reason}")

    if not user_ids:
        raise SystemExit("artifact mappings.json has no user_id_to_index entries")
    if not item_ids:
        raise SystemExit("artifact mappings.json has no item_id_to_index entries")

    applied_result = ranker.rerank(
        user_id=str(user_ids[0]),
        candidates=candidates,
        requested_model="LIGHTFM",
        limit=20,
        request_id="validate-known-user",
    )
    print("known_user_result=", applied_result.as_metadata())
    if applied_result.fallback:
        raise SystemExit(f"known user should apply LightFM, fallback_reason={applied_result.fallback_reason}")
    if len(applied_result.candidates) != 20:
        raise SystemExit(f"expected 20 candidates, got {len(applied_result.candidates)}")
    if not any(candidate.get("lightfmScore") is not None for candidate in applied_result.candidates):
        raise SystemExit("expected at least one scored candidate")

    sufficient_known_candidates = _build_candidates(item_ids=item_ids[:25], total=50)
    sufficient_known_result = ranker.rerank(
        user_id=str(user_ids[0]),
        candidates=sufficient_known_candidates,
        requested_model="LIGHTFM",
        limit=20,
        request_id="validate-sufficient-known-items",
    )
    print("sufficient_known_item_result=", sufficient_known_result.as_metadata())
    if sufficient_known_result.fallback:
        raise SystemExit(
            f"known items >= topN should apply LightFM, reason={sufficient_known_result.fallback_reason}"
        )
    if len(sufficient_known_result.candidates) != 20:
        raise SystemExit(f"expected 20 scored candidates, got {len(sufficient_known_result.candidates)}")
    if any(str(candidate.get("isbn", "")).startswith("unknown-validation-item-") for candidate in sufficient_known_result.candidates):
        raise SystemExit("unknown item candidates must be excluded from LightFM results")

    insufficient_known_candidates = _build_candidates(item_ids=item_ids[:10], total=50)
    insufficient_result = ranker.rerank(
        user_id=str(user_ids[0]),
        candidates=insufficient_known_candidates,
        requested_model="LIGHTFM",
        limit=20,
        request_id="validate-insufficient-known-items",
    )
    print("insufficient_known_item_result=", insufficient_result.as_metadata())
    if not insufficient_result.fallback or insufficient_result.fallback_reason != "INSUFFICIENT_KNOWN_ITEMS":
        raise SystemExit(
            "known items below topN must fallback with INSUFFICIENT_KNOWN_ITEMS, "
            f"got fallback={insufficient_result.fallback}, reason={insufficient_result.fallback_reason}"
        )
    if len(insufficient_result.candidates) != 20:
        raise SystemExit(f"expected fallback to return 20 rule-based candidates, got {len(insufficient_result.candidates)}")

    all_unknown_result = ranker.rerank(
        user_id=str(user_ids[0]),
        candidates=_build_candidates(item_ids=[], total=50),
        requested_model="LIGHTFM",
        limit=20,
        request_id="validate-all-unknown-items",
    )
    print("all_unknown_item_result=", all_unknown_result.as_metadata())
    if not all_unknown_result.fallback or all_unknown_result.fallback_reason != "NO_KNOWN_ITEMS":
        raise SystemExit(
            "all unknown items must fallback with NO_KNOWN_ITEMS, "
            f"got fallback={all_unknown_result.fallback}, reason={all_unknown_result.fallback_reason}"
        )

    print("lightfm_runtime_validation=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
