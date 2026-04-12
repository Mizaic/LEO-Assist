"""DOCUMENTS relationship and semantic link queries.

Centralised from services/api/app/models/neo4j_schema.py.

write_documents_from_sentences_payload() is the shared helper used by both
the coding worker (provisional write immediately after extraction) and the
review service (authoritative write when a reviewer approves/edits).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from libs.utils.deidentify import deidentify_with_span
from libs.cypher.surface_form_task_queries import INCREMENT_SURFACE_FORM_USE

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

# Semantic tags that must never be written as DOCUMENTS relationships on a
# patient encounter. Body structures and organisms are not clinical events
# -- they are anatomy/taxonomy reference nodes. Writing them as findings
# produces noise that the audit agent then has to correct.
_BLOCKED_SEMANTIC_TAGS: frozenset[str] = frozenset(
    {
        "bodystructure",
        "body structure",
        "organism",
        "virus",
        "bacterium",
        "fungus",
        "environment or geographical location",
        "physical object",
        "record artifact",
        "namespace concept",
        "special concept",
    }
)

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

    Provenance fields (model_name, model_version, contract_version, run_id) are
    stamped on the :DOCUMENTS relationship so every persisted link can be traced
    back to the extractor that produced it.
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
SET r.coded_at         = datetime(),
    r.evidence         = $evidence,
    r.confidence       = $confidence,
    r.domain           = $domain,
    r.context          = $context,
    r.modifiers        = $modifiers,
    r.value            = $numeric_value,
    r.unit             = $unit,
    r.referenceRange   = $reference_range,
    r.source           = $source,
    r.model_name       = $model_name,
    r.model_version    = $model_version,
    r.contract_version = $contract_version,
    r.run_id           = $run_id,
    r.audit_flag       = $audit_flag,
    r.decision_tier    = $decision_tier,
    r.evidence_sentence = $evidence_sentence,
    r.evidence_start   = $evidence_start,
    r.evidence_end     = $evidence_end,
    r.sentence_index   = $sentence_index,
    r.holdout          = $holdout
FOREACH (_ IN CASE WHEN $assertion IN ['present', 'historical'] THEN [1] ELSE [] END |
  MERGE (p)-[:{rel_type}]->(s)
)
"""


_NON_PRESENT = {
    "absent",
    "refuted",
    "possible",
    "historical",
    "planned",
    "hypothetical",
    "family",
    "declined",
    "cancelled",
}


def _increment_surface_form_use(session, span_text: str) -> None:
    """Increment use_count and set first_used_at on the matching SurfaceForm node.

    Called whenever a DOCUMENTS link is written from a terminology_api source,
    indicating the surface form lookup was used in the pipeline.
    Non-blocking: failures are silently swallowed.
    """
    normalized = " ".join(span_text.strip().lower().split())
    try:
        session.run(INCREMENT_SURFACE_FORM_USE, normalized=normalized)
    except Exception:
        logger.debug(
            "_increment_surface_form_use: no SurfaceForm for %r (expected)",
            normalized,
        )


def _assertion_context(assertion: str | None) -> dict:
    """Build the context dict persisted on :DOCUMENTS from the assertion string."""
    a = assertion or "present"
    return {
        "assertion": a,
        "negated": a == "absent",
        "refuted": a == "refuted",
        "uncertain": a == "possible",
        "historical": a == "historical",
        "planned": a == "planned",
        "hypothetical": a == "hypothetical",
        "family": a == "family",
        "declined": a == "declined",
        "cancelled": a == "cancelled",
    }


