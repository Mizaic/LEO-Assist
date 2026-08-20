"""DOCUMENTS relationship and semantic link queries.

Atlas trace:
  DO: DO-728930A1
  DI: DI-F71A6A69 (clinical facts storage); DI-79D15317 (deadlock retry)
  VT: VT-53AEAC08
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-728930A1")

Centralised from services/api/app/models/neo4j_schema.py.

write_documents_from_sentences_payload() is the shared helper used by both
the coding worker (provisional write immediately after extraction) and the
review service (authoritative write when a reviewer approves/edits).

upsert_encounter_documents_link() is the same write path for batch/deterministic
scripts that already have a patient and encounter id (toString-matched).
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
from dataclasses import dataclass
from typing import Any

from neo4j.exceptions import TransientError

from libs.cypher.surface_form_task_queries import INCREMENT_SURFACE_FORM_USE
from libs.utils.deidentify import deidentify_with_span

logger = logging.getLogger(__name__)

# Concurrent workers MERGEing the same SNOMED concept node can deadlock when
# lock order differs. All writers sort by concept_id before MERGE; retries
# cover residual cross-patient contention on shared concept nodes.
_DOC_WRITE_MAX_RETRIES = 6
_DOC_WRITE_BASE_DELAY_S = 0.05
_DOC_WRITE_MAX_JITTER_S = 0.08


def _is_neo4j_deadlock(exc: BaseException) -> bool:
    """True when Neo4j reports a transient deadlock (retryable)."""
    if isinstance(exc, TransientError):
        code = str(getattr(exc, "code", "") or "")
        if "DeadlockDetected" in code:
            return True
    return "DeadlockDetected" in str(exc)


def _doc_write_backoff_delay(attempt: int) -> float:
    """Exponential backoff with jitter for deadlock retries."""
    return _DOC_WRITE_BASE_DELAY_S * (2**attempt) + random.uniform(
        0, _DOC_WRITE_MAX_JITTER_S
    )


def _session_run_with_deadlock_retry(session: Any, query: str, **params: Any) -> None:
    """Run a Cypher write, retrying Neo4j deadlocks with short backoff."""
    concept_id = str(params.get("concept_id") or "")
    last_exc: BaseException | None = None
    for attempt in range(_DOC_WRITE_MAX_RETRIES):
        try:
            session.run(query, **params)
            if attempt > 0:
                logger.debug(
                    "Neo4j DOCUMENTS write succeeded after %d deadlock retries "
                    "concept_id=%s",
                    attempt,
                    concept_id,
                )
            return
        except Exception as exc:
            last_exc = exc
            if not _is_neo4j_deadlock(exc) or attempt >= _DOC_WRITE_MAX_RETRIES - 1:
                if _is_neo4j_deadlock(exc):
                    logger.warning(
                        "Neo4j deadlock on DOCUMENTS write failed after %d attempts "
                        "concept_id=%s",
                        _DOC_WRITE_MAX_RETRIES,
                        concept_id,
                    )
                raise
            delay = _doc_write_backoff_delay(attempt)
            logger.debug(
                "Neo4j deadlock on DOCUMENTS write (attempt %d/%d) "
                "concept_id=%s -- retry in %.2fs",
                attempt + 1,
                _DOC_WRITE_MAX_RETRIES,
                concept_id,
                delay,
            )
            time.sleep(delay)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("DOCUMENTS write failed after deadlock retries")


def _dedupe_pending_writes(pending: list[_PendingDocWrite]) -> list[_PendingDocWrite]:
    """Keep one write per (source, concept). Higher confidence wins."""
    best: dict[tuple[str, str], _PendingDocWrite] = {}
    for item in pending:
        cid = str(item.params.get("concept_id") or "").strip()
        src = str(item.params.get("source_id") or "")
        item.params["concept_id"] = cid
        key = (src, cid)
        prev = best.get(key)
        if prev is None:
            best[key] = item
            continue
        prev_conf = float(prev.params.get("confidence") or 0.0)
        if float(item.params.get("confidence") or 0.0) > prev_conf:
            best[key] = item
    return list(best.values())


def _doc_write_sort_key(
    concept_id: str,
    link_source_id: str,
    sentence_index: int,
) -> tuple[str, str, int]:
    """Stable lock order: concept node, then source, then sentence index."""
    return (str(concept_id), str(link_source_id), int(sentence_index))


@dataclass(frozen=True)
class _PendingDocWrite:
    sort_key: tuple[str, str, int]
    query: str
    params: dict[str, Any]
    surface_form_span: str | None = None


# Maps normalised semantic tag → Neo4j node label (mirrors patient_graph_writer.py)
_LABEL_BY_TAG: dict[str, str] = {
    "situation": "Situation",
    "clinicalfinding": "Clinical_finding",
    "finding": "Clinical_finding",
    # UK ethnicity census concepts often carry SNOMED semantic tag Ethnic_group.
    # Persist them as typed Clinical_finding nodes so DOCUMENTS + HAS_FINDING matches other demographics findings.
    "ethnicgroup": "Clinical_finding",
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
# body structure was removed from this set to allow reproductive anatomy
# SNOMED concepts (cervix, uterus, ovary, prostate, testis, fallopian tube)
# to be persisted for gender/anatomy conflict detection (DI-9AA2CDA5).
_BLOCKED_SEMANTIC_TAGS: frozenset[str] = frozenset(
    {
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


_VALID_SOURCE_LABELS: frozenset[str] = frozenset(
    {"Encounter", "Chunk", "Communication"}
)


def _build_upsert_query(
    label: str,
    rel_type: str,
    *,
    source_label: str = "Encounter",
) -> str:
    """Return a Cypher query that:
    1. MERGEs the concept node with the given label.
    2. MERGEs (source)-[:DOCUMENTS]->(concept) where source is Encounter or Chunk.
    3. MERGEs (Patient)-[:<rel_type>]->(concept) as a patient-level shortcut.

    The source can be an :Encounter (existing pattern) or a :Chunk (new in
    DI-LEO-AI-185, used when DocumentReference text is split into sentences
    that each carry their own SNOMED codes). When source_label is ``Chunk``
    the patient is reached via the parent DocumentReference.

    Provenance fields (model_name, model_version, contract_version, run_id) are
    stamped on the :DOCUMENTS relationship so every persisted link can be traced
    back to the extractor that produced it.
    """
    if source_label not in _VALID_SOURCE_LABELS:
        raise ValueError(
            f"Unsupported source_label {source_label!r}. "
            f"Allowed: {sorted(_VALID_SOURCE_LABELS)}"
        )

    if source_label == "Encounter":
        match_clause = (
            "MATCH (src:Encounter {id: $source_id})" "<-[:HAS_ENCOUNTER]-(p:Patient)"
        )
    elif source_label == "Communication":
        match_clause = (
            "MATCH (src:Communication {id: $source_id})"
            "<-[:HAS_CONVERSATION]-(:CommunicationRequest)"
            "-[:FOR_PATIENT]->(p:Patient)"
        )
    else:
        # For Chunk sources, the Patient-level shortcut is opportunistic:
        # the chunk's parent DocumentReference is not always linked back
        # to a Patient yet. Use OPTIONAL MATCH so missing shortcut paths
        # do not block the :DOCUMENTS write.
        match_clause = (
            "MATCH (src:Chunk {id: $source_id}) "
            "OPTIONAL MATCH (src)<-[:HAS_CHUNK]-(:DocumentReference)"
            "<-[:HAS_DOCUMENT_REFERENCE|HAS_DOCUMENT]-(p)"
        )

    return f"""
{match_clause}
MERGE (s:{label} {{conceptId: $concept_id}})
SET s.semanticTag  = $semantic_tag,
    s.name         = $name,
    s.readCode     = $read_code,
    s.source       = $source,
    s.updated_at   = datetime(),
    s.created_at   = coalesce(s.created_at, datetime())
