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
