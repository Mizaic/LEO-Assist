"""Tools for encounter coded links (:DOCUMENTS relationships).

Atlas trace:
  DO: DO-5F438C17
  DI: DI-5700882E
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-5F438C17")
"""

from __future__ import annotations

import json
from typing import Any

from services.api.app.models.neo4j_schema import (
    DELETE_CODED_LINK,
    LIST_ENCOUNTER_CODED_LINKS,
    UPDATE_CODED_LINK_MODIFIERS,
)
from services.neo4j_mcp._client import patient_run


UPSERT_CODED_LINK = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $patient_id AND toString(e.id) = $encounter_id
MERGE (c:Concept {conceptId: $concept_id})
ON CREATE SET c.term = coalesce($term, $concept_id),
              c.readCode = $read_code,
              c.semanticTag = $semantic_tag
MERGE (e)-[d:DOCUMENTS]->(c)
SET d.evidence = $evidence,
    d.context = $context_json,
    d.modifiers = $modifiers_json,
    d.source = $source,
    d.updated_at = datetime()
RETURN toString(e.id) AS encounter_id, c.conceptId AS concept_id
"""

DELETE_AND_REPLACE_CODED_LINK = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[old:DOCUMENTS]->(old_c:Concept)
WHERE toString(p.id) = $patient_id
  AND toString(e.id) = $encounter_id
  AND old_c.conceptId = $old_concept_id
DELETE old
WITH e
MERGE (new_c:Concept {conceptId: $new_concept_id})
ON CREATE SET new_c.term = coalesce($term, $new_concept_id),
              new_c.readCode = $read_code,
              new_c.semanticTag = $semantic_tag
MERGE (e)-[d:DOCUMENTS]->(new_c)
SET d.context = $context_json,
    d.modifiers = $modifiers_json,
    d.source = 'manual_recode',
    d.updated_at = datetime()
RETURN new_c.conceptId AS concept_id
"""


def _as_json(value: dict[str, Any] | None) -> str:
    return json.dumps(value or {})


def get_coded_links(patient_id: str, encounter_id: str) -> dict:
    rows = patient_run(
        LIST_ENCOUNTER_CODED_LINKS,
        patient_id=patient_id,
        encounter_id=encounter_id,
    )
    return {"items": rows, "count": len(rows)}


def add_coded_link(
    patient_id: str,
    encounter_id: str,
    concept_id: str,
    term: str | None = None,
    read_code: str | None = None,
    semantic_tag: str = "SnomedConcept",
    evidence: str = "",
    modifiers: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> dict:
    rows = patient_run(
        UPSERT_CODED_LINK,
        patient_id=patient_id,
        encounter_id=encounter_id,
        concept_id=concept_id,
        term=term,
        read_code=read_code,
        semantic_tag=semantic_tag,
        evidence=evidence,
        context_json=_as_json(context),
        modifiers_json=_as_json(modifiers),
        source="manual",
    )
    return {"item": rows[0] if rows else None}


def delete_coded_link(patient_id: str, encounter_id: str, concept_id: str) -> dict:
    rows = patient_run(
        DELETE_CODED_LINK,
        patient_id=patient_id,
        encounter_id=encounter_id,
        concept_id=concept_id,
    )
    deleted = int(rows[0].get("deleted") or 0) if rows else 0
    return {"deleted": deleted > 0, "deleted_count": deleted}


def recode_coded_link(
    patient_id: str,
    encounter_id: str,
    concept_id: str,
    new_concept_id: str,
    term: str | None = None,
    read_code: str | None = None,
    semantic_tag: str = "SnomedConcept",
    modifiers: dict[str, Any] | None = None,
) -> dict:
    rows = patient_run(
        DELETE_AND_REPLACE_CODED_LINK,
        patient_id=patient_id,
        encounter_id=encounter_id,
        old_concept_id=concept_id,
        new_concept_id=new_concept_id,
        term=term,
        read_code=read_code,
        semantic_tag=semantic_tag,
        context_json=_as_json({}),
        modifiers_json=_as_json(modifiers),
    )
    return {"item": rows[0] if rows else None}


def update_coded_link_modifiers(
    patient_id: str,
    encounter_id: str,
    concept_id: str,
    value: str | float | None = None,
    unit: str | None = None,
    reference_range: str | None = None,
    interpretation: str | None = None,
) -> dict:
    modifiers = {
        key: val
        for key, val in {
            "value": value,
            "unit": unit,
            "reference_range": reference_range,
            "interpretation": interpretation,
        }.items()
        if val is not None
    }
    rows = patient_run(
        UPDATE_CODED_LINK_MODIFIERS,
        patient_id=patient_id,
        encounter_id=encounter_id,
        concept_id=concept_id,
        modifiers=_as_json(modifiers),
    )
    return {"updated": bool(rows), "modifiers": modifiers}


TOOLS = [
    {
        "name": "get_coded_links",
        "description": "List coded links for an encounter.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string"},
                "encounter_id": {"type": "string"},
            },
            "required": ["patient_id", "encounter_id"],
        },
        "fn": get_coded_links,
    },
    {
        "name": "add_coded_link",
        "description": "Create or update one coded link for an encounter.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string"},
                "encounter_id": {"type": "string"},
                "concept_id": {"type": "string"},
                "term": {"type": "string"},
                "read_code": {"type": "string"},
                "semantic_tag": {"type": "string", "default": "SnomedConcept"},
                "evidence": {"type": "string", "default": ""},
                "modifiers": {"type": "object"},
                "context": {"type": "object"},
            },
            "required": ["patient_id", "encounter_id", "concept_id"],
        },
        "fn": add_coded_link,
    },
    {
        "name": "delete_coded_link",
        "description": "Delete one coded link from an encounter.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string"},
                "encounter_id": {"type": "string"},
                "concept_id": {"type": "string"},
            },
            "required": ["patient_id", "encounter_id", "concept_id"],
        },
        "fn": delete_coded_link,
    },
    {
        "name": "recode_coded_link",
        "description": "Replace coded link concept for an encounter.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string"},
                "encounter_id": {"type": "string"},
                "concept_id": {"type": "string"},
                "new_concept_id": {"type": "string"},
                "term": {"type": "string"},
                "read_code": {"type": "string"},
                "semantic_tag": {"type": "string", "default": "SnomedConcept"},
                "modifiers": {"type": "object"},
            },
            "required": ["patient_id", "encounter_id", "concept_id", "new_concept_id"],
        },
        "fn": recode_coded_link,
    },
    {
        "name": "update_coded_link_modifiers",
        "description": "Update modifiers on an existing coded link.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string"},
                "encounter_id": {"type": "string"},
                "concept_id": {"type": "string"},
                "value": {"type": ["string", "number"]},
                "unit": {"type": "string"},
                "reference_range": {"type": "string"},
                "interpretation": {"type": "string"},
            },
            "required": ["patient_id", "encounter_id", "concept_id"],
        },
        "fn": update_coded_link_modifiers,
    },
]

