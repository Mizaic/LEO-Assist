"""Cypher queries for the :Assessment node (DI-LEO-AI-188).

Atlas trace:
  DO: DO-3CAFDCC3
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-3CAFDCC3")

Produced by the SBAR orchestrator. Each section is persisted as soon as
it is generated so that a partial Assessment is recoverable if a later
stage fails.

Schema:

    (:Assessment {
        id, type='SBAR', status, created_at, updated_at,
        run_id, requested_by, tenant_id,
        upstream_correlation_id, source_system,
        context_integrity_status, context_integrity_errors,
        situation, background, assessment, recommendation, content,
        stt, stt_evidence, alternative_pathway, alternative_pathway_evidence,
        rtr, rtr_evidence,
        guideline_ids, errors,
        completeness_result_json
    })

Relationships (incoming):
    (Patient)-[:HAS_ASSESSMENT]->(Assessment)
    (ReferralRequest)-[:HAS_ASSESSMENT]->(Assessment)         # optional
    (ProcedureRequest)-[:HAS_ASSESSMENT]->(Assessment)        # optional
    (Encounter)-[:HAS_ASSESSMENT]->(Assessment)               # optional
"""

from __future__ import annotations

import json
from typing import Any

CREATE_ASSESSMENT = """
MATCH (p:Patient {id: $patient_id})
MERGE (a:Assessment {id: $assessment_id})
ON CREATE SET
    a.type          = 'SBAR',
    a.status        = 'draft',
    a.created_at    = datetime(),
    a.run_id        = $run_id,
    a.requested_by  = $requested_by,
    a.tenant_id     = $tenant_id,
    a.upstream_correlation_id = $upstream_correlation_id,
    a.source_system = $source_system,
    a.context_integrity_status = $context_integrity_status,
    a.context_integrity_errors = $context_integrity_errors,
    a.guideline_ids = $guideline_ids
SET a.updated_at  = datetime(),
    a.run_id      = coalesce(a.run_id, $run_id),
    a.upstream_correlation_id = coalesce(
        a.upstream_correlation_id, $upstream_correlation_id
    ),
    a.source_system = coalesce(a.source_system, $source_system)
MERGE (p)-[:HAS_ASSESSMENT]->(a)
RETURN a.id AS id, a.created_at AS created_at, a.status AS status
"""


# Optional relationship attachments. Each is safe to call zero or many
# times; the link is MERGEd, never duplicated.
LINK_ASSESSMENT_TO_REFERRAL_REQUEST = """
MATCH (a:Assessment {id: $assessment_id})
MATCH (rr:ReferralRequest {id: $artifact_id})
MERGE (rr)-[:HAS_ASSESSMENT]->(a)
"""

LINK_ASSESSMENT_TO_PROCEDURE_REQUEST = """
MATCH (a:Assessment {id: $assessment_id})
MATCH (pr:ProcedureRequest {id: $artifact_id})
MERGE (pr)-[:HAS_ASSESSMENT]->(a)
"""

LINK_ASSESSMENT_TO_ENCOUNTER = """
MATCH (a:Assessment {id: $assessment_id})
MATCH (e:Encounter {id: $encounter_id})
MERGE (e)-[:HAS_ASSESSMENT]->(a)
"""

# Phase 3 (DI-CC0BD732): per-episode SBAR. Each Episode SBAR is linked
# to its EpisodeOfCare via HAS_ASSESSMENT so the UI can render the
# section under the EpisodeDetailPanel. The orchestrator also tags the
# Assessment with assessment_scope = 'episode' so the patient rollup
# can pick all per-episode summaries up in one query.
LINK_ASSESSMENT_TO_EPISODE = """
MATCH (a:Assessment {id: $assessment_id})
MATCH (eoc:Episode {episode_id: $episode_id})
MERGE (eoc)-[:HAS_ASSESSMENT]->(a)
SET a.episode_id       = $episode_id,
    a.assessment_scope = coalesce(a.assessment_scope, 'episode'),
    a.updated_at       = datetime()
RETURN a.id AS id
"""

