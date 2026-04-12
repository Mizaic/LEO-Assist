"""Pipeline service — thin facade for the unified pipeline worker.

The legacy in-process CodingPipeline has been removed.  Callers should
use the ``/pipeline/run-patient`` or ``/pipeline/run-cohort`` endpoints
which publish jobs to the ``pipeline-jobs`` Service Bus queue.

This module keeps ``PipelineService`` and ``PipelineStats`` importable so
that any remaining in-process endpoints return a clear error rather than
crash at import time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_REMOVED_MSG = (
    "In-process pipeline execution has been removed. "
    "Use /pipeline/run-patient or /pipeline/run-cohort to dispatch "
    "jobs to the unified pipeline worker."
)


@dataclass
class PipelineStats:
    processed_encounters: int = 0
    queued_for_review: int = 0
    rejected_hard_fail: int = 0
    warnings_only: int = 0
    llm_usage: dict[str, Any] | None = None

    def snapshot(self) -> dict[str, Any]:
        return {
            "processed_encounters": self.processed_encounters,
            "queued_for_review": self.queued_for_review,
            "rejected_hard_fail": self.rejected_hard_fail,
            "warnings_only": self.warnings_only,
            "llm_usage": self.llm_usage or {},
        }


class PipelineService:
    """Stub — raises on any execution attempt."""

    def __init__(self, patient_client=None, coding_client=None) -> None:
        self.patient_graph = patient_client
        self.coding_graph = coding_client

    @classmethod
    def preload_embedder(cls) -> None:
        """Kick off a background thread to pre-load the few-shot sentence-transformer model.

        The model is stored in a process-level singleton so it is loaded at most once.
        Subsequent requests reuse the already-loaded model with no delay.
        Called at API startup so the first real pipeline (or dry-run) request doesn't
        pay the cold-start cost (1–2 minutes on CPU for Bio_ClinicalBERT).
        """
        try:
            from libs.prompts.few_shot_selector import warm_shared_embedder

            warm_shared_embedder()
        except Exception:
            import logging

            logging.getLogger(__name__).warning(
                "Embedder pre-warm failed (non-fatal) — model will load on first pipeline run",
                exc_info=True,
            )

    @classmethod
    def _try_load_embedder(cls):
        """Return shared sentence embedder, or None on failure."""
        try:
            from libs.prompts.few_shot_selector import _get_shared_embedder

            return _get_shared_embedder()
        except Exception:
            logger.warning("Embedder load failed (non-fatal)", exc_info=True)
            return None

    def run(self, **kwargs: Any) -> tuple[str, PipelineStats]:
        raise NotImplementedError(_REMOVED_MSG)

    def run_unprocessed(self, **kwargs: Any) -> tuple[str, PipelineStats]:
        raise NotImplementedError(_REMOVED_MSG)

    def run_single_encounter(self, **kwargs: Any) -> tuple[str, PipelineStats]:
        raise NotImplementedError(_REMOVED_MSG)


V3PipelineService = PipelineService
