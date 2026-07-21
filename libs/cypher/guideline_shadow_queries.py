"""Read-only Cypher for the historic guideline shadow-diff.

Compares a candidate ruleset against the live baseline by evaluating
real, already-coded patients from the **patient graph** -- never the
retired :TestPatient knowledge-graph library. These queries only ever
read; nothing here writes to the patient graph.
"""

from __future__ import annotations

ALLOWED_SHADOW_CONCEPT_EDGE_TYPES: tuple[str, ...] = (
    "HAS_FINDING",
    "HAS_DISORDER",
    "HAS_OBSERVABLE",
    "HAS_PROCEDURE",
    "HAS_SITUATION",
    "HAS_CONCEPT",
    "DOCUMENTS",
)


# Backs the "historic shadow" source-patient picker -- most active real
# patients first, so the comparison has something to evaluate against.
LIST_REAL_PATIENTS_FOR_SHADOW = """
MATCH (p:Patient)
WHERE coalesce(p.is_test, false) = false
OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(e:Encounter)
WITH p, count(DISTINCT e) AS encounter_count
ORDER BY encounter_count DESC, p.id ASC
LIMIT $limit
RETURN p.id                       AS id,
       coalesce(p.displayName, p.id) AS display_name,
       encounter_count
"""


READ_SHADOW_SOURCE_PATIENT = """
MATCH (p:Patient { id: $source_patient_id })
WHERE coalesce(p.is_test, false) = false
RETURN p.id   AS id,
       p.age  AS age,
       p.sex  AS sex
"""


READ_SHADOW_SOURCE_ENCOUNTERS = """
MATCH (p:Patient { id: $source_patient_id })-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE coalesce(p.is_test, false) = false
OPTIONAL MATCH (e)-[:DOCUMENTS]->(c)
WHERE c.id IS NOT NULL
RETURN collect(DISTINCT c.id) AS concept_ids
"""


READ_SHADOW_SOURCE_CONCEPT_EDGES = """
MATCH (p:Patient { id: $source_patient_id })-[r]->(c)
WHERE coalesce(p.is_test, false) = false
  AND c.id IS NOT NULL
  AND type(r) IN $allowed_types
RETURN collect(DISTINCT c.id) AS concept_ids
"""
