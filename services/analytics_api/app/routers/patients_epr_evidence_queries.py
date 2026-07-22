"""Cypher queries for coded-concept evidence provenance on the problem list.

The patient-level shortcut relationships (HAS_DISORDER, HAS_FINDING,
HAS_SITUATION, HAS_OBSERVABLE, HAS_PROCEDURE) carry no properties -- they
are bare existence edges. The evidence for a coded concept (the source
sentence, assertion, and confidence) lives on the encounter-level
:DOCUMENTS relationship instead. These queries walk Patient -> Encounter
-> DOCUMENTS -> the same concept node to recover that evidence.

Atlas trace:
  DO: DO-5D3EA371
  DI: DI-7DE8E8ED

Kept in a separate module so patients_epr_queries.py stays within the
500-LOC limit.
"""

from libs.auth.org_scope import ORG_PATIENT_FILTER

_ORG_GUARD = ORG_PATIENT_FILTER

# ---------------------------------------------------------------------------
# Dated mentions for one concept (lightweight -- no evidence sentence)
# ---------------------------------------------------------------------------

_MENTIONS_BODY = (
    "MATCH (p)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->(s) "
    "WHERE toString(s.conceptId) = toString($concept_id) "
    "RETURN toString(e.id) AS encounter_id, "
    "       toString(e.date) AS encounter_date, "
    "       r.context AS context_json, "
    "       r.confidence AS confidence, "
    "       toString(r.coded_at) AS coded_at "
    "ORDER BY coalesce(e.date, r.coded_at) DESC"
)

GET_CONCEPT_MENTIONS_SCOPED = (
    "MATCH (p:Patient {id: $patient_id}) " "WHERE " + _ORG_GUARD + " " + _MENTIONS_BODY
)

GET_CONCEPT_MENTIONS_ADMIN = "MATCH (p:Patient {id: $patient_id}) " + _MENTIONS_BODY

# ---------------------------------------------------------------------------
# Full evidence for one dated mention (fetched on demand)
# ---------------------------------------------------------------------------

_MENTION_DETAIL_BODY = (
    "MATCH (p)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->(s) "
    "WHERE toString(e.id) = $encounter_id "
    "  AND toString(s.conceptId) = toString($concept_id) "
    "RETURN toString(e.id) AS encounter_id, "
    "       toString(e.date) AS encounter_date, "
    "       s.name AS name, "
    "       s.readCode AS read_code, "
    "       s.semanticTag AS semantic_tag, "
    "       r.evidence AS evidence, "
    "       r.evidence_sentence AS evidence_sentence, "
    "       r.context AS context_json, "
    "       r.confidence AS confidence, "
    "       toString(r.coded_at) AS coded_at"
)

GET_CONCEPT_MENTION_DETAIL_SCOPED = (
    "MATCH (p:Patient {id: $patient_id}) "
    "WHERE " + _ORG_GUARD + " " + _MENTION_DETAIL_BODY
)

GET_CONCEPT_MENTION_DETAIL_ADMIN = (
    "MATCH (p:Patient {id: $patient_id}) " + _MENTION_DETAIL_BODY
)
