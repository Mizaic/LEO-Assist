"""DOCUMENTS relationship and semantic link queries.

Centralised from services/api/app/models/neo4j_schema.py.

write_documents_from_sentences_payload() is the shared helper used by both
the coding worker (provisional write immediately after extraction) and the
review service (authoritative write when a reviewer approves/edits).
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Maps normalised semantic tag → Neo4j node label (mirrors patient_graph_writer.py)
_LABEL_BY_TAG: dict[str, str] = {
    "situation": "Situation",
    "clinicalfinding": "Clinical_finding",
    "finding": "Clinical_finding",
    "disease": "Disease",
    "disorder": "Disease",
    "observableentity": "Observable_entity",
    "observable": "Observable_entity",
    "procedure": "Procedure",
    "regimetherapy": "Procedure",
    "substance": "SnomedConcept",
    "product": "SnomedConcept",
    "snomedconcept": "SnomedConcept",
    "medication": "SnomedConcept",
    "labtest": "SnomedConcept",
    "other": "SnomedConcept",
}

# Maps Neo4j node label → patient-level relationship type
_REL_BY_LABEL: dict[str, str] = {
    "Clinical_finding": "HAS_FINDING",
    "Disease": "HAS_DISORDER",
    "Observable_entity": "HAS_OBSERVABLE",
    "Procedure": "HAS_PROCEDURE",
    "Situation": "HAS_SITUATION",
    "SnomedConcept": "HAS_CONCEPT",
}


def _label_for_tag(tag: str) -> str:
    normalised = "".join(ch for ch in tag.lower() if ch.isalnum())
    return _LABEL_BY_TAG.get(normalised, "SnomedConcept")


def _build_upsert_query(label: str, rel_type: str) -> str:
    """Return a Cypher query that:
    1. MERGEs the concept node with the given label.
    2. MERGEs (Encounter)-[:DOCUMENTS]->(concept).
    3. MERGEs (Patient)-[:<rel_type>]->(concept) as a patient-level shortcut.
    """
    return f"""
MATCH (e:Encounter {{id: $encounter_id}})<-[:HAS_ENCOUNTER]-(p:Patient)
MERGE (s:{label} {{conceptId: $concept_id}})
SET s.semanticTag  = $semantic_tag,
    s.name         = $name,
    s.readCode     = $read_code,
    s.source       = $source,
    s.updated_at   = datetime(),
    s.created_at   = coalesce(s.created_at, datetime())
MERGE (e)-[r:DOCUMENTS {{conceptId: $concept_id}}]->(s)
SET r.coded_at  = datetime(),
    r.evidence  = $evidence,
    r.confidence = $confidence,
    r.domain    = $domain,
    r.context   = $context,
    r.modifiers = $modifiers,
    r.source    = $source
MERGE (p)-[:{rel_type}]->(s)
"""


def write_documents_from_sentences_payload(
    encounter_id: str,
    sentences_payload: list[dict[str, Any]],
    session,
    *,
    source: str = "provisional",
) -> int:
    """Write :DOCUMENTS and :HAS_<tag> links from a sentences_payload list.

    ``sentences_payload`` is the list produced by
    ``CodingPipeline._build_sentences_payload`` (and stored in
    ``EncounterCandidate.sentences_json``).  Each sentence item has a
    ``terms`` array whose elements carry::

        {
          "text": "...",
          "coding": {
              "snomed_concept_id": "...",   # may be None / missing
              "read_code": "...",
              "snomed_term": "...",
              "score": 0.95,
              "source": "terminology_api"
          },
          "semantic_tag": "finding",
          "modifiers": {}
        }

    Returns the number of DOCUMENTS links written.
    """
    written = 0
    for sentence in sentences_payload:
        for term in sentence.get("terms", []):
            coding = term.get("coding") or {}
            concept_id = coding.get("snomed_concept_id")
            if not concept_id:
                continue

            semantic_tag = term.get("semantic_tag") or "other"
            label = _label_for_tag(semantic_tag)
            rel_type = _REL_BY_LABEL.get(label, "HAS_CONCEPT")
            query = _build_upsert_query(label, rel_type)

            modifiers = term.get("modifiers") or {}

            try:
                session.run(
                    query,
                    encounter_id=encounter_id,
                    concept_id=str(concept_id),
                    semantic_tag=semantic_tag,
                    name=coding.get("snomed_term") or term.get("text", ""),
                    read_code=coding.get("read_code"),
                    evidence=term.get("text", ""),
                    confidence=float(coding.get("score") or 0.0),
                    domain=term.get("domain") or "clinical",
                    context="{}",
                    modifiers=json.dumps(modifiers),
                    source=source,
                )
                written += 1
            except Exception:
                logger.warning(
                    "write_documents_from_sentences_payload: failed for "
                    "encounter=%s concept=%s",
                    encounter_id,
                    concept_id,
                    exc_info=True,
                )

    return written

DELETE_CODED_LINK = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $patient_id AND toString(e.id) = $encounter_id
MATCH (e)-[r:DOCUMENTS]->(s)
WHERE s.conceptId = $concept_id
DELETE r
"""

UPDATE_CODED_LINK_MODIFIERS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $patient_id AND toString(e.id) = $encounter_id
MATCH (e)-[r:DOCUMENTS]->(s)
WHERE s.conceptId = $concept_id
SET r.modifiers = $modifiers
RETURN s.conceptId AS concept_id, r.modifiers AS modifiers
"""

LIST_ENCOUNTER_CODED_LINKS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $patient_id AND toString(e.id) = $encounter_id
OPTIONAL MATCH (e)-[r:DOCUMENTS]->(s)
RETURN toString(e.id) AS encounter_id,
       labels(s) AS node_labels,
       s.conceptId AS concept_id,
       s.name AS term,
       s.readCode AS read_code,
       s.semanticTag AS semantic_tag,
       r.evidence AS evidence,
       r.confidence AS confidence,
       r.domain AS domain,
       r.context AS context,
       r.modifiers AS modifiers,
       r.coded_at AS coded_at
ORDER BY r.coded_at DESC
"""

LIST_PATIENT_CODING_STATUS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $patient_id
OPTIONAL MATCH (e)-[r:DOCUMENTS]->(s)
WITH e, count(r) AS coded_count
RETURN toString(e.id) AS encounter_id, coded_count
"""
