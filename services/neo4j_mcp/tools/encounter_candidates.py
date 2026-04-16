"""EncounterCandidate CRUD tools on patient graph."""

from __future__ import annotations

from typing import Any

from services.neo4j_mcp._client import patient_run


LIST_ENCOUNTER_CANDIDATES = """
MATCH (c:EncounterCandidate)
WHERE ($patient_id IS NULL OR c.patient_id = $patient_id)
  AND ($encounter_id IS NULL OR c.encounter_id = $encounter_id)
  AND ($approval_status IS NULL OR c.approval_status = $approval_status)
RETURN c.candidate_id AS candidate_id,
       c.patient_id AS patient_id,
       c.encounter_id AS encounter_id,
       c.approval_status AS approval_status,
       c.warning_reasons AS warning_reasons,
       c.hard_fail_reasons AS hard_fail_reasons,
       c.extraction_model_name AS extraction_model_name,
       c.run_id AS run_id,
       toString(c.updated_at) AS updated_at
ORDER BY c.updated_at DESC
SKIP $offset
LIMIT $limit
"""

GET_ENCOUNTER_CANDIDATE = """
MATCH (c:EncounterCandidate {candidate_id: $candidate_id})
RETURN c
LIMIT 1
"""

UPDATE_ENCOUNTER_CANDIDATE = """
MATCH (c:EncounterCandidate {candidate_id: $candidate_id})
SET c.approval_status = $approval_status,
    c.updated_at = datetime()
RETURN c.candidate_id AS candidate_id,
       c.approval_status AS approval_status
"""

DELETE_ENCOUNTER_CANDIDATE = """
MATCH (c:EncounterCandidate {candidate_id: $candidate_id})
OPTIONAL MATCH (c)-[:HAS_TASK]->(t:ReviewTask)-[:HAS_APPROVAL]->(a:Approval)
OPTIONAL MATCH (c)-[:HAS_CHANGE]->(chg:Change)
WITH c, collect(DISTINCT t) AS tasks, collect(DISTINCT a) AS approvals, collect(DISTINCT chg) AS changes
FOREACH (n IN approvals | DETACH DELETE n)
FOREACH (n IN changes | DETACH DELETE n)
FOREACH (n IN tasks | DETACH DELETE n)
WITH c
DETACH DELETE c
RETURN $candidate_id AS candidate_id
"""


def list_encounter_candidates(
    patient_id: str | None = None,
    encounter_id: str | None = None,
    approval_status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    rows = patient_run(
        LIST_ENCOUNTER_CANDIDATES,
        patient_id=patient_id,
        encounter_id=encounter_id,
        approval_status=approval_status,
        limit=limit,
        offset=offset,
    )
    return {"items": rows, "count": len(rows)}


def get_candidate(candidate_id: str) -> dict[str, Any]:
    rows = patient_run(GET_ENCOUNTER_CANDIDATE, candidate_id=candidate_id)
    return {"item": rows[0] if rows else None}


def update_candidate_approval(candidate_id: str, approval_status: str) -> dict[str, Any]:
    rows = patient_run(
        UPDATE_ENCOUNTER_CANDIDATE,
        candidate_id=candidate_id,
        approval_status=approval_status,
    )
    return {"item": rows[0] if rows else None}


def delete_candidate(candidate_id: str) -> dict[str, Any]:
    rows = patient_run(DELETE_ENCOUNTER_CANDIDATE, candidate_id=candidate_id)
    return {"deleted": bool(rows), "candidate_id": candidate_id}


TOOLS = [
    {
        "name": "list_encounter_candidates",
        "description": "List encounter candidates from patient graph.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string"},
                "encounter_id": {"type": "string"},
                "approval_status": {"type": "string"},
                "limit": {"type": "integer", "default": 100},
                "offset": {"type": "integer", "default": 0},
            },
        },
        "fn": list_encounter_candidates,
    },
    {
        "name": "get_candidate",
        "description": "Get one encounter candidate.",
        "inputSchema": {
            "type": "object",
            "properties": {"candidate_id": {"type": "string"}},
            "required": ["candidate_id"],
        },
        "fn": get_candidate,
    },
    {
        "name": "update_candidate_approval",
        "description": "Update approval status for encounter candidate.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "candidate_id": {"type": "string"},
                "approval_status": {"type": "string"},
            },
            "required": ["candidate_id", "approval_status"],
        },
        "fn": update_candidate_approval,
    },
    {
        "name": "delete_candidate",
        "description": "Delete encounter candidate and related nodes.",
        "inputSchema": {
            "type": "object",
            "properties": {"candidate_id": {"type": "string"}},
            "required": ["candidate_id"],
        },
        "fn": delete_candidate,
    },
]

