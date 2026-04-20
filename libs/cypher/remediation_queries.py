"""Cypher queries for audit-driven encounter remediation.

Atlas trace:
  DO: DO-C5890265
  DI: DI-09E26C1D
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-C5890265")

These queries are called by scripts/remediate_audit_findings.py after
Sonnet verifies each proposed coding change (confidence >= 0.80).

All writes stamp source='audit_remediation' and remediated_at so the
provenance of every automated fix is visible in the graph.
"""

# -- Read encounter text + current DOCUMENTS ----------------------------------

GET_ENCOUNTER_FOR_REMEDIATION = """
MATCH (e:Encounter {id: $encounter_id})
OPTIONAL MATCH (e)-[r:DOCUMENTS]->(s)
RETURN
    e.text       AS text,
    toString(e.date) AS date,
    collect({
        concept_id:   toString(s.conceptId),
        name:         s.name,
        semantic_tag: s.semanticTag,
        context:      r.context,
        evidence:     r.evidence,
        source:       r.source,
        confidence:   r.confidence
    }) AS coded
"""

# -- DELETE overcoded DOCUMENTS -----------------------------------------------
# Deletes the DOCUMENTS relationship.
# If this was the LAST encounter for this patient coding this concept,
# also removes the patient-level shortcut relationship.

DELETE_OVERCODED_DOCUMENTS = """
MATCH (e:Encounter {id: $encounter_id})<-[:HAS_ENCOUNTER]-(p:Patient)
MATCH (e)-[r:DOCUMENTS]->(s)
WHERE toString(s.conceptId) = $concept_id
WITH p, s, collect(r) AS rels
UNWIND rels AS rel
DELETE rel
WITH p, s, size(rels) AS deleted_count
OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(e2:Encounter)-[r2:DOCUMENTS]->(s)
WITH p, s, deleted_count, count(r2) AS remaining
RETURN deleted_count, remaining AS remaining_encounter_docs
"""

# Separate pass to clean up patient shortcuts when no encounters remain.
# Called after DELETE_OVERCODED_DOCUMENTS when remaining_encounter_docs = 0.
CLEANUP_PATIENT_SHORTCUT = """
MATCH (p:Patient {id: $patient_id})-[pr]->(s)
WHERE toString(s.conceptId) = $concept_id
  AND type(pr) IN ['HAS_FINDING', 'HAS_DISORDER', 'HAS_SITUATION',
                   'HAS_OBSERVABLE', 'HAS_PROCEDURE', 'HAS_CONCEPT']
DELETE pr
RETURN count(pr) AS shortcuts_removed
"""

GET_PATIENT_FOR_ENCOUNTER = """
MATCH (e:Encounter {id: $encounter_id})<-[:HAS_ENCOUNTER]-(p:Patient)
RETURN toString(p.id) AS patient_id
"""


# -- ADD missing DOCUMENTS -----------------------------------------------------
# Creates concept node + DOCUMENTS + patient shortcut.
# Labels are fixed at query-build time (Cypher cannot parametrise labels).


def build_add_documents_query(label: str, rel_type: str) -> str:
    """Return a Cypher query string for adding a missing DOCUMENTS link.

    Parameters injected at runtime:
        $encounter_id, $concept_id, $name, $semantic_tag,
        $assertion, $evidence, $confidence
    """
    return f"""
MATCH (e:Encounter {{id: $encounter_id}})<-[:HAS_ENCOUNTER]-(p:Patient)
MERGE (s:{label} {{conceptId: $concept_id}})
SET s.name         = $name,
    s.semanticTag  = $semantic_tag,
    s.source       = coalesce(s.source, 'audit_remediation'),
    s.updated_at   = datetime(),
    s.created_at   = coalesce(s.created_at, datetime())
MERGE (e)-[r:DOCUMENTS {{conceptId: $concept_id}}]->(s)
SET r.context          = $context_json,
    r.evidence         = $evidence,
    r.confidence       = $confidence,
    r.source           = 'audit_remediation',
    r.coded_at         = datetime(),
    r.remediated_by    = 'audit_remediation_v1',
    r.remediated_at    = datetime()
FOREACH (_ IN CASE WHEN $assertion IN ['present', 'historical'] THEN [1] ELSE [] END |
    MERGE (p)-[:{rel_type}]->(s)
)
RETURN true AS written
"""


# Assertion updates use r.context JSON (same shape as pipeline writes).
GET_DOCUMENTS_CONTEXT = """
MATCH (e:Encounter {id: $encounter_id})-[r:DOCUMENTS]->(s)
WHERE toString(s.conceptId) = $concept_id
RETURN r.context AS context_json
LIMIT 1
"""

SET_DOCUMENTS_CONTEXT = """
MATCH (e:Encounter {id: $encounter_id})-[r:DOCUMENTS]->(s)
WHERE toString(s.conceptId) = $concept_id
SET r.context         = $context_json,
    r.remediated_by   = 'audit_remediation_v1',
    r.remediated_at   = datetime()
RETURN count(r) AS updated
"""
