"""Persistence subgraph for writing to patient graph and gold training.

Atlas trace:
  DO: DO-8620A68B
  Also implements: DO-93E086B0
  DI: DI-2D9F5064, DI-5A802C83, DI-F2C18D2E
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-8620A68B")

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
    errors: list[str]


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
            row["target_text"] = str(entities[idx].get("text") or row.get("target_text") or "")
    return rows


def write_patient_graph(state: PersistState) -> dict[str, Any]:
    if state.get("dry_run"):
        logger.info("dry_run=True - skipping patient graph write")
        return {"documents_written": 0}

    entities = state.get("entities") or []
    raw_sentences = state.get("sentences") or []
    encounter_text = state.get("encounter_text") or ""
    encounter_id = state.get("encounter_id") or ""
    patient_id = state.get("patient_id") or ""
    run_id = state.get("run_id") or ""
    tier_decisions = state.get("tier_decisions") or []
    llm_check_changes = state.get("llm_check_changes") or []
    errors = list(state.get("errors") or [])

    if not entities:
        return {"documents_written": 0, "errors": errors}
    if _has_coding_qc_hold(llm_check_changes):
        logger.info("Skipping patient graph write due to coding QC hold")
        return {
            "documents_written": 0,
            "errors": errors,
            "status": "held_pending_review",
        }

    try:
        from libs.cypher.coding_decision_queries import UPSERT_CODING_DECISION
        from libs.cypher.documents_queries import write_documents_from_sentences_payload

        client = _get_patient_graph_client()
        n = 0
        docs_written = 0
        try:
            with client.session() as session:
                # Build a sentence payload compatible with documents_queries writer.
                tier_by_index = {
                    int(d.get("entity_index")): d.get("tier")
                    for d in tier_decisions
                    if d.get("entity_index") is not None
                }
                terms_by_sentence: dict[str, list[dict[str, Any]]] = {}
                fallback_sentence_id = "s-fallback"
                for idx, e in enumerate(entities):
                    if bool(e.get("_relation_suppressed")):
                        continue
                    concept_id = e.get("concept_id")
                    if not concept_id or e.get("terminology_unresolved"):
                        continue
                    sentence_id = e.get("__sentence_id") or fallback_sentence_id
                    body_site, body_site_concept_id, body_site_term = (
                        _extract_body_site_fields(e, entities)
                    )
                    terms_by_sentence.setdefault(sentence_id, []).append(
                        {
                            "text": e.get("text", ""),
                            "semantic_tag": e.get("semantic_tag")
                            or e.get("label")
                            or "other",
                            "assertion": e.get("assertion", "present"),
                            "modifiers": e.get("modifiers") or {},
                            "body_site": body_site,
                            "body_site_concept_id": body_site_concept_id,
                            "body_site_term": body_site_term,
                            "relations": _canonical_entity_relations(e, entities),
                            "numeric_value": e.get("value"),
                            "unit": e.get("unit"),
                            "reference_range": e.get("reference_range"),
                            "decision_tier": tier_by_index.get(idx),
                            "coding": {
                                "snomed_concept_id": str(concept_id),
                                "read_code": e.get("read_code"),
                                "snomed_term": e.get("term") or e.get("text", ""),
                                "score": float(e.get("score") or 0.0),
                                "source": "pipeline",
                            },
                            "extraction_model_name": e.get("__model_name", ""),
                            "extraction_model_version": e.get("__model_version", ""),
                            "contract_version": e.get("__contract_version", ""),
                            "domain": e.get("domain", "clinical"),
                        }
                    )

                sentences_payload: list[dict[str, Any]] = []
                seen_ids: set[str] = set()
                for s in raw_sentences:
                    sid = str(s.get("sentence_id") or "")
                    if not sid or sid in seen_ids:
                        continue
                    seen_ids.add(sid)
                    sentences_payload.append(
                        {
                            "sentence_id": sid,
                            "text": s.get("text", ""),
                            "terms": terms_by_sentence.pop(sid, []),
                        }
                    )
                # Include any terms that did not carry a sentence_id.
                for sid, terms in terms_by_sentence.items():
                    fallback_text = encounter_text
                    sentences_payload.append(
                        {"sentence_id": sid, "text": fallback_text, "terms": terms}
                    )

                source_label = (
                    "Chunk"
                    if str(state.get("text_segmentation_mode") or "")
                    == "document_chunks"
                    else "Encounter"
                )
                docs_written = write_documents_from_sentences_payload(
                    encounter_id=encounter_id,
                    sentences_payload=sentences_payload,
                    session=session,
                    source="pipeline",
                    run_id=run_id,
                    source_label=source_label,
                )

                for e in entities:
                    if bool(e.get("_relation_suppressed")):
                        continue
                    text = e.get("text", "")
                    decision_id = hashlib.sha256(
                        f"{encounter_id}|{text}|{e.get('label', '')}".encode()
                    ).hexdigest()[:32]
                    session.run(
                        UPSERT_CODING_DECISION,
                        decision_id=decision_id,
                        encounter_id=encounter_id,
                        patient_id_hash=hashlib.sha256(patient_id.encode()).hexdigest()[
                            :16
                        ],
                        entity_text=text,
                        entity_label=e.get("label") or e.get("semantic_tag", ""),
                        assertion=e.get("assertion", "present"),
                        tier=e.get("tier", "silver"),
                        decision="auto_coded",
                        reason=f"pipeline run {run_id}",
                        terminology_score=float(e.get("score", 0)),
                        consensus_verdict=None,
                        model_ids=None,
                    )
                    n += 1
        finally:
            client.close()
        logger.info(
            "Wrote %d DOCUMENTS links and %d CodingDecision nodes for encounter %s",
            docs_written,
            n,
            encounter_id,
        )
        return {"documents_written": docs_written, "errors": errors}
    except Exception as exc:
        logger.exception("Patient graph persist failed")
        errors.append(f"persist_patient_graph: {exc}")
        return {"documents_written": 0, "errors": errors}


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

        _short_threshold = int(
            os.getenv("NER_SHORT_CONTEXT_THRESHOLD", "50")
        )

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
