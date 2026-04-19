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

from libs.llm_usage import LLMCostConfig, LLMUsage
from libs.neo4j_client.client import PatientGraphClient
from services.analysis_worker.app.episode_engine.schemas import Provenance, StageTrace

logger = logging.getLogger(__name__)


_WRITE_TRACE_Q = """
MERGE (t:EpisodeEngineTrace {trace_id: $trace_id})
SET t.patient_id                  = $patient_id,
    t.created_at                  = datetime($created_at),
    t.timeline_encounter_count    = $encounter_count,
    t.episode_count               = $episode_count,
    t.total_input_tokens          = $total_input_tokens,
    t.total_output_tokens         = $total_output_tokens,
    t.total_cached_input_tokens   = $total_cached_input_tokens,
    t.total_cost_usd              = $total_cost_usd,
    t.total_latency_ms            = $total_latency_ms,
    t.stages_json                 = $stages_json,
    t.errors_json                 = $errors_json,
    t.dry_run                     = $dry_run
WITH t
MATCH (p:Patient {id: $patient_id})
MERGE (p)-[:HAS_ENGINE_TRACE]->(t)
RETURN t.trace_id AS trace_id
"""


# DI-LEO-AI-517: write a PipelineRun :AuditEvent so episode-engine runs
# show up in the same /admin/billing dashboards as coding-extraction
# (EncounterCandidate.llm_usage_json) and SBAR (WRITE_SBAR_AUDIT_EVENT).
# Schema mirrors libs/cypher/sbar_assessment_queries.py::WRITE_SBAR_AUDIT_EVENT
# so the existing GET_AUDIT_EVENT_SPEND query returns these rows with
# zero UI changes. Best-effort: never raises.
_WRITE_EPISODE_ENGINE_AUDIT_EVENT = """
MERGE (ae:AuditEvent {id: $id})
SET ae.type                          = 'PipelineRun',
    ae.subtype                       = 'episode_engine',
    ae.plan_definition_id            = 'episode_engine',
    ae.patient_id                    = $patient_id,
    ae.run_id                        = $trace_id,
    ae.event_type                    = 'episode_engine_run',
    ae.status                        = $status,
    ae.step_count                    = $stage_count,
    ae.entity_count                  = $episode_count,
    ae.total_duration_ms             = $total_latency_ms,
    ae.error_count                   = $error_count,
    ae.first_error                   = $first_error,
    ae.llm_input_tokens              = $llm_input_tokens,
    ae.llm_output_tokens             = $llm_output_tokens,
    ae.llm_cached_tokens             = $llm_cached_tokens,
    ae.llm_cost_usd                  = $llm_cost_usd,
    ae.extraction_provider           = $extraction_provider,
    ae.extraction_model_tier         = $extraction_model_tier,
    ae.extraction_prompt_name        = 'episode_engine',
    ae.extraction_prompt_version     = 1,
    ae.dry_run                       = $dry_run,
    ae.created_at                    = datetime()
WITH ae
OPTIONAL MATCH (p:Patient {id: $patient_id})
FOREACH (_ IN CASE WHEN p IS NOT NULL THEN [1] ELSE [] END |
    MERGE (ae)-[:AUDIT_FOR]->(p)
)
RETURN ae.id AS id
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
    total_cached = sum(s.cached_input_tokens for s in stages)
    total_cost = round(sum(s.cost_usd for s in stages), 6)
    total_latency = sum(s.latency_ms for s in stages)
    return Provenance(
        trace_id=trace_id,
        stages=stages,
        total_input_tokens=total_in,
        total_output_tokens=total_out,
        total_cached_input_tokens=total_cached,
        total_cost_usd=total_cost,
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
    """Write an EpisodeEngineTrace node + a PipelineRun :AuditEvent.

    Best-effort: each write is wrapped independently so a transient
    failure on one does not skip the other and never bubbles up to the
    chain. The AuditEvent makes episode-engine LLM spend visible in the
    same /admin/billing dashboards as coding extraction and SBAR
    (DI-LEO-AI-517).
    """

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
            total_cached_input_tokens=int(
                sum(s.cached_input_tokens for s in stages)
            ),
            total_cost_usd=round(sum(s.cost_usd for s in stages), 6),
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

    _write_audit_event(
        client=client,
        trace_id=trace_id,
        patient_id=patient_id,
        stages=stages,
        episode_count=episode_count,
        errors=errors,
        dry_run=dry_run,
    )


def _resolve_total_cost_usd(stages: list[StageTrace]) -> float:
    """Return the total cost across all stages.

    StageTrace.cost_usd is populated during the run via LLMCostConfig.
    If any stage was missed (e.g. cost env vars unset for that tier),
    fall back to a recomputation from token counts so the AuditEvent
    matches the EpisodeEngineTrace number. Best-effort: returns 0.0 on
    any failure.
    """

    direct = sum(float(getattr(s, "cost_usd", 0.0) or 0.0) for s in stages)
    if direct > 0.0:
        return round(direct, 6)
    try:
        usage = LLMUsage(
            input_tokens=sum(int(s.input_tokens or 0) for s in stages),
            output_tokens=sum(int(s.output_tokens or 0) for s in stages),
            cached_input_tokens=sum(
                int(getattr(s, "cached_input_tokens", 0) or 0) for s in stages
            ),
            llm_calls=len(stages),
        )
        cfg = LLMCostConfig.for_tier("small")
        return round(usage.cost_usd(cfg), 6)
    except Exception:
        return 0.0


def _write_audit_event(
    *,
    client: PatientGraphClient,
    trace_id: str,
    patient_id: str,
    stages: list[StageTrace],
    episode_count: int,
    errors: list[str],
    dry_run: bool,
) -> None:
    """Write a PipelineRun :AuditEvent for an episode-engine run.

    Best-effort -- never raises.
    """

    try:
        ok_stages = [s for s in stages if getattr(s, "ok", True)]
        any_failed = len(ok_stages) != len(stages)
        status = (
            "completed"
            if not (errors or any_failed)
            else ("partial" if ok_stages else "failed")
        )
        first_error: str | None = None
        if errors:
            first_error = str(errors[0])[:400]
        else:
            failed = next(
                (s for s in stages if not getattr(s, "ok", True)), None
            )
            if failed is not None and getattr(failed, "error", None):
                first_error = str(failed.error)[:400]

        primary_provider = (
            "azure" if (stages and "azure" in (stages[0].model_id or "").lower())
            else "bedrock"
        )
        primary_tier = getattr(stages[0], "tier", "") if stages else ""

        client.run(
            _WRITE_EPISODE_ENGINE_AUDIT_EVENT,
            id=f"audit-eet-{trace_id}",
            trace_id=trace_id,
            patient_id=patient_id,
            status=status,
            stage_count=len(stages),
            episode_count=int(episode_count),
            total_latency_ms=int(sum(int(s.latency_ms or 0) for s in stages)),
            error_count=len(errors) + (len(stages) - len(ok_stages)),
            first_error=first_error,
            llm_input_tokens=int(sum(int(s.input_tokens or 0) for s in stages)),
            llm_output_tokens=int(sum(int(s.output_tokens or 0) for s in stages)),
            llm_cached_tokens=int(
                sum(int(getattr(s, "cached_input_tokens", 0) or 0) for s in stages)
            ),
            llm_cost_usd=_resolve_total_cost_usd(stages),
            extraction_provider=primary_provider,
            extraction_model_tier=str(primary_tier or "small"),
            dry_run=bool(dry_run),
        )
    except Exception:
        logger.warning(
            "Failed to write episode-engine PipelineRun AuditEvent for "
            "trace %s patient %s",
            trace_id,
            patient_id,
            exc_info=True,
        )


def trace_to_dict(stages: list[StageTrace]) -> list[dict[str, Any]]:
    return [s.model_dump() for s in stages]
