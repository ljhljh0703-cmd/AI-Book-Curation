from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.schemas.lightfm_training import (
    LightFmArtifactSummaryResponse,
    LightFmTrainingRequest,
    LightFmTrainingResponse,
)
from app.services.ranking.lightfm_artifact import LightFmArtifact


class LightFmTrainingService:
    """LightFM 운영 artifact 학습/promote를 담당합니다.

    backend가 DB export/job history/schedule을 관리하고, ai-server는 CPU 학습 subprocess를 실행합니다.
    실패 또는 timeout 시 current artifact는 교체하지 않습니다.
    """

    def artifact_summary(self) -> LightFmArtifactSummaryResponse:
        artifact_dir = Path(settings.LIGHTFM_ARTIFACT_DIR or settings.LIGHTFM_ARTIFACT_PATH or settings.LIGHTFM_ARTIFACT_ROOT)
        artifact_dir = artifact_dir.expanduser().resolve()
        metadata_path = artifact_dir / "metadata.json"
        mappings_path = artifact_dir / "mappings.json"
        if not artifact_dir.exists():
            return LightFmArtifactSummaryResponse(
                available=False,
                artifact_dir=str(artifact_dir),
                error_message="LightFM current artifact directory does not exist.",
            )
        if not metadata_path.exists() or not mappings_path.exists():
            return LightFmArtifactSummaryResponse(
                available=False,
                artifact_dir=str(artifact_dir),
                error_message="LightFM current artifact metadata/mappings file is missing.",
            )
        try:
            metadata = self._read_json(metadata_path)
            mappings = self._read_json(mappings_path)
            return LightFmArtifactSummaryResponse(
                available=True,
                artifact_version=self._optional_str(metadata.get("artifact_version") or metadata.get("version")),
                artifact_dir=str(artifact_dir),
                user_count=self._optional_int(metadata.get("user_count") or len(dict(mappings.get("user_id_to_index") or {}))),
                item_count=self._optional_int(metadata.get("item_count") or len(dict(mappings.get("item_id_to_index") or {}))),
                positive_event_count=self._optional_int(metadata.get("positive_event_count") or metadata.get("event_count")),
                trained_at=self._optional_str(metadata.get("trained_at")),
            )
        except Exception as exc:
            return LightFmArtifactSummaryResponse(
                available=False,
                artifact_dir=str(artifact_dir),
                error_message=f"LightFM artifact summary failed: {exc}",
            )

    def train_and_promote(self, request: LightFmTrainingRequest) -> LightFmTrainingResponse:
        work_dir = Path(request.work_dir).expanduser().resolve()
        versions_dir = Path(request.versions_dir).expanduser().resolve()
        current_dir = Path(request.current_dir).expanduser().resolve()
        output_dir = work_dir / "artifact"
        log_dir = Path(getattr(settings, "LIGHTFM_TRAINING_LOG_DIR", work_dir / "logs")).expanduser().resolve()
        log_dir.mkdir(parents=True, exist_ok=True)
        work_dir.mkdir(parents=True, exist_ok=True)
        versions_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        train_script = self._resolve_train_script()
        command = [
            sys.executable,
            str(train_script),
            "--output-dir",
            str(output_dir),
            "--loss",
            self._loss(request.loss),
            "--components",
            str(max(1, int(request.no_components))),
            "--epochs",
            str(max(1, int(request.epochs))),
            "--learning-rate",
            str(max(0.0001, float(request.learning_rate))),
            "--num-threads",
            str(self._bounded_num_threads(request.num_threads)),
            "--max-sampled",
            str(max(1, int(request.max_sampled))),
            "--training-mode",
            str(request.training_mode or "HYBRID_LITE"),
            "--synthetic-max-ratio",
            str(max(0.0, min(float(request.synthetic_max_ratio), 1.0))),
            "--real-weight-multiplier",
            str(max(0.0, float(request.real_weight_multiplier))),
            "--max-rows-per-source",
            str(max(0, int(request.max_rows_per_source))),
        ]
        for event_path in request.event_paths or []:
            command.extend(["--events-path", str(Path(event_path).expanduser().resolve())])

        if not request.event_paths:
            return LightFmTrainingResponse(
                status="FAILED",
                exit_code=2,
                error_message="No LightFM event paths were provided.",
                metrics={"job_id": request.job_id, "work_dir": str(work_dir)},
            )

        env = os.environ.copy()
        env.update(
            {
                "LIGHTFM_TRAINING_MODE": str(request.training_mode or "HYBRID_LITE"),
                "LIGHTFM_TRAINING_NUM_THREADS": str(self._bounded_num_threads(request.num_threads)),
                "LIGHTFM_TRAINING_EPOCHS": str(max(1, int(request.epochs))),
                "LIGHTFM_TRAINING_NO_COMPONENTS": str(max(1, int(request.no_components))),
                "LIGHTFM_TRAINING_MAX_SAMPLED": str(max(1, int(request.max_sampled))),
                "LIGHTFM_TRAINING_LEARNING_RATE": str(max(0.0001, float(request.learning_rate))),
                "LIGHTFM_TRAINING_LOSS": self._loss(request.loss),
            }
        )

        stdout_path = log_dir / f"{request.job_id}.stdout.log"
        stderr_path = log_dir / f"{request.job_id}.stderr.log"
        try:
            with stdout_path.open("w", encoding="utf-8") as stdout_file, stderr_path.open("w", encoding="utf-8") as stderr_file:
                completed = subprocess.run(
                    command,
                    cwd=str(train_script.parent.parent),
                    env=env,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    text=True,
                    timeout=max(1, int(request.timeout_seconds)),
                    check=False,
                )
        except subprocess.TimeoutExpired:
            return LightFmTrainingResponse(
                status="TIMEOUT",
                exit_code=-1,
                error_message=f"LightFM training timed out after {request.timeout_seconds} seconds.",
                metrics=self._base_metrics(request, stdout_path, stderr_path, command),
            )
        except Exception as exc:
            return LightFmTrainingResponse(
                status="FAILED",
                exit_code=-1,
                error_message=f"LightFM training subprocess failed: {exc}",
                metrics=self._base_metrics(request, stdout_path, stderr_path, command),
            )

        if completed.returncode != 0:
            return LightFmTrainingResponse(
                status="FAILED",
                exit_code=int(completed.returncode),
                error_message=self._tail_text(stderr_path) or self._tail_text(stdout_path) or "LightFM training failed.",
                metrics=self._base_metrics(request, stdout_path, stderr_path, command),
            )

        try:
            artifact = LightFmArtifact.load(output_dir)
            artifact_version = self._version_from_metadata(output_dir) or self._new_version()
            version_dir = self._unique_version_dir(versions_dir, artifact_version, request.job_id)
            self._write_metadata_value(output_dir / "metadata.json", "artifact_version", version_dir.name)
            shutil.copytree(output_dir, version_dir)
            LightFmArtifact.load(version_dir)
            self._promote_current(version_dir=version_dir, current_dir=current_dir)
            self._retain_versions(versions_dir=versions_dir, retention_count=max(1, int(request.retention_count)))
            metadata = self._read_json(version_dir / "metadata.json")
            metrics = {
                **self._base_metrics(request, stdout_path, stderr_path, command),
                **metadata,
                "artifact_dir": str(version_dir),
                "loaded_files": artifact.loaded_files,
            }
            return LightFmTrainingResponse(
                status="SUCCEEDED",
                artifact_version=version_dir.name,
                artifact_dir=str(version_dir),
                exit_code=0,
                metrics=metrics,
            )
        except Exception as exc:
            return LightFmTrainingResponse(
                status="FAILED",
                exit_code=0,
                error_message=f"LightFM artifact validation/promote failed: {exc}",
                metrics=self._base_metrics(request, stdout_path, stderr_path, command),
            )

    @staticmethod
    def _resolve_train_script() -> Path:
        candidate = Path(__file__).resolve().parents[3] / "script" / "train_lightfm.py"
        if candidate.exists():
            return candidate
        return Path("/app/script/train_lightfm.py")

    @staticmethod
    def _read_json(path: Path) -> Dict[str, Any]:
        with path.open("r", encoding="utf-8") as file:
            value = json.load(file)
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _write_metadata_value(path: Path, key: str, value: Any) -> None:
        metadata = LightFmTrainingService._read_json(path) if path.exists() else {}
        metadata[key] = value
        with path.open("w", encoding="utf-8") as file:
            json.dump(metadata, file, ensure_ascii=False, indent=2)

    @staticmethod
    def _promote_current(*, version_dir: Path, current_dir: Path) -> None:
        current_dir.parent.mkdir(parents=True, exist_ok=True)
        next_dir = current_dir.parent / f".current.next.{version_dir.name}"
        if next_dir.exists():
            shutil.rmtree(next_dir)
        shutil.copytree(version_dir, next_dir)

        if current_dir.is_symlink() or not current_dir.exists():
            tmp_link = current_dir.parent / f".current.link.{version_dir.name}"
            if tmp_link.exists() or tmp_link.is_symlink():
                tmp_link.unlink()
            tmp_link.symlink_to(version_dir, target_is_directory=True)
            os.replace(tmp_link, current_dir)
            shutil.rmtree(next_dir, ignore_errors=True)
            return

        backup_dir = current_dir.parent / f".current.backup.{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        current_dir.rename(backup_dir)
        try:
            next_dir.rename(current_dir)
            shutil.rmtree(backup_dir, ignore_errors=True)
        except Exception:
            if current_dir.exists():
                shutil.rmtree(current_dir, ignore_errors=True)
            backup_dir.rename(current_dir)
            raise

    @staticmethod
    def _retain_versions(*, versions_dir: Path, retention_count: int) -> None:
        if not versions_dir.exists():
            return
        version_dirs = [path for path in versions_dir.iterdir() if path.is_dir()]
        version_dirs.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        for old_dir in version_dirs[retention_count:]:
            shutil.rmtree(old_dir, ignore_errors=True)

    @staticmethod
    def _version_from_metadata(output_dir: Path) -> Optional[str]:
        metadata_path = output_dir / "metadata.json"
        if not metadata_path.exists():
            return None
        value = LightFmTrainingService._read_json(metadata_path).get("artifact_version")
        return str(value).strip() if value else None

    @staticmethod
    def _unique_version_dir(versions_dir: Path, artifact_version: str, job_id: str) -> Path:
        safe_version = "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in artifact_version)
        version_dir = versions_dir / safe_version
        if not version_dir.exists():
            return version_dir
        suffix = str(job_id or "")[:8] or datetime.now(timezone.utc).strftime("%H%M%S")
        return versions_dir / f"{safe_version}_{suffix}"

    @staticmethod
    def _new_version() -> str:
        return datetime.now(timezone.utc).strftime("lightfm_%Y%m%dT%H%M%SZ")

    @staticmethod
    def _bounded_num_threads(value: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = 1
        return max(1, min(parsed, 6))

    @staticmethod
    def _loss(value: str) -> str:
        normalized = str(value or "warp").strip().lower()
        return normalized if normalized in {"warp", "bpr", "warp-kos"} else "warp"

    @staticmethod
    def _base_metrics(
        request: LightFmTrainingRequest,
        stdout_path: Path,
        stderr_path: Path,
        command: List[str],
    ) -> Dict[str, Any]:
        return {
            "job_id": request.job_id,
            "dataset_manifest_path": request.dataset_manifest_path,
            "work_dir": request.work_dir,
            "stdout_log_path": str(stdout_path),
            "stderr_log_path": str(stderr_path),
            "stdout_tail": LightFmTrainingService._tail_text(stdout_path),
            "stderr_tail": LightFmTrainingService._tail_text(stderr_path),
            "command": command,
        }

    @staticmethod
    def _tail_text(path: Path, max_chars: int = 4000) -> str:
        if not path.exists():
            return ""
        text = path.read_text(encoding="utf-8", errors="replace")
        return text[-max_chars:]

    @staticmethod
    def _optional_str(value: Any) -> Optional[str]:
        return str(value) if value is not None and str(value).strip() else None

    @staticmethod
    def _optional_int(value: Any) -> Optional[int]:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
