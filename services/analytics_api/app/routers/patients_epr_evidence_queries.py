"""Cypher queries for coded-concept evidence provenance on the problem list.

The patient-level shortcut relationships (HAS_DISORDER, HAS_FINDING,
HAS_SITUATION, HAS_OBSERVABLE, HAS_PROCEDURE) carry no properties -- they
are bare existence edges. The evidence for a coded concept (the source
sentence, assertion, and confidence) lives on the :DOCUMENTS relationship
instead, and that relationship can hang off any of three source node
types (see libs/cypher/documents_queries.py::_VALID_SOURCE_LABELS):

  - Encounter:      (Patient)-[:HAS_ENCOUNTER]->(Encounter)-[:DOCUMENTS]->(concept)
  - Chunk:          (Patient)-[:HAS_DOCUMENT_REFERENCE|HAS_DOCUMENT]->(DocumentReference)
                       -[:HAS_CHUNK]->(Chunk)-[:DOCUMENTS]->(concept)
  - Communication:  (Patient)<-[:FOR_PATIENT]-(CommunicationRequest)
                       -[:HAS_CONVERSATION]->(Communication)-[:DOCUMENTS]->(concept)

All three must be walked, or coded entities produced by the document/chunk
or communication pipelines silently show "no recorded mentions".

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
    "CALL { "
    "  WITH p "
    "  MATCH (p)-[:HAS_ENCOUNTER]->(src:Encounter)-[r:DOCUMENTS]->(s) "
    "  WHERE toString(s.conceptId) = toString($concept_id) "
    "  RETURN toString(src.id) AS source_id, 'encounter' AS source_type, "
    "         toString(src.date) AS source_date, r.context AS context_json, "
    "         r.confidence AS confidence, toString(r.coded_at) AS coded_at "
    "  UNION "
    "  WITH p "
    "  MATCH (p)-[:HAS_DOCUMENT_REFERENCE|HAS_DOCUMENT]->(doc:DocumentReference) "
    "        -[:HAS_CHUNK]->(src:Chunk)-[r:DOCUMENTS]->(s) "
    "  WHERE toString(s.conceptId) = toString($concept_id) "
    "  RETURN toString(doc.id) AS source_id, 'document' AS source_type, "
    "         toString(coalesce(doc.date, doc.creation)) AS source_date, "
    "         r.context AS context_json, r.confidence AS confidence, "
    "         toString(r.coded_at) AS coded_at "
    "  UNION "
    "  WITH p "
    "  MATCH (p)<-[:FOR_PATIENT]-(:CommunicationRequest) "
    "        -[:HAS_CONVERSATION]->(src:Communication)-[r:DOCUMENTS]->(s) "
    "  WHERE toString(s.conceptId) = toString($concept_id) "
    "  RETURN toString(src.id) AS source_id, 'communication' AS source_type, "
    "         toString(src.sent_datetime) AS source_date, r.context AS context_json, "
    "         r.confidence AS confidence, toString(r.coded_at) AS coded_at "
    "} "
    "RETURN source_id, source_type, source_date, context_json, confidence, coded_at "
    "ORDER BY coalesce(source_date, coded_at) DESC"
)

GET_CONCEPT_MENTIONS_SCOPED = (
    "MATCH (p:Patient {id: $patient_id}) " "WHERE " + _ORG_GUARD + " " + _MENTIONS_BODY
)

GET_CONCEPT_MENTIONS_ADMIN = "MATCH (p:Patient {id: $patient_id}) " + _MENTIONS_BODY

# ---------------------------------------------------------------------------
# Full evidence for one dated mention (fetched on demand)
# ---------------------------------------------------------------------------

_MENTION_DETAIL_BODY = (
    "CALL { "
    "  WITH p "
    "  MATCH (p)-[:HAS_ENCOUNTER]->(src:Encounter)-[r:DOCUMENTS]->(s) "
    "  WHERE $source_type = 'encounter' AND toString(src.id) = toString($source_id) "
    "    AND toString(s.conceptId) = toString($concept_id) "
    "  RETURN toString(src.id) AS source_id, 'encounter' AS source_type, "
    "         toString(src.date) AS source_date, s.name AS name, "
    "         s.readCode AS read_code, r.evidence AS evidence, "
    "         r.evidence_sentence AS evidence_sentence, r.context AS context_json, "
    "         r.confidence AS confidence "
    "  UNION "
    "  WITH p "
    "  MATCH (p)-[:HAS_DOCUMENT_REFERENCE|HAS_DOCUMENT]->(doc:DocumentReference) "
    "        -[:HAS_CHUNK]->(src:Chunk)-[r:DOCUMENTS]->(s) "
    "  WHERE $source_type = 'document' AND toString(doc.id) = toString($source_id) "
    "    AND toString(s.conceptId) = toString($concept_id) "
    "  RETURN toString(doc.id) AS source_id, 'document' AS source_type, "
    "         toString(coalesce(doc.date, doc.creation)) AS source_date, "
    "         s.name AS name, s.readCode AS read_code, r.evidence AS evidence, "
    "         r.evidence_sentence AS evidence_sentence, r.context AS context_json, "
    "         r.confidence AS confidence "
    "  UNION "
    "  WITH p "
    "  MATCH (p)<-[:FOR_PATIENT]-(:CommunicationRequest) "
    "        -[:HAS_CONVERSATION]->(src:Communication)-[r:DOCUMENTS]->(s) "
    "  WHERE $source_type = 'communication' AND toString(src.id) = toString($source_id) "
    "    AND toString(s.conceptId) = toString($concept_id) "
    "  RETURN toString(src.id) AS source_id, 'communication' AS source_type, "
    "         toString(src.sent_datetime) AS source_date, s.name AS name, "
    "         s.readCode AS read_code, r.evidence AS evidence, "
    "         r.evidence_sentence AS evidence_sentence, r.context AS context_json, "
    "         r.confidence AS confidence "
    "} "
    "RETURN source_id, source_type, source_date, name, read_code, evidence, "
    "       evidence_sentence, context_json, confidence "
    "LIMIT 1"
)

GET_CONCEPT_MENTION_DETAIL_SCOPED = (
    "MATCH (p:Patient {id: $patient_id}) "
    "WHERE " + _ORG_GUARD + " " + _MENTION_DETAIL_BODY
)

GET_CONCEPT_MENTION_DETAIL_ADMIN = (
    "MATCH (p:Patient {id: $patient_id}) " + _MENTION_DETAIL_BODY
)
