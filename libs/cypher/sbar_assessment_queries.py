"""Cypher queries for the :Assessment node (DI-LEO-AI-188).

Produced by the SBAR orchestrator. Each section is persisted as soon as
it is generated so that a partial Assessment is recoverable if a later
stage fails.

Schema:

    (:Assessment {
        id, type='SBAR', status, created_at, updated_at,
        run_id, requested_by, tenant_id,
        situation, background, assessment, recommendation, content,
        stt, stt_evidence, alternative_pathway, alternative_pathway_evidence,
        rtr, rtr_evidence,
        guideline_ids, errors
    })

Relationships (incoming):
    (Patient)-[:HAS_ASSESSMENT]->(Assessment)
    (ReferralRequest)-[:HAS_ASSESSMENT]->(Assessment)         # optional
    (ProcedureRequest)-[:HAS_ASSESSMENT]->(Assessment)        # optional
    (Encounter)-[:HAS_ASSESSMENT]->(Assessment)               # optional
"""

from __future__ import annotations

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
    a.guideline_ids = $guideline_ids
SET a.updated_at  = datetime(),
    a.run_id      = coalesce(a.run_id, $run_id)
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
    a.background_status = 'completed',
    a.updated_at        = datetime()
RETURN a.id AS id
"""

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
    a.updated_at                    = datetime()
RETURN a.id AS id, a.status AS status
"""

# DI-LEO-AI-506: denormalise per-run LLM token usage and cost onto the
# Assessment node so the per-encounter LLM-spend drill-down can return
# SBAR rows alongside :EncounterCandidate rows. The flat fields mirror
# the wire format used by the coding pipeline AuditEvent so the same UI
# components render both.
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
       a.errors                        AS errors,
       p.id                            AS patient_id
"""


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
    }