MERGE (src)-[r:DOCUMENTS {{conceptId: $concept_id}}]->(s)
SET r.coded_at         = datetime(),
    r.evidence         = $evidence,
    r.confidence       = $confidence,
    r.domain           = $domain,
    r.context          = $context,
    r.modifiers        = $modifiers,
    r.body_site        = $body_site,
    r.body_site_concept_id = $body_site_concept_id,
    r.body_site_term   = $body_site_term,
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
FOREACH (_ IN CASE WHEN p IS NOT NULL AND $assertion IN ['present', 'historical'] THEN [1] ELSE [] END |
  MERGE (p)-[:{rel_type}]->(s)
)
"""


def _build_upsert_query_patient_encounter(
    label: str,
    rel_type: str,
) -> str:
    """Like _build_upsert_query for :Encounter, but match via patient + encounter ids.

    Uses the same toString() equality as deterministic batch scripts so
    :Encounter id storage (string vs int) does not break the MATCH.
    """
    return f"""
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $patient_id AND toString(e.id) = $encounter_id
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
    r.body_site        = $body_site,
    r.body_site_concept_id = $body_site_concept_id,
    r.body_site_term   = $body_site_term,
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
FOREACH (_ IN CASE WHEN p IS NOT NULL AND $assertion IN ['present', 'historical'] THEN [1] ELSE [] END |
  MERGE (p)-[:{rel_type}]->(s)
)
"""


def upsert_encounter_documents_link(
    session: Any,
    patient_id: str,
    encounter_id: str,
    concept_id: str,
    semantic_tag: str,
    name: str,
    evidence: str,
    *,
    read_code: str | None = None,
    evidence_sentence: str | None = None,
    assertion: str = "present",
    modifiers: dict[str, Any] | None = None,
    source: str = "provisional",
    model_name: str = "",
    model_version: str = "",
    contract_version: str = "",
    run_id: str = "",
    domain: str = "clinical",
    confidence: float = 0.0,
    numeric_value: float | None = None,
    unit: str | None = None,
    reference_range: str | None = None,
) -> bool:
    """One encounter-level DOCUMENTS write plus patient HAS_* when assertion allows.

    Matches ``write_documents_from_sentences_payload`` (typed SNOMED node, full
    relationship provenance, FOREACH for present/historical). Returns False if
    ``semantic_tag`` is blocked and nothing was written.
    """
    st = (semantic_tag or "").strip()
    norm_tag = "".join(ch for ch in st.lower() if ch.isalnum() or ch == " ").strip()
    if norm_tag in _BLOCKED_SEMANTIC_TAGS or st.lower().replace(" ", "") in {
        t.replace(" ", "") for t in _BLOCKED_SEMANTIC_TAGS
    }:
        logger.debug(
            "upsert_encounter_documents_link: blocked semantic tag %r", semantic_tag
        )
        return False
    label = _label_for_tag(semantic_tag)
    rel_type = _REL_BY_LABEL.get(label, "HAS_CONCEPT")
    query = _build_upsert_query_patient_encounter(label, rel_type)
    span = evidence or ""
    ev_sentence = evidence_sentence if evidence_sentence is not None else span
    term_assertion = assertion or "present"
    conf = float(confidence) if confidence else 0.0
    _session_run_with_deadlock_retry(
        session,
        query,
        patient_id=patient_id,
        encounter_id=encounter_id,
        concept_id=str(concept_id),
        semantic_tag=semantic_tag,
        name=name,
        read_code=read_code,
        evidence=span,
        confidence=conf,
        domain=domain,
        context=json.dumps(_assertion_context(term_assertion)),
        modifiers=json.dumps(modifiers or {}),
        body_site=None,
        body_site_concept_id=None,
        body_site_term=None,
        numeric_value=numeric_value,
        unit=unit,
        reference_range=reference_range,
        source=source,
        model_name=model_name,
        model_version=model_version,
        contract_version=contract_version,
        run_id=run_id,
        audit_flag=False,
        decision_tier="auto",
        assertion=term_assertion,
        evidence_sentence=ev_sentence,
        evidence_start=0,
        evidence_end=len(span) if span else 0,
        sentence_index=0,
        holdout=False,
    )
    return True


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


def _collect_pending_document_writes(
    encounter_id: str,
    sentences_payload: list[dict[str, Any]],
    *,
    source: str,
    model_name: str,
    model_version: str,
    contract_version: str,
    run_id: str,
    source_label: str,
    active_terms: set[str],
) -> list[_PendingDocWrite]:
    """Build DOCUMENTS upserts sorted for consistent Neo4j lock acquisition."""
    pending: list[_PendingDocWrite] = []
    for sentence_index, sentence in enumerate(sentences_payload):
        sentence_text = sentence.get("text") or ""
        sentence_source_id = str(sentence.get("sentence_id") or encounter_id).strip()
        sentence_source_label = str(
            sentence.get("persist_source_label") or source_label
        ).strip()
        if sentence_source_label == "Chunk":
            link_source_id = sentence_source_id
        elif sentence_source_label == "Communication":
            link_source_id = sentence_source_id
        else:
            link_source_id = encounter_id
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
            snomed_term_lower = (coding.get("snomed_term") or "").strip().lower()
            if semantic_tag.lower() == "situation" and snomed_term_lower.startswith(
                "history of "
            ):
                underlying = (
                    snomed_term_lower.removeprefix("history of ").split("(")[0].strip()
                )
                if underlying and underlying in active_terms:
                    logger.debug(
                        "Suppressing redundant 'History of %s' situation (active "
                        "disorder already coded in this encounter)",
                        underlying,
                    )
                    continue

            if not sentence_text or not (term.get("text") or ""):
                continue

            label = _label_for_tag(semantic_tag)
            rel_type = _REL_BY_LABEL.get(label, "HAS_CONCEPT")
            query = _build_upsert_query(
                label, rel_type, source_label=sentence_source_label
            )
            span_text = term.get("text") or ""
            narrowed_sentence = _select_evidence_sentence(sentence_text, span_text)
            deident, ev_start, ev_end = deidentify_with_span(
                narrowed_sentence, span_text
            )
            evidence_sentence = deident
            evidence_start: int | None = None
            evidence_end: int | None = None
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

            term_assertion = term.get("assertion") or "present"
            term_source = coding.get("source") or source
            modifiers = term.get("modifiers") or {}
            surface_form_span = span_text if term_source == "terminology_api" else None

            sort_key = _doc_write_sort_key(
                str(concept_id), link_source_id, sentence_index
            )
            pending.append(
                _PendingDocWrite(
                    sort_key=sort_key,
                    query=query,
                    params={
                        "source_id": link_source_id,
                        "concept_id": str(concept_id),
                        "semantic_tag": semantic_tag,
                        "name": coding.get("snomed_term") or span_text,
                        "read_code": coding.get("read_code"),
                        "evidence": span_text,
                        "confidence": float(coding.get("score") or 0.0),
                        "domain": term.get("domain") or "clinical",
                        "context": json.dumps(_assertion_context(term_assertion)),
                        "modifiers": json.dumps(modifiers),
                        "body_site": term.get("body_site"),
                        "body_site_concept_id": term.get("body_site_concept_id"),
                        "body_site_term": term.get("body_site_term"),
                        "numeric_value": term.get("numeric_value") or None,
                        "unit": term.get("unit") or None,
                        "reference_range": term.get("reference_range") or None,
                        "source": source,
                        "model_name": model_name
                        or term.get("extraction_model_name", ""),
                        "model_version": model_version
                        or term.get("extraction_model_version", ""),
                        "contract_version": contract_version
                        or term.get("contract_version", ""),
                        "run_id": run_id,
                        "audit_flag": bool(term.get("audit_flag", False)),
                        "decision_tier": term.get("decision_tier"),
                        "assertion": term_assertion,
                        "evidence_sentence": evidence_sentence,
                        "evidence_start": evidence_start,
                        "evidence_end": evidence_end,
                        "sentence_index": sentence_index,
                        "holdout": False,
                    },
                    surface_form_span=surface_form_span,
                )
            )
    pending = _dedupe_pending_writes(pending)
    pending.sort(key=lambda item: item.sort_key)
    return pending


def _execute_pending_document_writes(
    session: Any,
    pending: list[_PendingDocWrite],
    *,
    encounter_id: str,
) -> int:
    """Run sorted DOCUMENTS upserts; return count written."""
    written = 0
    for item in pending:
        concept_id = item.params.get("concept_id")
        try:
            _session_run_with_deadlock_retry(session, item.query, **item.params)
            if item.surface_form_span:
                _increment_surface_form_use(session, item.surface_form_span)
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
    source_label: str = "Encounter",
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
    active_terms: set[str] = set()
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
                active_terms.add(_pterm)

    pending = _collect_pending_document_writes(
        encounter_id,
        sentences_payload,
        source=source,
        model_name=model_name,
        model_version=model_version,
        contract_version=contract_version,
        run_id=run_id,
        source_label=source_label,
        active_terms=active_terms,
    )
    return _execute_pending_document_writes(session, pending, encounter_id=encounter_id)


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
       coalesce(s.name, s.term) AS term,
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
       r.body_site AS body_site,
       r.body_site_concept_id AS body_site_concept_id,
       r.body_site_term AS body_site_term,
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

GET_ENCOUNTERS_PAGE = """
MATCH (e:Encounter)
WHERE e.text IS NOT NULL
  AND NOT (e)-[:DOCUMENTS {source: 'lab_coder_v1'}]->()
RETURN toString(e.id) AS encounter_id, e.text AS text
ORDER BY e.id
SKIP $skip LIMIT $limit
"""

GET_ENCOUNTERS_PAGE_TOTAL = """
MATCH (e:Encounter)
WHERE e.text IS NOT NULL
  AND NOT (e)-[:DOCUMENTS {source: 'lab_coder_v1'}]->()
RETURN count(e) AS total
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