# Phase 3: list every episode-scoped Assessment for a patient. Used
# by the rollup orchestrator to gather inputs for the cross-episode
# Recommendation prompt.
LIST_PATIENT_EPISODE_ASSESSMENTS = """
MATCH (p:Patient {id: $patient_id})-[:HAS_ASSESSMENT]->(a:Assessment)
WHERE a.assessment_scope = 'episode'
RETURN a.id              AS assessment_id,
       a.episode_id      AS episode_id,
       a.situation       AS situation,
       a.background      AS background,
       a.assessment      AS assessment,
       a.recommendation  AS recommendation,
       a.created_at      AS created_at
ORDER BY a.created_at DESC
"""


# Per-section updates. Each is a SET so the orchestrator can persist
# incrementally without overwriting earlier sections.
SET_SITUATION = """
MATCH (a:Assessment {id: $assessment_id})
SET a.situation        = $situation,
    a.situation_status = 'completed',
    a.updated_at       = datetime()
RETURN a.id AS id
"""

SET_BACKGROUND = """
MATCH (a:Assessment {id: $assessment_id})
SET a.background        = $background,
    a.background_parts  = $background_parts,
    a.background_status = 'completed',
    a.updated_at        = datetime()
RETURN a.id AS id
"""
# ``background_parts`` is a JSON-encoded list of per-partition summaries
# (one entry per LLM call) emitted by libs.sbar.prompt_calls.
# _build_part_summary. Each entry carries ``index``, ``total``,
# ``record_count``, ``record_range``, ``source_ids``, ``status``, and
# any ``error_code``/``error_message``. The UI renders this as the
# "Show source records" disclosure on the Background section so the
# raw source UUIDs no longer leak into the rendered markdown body.

SET_ASSESSMENT_NARRATIVE = """
MATCH (a:Assessment {id: $assessment_id})
SET a.assessment        = $assessment,
    a.assessment_status = 'completed',
    a.assessment_codes  = $assessment_codes,
    a.assessment_rules  = $assessment_rules,
    a.updated_at        = datetime()
RETURN a.id AS id
"""

SET_RECOMMENDATION = """
MATCH (a:Assessment {id: $assessment_id})
SET a.recommendation         = $recommendation,
    a.recommendation_actions = $recommendation_actions,
    a.recommendation_status  = 'completed',
    a.updated_at             = datetime()
RETURN a.id AS id
"""

# Final composition: SBAR markdown content + status + (rule-derived)
# pathway hints. STT / RTR / alternative_pathway are derived from rule
# matches in V1 (no LLM interpretation) -- see DI-LEO-AI-189.
FINALISE_ASSESSMENT = """
MATCH (a:Assessment {id: $assessment_id})
SET a.content                       = $content,
    a.status                        = $status,
    a.errors                        = $errors,
    a.stt                           = $stt,
    a.stt_evidence                  = $stt_evidence,
    a.alternative_pathway           = $alternative_pathway,
    a.alternative_pathway_evidence  = $alternative_pathway_evidence,
    a.rtr                           = $rtr,
    a.rtr_evidence                  = $rtr_evidence,
    a.spoa_disposition              = $spoa_disposition,
    a.spoa_disposition_evidence     = $spoa_disposition_evidence,
    a.updated_at                    = datetime()
RETURN a.id AS id, a.status AS status
"""

# DI-LEO-AI-506: denormalise per-run LLM token usage and cost onto the
# Assessment node so the per-encounter LLM-spend drill-down can return
# SBAR rows alongside :EncounterCandidate rows. The flat fields mirror
# the wire format used by the coding pipeline AuditEvent so the same UI
# components render both.
SET_ASSESSMENT_PROVENANCE = """
MATCH (a:Assessment {id: $assessment_id})
SET a.execution_manifest_json = $execution_manifest_json,
    a.prompt_provenance_json = $prompt_provenance_json,
    a.model_provenance_json = $model_provenance_json,
    a.source_accounting_json = $source_accounting_json,
    a.audit_event_id = $audit_event_id,
    a.updated_at = datetime()
RETURN a.id AS id
"""

SET_ASSESSMENT_USAGE = """
MATCH (a:Assessment {id: $assessment_id})
SET a.llm_usage_json     = $llm_usage_json,
    a.llm_input_tokens   = $llm_input_tokens,
    a.llm_output_tokens  = $llm_output_tokens,
    a.llm_cached_tokens  = $llm_cached_tokens,
    a.llm_total_tokens   = $llm_total_tokens,
    a.llm_calls          = $llm_calls,
    a.llm_cost_usd       = $llm_cost_usd,
    a.llm_latency_ms     = $llm_latency_ms,
    a.llm_model_id       = $llm_model_id,
    a.llm_model_provider = $llm_model_provider,
    a.updated_at         = datetime()
RETURN a.id AS id
"""