def _select_evidence_sentence(sentence_text: str, span_text: str) -> str:
    """Choose the smallest sentence/line containing span_text.

    Some pipelines can pass a multi-line encounter block as sentence text.
    We still persist sentence-level evidence by shrinking to the best
    matching line/sentence before de-identification.
    """
    text = (sentence_text or "").strip()
    span = (span_text or "").strip()
    if not text or not span:
        return text

    span_lower = span.lower()
    if span_lower not in text.lower():
        return text

    lines = [ln.strip() for ln in re.split(r"\n+", text) if ln.strip()]
    line_hits = [ln for ln in lines if span_lower in ln.lower()]
    if line_hits:
        return min(line_hits, key=len)

    sentence_parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", text) if p.strip()]
    sentence_hits = [p for p in sentence_parts if span_lower in p.lower()]
    if sentence_hits:
        return min(sentence_hits, key=len)

    return text


def write_documents_from_sentences_payload(
    encounter_id: str,
    sentences_payload: list[dict[str, Any]],
    session,
    *,
    source: str = "provisional",
    model_name: str = "",
    model_version: str = "",
    contract_version: str = "",
    run_id: str = "",
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
    # Pre-scan: collect active (present-assertion) disorder/finding terms so
    # "History of X" situation codes can be suppressed when X is already active.
    _active_terms: set[str] = set()
    for _sent in sentences_payload:
        for _term in _sent.get("terms", []):
            _tag = (_term.get("semantic_tag") or "").lower()
            _assertion = (_term.get("assertion") or "present").lower()
            _coding = _term.get("coding") or {}
            _pterm = (_coding.get("snomed_term") or "").strip().lower()
            if (
                _tag in {"disorder", "finding", "clinicalfinding"}
                and _assertion == "present"
                and _pterm
            ):
                _active_terms.add(_pterm)

    written = 0
    for sentence_index, sentence in enumerate(sentences_payload):
        sentence_text = sentence.get("text") or ""
        for term in sentence.get("terms", []):
            coding = term.get("coding") or {}
            concept_id = coding.get("snomed_concept_id")
            if not concept_id:
                continue

            semantic_tag = term.get("semantic_tag") or "other"
            norm_tag = "".join(
                ch for ch in semantic_tag.lower() if ch.isalnum() or ch == " "
            ).strip()
            if norm_tag in _BLOCKED_SEMANTIC_TAGS or semantic_tag.lower().replace(
                " ", ""
            ) in {t.replace(" ", "") for t in _BLOCKED_SEMANTIC_TAGS}:
                logger.debug(
                    "Skipping write for concept %s: blocked semantic tag '%s'",
                    concept_id,
                    semantic_tag,
                )
                continue
            # Suppress "History of X (situation)" when active X is already
            # being written in this payload -- avoids redundant co-coding.
            snomed_term_lower = (coding.get("snomed_term") or "").strip().lower()
            if semantic_tag.lower() == "situation" and snomed_term_lower.startswith(
                "history of "
            ):
                underlying = (
                    snomed_term_lower.removeprefix("history of ").split("(")[0].strip()
                )
                if underlying and underlying in _active_terms:
                    logger.debug(
                        "Suppressing redundant 'History of %s' situation (active "
                        "disorder already coded in this encounter)",
                        underlying,
                    )
                    continue

            label = _label_for_tag(semantic_tag)
            rel_type = _REL_BY_LABEL.get(label, "HAS_CONCEPT")
            query = _build_upsert_query(label, rel_type)

            modifiers = term.get("modifiers") or {}
            span_text = term.get("text") or ""

            evidence_sentence: str | None = None
            evidence_start: int | None = None
            evidence_end: int | None = None
            if sentence_text and span_text:
                narrowed_sentence = _select_evidence_sentence(sentence_text, span_text)
                deident, ev_start, ev_end = deidentify_with_span(
                    narrowed_sentence, span_text
                )
                evidence_sentence = deident
                if ev_start == -1:
                    logger.debug(
                        "deidentify_with_span: span not found after deident "
                        "encounter=%s span=%r -- skipping offsets",
                        encounter_id,
                        span_text,
                    )
                else:
                    evidence_start = ev_start
                    evidence_end = ev_end

                try:
                    term_assertion = term.get("assertion") or "present"
                    term_source = coding.get("source") or source
                    session.run(
                        query,
                        encounter_id=encounter_id,
                        concept_id=str(concept_id),
                        semantic_tag=semantic_tag,
                        name=coding.get("snomed_term") or span_text,
                        read_code=coding.get("read_code"),
                        evidence=span_text,
                        confidence=float(coding.get("score") or 0.0),
                        domain=term.get("domain") or "clinical",
                        context=json.dumps(_assertion_context(term_assertion)),
                        modifiers=json.dumps(modifiers),
                        numeric_value=term.get("numeric_value") or None,
                        unit=term.get("unit") or None,
                        reference_range=term.get("reference_range") or None,
                        source=source,
                        model_name=model_name or term.get("extraction_model_name", ""),
                        model_version=model_version
                        or term.get("extraction_model_version", ""),
                        contract_version=contract_version
                        or term.get("contract_version", ""),
                        run_id=run_id,
                        audit_flag=bool(term.get("audit_flag", False)),
                        decision_tier=term.get("decision_tier"),
                        assertion=term_assertion,
                        evidence_sentence=evidence_sentence,
                        evidence_start=evidence_start,
                        evidence_end=evidence_end,
                        sentence_index=sentence_index,
                        holdout=False,
                    )
                    if term_source == "terminology_api" and span_text:
                        _increment_surface_form_use(session, span_text)
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
WHERE toString(s.conceptId) = toString($concept_id)
   OR toString(r.conceptId) = toString($concept_id)
WITH collect(r) AS rels
WITH rels, size(rels) AS deleted
UNWIND rels AS rel
DELETE rel
RETURN deleted
"""

UPDATE_CODED_LINK_MODIFIERS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $patient_id AND toString(e.id) = $encounter_id
MATCH (e)-[r:DOCUMENTS]->(s)
WHERE toString(s.conceptId) = toString($concept_id)
   OR toString(r.conceptId) = toString($concept_id)
SET r.modifiers = $modifiers
RETURN toString(s.conceptId) AS concept_id, r.modifiers AS modifiers
"""

LIST_ENCOUNTER_CODED_LINKS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $patient_id AND toString(e.id) = $encounter_id
OPTIONAL MATCH (e)-[r:DOCUMENTS]->(s)
RETURN toString(e.id) AS encounter_id,
       labels(s) AS node_labels,
       toString(s.conceptId) AS concept_id,
       s.name AS term,
       s.readCode AS read_code,
       s.semanticTag AS semantic_tag,
       r.evidence AS evidence,
       r.evidence_sentence AS evidence_sentence,
       r.sentence_index AS sentence_index,
       r.evidence_start AS evidence_start,
       r.evidence_end AS evidence_end,
       r.value AS value,
       r.unit AS unit,
       r.referenceRange AS reference_range,
       r.confidence AS confidence,
       r.domain AS domain,
       r.source AS source,
       r.model_name AS model_name,
       r.model_version AS model_version,
       r.contract_version AS contract_version,
       r.run_id AS run_id,
       r.context AS context,
       r.modifiers AS modifiers,
       r.coded_at AS coded_at,
       r.audit_flag AS audit_flag,
       r.decision_tier AS decision_tier
ORDER BY r.coded_at DESC
"""

LIST_PATIENT_CODING_STATUS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $patient_id
OPTIONAL MATCH (e)-[r:DOCUMENTS]->(s)
WITH e, count(r) AS coded_count
RETURN toString(e.id) AS encounter_id, coded_count
"""

GET_PATIENT_CODING_TIMELINE = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->(s)
WHERE toString(p.id) = $patient_id AND e.date IS NOT NULL
RETURN e.date            AS encounter_date,
       toString(e.id)    AS encounter_id,
       s.conceptId       AS concept_id,
       s.name            AS term,
       s.semanticTag     AS semantic_tag,
       s.readCode        AS read_code,
       r.context         AS context_json,
       r.confidence      AS confidence,
       r.domain          AS domain,
       r.decision_tier   AS decision_tier
ORDER BY e.date ASC
"""
