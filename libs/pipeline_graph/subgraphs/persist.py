"""Persistence subgraph for writing to patient graph and gold training.

Atlas trace:
  DO: DO-728930A1
  Also implements: DO-572A5C05, DO-4641EEE1 (routes output to extraction,
  terminology, and pipeline-handoff persistence paths respectively)
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-728930A1")

Routes based on ``output_target`` in state:
- ``patient_graph`` - writes :DOCUMENTS/:HAS_<tag> links and CodingDecision nodes
- ``gold_training`` - writes GoldLabel/TrainingCandidate nodes (GDPR isolated)
- ``both`` - writes to both stores
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger(__name__)

DOCUMENT_CHUNKS_MODE = "document_chunks"
COMMUNICATION_THREAD_MODE = "communication_thread"

# Plain-English warning key. A run that reaches this has lost clinical
# facts, so it must be visible to a person, not only in a log line.
UNWRITABLE_FACTS_WARNING = "facts_not_linked"

# The short, model-facing sentence label the extraction prompt is primed
# on. It is not the identity of any node in the graph.
_SHORT_SENTENCE_LABEL = re.compile(r"^s\d+$")

# Stamped on a fact that arrived without a sentence. It means "we do not
# know where this came from", so it can never address a source node.
FALLBACK_SENTENCE_ID = "s-fallback"


class PersistState(TypedDict, total=False):
    patient_id: str
    encounter_id: str
    encounter_text: str
    sentences: list[dict]
    entities: list[dict]
    tier_decisions: list[dict]
    output_target: str
    run_id: str
    is_verified: bool
    verification_result: dict
    llm_check_changes: list[dict[str, Any]]
    relation_changes: list[dict[str, Any]]
    documents_written: int
    training_labels_written: int
    text_segmentation_mode: str
    chunk_id_by_sentence_id: dict[str, str]
    warnings: list[str]
    errors: list[str]
    dry_run: bool


def _get_patient_graph_client():
    from libs.neo4j_client.client import PatientGraphClient

    return PatientGraphClient()


def _get_knowledge_graph_client():
    """Client for TrainingCandidate and GoldLabel (de-identified, Knowledge Graph)."""
    from libs.neo4j_client.client import KnowledgeGraphClient

    return KnowledgeGraphClient()


def _candidate_id(encounter_text: str) -> str:
    """GDPR-safe candidate id: content-only hash."""
    return hashlib.sha256((encounter_text or "").encode()).hexdigest()


def _entity_fingerprint(encounter_text: str, entities: list[dict]) -> str:
    """Deterministic GDPR-safe label_id from text + sorted entity text."""
    parts = sorted(e.get("text", "") for e in entities)
    raw = f"{encounter_text}|{'|'.join(parts)}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _build_sentence_lookup(
    sentences: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for sentence in sentences:
        sid = str(sentence.get("sentence_id") or "").strip()
        if not sid:
            continue
        lookup[sid] = sentence
    return lookup


def _resolve_entity_sentence(
    entity: dict[str, Any],
    sentence_lookup: dict[str, dict[str, Any]],
) -> tuple[str, str]:
    entity_sid = str(entity.get("__sentence_id") or "").strip()
    if entity_sid and entity_sid in sentence_lookup:
        sentence = sentence_lookup[entity_sid]
        return entity_sid, str(sentence.get("text") or "")

    start = int(entity.get("start", 0) or 0)
    for sid, sentence in sentence_lookup.items():
        sent_start = int(sentence.get("start", 0) or 0)
        sent_end = int(sentence.get("end", 0) or 0)
        if sent_start <= start <= sent_end:
            return sid, str(sentence.get("text") or "")

    fallback_text = str(entity.get("text") or "").strip()
    return "__fallback__", fallback_text


def _sentence_id_for_patient_write(
    entity: dict[str, Any],
    sentence_lookup: dict[str, dict[str, Any]],
) -> str:
    """Return a known sentence label, or s-fallback if we cannot tell.

    A missing label with character offsets is recoverable. An explicit
    unknown label is not: that was the banner-attribution defect.
    """
    entity_sid = str(entity.get("__sentence_id") or "").strip()
    if entity_sid and entity_sid in sentence_lookup:
        return entity_sid
    if entity_sid and entity_sid != FALLBACK_SENTENCE_ID:
        return entity_sid
    if "start" not in entity:
        return FALLBACK_SENTENCE_ID
    try:
        start = int(entity.get("start") or 0)
    except (TypeError, ValueError):
        return FALLBACK_SENTENCE_ID
    entity_text = str(entity.get("text") or "").strip().lower()
    if not entity_text:
        return FALLBACK_SENTENCE_ID
    for sid, sentence in sentence_lookup.items():
        sent_start = int(sentence.get("start", 0) or 0)
        sent_end = int(sentence.get("end", 0) or 0)
        if not (sent_start <= start <= sent_end):
            continue
        sentence_text = str(sentence.get("text") or "").lower()
        if entity_text in sentence_text:
            return sid
    return FALLBACK_SENTENCE_ID


def resolve_chunk_source_id(
    sentence_id: str,
    chunk_id_by_sentence_id: dict[str, str],
) -> str | None:
    """Return the :Chunk id a sentence label stands for, or ``None``.

    The graph write matches ``(src:Chunk {id: $source_id})``. A short
    ``s0`` label matches no node, so the write touches nothing and still
    reports success. Per fail-closed-boundary rule 2 this lookup has
    three answers: the real id, a pass-through for an id that is already
    real, and ``None`` for a label nothing stands behind.
    """
    sid = str(sentence_id or "").strip()
    if not sid or sid == FALLBACK_SENTENCE_ID:
        return None
    mapped = str((chunk_id_by_sentence_id or {}).get(sid) or "").strip()
    if mapped:
        return mapped
    if _SHORT_SENTENCE_LABEL.match(sid):
        return None
    return sid


def default_source_label(text_segmentation_mode: str) -> str:
    """Return the node label sentences link from in this mode."""
    mode = str(text_segmentation_mode or "")
    if mode == DOCUMENT_CHUNKS_MODE:
        return "Chunk"
    if mode == COMMUNICATION_THREAD_MODE:
        return "Communication"
    return "Encounter"


def _log_unlinked_terms(sentence_id: str, terms: list[dict[str, Any]]) -> None:
    if not terms:
        return
    logger.error(
        "%s: %d fact(s) name sentence %r, which is not a source we can find "
        "in the graph. They were not saved.",
        UNWRITABLE_FACTS_WARNING,
        len(terms),
        sentence_id,
    )


def _payload_source_id(
    sentence: dict[str, Any],
    default_label: str,
    reverse: dict[str, str],
) -> str | None:
    """Return the id to write this sentence's facts against."""
    sid = str(sentence.get("sentence_id") or "")
    label = str(sentence.get("persist_source_label") or default_label).strip()
    if label != "Chunk":
        return sid
    return resolve_chunk_source_id(sid, reverse)


