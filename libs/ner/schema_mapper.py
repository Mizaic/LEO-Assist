"""Full target-schema mapper for NER training records.

Converts raw extraction dicts (as produced by mine_all_domains.py) into the
canonical training schema:

    {
        "document_id":  str,   # stable, deterministic
        "text":         str,   # de-identified sentence text
        "entities":     [...], # full entity objects with validated offsets
        "relations":    [...], # relation objects
        "metadata":     {...}
    }

Entity labels are validated against VALID_LABELS.  Offsets are verified so
that text[start:end] == entity.text.  Malformed records are returned as
rejected items with structured reasons.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

# ---------------------------------------------------------------------------
# Canonical label enum
# ---------------------------------------------------------------------------
VALID_LABELS: frozenset[str] = frozenset(
    {
        # Clinical semantic types (SNOMED hierarchy)
        "disorder",
        "finding",
        "procedure",
        "observable_entity",
        "qualifier_value",
        "substance",
        "medicinal_product",
        "clinical_drug",
        "situation",
        "event",
        "body_structure",
        "tumor_staging",
        "assessment_scale",
        "staging_scale",
        "regime_therapy",
        "record_artifact",
        "physical_object",
        "organism",
        "morphologic_abnormality",
        "occupation",
        "attribute",
        "environment",
        "product",
        # Modifier / context labels
        "X_TEMPORAL",
        "X_DOSAGE",
        "X_FREQUENCY",
        "X_ROUTE",
    }
)

# Map legacy / alternate label spellings to canonical form
_LABEL_NORMALISATION: dict[str, str] = {
    "observation": "observable_entity",
    "obs": "observable_entity",
    "clinical_finding": "finding",
    "morphologic_abnormality": "morphologic_abnormality",
    "morphologic abnormality": "morphologic_abnormality",
    "body structure": "body_structure",
    "body_part": "body_structure",
    "observable entity": "observable_entity",
    "substance_use": "substance",
    "medicinal product": "medicinal_product",
    "clinical drug": "clinical_drug",
    "qualifier": "qualifier_value",
    "tumor staging": "tumor_staging",
    "tumour staging": "tumor_staging",
    "regime/therapy": "regime_therapy",
    "record artifact": "record_artifact",
    "physical object": "physical_object",
    "assessment scale": "assessment_scale",
    "staging scale": "staging_scale",
    "attribute": "attribute",
    "occupation": "occupation",
    "environment": "environment",
    "product": "product",
    "context_dependent": "situation",
}

# Canonical NER label -> SNOMED semantic tag (inverse of _LABEL_NORMALISATION
# for the subset that differs between our underscore schema and SNOMED's
# space-separated convention).  Used by the pipeline and label verifier to
# pass expected_tags into the terminology resolver so it can boost/penalise
# candidates by semantic tag.
LABEL_TO_SNOMED_TAG: dict[str, str] = {
    "disorder": "disorder",
    "finding": "finding",
    "situation": "situation",
    "procedure": "procedure",
    "substance": "substance",
    "product": "product",
    "regime_therapy": "regime/therapy",
    "medicinal_product": "medicinal product",
    "clinical_drug": "clinical drug",
    "observable_entity": "observable entity",
    "qualifier_value": "qualifier value",
    "body_structure": "body structure",
    "assessment_scale": "assessment scale",
    "staging_scale": "staging scale",
    "tumor_staging": "tumor staging",
    "record_artifact": "record artifact",
    "physical_object": "physical object",
    "morphologic_abnormality": "morphologic abnormality",
    "organism": "organism",
    "occupation": "occupation",
    "attribute": "attribute",
    "environment": "environment",
    "event": "event",
}

# Canonical relation type enum
VALID_RELATION_TYPES: frozenset[str] = frozenset(
    {
        "negates",
        "temporal_of",
        "associated_finding",
        "location_of",
        "triggers",
        "qualifies",
        "route_of",
        "dose_of",
        "frequency_of",
        "caused_by",
        "part_of",
    }
)


# ---------------------------------------------------------------------------
# Deterministic ID helpers
# ---------------------------------------------------------------------------

def _stable_document_id(encounter_id: str, sentence_id: str) -> str:
    """SHA-256 truncated to 16 hex chars, prefixed with 'doc_'."""
    raw = f"{encounter_id}|{sentence_id}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"doc_{digest}"


def _stable_entity_id(document_id: str, start: int, end: int, label: str) -> str:
    raw = f"{document_id}|{start}|{end}|{label}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10]
    return f"e_{digest}"


def _stable_relation_id(document_id: str, head_id: str, tail_id: str, rel_type: str) -> str:
    raw = f"{document_id}|{head_id}|{tail_id}|{rel_type}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10]
    return f"r_{digest}"


# ---------------------------------------------------------------------------
# Label normalisation
# ---------------------------------------------------------------------------

def normalise_label(raw_label: str | None) -> str | None:
    """Return canonical label or None if unrecognised."""
    if not raw_label:
        return None
    canon = _LABEL_NORMALISATION.get(raw_label.strip().lower())
    if canon:
        return canon
    if raw_label in VALID_LABELS:
        return raw_label
    # Try lowercase match
    for v in VALID_LABELS:
        if raw_label.lower() == v.lower():
            return v
    return None


# ---------------------------------------------------------------------------
# Offset verification
# ---------------------------------------------------------------------------

def _verify_offset(text: str, start: int, end: int, entity_text: str) -> bool:
    """Return True iff text[start:end] matches entity_text (whitespace-normalised)."""
    if start < 0 or end > len(text) or start >= end:
        return False
    span = text[start:end]
    # Accept exact match or single-space-collapsed match
    return span == entity_text or re.sub(r"\s+", " ", span) == re.sub(r"\s+", " ", entity_text)


# ---------------------------------------------------------------------------
# Entity mapper
# ---------------------------------------------------------------------------

def _map_entity(
    raw_entity: dict[str, Any],
    text: str,
    document_id: str,
    idx: int,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Map a raw entity dict to canonical schema.  Returns (entity, reasons_rejected)."""
    reasons: list[str] = []

    start = raw_entity.get("start")
    end = raw_entity.get("end")
    entity_text = raw_entity.get("text") or raw_entity.get("phrase") or ""

    if start is None or end is None:
        reasons.append("missing_offset")
        return None, reasons

    try:
        start, end = int(start), int(end)
    except (TypeError, ValueError):
        reasons.append("non_integer_offset")
        return None, reasons

    if not _verify_offset(text, start, end, entity_text):
        # Attempt to fix by re-finding the entity in text
        found_idx = text.find(entity_text, max(0, start - 5))
        if found_idx >= 0 and found_idx <= start + 5:
            start = found_idx
            end = found_idx + len(entity_text)
        else:
            reasons.append(f"offset_mismatch|expected={repr(entity_text)}|got={repr(text[start:end])}")
            return None, reasons

    raw_label = (
        raw_entity.get("label")
        or raw_entity.get("semantic_tag")
        or raw_entity.get("entity_type")
    )
    label = normalise_label(raw_label)
    if label is None:
        # Fall back: try to map from semantic_tag on snomed side
        snomed_tag = raw_entity.get("snomed_tag") or raw_entity.get("semantic_tag")
        label = normalise_label(snomed_tag)
    if label is None:
        reasons.append(f"unknown_label|{raw_label!r}")
        return None, reasons

    assertion = raw_entity.get("assertion", "present")
    if assertion not in (
        "present", "absent", "refuted", "possible", "historical",
        "planned", "hypothetical", "family", "declined", "cancelled",
    ):
        assertion = "present"

    eid = raw_entity.get("entity_id") or _stable_entity_id(document_id, start, end, label)

    snomed = raw_entity.get("snomed_id") or raw_entity.get("snomed_code")
    snomed_term = raw_entity.get("snomed_term") or raw_entity.get("preferred_term")
    normalised_code: dict[str, Any] | None = None
    if snomed:
        normalised_code = {
            "system": "SNOMED_CT",
            "code": str(snomed),
            "display": snomed_term or "",
        }
    elif raw_entity.get("normalised_code"):
        normalised_code = raw_entity["normalised_code"]

    entity: dict[str, Any] = {
        "entity_id": eid,
        "start": start,
        "end": end,
        "text": entity_text,
        "label": label,
        "assertion": assertion,
        "confidence": float(raw_entity.get("confidence") or raw_entity.get("resolver_score") or 0.0),
    }
    if normalised_code:
        entity["normalised_code"] = normalised_code

    # Preserve milestone_type if present (for X_PATHWAY_MILESTONE)
    if raw_entity.get("milestone_type"):
        entity["milestone_type"] = raw_entity["milestone_type"]

    # Preserve value/unit for observable entities
    if label == "observable_entity":
        if raw_entity.get("value") is not None:
            entity["value"] = raw_entity["value"]
        if raw_entity.get("unit"):
            entity["unit"] = raw_entity["unit"]

    # Preserve domain provenance
    if raw_entity.get("domain"):
        entity["domain"] = raw_entity["domain"]

    return entity, []


