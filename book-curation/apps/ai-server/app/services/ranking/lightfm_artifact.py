from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List


@dataclass(frozen=True)
class LightFmArtifact:
    """LightFM serving에 필요한 model, mapping, feature matrix를 메모리에 올린 객체입니다."""

    model: Any
    user_id_to_index: Dict[str, int]
    item_id_to_index: Dict[str, int]
    metadata: Dict[str, Any]
    artifact_path: Path
    user_features: Any | None = None
    item_features: Any | None = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    feature_sources: Dict[str, Any] = field(default_factory=dict)
    loaded_files: List[str] = field(default_factory=list)

    @property
    def version(self) -> str | None:
        value = self.metadata.get("artifact_version") or self.metadata.get("version")
        return str(value) if value is not None else None

    @property
    def feature_mode(self) -> str:
        value = self.metadata.get("feature_mode") or self.metrics.get("feature_mode") or "identity"
        return str(value or "identity").strip().lower()

    @property
    def uses_feature_matrices(self) -> bool:
        return self.user_features is not None or self.item_features is not None

    @classmethod
    def load(cls, artifact_path: str | Path) -> "LightFmArtifact":
        path = Path(artifact_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"LightFM artifact path does not exist: {path}")
        if not path.is_dir():
            raise NotADirectoryError(f"LightFM artifact path must be a directory: {path}")

        try:
            import joblib
        except ImportError as exc:
            raise RuntimeError("joblib is required to load LightFM artifacts") from exc

        model_path = path / "model.joblib"
        mappings_path = path / "mappings.json"
        metadata_path = path / "metadata.json"
        metrics_path = path / "metrics.json"
        feature_sources_path = path / "feature_sources.json"
        user_features_path = path / "user_features.npz"
        item_features_path = path / "item_features.npz"

        required_files = [model_path, mappings_path]
        missing_required = [str(file_path) for file_path in required_files if not file_path.exists()]
        if missing_required:
            raise FileNotFoundError(f"LightFM artifact required file missing: {', '.join(missing_required)}")

        model = joblib.load(model_path)
        mappings = cls._read_json(mappings_path)
        metadata = cls._read_json(metadata_path) if metadata_path.exists() else {}
        metrics = cls._read_json(metrics_path) if metrics_path.exists() else {}
        feature_sources = cls._read_json(feature_sources_path) if feature_sources_path.exists() else {}

        user_id_to_index = {
            str(user_id): int(index)
            for user_id, index in dict(mappings.get("user_id_to_index") or {}).items()
        }
        item_id_to_index = {
            str(item_id): int(index)
            for item_id, index in dict(mappings.get("item_id_to_index") or {}).items()
        }
        if not user_id_to_index:
            raise ValueError("LightFM artifact has no user_id_to_index mapping")
        if not item_id_to_index:
            raise ValueError("LightFM artifact has no item_id_to_index mapping")

        feature_mode = str(metadata.get("feature_mode") or "identity").strip().lower()
        needs_feature_matrices = cls._is_hybrid_feature_mode(feature_mode)
        has_feature_matrices = user_features_path.exists() or item_features_path.exists()
        user_features = None
        item_features = None

        if needs_feature_matrices or has_feature_matrices:
            if not user_features_path.exists() or not item_features_path.exists():
                raise FileNotFoundError(
                    "LightFM hybrid artifact requires both user_features.npz and item_features.npz"
                )
            try:
                from scipy.sparse import load_npz
            except ImportError as exc:
                raise RuntimeError("scipy is required to load LightFM feature matrices") from exc
            user_features = load_npz(user_features_path)
            item_features = load_npz(item_features_path)
            cls._validate_feature_matrix_shapes(
                user_features=user_features,
                item_features=item_features,
                user_id_to_index=user_id_to_index,
                item_id_to_index=item_id_to_index,
            )

        loaded_files = [
            file_path.name
            for file_path in [
                model_path,
                mappings_path,
                metadata_path,
                metrics_path,
                feature_sources_path,
                user_features_path,
                item_features_path,
            ]
            if file_path.exists()
        ]

        return cls(
            model=model,
            user_id_to_index=user_id_to_index,
            item_id_to_index=item_id_to_index,
            metadata=metadata,
            artifact_path=path,
            user_features=user_features,
            item_features=item_features,
            metrics=metrics,
            feature_sources=feature_sources,
            loaded_files=loaded_files,
        )

    @staticmethod
    def _read_json(path: Path) -> Dict[str, Any]:
        with path.open("r", encoding="utf-8") as file:
            value = json.load(file)
        if not isinstance(value, dict):
            raise ValueError(f"LightFM artifact json must be an object: {path}")
        return value

    @staticmethod
    def _is_hybrid_feature_mode(feature_mode: str) -> bool:
        normalized = str(feature_mode or "").strip().lower().replace("_", "-")
        return normalized in {"hybrid", "hybrid-lite", "shared-pool-hybrid", "shared-pool-hybrid-lite"}

    @staticmethod
    def _validate_feature_matrix_shapes(
        *,
        user_features: Any,
        item_features: Any,
        user_id_to_index: Dict[str, int],
        item_id_to_index: Dict[str, int],
    ) -> None:
        user_row_count = int(getattr(user_features, "shape", (0, 0))[0])
        item_row_count = int(getattr(item_features, "shape", (0, 0))[0])
        if user_row_count < len(user_id_to_index):
            raise ValueError(
                f"user_features row count is smaller than user mapping size: {user_row_count} < {len(user_id_to_index)}"
            )
        if item_row_count < len(item_id_to_index):
            raise ValueError(
                f"item_features row count is smaller than item mapping size: {item_row_count} < {len(item_id_to_index)}"
            )
