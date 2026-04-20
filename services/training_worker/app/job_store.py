"""In-memory + Redis job state store for training jobs.

Atlas trace:
  DO: DO-A35D2D57
  DI: DI-37B3DC71
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-A35D2D57")

Mirrors the pattern used by the coding worker job store.  In-process dict
is the primary store (fast reads); Redis is used for pub/sub progress events
that the SSE relay endpoint consumes.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from typing import Any, Optional

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
_MAX_JOBS = int(os.getenv("TRAINING_MAX_JOB_HISTORY", "100"))


class TrainingJob:
    def __init__(
        self,
        *,
        base_model_version: str = "",
        hf_model_name: str = "emilyalsentzer/Bio_ClinicalBERT",
        notes: str = "",
        triggered_by: str = "unknown",
    ) -> None:
        self.job_id = str(uuid.uuid4())
        self.base_model_version = base_model_version
        self.hf_model_name = hf_model_name
        self.notes = notes
        self.triggered_by = triggered_by
        self.status: str = (
            "queued"  # queued | running | evaluating | uploading | done | failed | cancelled
        )
        self.phase: str = ""  # export | qa | train | evaluate | upload | register
        self.log_lines: list[str] = []
        self.metrics: dict[str, Any] = {}
        self.artifact_uri: str = ""
        self.model_version: str = ""
        self.error: str = ""
        self.created_at = time.time()
        self.started_at: Optional[float] = None
        self.finished_at: Optional[float] = None

    def to_dict(self, *, log_tail: int = 25) -> dict[str, Any]:
        ner_metrics = self.metrics.get("ner", {})
        export_metrics = self.metrics.get("export", {})
        return {
            "job_id": self.job_id,
            "base_model_version": self.base_model_version,
            "hf_model_name": self.hf_model_name,
            "notes": self.notes,
            "triggered_by": self.triggered_by,
            "status": self.status,
            "phase": self.phase,
            "log_lines": self.log_lines[-max(0, log_tail) :] if log_tail > 0 else [],
            "log_line_count": len(self.log_lines),
            "metrics": self.metrics,
            # Top-level shortcuts so the UI doesn't dig through nested dicts.
            "precision": ner_metrics.get("precision"),
            "recall": ner_metrics.get("recall"),
            "f1": ner_metrics.get("f1"),
            "per_label_f1": ner_metrics.get("per_label", {}),
            "dev_doc_count": ner_metrics.get("dev_doc_count"),
            "passed_gates": ner_metrics.get("passed_gates"),
            "export_total": export_metrics.get("total"),
            "export_assertion_filtered": export_metrics.get("assertion_filtered"),
            "export_span_misaligned": export_metrics.get("span_misaligned"),
            "artifact_uri": self.artifact_uri,
            "model_version": self.model_version,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed_s": (
                round(
                    (
                        (self.finished_at or time.time())
                        - (self.started_at or self.created_at)
                    ),
                    1,
                )
                if self.started_at
                else None
            ),
        }


class TrainingJobStore:
    """Thread-safe in-memory store with Redis pub/sub for SSE relay."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, TrainingJob] = {}
        self._redis = None

    def _get_redis(self):
        if self._redis is None:
            try:
                import redis as _redis

                self._redis = _redis.from_url(REDIS_URL)
            except Exception:
                logger.debug("Redis unavailable — SSE relay will be silent")
        return self._redis

    def create(self, **kwargs) -> TrainingJob:
        job = TrainingJob(**kwargs)
        with self._lock:
            self._jobs[job.job_id] = job
            self._evict_old_jobs()
        self._publish(
            job.job_id,
            {"type": "job_created", "job_id": job.job_id, "status": job.status},
        )
        return job

    def get(self, job_id: str) -> Optional[TrainingJob]:
        with self._lock:
            return self._jobs.get(job_id)

    def list_all(self, *, log_tail: int = 25) -> list[dict[str, Any]]:
        with self._lock:
            return [
                j.to_dict(log_tail=log_tail)
                for j in sorted(
                    self._jobs.values(), key=lambda j: j.created_at, reverse=True
                )
            ]

    def update(self, job: TrainingJob, **fields) -> None:
        """Update job fields and publish progress event."""
        with self._lock:
            for k, v in fields.items():
                setattr(job, k, v)
        event_type = f"training_{fields.get('phase', job.phase) or 'progress'}"
        self._publish(
            job.job_id,
            {
                "type": event_type,
                "job_id": job.job_id,
                "status": job.status,
                "phase": job.phase,
                **{k: v for k, v in fields.items() if k not in ("log_lines",)},
            },
        )

    def append_log(self, job: TrainingJob, line: str) -> None:
        with self._lock:
            job.log_lines.append(line)
        self._publish(
            job.job_id,
            {
                "type": "training_log",
                "job_id": job.job_id,
                "line": line,
            },
        )

    def _evict_old_jobs(self) -> None:
        """Drop oldest terminal jobs when the store exceeds _MAX_JOBS.

        Must be called with self._lock held.
        """
        if len(self._jobs) <= _MAX_JOBS:
            return
        terminal = {"done", "failed", "cancelled"}
        evictable = sorted(
            (j for j in self._jobs.values() if j.status in terminal),
            key=lambda j: j.created_at,
        )
        for job in evictable[: len(self._jobs) - _MAX_JOBS]:
            del self._jobs[job.job_id]

    def _publish(self, job_id: str, payload: dict[str, Any]) -> None:
        r = self._get_redis()
        if r:
            try:
                r.publish(f"training:{job_id}", json.dumps(payload, default=str))
            except Exception:
                logger.debug("Redis publish failed for training:%s", job_id)


# Singleton
_store = TrainingJobStore()


def get_store() -> TrainingJobStore:
    return _store
