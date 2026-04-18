"""Audit-grade trace recording for every episode-engine run.

Each chain run generates an ``EpisodeEngineTrace`` node in the patient
graph holding:
  - trace_id (UUID per run)
  - patient_id
  - per-stage prompt_version, model_id, tokens, latency_ms, ok flag
  - total cost approximation
  - timestamp

Traces are append-only. Quality gates (``dq_episode_engine_low_confidence_rate``)
read these nodes to monitor drift over time.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from libs.neo4j_client.client import PatientGraphClient
from services.analysis_worker.app.episode_engine.schemas import Provenance, StageTrace

logger = logging.getLogger(__name__)


_WRITE_TRACE_Q = """
MERGE (t:EpisodeEngineTrace {trace_id: $trace_id})
SET t.patient_id            = $patient_id,
    t.created_at            = datetime($created_at),
    t.timeline_encounter_count = $encounter_count,
    t.episode_count         = $episode_count,
    t.total_input_tokens    = $total_input_tokens,
    t.total_output_tokens   = $total_output_tokens,
    t.total_latency_ms      = $total_latency_ms,
    t.stages_json           = $stages_json,
    t.errors_json           = $errors_json,
    t.dry_run               = $dry_run
WITH t
MATCH (p:Patient {id: $patient_id})
MERGE (p)-[:HAS_ENGINE_TRACE]->(t)
RETURN t.trace_id AS trace_id
"""


def new_trace_id() -> str:
    return f"eet-{uuid.uuid4().hex[:16]}"


def build_provenance(
    *,
    trace_id: str,
    stages: list[StageTrace],
    encounter_count: int,
) -> Provenance:
    total_in = sum(s.input_tokens for s in stages)
    total_out = sum(s.output_tokens for s in stages)
    total_latency = sum(s.latency_ms for s in stages)
    return Provenance(
        trace_id=trace_id,
        stages=stages,
        total_input_tokens=total_in,
        total_output_tokens=total_out,
        total_latency_ms=total_latency,
        timeline_encounter_count=encounter_count,
    )


def persist_trace(
    *,
    client: PatientGraphClient,
    trace_id: str,
    patient_id: str,
    stages: list[StageTrace],
    encounter_count: int,
    episode_count: int,
    errors: list[str],
    dry_run: bool,
) -> None:
    """Write an EpisodeEngineTrace node. Best-effort -- never raises."""

    try:
        stages_json = json.dumps([s.model_dump() for s in stages], default=str)
        client.run(
            _WRITE_TRACE_Q,
            trace_id=trace_id,
            patient_id=patient_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            encounter_count=int(encounter_count),
            episode_count=int(episode_count),
            total_input_tokens=int(sum(s.input_tokens for s in stages)),
            total_output_tokens=int(sum(s.output_tokens for s in stages)),
            total_latency_ms=int(sum(s.latency_ms for s in stages)),
            stages_json=stages_json,
            errors_json=json.dumps(list(errors)),
            dry_run=bool(dry_run),
        )
    except Exception:
        logger.exception(
            "Failed to persist EpisodeEngineTrace %s for patient %s",
            trace_id,
            patient_id,
        )


def trace_to_dict(stages: list[StageTrace]) -> list[dict[str, Any]]:
    return [s.model_dump() for s in stages]
