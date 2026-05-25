#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate LightFM artifact directory.")
    parser.add_argument("--artifact-dir", default="artifacts/lightfm/latest")
    parser.add_argument("--user-id", default="")
    parser.add_argument("--item-id", action="append", default=[])
    args = parser.parse_args()

    artifact_dir = Path(args.artifact_dir).expanduser().resolve()
    weights_path = artifact_dir / "weights.joblib"
    model_path = artifact_dir / "model.joblib"
    mappings_path = artifact_dir / "mappings.json"
    metadata_path = artifact_dir / "metadata.json"

    if not weights_path.exists() and not model_path.exists():
        raise SystemExit(f"Missing required artifact file: neither weights.joblib nor model.joblib exists under: {artifact_dir}")
    if not mappings_path.exists():
        raise SystemExit(f"Missing required artifact file: {mappings_path}")

    try:
        import joblib
        import numpy as np
    except ImportError as exc:
        raise SystemExit(f"Validation dependencies are missing: {exc}") from exc

    is_pure_weights = False
    if weights_path.exists():
        weights = joblib.load(weights_path)
        user_embeddings = weights["user_embeddings"]
        item_embeddings = weights["item_embeddings"]
        user_biases = weights["user_biases"]
        item_biases = weights["item_biases"]
        is_pure_weights = True
    else:
        model = joblib.load(model_path)
        user_embeddings = model.user_embeddings
        item_embeddings = model.item_embeddings
        user_biases = model.user_biases
        item_biases = model.item_biases

    with mappings_path.open("r", encoding="utf-8") as file:
        mappings = json.load(file)
    metadata = {}
    if metadata_path.exists():
        with metadata_path.open("r", encoding="utf-8") as file:
            metadata = json.load(file)

    user_map = {str(key): int(value) for key, value in dict(mappings.get("user_id_to_index") or {}).items()}
    item_map = {str(key): int(value) for key, value in dict(mappings.get("item_id_to_index") or {}).items()}
    user_keys = list(user_map.keys())
    persona_count = sum(1 for key in user_keys if key.startswith("persona:"))
    real_user_count = sum(1 for key in user_keys if key.startswith("real_user:"))
    other_user_count = max(0, len(user_keys) - persona_count - real_user_count)
    print(
        "[LIGHTFM ARTIFACT] "
        f"path={artifact_dir} users={len(user_map)} items={len(item_map)} "
        f"real_users={real_user_count} persona_users={persona_count} other_users={other_user_count} "
        f"version={metadata.get('artifact_version')}"
    )
    print("sample_user_keys=", user_keys[:10])

    if not args.user_id or not args.item_id:
        return
    lookup_candidates = _user_key_candidates(args.user_id)
    user_index = None
    matched_user_key = None
    for lookup_key in lookup_candidates:
        if lookup_key in user_map:
            matched_user_key = lookup_key
            user_index = user_map[lookup_key]
            break
    if user_index is None:
        raise SystemExit(
            f"Unknown user_id in artifact: {args.user_id}. "
            f"lookup_candidates={lookup_candidates} real_users={real_user_count} persona_users={persona_count}"
        )
    known_item_ids = [item_id for item_id in args.item_id if str(item_id) in item_map]
    if not known_item_ids:
        raise SystemExit("None of the given item ids exist in the artifact mapping")

    item_indices = [item_map[str(item_id)] for item_id in known_item_ids]
    if is_pure_weights:
        user_emb = user_embeddings[user_index]
        item_embs = item_embeddings[item_indices]
        user_bias = user_biases[user_index]
        item_biases_subset = item_biases[item_indices]
        scores = (item_embs * user_emb).sum(axis=1) + user_bias + item_biases_subset
    else:
        user_indices = np.full(len(known_item_ids), user_index, dtype=np.int32)
        item_indices_arr = np.asarray(item_indices, dtype=np.int32)
        scores = model.predict(user_ids=user_indices, item_ids=item_indices_arr)

    for item_id, score in zip(known_item_ids, scores):
        print(f"user_id={args.user_id} matched_user_key={matched_user_key} item_id={item_id} score={float(score):.6f}")


def _user_key_candidates(user_id: str) -> list[str]:
    normalized = str(user_id or "").strip()
    if not normalized:
        return []
    candidates = [normalized]
    if not normalized.startswith("real_user:"):
        candidates.append(f"real_user:{normalized}")
    if normalized.startswith("real_user:"):
        candidates.append(normalized.removeprefix("real_user:"))
    result: list[str] = []
    seen = set()
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen.add(candidate)
            result.append(candidate)
    return result


if __name__ == "__main__":
    main()
