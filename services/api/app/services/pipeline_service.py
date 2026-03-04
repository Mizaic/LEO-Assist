"""Canonical API pipeline service.

Delegates all pipeline execution to the coding-worker pipeline implementation.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from services.coding_worker.app.pipeline.pipeline_service import (
    CodingPipeline,
    PipelineStats as WorkerPipelineStats,
)

logger = logging.getLogger(__name__)

_DEFAULT_WORKERS = 4
_MAX_WORKERS = 8


@dataclass
class PipelineStats:
    processed_encounters: int = 0
    queued_for_review: int = 0
    rejected_hard_fail: int = 0
    warnings_only: int = 0
    llm_usage: dict[str, Any] | None = None

    @classmethod
    def from_worker(cls, stats: WorkerPipelineStats) -> "PipelineStats":
        return cls(
            processed_encounters=stats.processed_encounters,
            queued_for_review=stats.queued_for_review,
            rejected_hard_fail=stats.rejected_hard_fail,
            warnings_only=stats.warnings_only,
            llm_usage=None,
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "processed_encounters": self.processed_encounters,
            "queued_for_review": self.queued_for_review,
            "rejected_hard_fail": self.rejected_hard_fail,
            "warnings_only": self.warnings_only,
            "llm_usage": self.llm_usage or {},
        }


class PipelineService:
    _embedder_cache: Any = None

    def __init__(self, patient_client, coding_client) -> None:
        self.patient_graph = patient_client
        self.coding_graph = coding_client
        self._canonical = CodingPipeline(
            patient_client=self.patient_graph,
            knowledge_client=self.coding_graph,
            coding_mode=os.getenv("CODING_MODE", "hitl"),
        )

    @classmethod
    def _try_load_embedder(cls):
        if cls._embedder_cache is not None:
            return cls._embedder_cache
        try:
            from scripts.embedding_utils import TextEmbedder, load_vector_settings

            settings = load_vector_settings()
            embedder = TextEmbedder(settings)
            embedder.encode(["x"])
            cls._embedder_cache = embedder
            logger.info("Vector embedder loaded: model=%s", settings.model_name)
            return embedder
        except Exception:
            logger.info("Vector embedder unavailable for encounter semantic search")
            return None

    @classmethod
    def preload_embedder(cls) -> None:
        cls._try_load_embedder()

    def run(
        self,
        patient_ids: list[str],
        max_encounters_per_patient: int | None = None,
        dry_run: bool = False,
        workers: int = _DEFAULT_WORKERS,
        progress_hook: Callable[[dict[str, Any]], None] | None = None,
    ) -> tuple[str, PipelineStats]:
        if max_encounters_per_patient:
            logger.warning(
                "max_encounters_per_patient is ignored in canonical pipeline cutover mode"
            )
        _ = max(1, min(workers, _MAX_WORKERS))
        run_id = str(uuid.uuid4())
        worker_stats = asyncio.run(
            self._canonical.run(
                patient_ids=patient_ids,
                dry_run=dry_run,
                progress_hook=progress_hook,
            )
        )
        return run_id, PipelineStats.from_worker(worker_stats)

    def run_unprocessed(
        self,
        patient_ids: list[str],
        dry_run: bool = False,
        workers: int = _DEFAULT_WORKERS,
        progress_hook: Callable[[dict[str, Any]], None] | None = None,
    ) -> tuple[str, PipelineStats]:
        _ = max(1, min(workers, _MAX_WORKERS))
        run_id = str(uuid.uuid4())
        worker_stats = asyncio.run(
            self._canonical.run_unprocessed(
                patient_ids=patient_ids,
                dry_run=dry_run,
                progress_hook=progress_hook,
            )
        )
        return run_id, PipelineStats.from_worker(worker_stats)

    def run_single_encounter(
        self,
        patient_id: str,
        encounter_id: str,
        dry_run: bool = False,
        progress_hook: Callable[[dict[str, Any]], None] | None = None,
    ) -> tuple[str, PipelineStats]:
        run_id = str(uuid.uuid4())
        worker_stats = asyncio.run(
            self._canonical.run_single_encounter(
                patient_id=patient_id,
                encounter_id=encounter_id,
                dry_run=dry_run,
                progress_hook=progress_hook,
            )
        )
        return run_id, PipelineStats.from_worker(worker_stats)


# Temporary compatibility alias while refs are migrated.
V3PipelineService = PipelineService
