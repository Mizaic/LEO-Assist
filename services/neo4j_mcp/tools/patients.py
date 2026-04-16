"""Patient and encounter tools backed by patient Neo4j graph."""

from __future__ import annotations

from services.api.app.models.neo4j_schema import (
    GET_ENCOUNTER,
    GET_PATIENT,
    GET_PATIENT_CODING_TIMELINE,
    LIST_PATIENT_ENCOUNTERS,
    LIST_PATIENTS,
    SEARCH_ENCOUNTERS_KEYWORD,
)
from services.neo4j_mcp._client import patient_run


PATIENT_CODING_SUMMARY = """
MATCH (p:Patient)
WHERE toString(p.id) = $patient_id
OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(e:Encounter)
WITH p, collect(DISTINCT e) AS encounters
OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(e2:Encounter)
OPTIONAL MATCH (c:EncounterCandidate {
  patient_id: toString(p.id),
  encounter_id: toString(e2.id)
})
WITH p, encounters, collect(DISTINCT c) AS candidates
OPTIONAL MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare)
WITH p, encounters, candidates, count(DISTINCT ep) AS episode_count
OPTIONAL MATCH (p)-[:HAS_SAFETY_NET_ALERT]->(a:SafetyNetAlert)
WITH p, encounters, candidates, episode_count, count(DISTINCT a) AS safety_alert_count
RETURN toString(p.id) AS patient_id,
       p.gender AS gender,
       toString(p.birthDate) AS birth_date,
       size(encounters) AS total_encounters,
       size([e IN encounters WHERE e.classification_content_type IS NOT NULL]) AS classified_count,
       size([e IN encounters WHERE e.classification_content_type = 'clinical']) AS clinical_count,
       size([e IN encounters WHERE e.classification_content_type = 'admin_only']) AS admin_count,
       size([e IN encounters WHERE e.classification_content_type = 'document_transfer']) AS document_transfer_count,
       size([e IN encounters WHERE any(c IN candidates WHERE c IS NOT NULL AND c.encounter_id = toString(e.id))]) AS coded_count,
       size([e IN encounters WHERE NOT any(c IN candidates WHERE c IS NOT NULL AND c.encounter_id = toString(e.id))]) AS uncoded_count,
       size([c IN candidates WHERE c IS NOT NULL AND c.approval_status = 'approved']) AS approved_count,
       size([c IN candidates WHERE c IS NOT NULL AND c.approval_status = 'pending']) AS pending_review_count,
       size([c IN candidates WHERE c IS NOT NULL AND c.approval_status = 'rejected']) AS failed_count,
       episode_count,
       safety_alert_count
"""


def list_patients(limit: int = 500) -> dict:
    rows = patient_run(f"{LIST_PATIENTS}\nLIMIT $limit", limit=limit)
    return {"items": rows, "count": len(rows)}


def get_patient(patient_id: str) -> dict:
    rows = patient_run(GET_PATIENT, patient_id=patient_id)
    return {"item": rows[0] if rows else None}


def get_patient_coding_summary(patient_id: str) -> dict:
    rows = patient_run(PATIENT_CODING_SUMMARY, patient_id=patient_id)
    return {"item": rows[0] if rows else None}


def get_patient_timeline(patient_id: str, limit: int = 5000) -> dict:
    rows = patient_run(
        f"{GET_PATIENT_CODING_TIMELINE}\nLIMIT $limit",
        patient_id=patient_id,
        limit=limit,
    )
    return {"items": rows, "count": len(rows)}


def list_encounters(patient_id: str, limit: int = 500) -> dict:
    rows = patient_run(LIST_PATIENT_ENCOUNTERS, patient_id=patient_id, limit=limit)
    return {"items": rows, "count": len(rows)}


def get_encounter(patient_id: str, encounter_id: str) -> dict:
    rows = patient_run(GET_ENCOUNTER, patient_id=patient_id, encounter_id=encounter_id)
    return {"item": rows[0] if rows else None}


def search_encounters(patient_id: str, q: str, limit: int = 50) -> dict:
    rows = patient_run(SEARCH_ENCOUNTERS_KEYWORD, patient_id=patient_id, q=q, limit=limit)
    return {"items": rows, "count": len(rows)}


TOOLS = [
    {
        "name": "list_patients",
        "description": "List patients with encounter counts.",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 500}},
        },
        "fn": list_patients,
    },
    {
        "name": "get_patient",
        "description": "Get one patient by ID.",
        "inputSchema": {
            "type": "object",
            "properties": {"patient_id": {"type": "string"}},
            "required": ["patient_id"],
        },
        "fn": get_patient,
    },
    {
        "name": "get_patient_coding_summary",
        "description": "Get coding summary for one patient.",
        "inputSchema": {
            "type": "object",
            "properties": {"patient_id": {"type": "string"}},
            "required": ["patient_id"],
        },
        "fn": get_patient_coding_summary,
    },
    {
        "name": "get_patient_timeline",
        "description": "Get coding timeline for one patient.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string"},
                "limit": {"type": "integer", "default": 5000},
            },
            "required": ["patient_id"],
        },
        "fn": get_patient_timeline,
    },
    {
        "name": "list_encounters",
        "description": "List encounters for one patient.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string"},
                "limit": {"type": "integer", "default": 500},
            },
            "required": ["patient_id"],
        },
        "fn": list_encounters,
    },
    {
        "name": "get_encounter",
        "description": "Get one encounter by patient and encounter ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string"},
                "encounter_id": {"type": "string"},
            },
            "required": ["patient_id", "encounter_id"],
        },
        "fn": get_encounter,
    },
    {
        "name": "search_encounters",
        "description": "Keyword search encounters for a patient.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string"},
                "q": {"type": "string"},
                "limit": {"type": "integer", "default": 50},
            },
            "required": ["patient_id", "q"],
        },
        "fn": search_encounters,
    },
]