# ---------------------------------------------------------------------------
# Relation mapper
# ---------------------------------------------------------------------------

def _map_relation(
    raw_rel: dict[str, Any],
    entity_id_set: set[str],
    document_id: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    reasons: list[str] = []
    rel_type = raw_rel.get("type") or raw_rel.get("relation_type") or ""
    if rel_type not in VALID_RELATION_TYPES:
        reasons.append(f"unknown_relation_type|{rel_type!r}")
        return None, reasons

    head = raw_rel.get("head") or raw_rel.get("head_id") or ""
    tail = raw_rel.get("tail") or raw_rel.get("tail_id") or ""

    if head not in entity_id_set:
        reasons.append(f"head_entity_not_found|{head!r}")
        return None, reasons
    if tail not in entity_id_set:
        reasons.append(f"tail_entity_not_found|{tail!r}")
        return None, reasons

    rid = raw_rel.get("relation_id") or _stable_relation_id(document_id, head, tail, rel_type)
    return {"relation_id": rid, "type": rel_type, "head": head, "tail": tail}, []


# ---------------------------------------------------------------------------
# Full record mapper
# ---------------------------------------------------------------------------

def map_raw_record(
    raw: dict[str, Any],
    source_origin: str = "mined_raw",
) -> tuple[dict[str, Any] | None, list[str]]:
    """Convert a raw extraction record to the canonical training schema.

    Returns (canonical_record, rejection_reasons).
    If rejection_reasons is non-empty the record should not be included in the
    output; the reasons list explains why.
    """
    reasons: list[str] = []

    # Support both sentence-level records (mine_all_domains) and doc-level (seed)
    text = (
        raw.get("text")
        or raw.get("sentence_text")
        or ""
    ).strip()
    if not text:
        reasons.append("empty_text")
        return None, reasons

    encounter_id = str(raw.get("encounter_id") or raw.get("document_id") or "")
    sentence_id = str(raw.get("sentence_id") or "s0")
    document_id = raw.get("document_id") or _stable_document_id(encounter_id, sentence_id)

    raw_entities: list[dict[str, Any]] = raw.get("entities") or []
    mapped_entities: list[dict[str, Any]] = []
    entity_reject_reasons: list[str] = []

    for idx, ent in enumerate(raw_entities):
        mapped, ent_reasons = _map_entity(ent, text, document_id, idx)
        if mapped:
            mapped_entities.append(mapped)
        else:
            entity_reject_reasons.extend(ent_reasons)

    if not mapped_entities:
        if raw_entities:
            reasons.append("all_entities_rejected")
            reasons.extend(entity_reject_reasons)
        else:
            reasons.append("no_entities")
        return None, reasons

    entity_id_set = {e["entity_id"] for e in mapped_entities}

    raw_relations: list[dict[str, Any]] = raw.get("relations") or []
    mapped_relations: list[dict[str, Any]] = []
    for rel in raw_relations:
        mapped_rel, rel_reasons = _map_relation(rel, entity_id_set, document_id)
        if mapped_rel:
            mapped_relations.append(mapped_rel)

    # Build metadata
    meta = dict(raw.get("metadata") or {})
    meta.setdefault("source_type", "gp_record")
    meta["source_origin"] = source_origin
    meta.setdefault("annotation_guidelines_version", "v1")

    # Preserve search scores as provenance but not as training signal
    if raw.get("_ft_score") is not None:
        meta["_ft_score"] = float(raw["_ft_score"])
    if raw.get("_vec_score") is not None:
        meta["_vec_score"] = float(raw["_vec_score"])
    if raw.get("_search_source"):
        meta["_search_source"] = raw["_search_source"]
    if raw.get("encounter_date"):
        meta["encounter_year"] = str(raw["encounter_date"])[:4]

    record: dict[str, Any] = {
        "document_id": document_id,
        "text": text,
        "entities": mapped_entities,
        "relations": mapped_relations,
        "metadata": meta,
    }
    return record, []


# ---------------------------------------------------------------------------
# Batch helpers
# ---------------------------------------------------------------------------

def map_records_batch(
    raw_records: list[dict[str, Any]],
    source_origin: str = "mined_raw",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Map a list of raw records; return (mapped, rejected_with_reasons)."""
    mapped: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for raw in raw_records:
        record, reasons = map_raw_record(raw, source_origin=source_origin)
        if record:
            mapped.append(record)
        else:
            rejected.append({"raw": raw, "reasons": reasons})
    return mapped, rejected