# DI-LEO-AI-506: write a PipelineRun AuditEvent so SBAR runs show up in
# the dashboard LLMSpendPanel and per-tenant billing aggregates. Schema
# matches libs/workflow/engine.py::_write_audit_event so the existing
# /analytics/llm-spend/runs query (libs/cypher/model_config_queries.py)
# returns SBAR rows with no UI change.
WRITE_SBAR_AUDIT_EVENT = """
MERGE (ae:AuditEvent {id: $id})
SET ae.type                          = 'PipelineRun',
    ae.plan_definition_id            = $plan_definition_id,
    ae.patient_id                    = $patient_id,
    ae.encounter_id                  = $encounter_id,
    ae.run_id                        = $run_id,
    ae.event_type                    = $event_type,
    ae.status                        = $status,
    ae.step_count                    = $step_count,
    ae.total_duration_ms             = $total_duration_ms,
    ae.entity_count                  = $entity_count,
    ae.error_count                   = $error_count,
    ae.first_error                   = $first_error,
    ae.llm_input_tokens              = $llm_input_tokens,
    ae.llm_output_tokens             = $llm_output_tokens,
    ae.llm_cached_tokens             = $llm_cached_tokens,
    ae.llm_cost_usd                  = $llm_cost_usd,
    ae.extraction_provider           = $extraction_provider,
    ae.extraction_model_tier         = $extraction_model_tier,
    ae.extraction_prompt_name        = $extraction_prompt_name,
    ae.extraction_prompt_version     = $extraction_prompt_version,
    ae.assessment_id                 = $assessment_id,
    ae.created_at                    = datetime()
WITH ae
OPTIONAL MATCH (p:Patient {id: $patient_id})
FOREACH (_ IN CASE WHEN p IS NOT NULL THEN [1] ELSE [] END |
    MERGE (ae)-[:AUDIT_FOR]->(p)
)
RETURN ae.id AS id
"""


SET_ASSESSMENT_COMPLETENESS = """
MATCH (a:Assessment {id: $assessment_id})
SET a.completeness_result_json  = $completeness_result_json,
    a.completeness_failed_count = $completeness_failed_count,
    a.updated_at                = datetime()
RETURN a.id AS id
"""

SET_ASSESSMENT_COMPLIANCE_ALERTS = """
MATCH (a:Assessment {id: $assessment_id})
SET a.compliance_alerts_json = $compliance_alerts_json,
    a.updated_at             = datetime()
RETURN a.id AS id
"""

SET_ASSESSMENT_GATE3 = """
MATCH (a:Assessment {id: $assessment_id})
SET a.referral_reason_evidence_json = $referral_reason_evidence_json,
    a.recall_exhaustion_json        = $recall_exhaustion_json,
    a.recall_needs_review           = $recall_needs_review,
    a.updated_at                    = datetime()
RETURN a.id AS id
"""


GET_ASSESSMENT = """
MATCH (a:Assessment {id: $assessment_id})
OPTIONAL MATCH (p:Patient)-[:HAS_ASSESSMENT]->(a)
RETURN a.id                            AS id,
       a.type                          AS type,
       a.status                        AS status,
       a.created_at                    AS created_at,
       a.updated_at                    AS updated_at,
       a.run_id                        AS run_id,
       a.requested_by                  AS requested_by,
       a.tenant_id                     AS tenant_id,
       a.guideline_ids                 AS guideline_ids,
       a.situation                     AS situation,
       a.background                    AS background,
       a.background_parts              AS background_parts,
       a.assessment                    AS assessment,
       a.assessment_codes              AS assessment_codes,
       a.assessment_rules              AS assessment_rules,
       a.recommendation                AS recommendation,
       a.recommendation_actions        AS recommendation_actions,
       a.content                       AS content,
       a.stt                           AS stt,
       a.stt_evidence                  AS stt_evidence,
       a.alternative_pathway           AS alternative_pathway,
       a.alternative_pathway_evidence  AS alternative_pathway_evidence,
       a.rtr                           AS rtr,
       a.rtr_evidence                  AS rtr_evidence,
       a.spoa_disposition              AS spoa_disposition,
       a.spoa_disposition_evidence     AS spoa_disposition_evidence,
       a.errors                        AS errors,
       a.completeness_result_json      AS completeness_result_json,
       a.compliance_alerts_json        AS compliance_alerts_json,
       a.referral_reason_evidence_json AS referral_reason_evidence_json,
       a.recall_exhaustion_json        AS recall_exhaustion_json,
       a.recall_needs_review           AS recall_needs_review,
       a.llm_usage_json                AS llm_usage_json,
       a.llm_input_tokens              AS llm_input_tokens,
       a.llm_output_tokens             AS llm_output_tokens,
       a.llm_cached_tokens             AS llm_cached_tokens,
       a.llm_total_tokens              AS llm_total_tokens,
       a.llm_calls                     AS llm_calls,
       a.llm_cost_usd                  AS llm_cost_usd,
       a.llm_latency_ms                AS llm_latency_ms,
       a.llm_model_id                  AS llm_model_id,
       a.llm_model_provider            AS llm_model_provider,
       p.id                            AS patient_id
"""