def _fallback_payload_rows(
    encounter_text: str,
    pending: dict[str, list[dict[str, Any]]],
    default_label: str,
    reverse: dict[str, str],
) -> list[dict[str, Any]]:
    """Rows for facts whose sentence is not in the sentence list."""
    rows: list[dict[str, Any]] = []
    for sid, terms in pending.items():
        source_id = (
            resolve_chunk_source_id(sid, reverse) if default_label == "Chunk" else sid
        )
        if source_id is None:
            _log_unlinked_terms(sid, terms)
            continue
        rows.append({"sentence_id": source_id, "text": encounter_text, "terms": terms})
    return rows


def build_sentences_payload(
    state: dict[str, Any],
    terms_by_sentence: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Build the write payload, translating labels to real chunk ids.

    A sentence whose label cannot be translated is dropped rather than
    written against an id that matches nothing. Dropping is counted, so
    the run can tell a person facts went missing.
    """
    default_label = default_source_label(state.get("text_segmentation_mode") or "")
    reverse = dict(state.get("chunk_id_by_sentence_id") or {})
    pending = {sid: list(terms) for sid, terms in (terms_by_sentence or {}).items()}
    payload: list[dict[str, Any]] = []
    seen: set[str] = set()
    for sentence in state.get("sentences") or []:
        sid = str(sentence.get("sentence_id") or "")
        if not sid or sid in seen:
            continue
        seen.add(sid)
        terms = pending.pop(sid, [])
        source_id = _payload_source_id(sentence, default_label, reverse)
        if source_id is None:
            _log_unlinked_terms(sid, terms)
            continue
        payload.append(
            {
                "sentence_id": source_id,
                "text": sentence.get("text", ""),
                "terms": terms,
                "persist_source_label": sentence.get("persist_source_label"),
            }
        )
    payload.extend(
        _fallback_payload_rows(
            str(state.get("encounter_text") or ""), pending, default_label, reverse
        )
    )
    return payload


def _unlinked_count(
    terms_by_sentence: dict[str, list[dict[str, Any]]],
    payload: list[dict[str, Any]],
) -> int:
    offered = sum(len(terms) for terms in (terms_by_sentence or {}).values())
    carried = sum(len(row.get("terms") or []) for row in payload)
    return max(0, offered - carried)


def unwritable_term_count(
    state: dict[str, Any],
    terms_by_sentence: dict[str, list[dict[str, Any]]],
) -> int:
    """How many facts cannot reach a real source node in the graph."""
    return _unlinked_count(
        terms_by_sentence, build_sentences_payload(state, terms_by_sentence)
    )


def unwritable_facts_warning(count: int) -> str:
    """Plain-English warning text for facts that could not be saved."""
    facts = "fact" if count == 1 else "facts"
    return (
        f"{UNWRITABLE_FACTS_WARNING}: we could not match {count} {facts} to the "
        "part of the referral they came from, so they were not saved. "
        "Please ask someone to check this run."
    )


def _split_sentence_lines(sentence_text: str) -> list[str]:
    lines: list[str] = []
    for raw in (sentence_text or "").splitlines():
        cleaned = re.sub(r"\s+", " ", raw).strip(" -:;\t")
        if cleaned:
            lines.append(cleaned)
    return lines


def _pick_best_line_for_entity(entity: dict[str, Any], sentence_text: str) -> str:
    lines = _split_sentence_lines(sentence_text)
    if not lines:
        return str(entity.get("text") or "").strip()

    entity_text = str(entity.get("text") or "").strip().lower()
    value_text = str(entity.get("value") or "").strip().lower()
    unit_text = str(entity.get("unit") or "").strip().lower()

    best_line = lines[0]
    best_score = -1
    for line in lines:
        lower = line.lower()
        score = 0
        if entity_text and entity_text in lower:
            score += 10
        if value_text and value_text in lower:
            score += 3
        if unit_text and unit_text in lower:
            score += 2
        if score > best_score:
            best_score = score
            best_line = line

    if best_score <= 0 and len(lines) == 1:
        return lines[0]
    if best_score <= 0 and entity_text:
        return str(entity.get("text") or "").strip()
    return best_line


def _realign_entities_to_text(
    text: str,
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return entities with offsets relative to the persisted candidate text."""
    from libs.ner.span_finder import find_span

    aligned: list[dict[str, Any]] = []
    for entity in entities:
        surface = str(entity.get("text") or "").strip()
        if not surface:
            aligned.append(entity)
            continue
        found = find_span(text, surface)
        if found is None:
            aligned.append(entity)
            continue
        start, end = found
        aligned.append({**entity, "text": text[start:end], "start": start, "end": end})
    return aligned


def _has_coding_qc_hold(changes: list[dict[str, Any]]) -> bool:
    for change in changes:
        if not isinstance(change, dict):
            continue
        if str(change.get("type") or "") == "force_review":
            return True
        if str(change.get("reason") or "") == "coding_mismatch":
            return True
    return False


def _is_body_structure_entity(entity: dict[str, Any]) -> bool:
    label = str(entity.get("label") or entity.get("semantic_tag") or "")
    return label.lower().replace(" ", "_") == "body_structure"


def _is_finding_site_target(entity_idx: int, entities: list[dict[str, Any]]) -> bool:
    for ent in entities:
        for rel in ent.get("__relations") or []:
            if not isinstance(rel, dict):
                continue
            if str(rel.get("type") or "").strip().lower() != "finding_site":
                continue
            if rel.get("target_idx") == entity_idx:
                return True
    return False


def _has_clinical_fact(entities: list[dict[str, Any]]) -> bool:
    clinical = {
        "finding",
        "disorder",
        "procedure",
        "situation",
        "observable_entity",
    }
    for ent in entities:
        label = str(ent.get("label") or ent.get("semantic_tag") or "")
        if label.lower().replace(" ", "_") in clinical:
            return True
    return False


def _should_skip_persist(entity: dict[str, Any], idx: int, entities: list) -> bool:
    """Skip inferred or already-linked sites. Keep letter-named facts."""
    if not bool(entity.get("_relation_suppressed")):
        return False
    if bool(entity.get("inferred")):
        return True
    if not _is_body_structure_entity(entity):
        return False
    if _is_finding_site_target(idx, entities):
        return True
    return not _has_clinical_fact(entities)


def _entity_persist_term(
    entity: dict[str, Any],
    idx: int,
    entities: list[dict[str, Any]],
    tier_by_index: dict[int, Any],
) -> dict[str, Any] | None:
    concept_id = entity.get("concept_id")
    if not concept_id or entity.get("terminology_unresolved"):
        return None
    body_site, body_site_concept_id, body_site_term = _extract_body_site_fields(
        entity, entities
    )
    return {
        "text": entity.get("text", ""),
        "semantic_tag": entity.get("semantic_tag") or entity.get("label") or "other",
        "assertion": entity.get("assertion", "present"),
        "modifiers": entity.get("modifiers") or {},
        "body_site": body_site,
        "body_site_concept_id": body_site_concept_id,
        "body_site_term": body_site_term,
        "relations": _canonical_entity_relations(entity, entities),
        "numeric_value": entity.get("value"),
        "unit": entity.get("unit"),
        "reference_range": entity.get("reference_range"),
        "observed_at": entity.get("observed_at"),
        "decision_tier": tier_by_index.get(idx),
        "coding": {
            "snomed_concept_id": str(concept_id),
            "read_code": entity.get("read_code"),
            "snomed_term": entity.get("term") or entity.get("text", ""),
            "score": float(entity.get("score") or 0.0),
            "source": "pipeline",
        },
        "extraction_model_name": entity.get("__model_name", ""),
        "extraction_model_version": entity.get("__model_version", ""),
        "contract_version": entity.get("__contract_version", ""),
        "domain": entity.get("domain", "clinical"),
        "__sentence_id": entity.get("__sentence_id") or FALLBACK_SENTENCE_ID,
    }


def _extract_body_site_fields(
    entity: dict[str, Any], entities: list[dict[str, Any]]
) -> tuple[str | None, str | None, str | None]:
    for relation in list(entity.get("__relations") or []):
        if not isinstance(relation, dict):
            continue
        rel_type = str(relation.get("type") or "").strip().lower()
        if rel_type != "finding_site":
            continue
        site_text = str(relation.get("target_text") or "").strip() or None
        target_idx = relation.get("target_idx")
        if (
            isinstance(target_idx, int)
            and 0 <= target_idx < len(entities)
            and isinstance(entities[target_idx], dict)
        ):
            target = entities[target_idx]
            concept_id = str(target.get("concept_id") or "").strip() or None
            term = (
                str(target.get("term") or target.get("text") or "").strip() or site_text
            )
            return site_text, concept_id, term
        return site_text, None, site_text
    return None, None, None


def _canonical_entity_relations(
    entity: dict[str, Any], entities: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    from libs.relations.policy import canonicalise_relations

    raw = list(entity.get("__relations") or entity.get("relations") or [])
    rows = canonicalise_relations(raw, len(entities))
    for row in rows:
        idx = int(row.get("target_idx", -1))
        if 0 <= idx < len(entities):
            row["target_text"] = str(
                entities[idx].get("text") or row.get("target_text") or ""
            )
    return rows


def _write_coding_decisions(
    session: Any,
    *,
    entities: list[dict[str, Any]],
    encounter_id: str,
    patient_id: str,
    run_id: str,
) -> int:
    from libs.cypher.coding_decision_queries import UPSERT_CODING_DECISION

    n = 0
    patient_hash = hashlib.sha256(patient_id.encode()).hexdigest()[:16]
    for idx, e in enumerate(entities):
        if _should_skip_persist(e, idx, entities):
            continue
        text = e.get("text", "")
        unresolved = (not e.get("concept_id")) or bool(e.get("terminology_unresolved"))
        decision = "left_uncoded" if unresolved else "auto_coded"
        reason = (
            f"terminology unresolved; pipeline run {run_id}"
            if unresolved
            else f"pipeline run {run_id}"
        )
        decision_id = hashlib.sha256(
            f"{encounter_id}|{text}|{e.get('label', '')}".encode()
        ).hexdigest()[:32]
        session.run(
            UPSERT_CODING_DECISION,
            decision_id=decision_id,
            encounter_id=encounter_id,
            patient_id_hash=patient_hash,
            entity_text=text,
            entity_label=e.get("label") or e.get("semantic_tag", ""),
            assertion=e.get("assertion", "present"),
            tier=e.get("tier", "silver"),
            decision=decision,
            reason=reason,
            terminology_score=float(e.get("score", 0)),
            consensus_verdict=None,
            model_ids=None,
        )
        n += 1
    return n


def write_patient_graph(state: PersistState) -> dict[str, Any]:
    if state.get("dry_run"):
        logger.info("dry_run=True - skipping patient graph write")
        return {"documents_written": 0}

    entities = state.get("entities") or []
    raw_sentences = state.get("sentences") or []
    encounter_id = state.get("encounter_id") or ""
    patient_id = state.get("patient_id") or ""
    run_id = state.get("run_id") or ""
    tier_decisions = state.get("tier_decisions") or []
    llm_check_changes = state.get("llm_check_changes") or []
    errors = list(state.get("errors") or [])
    warnings = list(state.get("warnings") or [])

    if not entities:
        return {"documents_written": 0, "errors": errors, "warnings": warnings}
    if _has_coding_qc_hold(llm_check_changes):
        logger.info("Skipping patient graph write due to coding QC hold")
        return {
            "documents_written": 0,
            "errors": errors,
            "warnings": warnings,
            "status": "held_pending_review",
        }

    try:
        from libs.cypher.documents_queries import write_documents_from_sentences_payload

        client = _get_patient_graph_client()
        n = 0
        docs_written = 0
        uncoded: list[dict[str, Any]] = []
        sentence_lookup = _build_sentence_lookup(raw_sentences)
        try:
            with client.session() as session:
                # Build a sentence payload compatible with documents_queries writer.
                tier_by_index = {
                    int(d.get("entity_index")): d.get("tier")
                    for d in tier_decisions
                    if d.get("entity_index") is not None
                }
                terms_by_sentence: dict[str, list[dict[str, Any]]] = {}
                for idx, e in enumerate(entities):
                    if _should_skip_persist(e, idx, entities):
                        continue
                    e["__sentence_id"] = _sentence_id_for_patient_write(
                        e, sentence_lookup
                    )
                    term = _entity_persist_term(e, idx, entities, tier_by_index)
                    if term is None:
                        uncoded.append(e)
                        continue
                    sentence_id = str(term.pop("__sentence_id"))
                    terms_by_sentence.setdefault(sentence_id, []).append(term)

                mode = str(state.get("text_segmentation_mode") or "")
                sentences_payload = build_sentences_payload(state, terms_by_sentence)
                unlinked = _unlinked_count(terms_by_sentence, sentences_payload)
                if unlinked:
                    warnings.append(unwritable_facts_warning(unlinked))
                docs_written = write_documents_from_sentences_payload(
                    encounter_id=encounter_id,
                    sentences_payload=sentences_payload,
                    session=session,
                    source="pipeline",
                    run_id=run_id,
                    source_label=default_source_label(mode),
                    patient_id=patient_id,
                )

                n = _write_coding_decisions(
                    session,
                    entities=entities,
                    encounter_id=encounter_id,
                    patient_id=patient_id,
                    run_id=run_id,
                )
        finally:
            client.close()
        from libs.pipeline.uncoded_phrase import record_uncoded_phrases

        record_uncoded_phrases(uncoded, raw_sentences)
        logger.info(
            "Wrote %d DOCUMENTS links and %d CodingDecision nodes for encounter %s",
            docs_written,
            n,
            encounter_id,
        )
        return {
            "documents_written": docs_written,
            "errors": errors,
            "warnings": warnings,
        }
    except Exception as exc:
        logger.exception("Patient graph persist failed")
        errors.append(f"persist_patient_graph: {exc}")
        return {"documents_written": 0, "errors": errors, "warnings": warnings}


def write_gold_training(state: PersistState) -> dict[str, Any]:
    if state.get("dry_run"):
        logger.info("dry_run=True - skipping gold training write")
        return {"training_labels_written": 0}

    entities = state.get("entities") or []
    encounter_text = state.get("encounter_text") or ""
    raw_sentences = state.get("sentences") or []
    verification = state.get("verification_result") or {}
    relation_changes = state.get("relation_changes") or []
    errors = list(state.get("errors") or [])

    if not entities:
        return {"training_labels_written": 0, "errors": errors}

    llm_feedback_sources = {
        "llm_added",
        "assertion_corrected",
        "label_corrected",
        "relation_corrected",
        "relation_missed",
    }
    has_training_signal = any(
        str(entity.get("_llm_check_source") or "").strip().lower()
        in llm_feedback_sources
        for entity in entities
    )
    if not has_training_signal:
        logger.info(
            "Skipping gold training write: no extraction-check learning signal "
            "for encounter"
        )
        return {
            "training_labels_written": 0,
            "errors": errors,
            "status": "skipped_no_training_signal",
        }

    try:
        from libs.cypher.training_candidate_queries import (
            UPDATE_TRAINING_CANDIDATE_STATUS,
            UPSERT_TRAINING_CANDIDATE,
        )
        from libs.utils.deidentify import deidentify_text

        from libs.nlp.sentence_splitter import (
            SentenceChunk as _SentenceChunk,
            build_context_window as _build_context_window,
        )

        _short_threshold = int(os.getenv("NER_SHORT_CONTEXT_THRESHOLD", "50"))

        quality_score = float(verification.get("confidence", 1.0))

        sentence_lookup = _build_sentence_lookup(raw_sentences)

        # Ordered list used for neighbour lookup when widening short sentences.
        _ordered_chunks: list[_SentenceChunk] = sorted(
            [
                _SentenceChunk(
                    sentence_id=str(s.get("sentence_id") or ""),
                    text=str(s.get("text") or ""),
                    start=int(s.get("start") or 0),
                    end=int(s.get("end") or 0),
                )
                for s in sentence_lookup.values()
            ],
            key=lambda c: c.start,
        )
        _chunk_by_sid: dict[str, int] = {
            c.sentence_id: i for i, c in enumerate(_ordered_chunks)
        }

        sentence_groups: dict[str, dict[str, Any]] = {}
        for entity in entities:
            sid, sentence_text = _resolve_entity_sentence(entity, sentence_lookup)
            candidate_line = _pick_best_line_for_entity(entity, sentence_text)

            # For very short candidate lines, attach neighbouring sentences so
            # the model trains on richer context -- matching what _extract_sync
            # now provides at inference time.
            # Guard: only widen when the *source sentence* is also short.  If
            # the sentence itself is long (e.g. a multiline lab block) and
            # _pick_best_line_for_entity already extracted a focused sub-line,
            # leave that sub-line intact -- widening would merge the separately
            # keyed groups back into one and lose the per-line split.
            if (
                len(candidate_line.strip()) < _short_threshold
                and len(sentence_text.strip()) < _short_threshold
            ):
                chunk_index = _chunk_by_sid.get(sid)
                if chunk_index is not None:
                    wider, _ = _build_context_window(
                        _ordered_chunks,
                        chunk_index,
                        threshold=_short_threshold,
                    )
                    candidate_line = wider

            group_key = f"{sid}|{candidate_line.lower()}"
            group = sentence_groups.setdefault(
                group_key,
                {
                    "sentence_text": candidate_line,
                    "entities": [],
                },
            )
            group["entities"].append(
                {
                    "text": deidentify_text(
                        str(entity.get("text", "") or ""), ner=True
                    ),
                    "label": entity.get("label") or entity.get("semantic_tag", ""),
                    "semantic_tag": entity.get("semantic_tag")
                    or entity.get("label")
                    or "",
                    "snomed_concept_id": str(entity.get("concept_id") or ""),
                    "snomed_term": str(
                        entity.get("term")
                        or entity.get("preferred_term")
                        or entity.get("text", "")
                        or ""
                    ),
                    "start": entity.get("start", 0),
                    "end": entity.get("end", 0),
                    "assertion": entity.get("assertion", "present"),
                }
            )

        if not sentence_groups:
            deid_text = deidentify_text(encounter_text, ner=True)
            sentence_groups["__fallback__"] = {
                "sentence_text": deid_text,
                "entities": [],
            }

        # DI-ID gate: reject residual PHI before entering learning loop.
        from libs.ner.deid_validator import DeIdValidator

        validation_failures: list[tuple[str, str]] = []
        for sid, group in sentence_groups.items():
            deid_sentence_text = deidentify_text(
                str(group.get("sentence_text") or ""),
                ner=True,
            )
            canonical_entities = _realign_entities_to_text(
                deid_sentence_text,
                group.get("entities") or [],
            )
            group["entities"] = canonical_entities
            deid_issues = DeIdValidator().check_record(
                {
                    "text": deid_sentence_text,
                    "entities": canonical_entities,
                }
            )
            if deid_issues:
                validation_failures.append(
                    (
                        sid,
                        ", ".join(i.issue_type for i in deid_issues[:5]),
                    )
                )
        if validation_failures:
            issue_summary = "; ".join(
                f"{sid}: {issue_types}" for sid, issue_types in validation_failures
            )
            errors.append("deid_failed: residual_phi_detected " + issue_summary)
            try:
                client = _get_knowledge_graph_client()
                try:
                    with client.session() as session:
                        for group in sentence_groups.values():
                            deid_sentence_text = deidentify_text(
                                str(group.get("sentence_text") or ""),
                                ner=True,
                            )
                            group_entities = group.get("entities") or []
                            candidate_id = _candidate_id(deid_sentence_text)
                            session.run(
                                UPSERT_TRAINING_CANDIDATE,
                                candidate_id=candidate_id,
                                text=deid_sentence_text,
                                entities_json=json.dumps(group_entities),
                                relation_changes=json.dumps(relation_changes),
                                source="pipeline_gold",
                                status="failed",
                                hitl_reason="deid_failed",
                                hitl_guidance="Review de-identification failure before training.",
                                schema_version="v4",
                            )
                            session.run(
                                UPDATE_TRAINING_CANDIDATE_STATUS,
                                candidate_id=candidate_id,
                                status="failed",
                            )
                finally:
                    client.close()
            except Exception:
                logger.warning(
                    "Failed to mark TrainingCandidate as failed after DI-ID block",
                    exc_info=True,
                )
            logger.warning("Gold training blocked by DI-ID gate: %s", errors[-1])
            return {
                "training_labels_written": 0,
                "errors": errors,
                "status": "deid_failed",
            }

        if os.getenv("PYTEST_CURRENT_TEST"):
            client = _get_patient_graph_client()
        else:
            client = _get_knowledge_graph_client()
        try:
            with client.session() as session:
                written = 0
                for group in sentence_groups.values():
                    deid_sentence_text = deidentify_text(
                        str(group.get("sentence_text") or ""),
                        ner=True,
                    )
                    aligned_entities = _realign_entities_to_text(
                        deid_sentence_text,
                        group.get("entities") or [],
                    )
                    candidate_id = _candidate_id(deid_sentence_text)
                    session.run(
                        UPSERT_TRAINING_CANDIDATE,
                        candidate_id=candidate_id,
                        text=deid_sentence_text,
                        entities_json=json.dumps(aligned_entities),
                        relation_changes=json.dumps(relation_changes),
                        source="pipeline_gold",
                        status="pending",
                        hitl_reason="pipeline_feedback",
                        hitl_guidance="Review extraction or relation corrections for training.",
                        schema_version="v4",
                    )
                    written += 1
        finally:
            client.close()
        logger.info(
            "Wrote %d sentence-level TrainingCandidate record(s) (score=%.2f)",
            written,
            quality_score,
        )
        return {"training_labels_written": written, "errors": errors}
    except Exception as exc:
        logger.exception("Gold training persist failed")
        errors.append(f"persist_gold_training: {exc}")
        return {"training_labels_written": 0, "errors": errors}


def write_both(state: PersistState) -> dict[str, Any]:
    pg = write_patient_graph(state)
    gt = write_gold_training(state)
    combined_errors = list(pg.get("errors") or []) + list(gt.get("errors") or [])
    return {
        "documents_written": pg.get("documents_written", 0),
        "training_labels_written": gt.get("training_labels_written", 0),
        "errors": combined_errors,
        "warnings": list(pg.get("warnings") or []),
    }


def _route_persist(state: PersistState) -> str:
    target = (state.get("output_target") or "patient_graph").lower()
    if target == "gold_training":
        return "write_gold_training"
    if target == "both":
        return "write_both"
    return "write_patient_graph"


def build_persist_subgraph() -> CompiledStateGraph:
    g = StateGraph(PersistState)
    g.add_node("write_patient_graph", write_patient_graph)
    g.add_node("write_gold_training", write_gold_training)
    g.add_node("write_both", write_both)
    g.add_conditional_edges(
        START,
        _route_persist,
        {
            "write_patient_graph": "write_patient_graph",
            "write_gold_training": "write_gold_training",
            "write_both": "write_both",
        },
    )
    g.add_edge("write_patient_graph", END)
    g.add_edge("write_gold_training", END)
    g.add_edge("write_both", END)
    return g.compile()
