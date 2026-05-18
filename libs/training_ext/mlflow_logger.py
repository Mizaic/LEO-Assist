"""Thin MLflow logger for training runs.

Atlas trace:
  DO: DO-236545C8
  DI: DI-37B3DC71

All calls are no-ops when the ``mlflow`` package is not installed or when
``MLFLOW_TRACKING_URI`` is unset. The training job therefore never hard-fails
just because observability is offline.

Usage inside a training job::

    with MlflowRunContext(job_id="abc", tags={...}) as run:
        run.log_params({"model": "bio_clinical_bert", "mode": "lora"})
        run.log_metrics({"f1": 0.82, "precision": 0.81, "recall": 0.83})
        run.log_artifact(model_dir / "calibration.json")
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _mlflow_enabled() -> bool:
    if os.getenv("MLFLOW_TRACKING_URI", "").strip() == "":
        return False
    try:
        import mlflow  # noqa: F401
    except Exception:
        return False
    return True


class MlflowRunContext:
    """Context manager that starts a run when MLflow is available."""

    def __init__(
        self,
        *,
        job_id: str = "",
        run_name: str = "training",
        experiment: str = "clinical-ner",
        tags: Optional[dict] = None,
    ) -> None:
        self._job_id = job_id
        self._run_name = run_name
        self._experiment = experiment
        self._tags = tags or {}
        self._mlflow = None
        self._run = None

    def __enter__(self) -> "MlflowRunContext":
        if not _mlflow_enabled():
            return self
        try:
            import mlflow

            mlflow.set_experiment(self._experiment)
            self._mlflow = mlflow
            self._run = mlflow.start_run(run_name=self._run_name)
            if self._job_id:
                mlflow.set_tag("leo.job_id", self._job_id)
            for k, v in self._tags.items():
                mlflow.set_tag(k, v)
        except Exception as exc:
            logger.warning("[mlflow] start_run failed (%s) — falling back to no-op", exc)
            self._mlflow = None
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._mlflow is None:
            return
        try:
            if exc_type is not None:
                self._mlflow.set_tag("leo.failed", "true")
            self._mlflow.end_run()
        except Exception as cleanup_exc:
            logger.warning("[mlflow] end_run failed: %s", cleanup_exc)

    # ------------------------------------------------------------------
    # Logging helpers — all tolerant of MLflow being unavailable.
    # ------------------------------------------------------------------

    def log_params(self, params: dict) -> None:
        if self._mlflow is None:
            return
        try:
            self._mlflow.log_params({k: _stringify(v) for k, v in params.items()})
        except Exception as exc:
            logger.debug("[mlflow] log_params failed: %s", exc)

    def log_metrics(self, metrics: dict, step: int | None = None) -> None:
        if self._mlflow is None:
            return
        safe = {k: float(v) for k, v in metrics.items() if isinstance(v, (int, float))}
        try:
            if step is None:
                self._mlflow.log_metrics(safe)
            else:
                self._mlflow.log_metrics(safe, step=step)
        except Exception as exc:
            logger.debug("[mlflow] log_metrics failed: %s", exc)

    def log_artifact(self, path: Path | str) -> None:
        if self._mlflow is None:
            return
        try:
            self._mlflow.log_artifact(str(path))
        except Exception as exc:
            logger.debug("[mlflow] log_artifact failed: %s", exc)


def _stringify(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ",".join(str(v) for v in value)
    return str(value)