def _decode_background_parts(raw: Any) -> list[dict[str, Any]]:
    """Decode the JSON-encoded ``background_parts`` column.

    Stored as a JSON string so the per-partition summary structure
    (index, total, record_range, source_ids, status, error_*) survives
    a round-trip through Neo4j without flattening. Tolerates legacy
    rows where the column is missing or malformed by returning [].
    """
    if not raw:
        return []
    if isinstance(raw, list):
        return [part for part in raw if isinstance(part, dict)]
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            return []
    if not isinstance(raw, str):
        return []
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [part for part in parsed if isinstance(part, dict)]


def assessment_to_dict(record: Any) -> dict[str, Any]:
    """Map a Neo4j record from GET_ASSESSMENT to a JSON-serialisable dict."""
    if record is None:
        return {}
    return {
        "id": record["id"],
        "type": record["type"],
        "status": record["status"],
        "created_at": str(record["created_at"]) if record["created_at"] else None,
        "updated_at": str(record["updated_at"]) if record["updated_at"] else None,
        "run_id": record["run_id"],
        "requested_by": record["requested_by"],
        "tenant_id": record["tenant_id"],
        "guideline_ids": record["guideline_ids"] or [],
        "patient_id": record["patient_id"],
        "situation": record["situation"],
        "background": record["background"],
        "background_parts": _decode_background_parts(record["background_parts"]),
        "assessment": record["assessment"],
        "assessment_codes": record["assessment_codes"] or [],
        "assessment_rules": record["assessment_rules"] or [],
        "recommendation": record["recommendation"],
        "recommendation_actions": record["recommendation_actions"] or [],
        "content": record["content"],
        "stt": record["stt"],
        "stt_evidence": record["stt_evidence"],
        "alternative_pathway": record["alternative_pathway"],
        "alternative_pathway_evidence": record["alternative_pathway_evidence"],
        "rtr": record["rtr"],
        "rtr_evidence": record["rtr_evidence"],
        "errors": record["errors"] or [],
        "completeness_result_json": record.get("completeness_result_json"),
        "compliance_alerts": _decode_compliance_alerts(
            record.get("compliance_alerts_json")
        ),
        "referral_reason_evidence": _decode_json_object(
            record.get("referral_reason_evidence_json")
        ),
        "recall_exhaustion": _decode_json_object(record.get("recall_exhaustion_json")),
        "recall_needs_review": bool(record.get("recall_needs_review")),
        "llm_usage_json": record.get("llm_usage_json"),
        "llm_input_tokens": int(record.get("llm_input_tokens") or 0),
        "llm_output_tokens": int(record.get("llm_output_tokens") or 0),
        "llm_cached_tokens": int(record.get("llm_cached_tokens") or 0),
        "llm_total_tokens": int(record.get("llm_total_tokens") or 0),
        "llm_calls": int(record.get("llm_calls") or 0),
        "llm_cost_usd": float(record.get("llm_cost_usd") or 0.0),
        "llm_latency_ms": int(record.get("llm_latency_ms") or 0),
        "llm_model_id": record.get("llm_model_id") or "",
        "llm_model_provider": record.get("llm_model_provider") or "",
    }


def _decode_json_object(raw: Any) -> dict[str, Any] | None:
    if not raw:
        return None
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _decode_compliance_alerts(raw: Any) -> list[dict[str, Any]]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
    return []
