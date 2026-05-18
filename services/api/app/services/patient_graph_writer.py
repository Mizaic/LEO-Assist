"""Write and read semantic DOCUMENTS links in patient graph.

Atlas trace:
  DO: DO-92F92EFB
  DI: DI-88C1715A
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-92F92EFB")
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

_LABEL_BY_TAG = {
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


def _label_for_tag(tag: str) -> str:
    normalized = "".join(ch for ch in tag.lower() if ch.isalnum())
    return _LABEL_BY_TAG.get(normalized, "SnomedConcept")


def _upsert_query(label: str) -> str:
    return f"""
MATCH (e:Encounter {{id: $encounter_id}})
MERGE (s:{label} {{conceptId: $concept_id}})
SET s.semanticTag = $semantic_tag,
    s.name = $name,
    s.readCode = $read_code,
    s.source = $source,
    s.updated_at = datetime(),
    s.created_at = coalesce(s.created_at, datetime())
MERGE (e)-[r:DOCUMENTS {{conceptId: $concept_id}}]->(s)
SET r.coded_at = datetime(),
    r.evidence = $evidence,
    r.confidence = $confidence,
    r.domain = $domain,
    r.context = $context,
    r.modifiers = $modifiers,
    r.source = $source
"""


LIST_ENCOUNTER_CODED_LINKS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $patient_id AND toString(e.id) = $encounter_id
OPTIONAL MATCH (e)-[r:DOCUMENTS]->(s)
RETURN toString(e.id) AS encounter_id,
       labels(s) AS node_labels,
       s.conceptId AS concept_id,
       coalesce(s.name, s.term) AS term,
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


@dataclass(frozen=True)
class SemanticLinkPayload:
    encounter_id: str
    semantic_tag: str
    concept_id: str
    term: str | None
    read_code: str | None
    evidence: str
    confidence: float
    domain: str
    context: dict[str, Any]
    modifiers: dict[str, Any]
    source: str


class PatientGraphWriter:
    def upsert_documents_link(self, payload: SemanticLinkPayload, *, session) -> None:
        if not payload.concept_id:
            return
        label = _label_for_tag(payload.semantic_tag)
        session.run(
            _upsert_query(label),
            encounter_id=payload.encounter_id,
            semantic_tag=payload.semantic_tag,
            concept_id=payload.concept_id,
            name=payload.term,
            read_code=payload.read_code,
            evidence=payload.evidence,
            confidence=float(payload.confidence),
            domain=payload.domain,
            context=json.dumps(payload.context) if payload.context else "{}",
            modifiers=json.dumps(payload.modifiers) if payload.modifiers else "{}",
            source=payload.source,
        )

    def delete_documents_link(
        self,
        *,
        encounter_id: str,
        concept_id: str,
        patient_id: str,
        session,
    ) -> None:
        from app.models.neo4j_schema import DELETE_CODED_LINK

        result = session.run(
            DELETE_CODED_LINK,
            patient_id=patient_id,
            encounter_id=encounter_id,
            concept_id=concept_id,
        )
        row = result.single()
        deleted = int(row["deleted"]) if row and "deleted" in row else 0
        if deleted == 0:
            raise ValueError("coded_link_not_found")

    def recode_documents_link(
        self,
        *,
        patient_id: str,
        old_concept_id: str,
        new_payload: SemanticLinkPayload,
        session,
    ) -> None:
        self.delete_documents_link(
            encounter_id=new_payload.encounter_id,
            concept_id=old_concept_id,
            patient_id=patient_id,
            session=session,
        )
        self.upsert_documents_link(new_payload, session=session)
