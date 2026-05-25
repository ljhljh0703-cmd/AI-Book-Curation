from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class LightFmArtifactSummaryResponse(BaseModel):
    available: bool = False
    artifact_version: Optional[str] = Field(default=None, alias="artifact_version")
    artifact_dir: Optional[str] = Field(default=None, alias="artifact_dir")
    user_count: Optional[int] = Field(default=None, alias="user_count")
    item_count: Optional[int] = Field(default=None, alias="item_count")
    positive_event_count: Optional[int] = Field(default=None, alias="positive_event_count")
    trained_at: Optional[str] = Field(default=None, alias="trained_at")
    error_message: Optional[str] = Field(default=None, alias="error_message")


class LightFmTrainingRequest(BaseModel):
    job_id: str = Field(alias="job_id")
    dataset_manifest_path: str = Field(alias="dataset_manifest_path")
    event_paths: List[str] = Field(default_factory=list, alias="event_paths")
    work_dir: str = Field(alias="work_dir")
    versions_dir: str = Field(alias="versions_dir")
    current_dir: str = Field(alias="current_dir")
    training_mode: str = Field(default="HYBRID_LITE", alias="training_mode")
    num_threads: int = Field(default=1, alias="num_threads")
    epochs: int = 10
    no_components: int = Field(default=32, alias="no_components")
    max_sampled: int = Field(default=10, alias="max_sampled")
    learning_rate: float = Field(default=0.03, alias="learning_rate")
    loss: str = "warp"
    timeout_seconds: int = Field(default=7200, alias="timeout_seconds")
    retention_count: int = Field(default=3, alias="retention_count")
    synthetic_max_ratio: float = Field(default=0.5, alias="synthetic_max_ratio")
    real_weight_multiplier: float = Field(default=2.0, alias="real_weight_multiplier")
    max_rows_per_source: int = Field(default=50000, alias="max_rows_per_source")


class LightFmTrainingResponse(BaseModel):
    status: str
    artifact_version: Optional[str] = Field(default=None, alias="artifact_version")
    artifact_dir: Optional[str] = Field(default=None, alias="artifact_dir")
    exit_code: Optional[int] = Field(default=None, alias="exit_code")
    error_message: Optional[str] = Field(default=None, alias="error_message")
    metrics: Dict[str, Any] = Field(default_factory=dict)
