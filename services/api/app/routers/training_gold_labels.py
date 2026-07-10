"""GoldLabel router -- reviewer-approved training data.

Atlas trace:
  DO: DO-236545C8
  Also implements: DO-2D2CE052, DO-54397CCD, DO-6CD07544, DO-94D87FA7, DO-A35D2D57, DO-B88D4941, DO-BA2B7A99
  DI: DI-2D9F5064, DI-37B3DC71, DI-3EA60D5A, DI-54D00E21, DI-6EFD68D0, DI-A0579B64, DI-AF5A1668, DI-D2D0117E
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-236545C8")

Extracted from services/api/app/routers/training.py (2026-07 CTO peer-review
item 2: core-api router decomposition). Pure move, no behaviour change --
existing DO/DI trace headers carried over unchanged.

Routes: gold-labels stats/distribution/phrase-multilabel-approvals/phrase-consistency/list/export(+diagnostics)/repair-spans/get/by-candidate/from-dry-run/from-encounter/approve-from-dry-run/per-encounter-weights/delete/update-entities/golden-set(+stats), annotation-guidelines.

Depends on app.routers._training_common for _VALID_ENTITY_LABELS, UpdateEntitiesRequest, and _enrich_items_entities_with_pt_cache (shared with training_labels / coding_review / training_candidates).
"""

from __future__ import annotations

import json
import hashlib
import logging
import re
import uuid
from collections import Counter, defaultdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from libs.auth.org_scope import (
    CallerScope,
    get_caller_scope,
    require_patient_in_scope,
)
from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient
from app.deps import require_admin
from libs.cypher.training_candidate_queries import (
    GET_TRAINING_CANDIDATE_BY_ID,
    UPSERT_TRAINING_CANDIDATE,
)
from libs.cypher.gold_label_queries import (
    COUNT_GOLD_LABELS_PAGE,
    DELETE_GOLD_LABEL_AND_RESET_CANDIDATE,
    GET_ALL_GOLD_LABELS_FOR_EXPORT,
    GET_GOLD_LABEL_BY_CANDIDATE_ID,
    GET_GOLD_LABEL_BY_ID,
    GET_GOLD_LABEL_STATS,
    GET_GOLD_LABELS_PAGE,
    UPSERT_GOLD_LABEL,
    UPDATE_GOLD_LABEL_ENTITIES,
)
from libs.search.term_expansion import expand_search_terms
from libs.cypher.phrase_consistency_queries import (
    DELETE_PHRASE_MULTILABEL_APPROVAL,
    LIST_PHRASE_MULTILABEL_APPROVALS,
    UPSERT_PHRASE_MULTILABEL_APPROVAL,
)
from libs.cypher.documents_queries import LIST_ENCOUNTER_CODED_LINKS
from app.models.neo4j_schema import GET_ENCOUNTER
from libs.ner.schema_mapper import LABEL_TO_SNOMED_TAG
from libs.ner.span_finder import find_span
from libs.training_data.gold_granularity import (
    classify_gold_record,
    parse_entities_json,
)
from libs.utils.deidentify import deidentify_text
from app.routers._training_common import (
    _VALID_ENTITY_LABELS,
    UpdateEntitiesRequest,
    _enrich_items_entities_with_pt_cache,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# -- Entity label normalisation maps -----------------------------------------
# Stored labels are lowercase SNOMED semantic tags.  Display labels shown in
# the distribution chart are uppercase abbreviations.  The reverse map lets the
# list endpoint accept a display label and look up the stored form for filtering.

_ENTITY_STORED_TO_DISPLAY: dict[str, str] = {
    "disorder": "DISORDER",
    "finding": "FINDING",
    "procedure": "PROCEDURE",
    "observable_entity": "OBSERVABLE",
    "qualifier_value": "QUALIFIER",
    "substance": "SUBSTANCE",
    "medicinal_product": "MEDICINAL_PRODUCT",
    "clinical_drug": "CLINICAL_DRUG",
    "situation": "SITUATION",
    "event": "EVENT",
    "body_structure": "BODY_STRUCTURE",
    "tumor_staging": "TUMOR_STAGING",
    "assessment_scale": "ASSESSMENT_SCALE",
    "staging_scale": "STAGING_SCALE",
    "regime_therapy": "REGIME_THERAPY",
    "record_artifact": "RECORD_ARTIFACT",
    "physical_object": "PHYSICAL_OBJECT",
    "organism": "ORGANISM",
    "morphologic_abnormality": "MORPHOLOGIC_ABNORMALITY",
    "occupation": "OCCUPATION",
    "attribute": "ATTRIBUTE",
    "environment": "ENVIRONMENT",
    "product": "PRODUCT",
    "x_temporal": "TEMPORAL",
    "x_dosage": "DOSAGE",
    "x_frequency": "FREQUENCY",
    "x_route": "ROUTE",
}

# Reverse: display label -> stored label (lower-case for CONTAINS matching)
_ENTITY_DISPLAY_TO_STORED: dict[str, str] = {
    v.lower(): k for k, v in _ENTITY_STORED_TO_DISPLAY.items()
}


def _normalise_entity_label_param(display_label: str | None) -> str | None:
    """Convert a chart display label to the stored lowercase form.

    e.g. "FINDING" -> "finding", "OBSERVABLE" -> "observable_entity".
    Falls back to lower-casing the input when no explicit mapping exists.
    """
    if display_label is None:
        return None
    return _ENTITY_DISPLAY_TO_STORED.get(display_label.lower(), display_label.lower())


class DryRunCandidateRequest(BaseModel):
    """Create or fetch a TrainingCandidate seeded from a dry-run extraction.

    The encounter text is de-identified server-side before hashing so
    PHI never enters the candidate text or the candidate_id.
    """

    encounter_text: str
    entities: list[dict[str, Any]] = Field(default_factory=list)
    source_hint: str | None = None


class DryRunApproveRequest(BaseModel):
    """Approve a dry-run extraction as gold without opening the editor.

    The reviewer must echo back ``expected_entity_count`` -- the number
    of entities they saw on the row card -- so the server can refuse
    when de-identification drops or merges entities (which would mean
    the reviewer never saw the persisted set).
    """

    encounter_text: str
    entities: list[dict[str, Any]] = Field(default_factory=list)
    expected_entity_count: int = Field(..., ge=0)
    source_hint: str | None = None
    quality_score: float = Field(default=1.0, ge=0.0, le=1.0)


class EncounterGoldLabelRequest(BaseModel):
    """Create or fetch a draft GoldLabel seeded from a live patient encounter.

    The dialog opens against the de-identified text (so PHI never reaches
    the gold dataset).  The reviewer's edits are persisted both to the
    GoldLabel and -- via a separate sync endpoint -- back to the live
    Encounter's :DOCUMENTS links.  The (patient_id, encounter_id) pair
    must be carried by the client because the gold label itself is
    GDPR-isolated and does not store live identifiers.
    """

    patient_id: str = Field(..., min_length=1)
    encounter_id: str = Field(..., min_length=1)


class PerEncounterWeightLookupRow(BaseModel):
    encounter_id: str
    text: str


class PerEncounterWeightLookupRequest(BaseModel):
    """Look up per-encounter error contribution from the latest canary run.

    The server de-identifies + sha256s each encounter text, joins the
    hash to ``candidate_id`` in the most recent completed canary job's
    ``per_document`` block, and returns the weight keyed by the
    encounter_id supplied by the caller. PHI never crosses back over
    the wire.
    """

    encounters: list[PerEncounterWeightLookupRow] = Field(default_factory=list)
    version: str | None = None


@router.get("/gold-labels/stats")
def get_gold_label_stats(
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            row = session.run(GET_GOLD_LABEL_STATS).single()
        return (
            dict(row)
            if row
            else {"total": 0, "avg_quality_score": 0.0, "high_quality": 0}
        )
    finally:
        client.close()


@router.get("/annotation-guidelines")
def get_annotation_guidelines(
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Return the canonical annotation guideline text used by prompt composition."""
    from libs.prompts.registry import get_prompt_config

    try:
        cfg = get_prompt_config("annotation_guidelines", version=1)
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"Annotation guidelines unavailable: {exc}"
        ) from exc

    return {
        "name": cfg.get("name", "annotation_guidelines"),
        "version": int(cfg.get("version", 1) or 1),
        "guidelines": str(cfg.get("systemPrompt") or ""),
        "applies_to": [
            "extraction",
            "label_verification",
            "extraction_check",
            "coding_check",
            "relation_linking",
        ],
    }


@router.get("/gold-labels/label-distribution")
def get_gold_label_distribution(
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Return entity-type label counts across all verified gold labels."""
    import json as _json
    from collections import Counter

    client = KnowledgeGraphClient()
    try:
        counter: Counter = Counter()
        total_records = 0
        with client.session() as session:
            rows = session.run(
                """
                MATCH (c:TrainingCandidate)-[:PRODUCED]->(g:GoldLabel)
                WHERE c.status = 'completed'
                  AND g.entities_json IS NOT NULL
                RETURN g.entities_json AS entities_json
                """
            )
            for row in rows:
                total_records += 1
                entities = _json.loads(row["entities_json"] or "[]")
                for ent in entities:
                    raw = str(
                        ent.get("label") or ent.get("semantic_tag") or "UNKNOWN"
                    ).lower()
                    label = _ENTITY_STORED_TO_DISPLAY.get(raw, raw.upper())
                    counter[label] += 1
    finally:
        client.close()

    return {
        "total_records": total_records,
        "total_entities": sum(counter.values()),
        "distribution": [
            {"label": lbl, "count": cnt} for lbl, cnt in counter.most_common()
        ],
    }


def _normalise_phrase_for_consistency(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip()).lower()


_APPROVED_MULTI_LABEL_PHRASES: dict[str, set[str]] = {
    # Program-defined dual meaning phrases where both labels are expected.
    "2ww breast": {"PROCEDURE", "SITUATION"},
    "2ww gynae": {"PROCEDURE", "SITUATION"},
    "2ww gynaecology": {"PROCEDURE", "SITUATION"},
    "2ww head and neck": {"PROCEDURE", "SITUATION"},
    "2ww referral": {"PROCEDURE", "SITUATION"},
}


class PhraseMultiLabelApprovalRequest(BaseModel):
    phrase: str = Field(..., min_length=1, max_length=200)
    allowed_labels: list[str] = Field(..., min_length=2, max_length=10)


def _normalise_label_name(label: str) -> str:
    return str(label or "").strip().replace(" ", "_").upper()


def _normalise_phrase_key(phrase: str) -> str:
    return _normalise_phrase_for_consistency(phrase)


def _load_phrase_multilabel_policy(
    session,
) -> tuple[dict[str, set[str]], list[dict[str, Any]]]:
    policy = {k: set(v) for k, v in _APPROVED_MULTI_LABEL_PHRASES.items()}
    rows: list[dict[str, Any]] = []
    for row in session.run(LIST_PHRASE_MULTILABEL_APPROVALS):
        item = dict(row)
        phrase_norm = str(item.get("phrase_norm") or "").strip().lower()
        if not phrase_norm:
            continue
        labels = {
            _normalise_label_name(str(label))
            for label in (item.get("allowed_labels") or [])
            if str(label).strip()
        }
        if len(labels) < 2:
            continue
        policy[phrase_norm] = labels
        rows.append(
            {
                "phrase_norm": phrase_norm,
                "phrase_display": str(item.get("phrase_display") or phrase_norm),
                "allowed_labels": sorted(labels),
                "created_at": item.get("created_at"),
                "created_by": item.get("created_by"),
                "updated_at": item.get("updated_at"),
                "updated_by": item.get("updated_by"),
            }
        )
    return policy, rows


def _is_approved_multilabel_phrase_with_policy(
    phrase: str,
    labels: set[str],
    policy: dict[str, set[str]],
) -> bool:
    allowed = policy.get(phrase)
    return bool(allowed and len(labels) > 1 and labels.issubset(allowed))


def _is_approved_multilabel_phrase(phrase: str, labels: set[str]) -> bool:
    allowed = _APPROVED_MULTI_LABEL_PHRASES.get(phrase)
    return bool(allowed and len(labels) > 1 and labels.issubset(allowed))


def _safe_entities_json_list(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if not isinstance(raw, str):
        return []
    payload = raw.strip()
    if not payload:
        return []
    try:
        parsed = json.loads(payload)
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def _build_phrase_groups(
    rows: list[dict[str, Any]],
    phrase_filter: str | None,
) -> tuple[dict[str, list[dict[str, str]]], int]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    needle = _normalise_phrase_for_consistency(phrase_filter) if phrase_filter else ""
    total_entities = 0
    for row in rows:
        sentence_preview = str(row.get("text") or "").replace("\n", " ")[:180]
        for ent in _safe_entities_json_list(row.get("entities_json")):
            phrase = _normalise_phrase_for_consistency(ent.get("text") or "")
            if not phrase:
                continue
            if needle and needle not in phrase:
                continue
            total_entities += 1
            grouped[phrase].append(
                {
                    "label": _normalise_label_name(
                        ent.get("label") or ent.get("semantic_tag") or "UNKNOWN"
                    ),
                    "assertion": str(ent.get("assertion") or "present").strip().lower()
                    or "present",
                    "label_id": str(row.get("label_id") or ""),
                    "source": str(row.get("source") or ""),
                    "sentence_preview": sentence_preview,
                }
            )
    return grouped, total_entities


def _build_phrase_conflict_entry(
    phrase: str,
    items: list[dict[str, str]],
    max_examples: int,
) -> dict[str, Any]:
    signature_counts: Counter[str] = Counter(
        f"{item['label']}|{item['assertion']}" for item in items
    )
    label_counts: Counter[str] = Counter(item["label"] for item in items)
    primary_label = label_counts.most_common(1)[0][0] if label_counts else "UNKNOWN"
    examples: list[dict[str, str]] = []
    seen_examples: set[str] = set()
    for item in items:
        sig = f"{item['label']}|{item['assertion']}"
        ex_key = f"{sig}:{item['label_id']}"
        if ex_key in seen_examples:
            continue
        seen_examples.add(ex_key)
        examples.append(item)
        if len(examples) >= max_examples:
            break
    outlier_examples: list[dict[str, str]] = []
    seen_outliers: set[str] = set()
    for item in items:
        if item["label"] == primary_label:
            continue
        label_id = item["label_id"]
        if label_id in seen_outliers:
            continue
        seen_outliers.add(label_id)
        outlier_examples.append(
            {
                "label_id": label_id,
                "source": item["source"],
                "label": item["label"],
                "assertion": item["assertion"],
                "sentence_preview": item["sentence_preview"],
            }
        )
        if len(outlier_examples) >= max_examples:
            break
    return {
        "phrase": phrase,
        "occurrences": len(items),
        "distinct_labels": len({item["label"] for item in items}),
        "distinct_assertions": len({item["assertion"] for item in items}),
        "primary_label": primary_label,
        "outlier_count": len(
            {item["label_id"] for item in items if item["label"] != primary_label}
        ),
        "outlier_examples": outlier_examples,
        "signature_counts": [
            {
                "label": sig.split("|", 1)[0],
                "assertion": sig.split("|", 1)[1],
                "count": count,
            }
            for sig, count in signature_counts.most_common()
        ],
        "examples": examples,
    }


def _extract_phrase_conflicts(
    rows: list[dict[str, Any]],
    *,
    phrase_filter: str | None,
    min_occurrences: int,
    max_examples: int,
    top: int,
    policy: dict[str, set[str]] | None = None,
    policy_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    grouped, total_entities = _build_phrase_groups(rows, phrase_filter)
    active_policy = policy or _APPROVED_MULTI_LABEL_PHRASES

    conflicts: list[dict[str, Any]] = []
    approved_multilabel: list[dict[str, Any]] = []
    assertion_only_variants = 0
    for phrase, items in grouped.items():
        if len(items) < min_occurrences:
            continue
        labels = {item["label"] for item in items}
        assertions = {item["assertion"] for item in items}
        if len(labels) <= 1:
            if len(assertions) > 1:
                assertion_only_variants += 1
            continue
        if _is_approved_multilabel_phrase_with_policy(phrase, labels, active_policy):
            approved_multilabel.append(
                _build_phrase_conflict_entry(phrase, items, max_examples)
            )
            continue
        conflicts.append(_build_phrase_conflict_entry(phrase, items, max_examples))

    conflicts.sort(key=lambda item: (-int(item["occurrences"]), str(item["phrase"])))
    approved_multilabel.sort(
        key=lambda item: (-int(item["occurrences"]), str(item["phrase"]))
    )
    return {
        "summary": {
            "total_records": len(rows),
            "total_entities": total_entities,
            "unique_phrases": len(grouped),
            "conflicting_phrases": len(conflicts),
            "assertion_only_variants": assertion_only_variants,
            "approved_multilabel_variants": len(approved_multilabel),
            "min_occurrences": min_occurrences,
        },
        "conflicts": conflicts[:top],
        "approved_multilabel": approved_multilabel[:top],
        "policy": policy_rows or [],
    }


@router.get("/gold-labels/phrase-multilabel-approvals")
def list_phrase_multilabel_approvals(
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            _, rows = _load_phrase_multilabel_policy(session)
    finally:
        client.close()
    return {"items": rows, "count": len(rows)}


@router.post("/gold-labels/phrase-multilabel-approvals")
def upsert_phrase_multilabel_approval(
    body: PhraseMultiLabelApprovalRequest,
    scope: CallerScope = Depends(get_caller_scope),
    _admin: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    phrase_norm = _normalise_phrase_key(body.phrase)
    if not phrase_norm:
        raise HTTPException(status_code=422, detail="phrase must be non-empty")
    labels = sorted(
        {
            _normalise_label_name(label)
            for label in body.allowed_labels
            if str(label).strip()
        }
    )
    if len(labels) < 2:
        raise HTTPException(
            status_code=422, detail="allowed_labels must contain at least 2 labels"
        )

    actor = getattr(scope, "email", "") or "admin"
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            row = session.run(
                UPSERT_PHRASE_MULTILABEL_APPROVAL,
                id=str(uuid.uuid4()),
                phrase_norm=phrase_norm,
                phrase_display=str(body.phrase).strip(),
                allowed_labels=labels,
                updated_by=actor,
            ).single()
            result = dict(row) if row else {}
    finally:
        client.close()
    return result


@router.delete("/gold-labels/phrase-multilabel-approvals/{phrase_norm}")
def delete_phrase_multilabel_approval(
    phrase_norm: str,
    scope: CallerScope = Depends(get_caller_scope),
    _admin: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    key = _normalise_phrase_key(phrase_norm)
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            row = session.run(
                DELETE_PHRASE_MULTILABEL_APPROVAL, phrase_norm=key
            ).single()
            deleted = int((row or {}).get("deleted") or 0)
    finally:
        client.close()
    return {"phrase_norm": key, "deleted": deleted}


@router.get("/gold-labels/phrase-consistency")
def get_gold_label_phrase_consistency(
    phrase: str | None = Query(default=None),
    min_occurrences: int = Query(default=2, ge=1, le=50),
    max_examples: int = Query(default=5, ge=1, le=20),
    top: int = Query(default=25, ge=1, le=100),
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            policy, policy_rows = _load_phrase_multilabel_policy(session)
            rows = [
                dict(r)
                for r in session.run(
                    """
                    MATCH (c:TrainingCandidate)-[:PRODUCED]->(g:GoldLabel)
                    WHERE c.status = 'completed'
                      AND g.entities_json IS NOT NULL
                    RETURN
                      g.label_id AS label_id,
                      g.text AS text,
                      g.entities_json AS entities_json,
                      g.source AS source
                    ORDER BY g.updated_at DESC
                    """
                )
            ]
    finally:
        client.close()
    return _extract_phrase_conflicts(
        rows,
        phrase_filter=phrase,
        min_occurrences=min_occurrences,
        max_examples=max_examples,
        top=top,
        policy=policy,
        policy_rows=policy_rows,
    )


@router.get("/gold-labels")
def list_gold_labels(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    source: str | None = None,
    search: str | None = None,
    entity_label: str | None = None,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    skip = (page - 1) * page_size
    stored_label = _normalise_entity_label_param(entity_label)
    # DI-LEO-AI-526 -- mirror the candidates endpoint: expand the search
    # so verified-gold and synthetic-gold rows that share host-search
    # synonyms surface even when the literal query token is absent.
    terms = expand_search_terms(search)
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            rows = session.run(
                GET_GOLD_LABELS_PAGE,
                skip=skip,
                limit=page_size,
                source=source,
                search=search,
                terms=terms,
                entity_label=stored_label,
            )
            items = [dict(r) for r in rows]
            _enrich_items_entities_with_pt_cache(session, items)
            count_row = session.run(
                COUNT_GOLD_LABELS_PAGE,
                source=source,
                search=search,
                terms=terms,
                entity_label=stored_label,
            ).single()
        total = count_row["total"] if count_row else 0
        return {"items": items, "page": page, "page_size": page_size, "total": total}
    finally:
        client.close()


@router.get("/gold-labels/export")
def export_gold_labels(
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            rows = session.run(GET_ALL_GOLD_LABELS_FOR_EXPORT)
            return {"items": [dict(r) for r in rows]}
    finally:
        client.close()


@router.get("/gold-labels/export-diagnostics")
def get_export_diagnostics(
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Replay the export filter path and return per-entity drop diagnostics.

    Runs the same assertion-filter + span-realignment logic as the training
    export without writing DocBins. Returns two lists:
    - assertion_filtered: entities removed because their assertion is excluded
    - span_misaligned: entities whose surface text was not found in the sentence
    """
    from libs.pipeline.label_filter import compute_export_diagnostics

    return compute_export_diagnostics()


@router.post("/gold-labels/{label_id}/repair-spans")
def repair_gold_label_spans(
    label_id: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Re-align entity spans for a single GoldLabel using normalised matching.

    For each entity whose stored start/end is stale (e.g. em-dash vs hyphen,
    whitespace changes after editing), this re-derives the offsets from the
    entity surface text using find_span's normalised matching pass.

    Entities that genuinely cannot be found are reported and left unchanged so
    bulk cleanup never silently deletes review work.

    Returns:
        repaired     -- entities whose text or offsets were updated
        unchanged    -- entities already aligned
        unrepairable -- entities whose surface text was not found
        ambiguous    -- entities with multiple candidate spans
    """
    from libs.pipeline.label_filter import repair_entity_spans

    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            row = session.run(GET_GOLD_LABEL_BY_ID, label_id=label_id).single()
        if not row:
            raise HTTPException(
                status_code=404, detail=f"GoldLabel {label_id!r} not found"
            )
    finally:
        client.close()

    text = str(row.get("text") or "")
    entities = json.loads(row.get("entities_json") or "[]")

    repair = repair_entity_spans(text, entities)
    kept = repair["entities"]
    changed = bool(repair["repaired"])

    if changed:
        updated = json.dumps(kept)
        client2 = KnowledgeGraphClient()
        try:
            with client2.session() as session:
                session.run(
                    UPDATE_GOLD_LABEL_ENTITIES,
                    label_id=label_id,
                    entities_json=updated,
                )
        finally:
            client2.close()

    return {
        "label_id": label_id,
        "repaired": len(repair["repaired"]),
        "unchanged": len(repair["unchanged"]),
        "unrepairable": len(repair["unrepairable"]),
        "ambiguous": len(repair["ambiguous"]),
        "remaining": len(kept),
        "updated": changed,
        "details": {
            "repaired": repair["repaired"],
            "unrepairable": repair["unrepairable"],
            "ambiguous": repair["ambiguous"],
        },
    }


@router.get("/gold-labels/{label_id}")
def get_gold_label(
    label_id: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            row = session.run(GET_GOLD_LABEL_BY_ID, label_id=label_id).single()
        if not row:
            raise HTTPException(
                status_code=404, detail=f"GoldLabel {label_id!r} not found"
            )
        return dict(row)
    finally:
        client.close()


@router.get("/gold-labels/by-candidate/{candidate_id}")
def get_gold_label_by_candidate_id(
    candidate_id: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            row = session.run(
                GET_GOLD_LABEL_BY_CANDIDATE_ID,
                candidate_id=candidate_id,
            ).single()
        if not row:
            raise HTTPException(
                status_code=404,
                detail=f"No GoldLabel linked to candidate {candidate_id!r}",
            )
        return dict(row)
    finally:
        client.close()


@router.post("/gold-labels/by-candidate/{candidate_id}/ensure")
def ensure_gold_label_for_candidate(
    candidate_id: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Return existing GoldLabel for a candidate, or create one if missing."""
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            candidate_row = session.run(
                GET_TRAINING_CANDIDATE_BY_ID,
                candidate_id=candidate_id,
            ).single()
            if not candidate_row:
                raise HTTPException(
                    status_code=404, detail=f"Candidate {candidate_id!r} not found"
                )

            # -- AI first-pass audit fields (DI-LEO-AI-208 / DI-LEO-AI-209) --
            # Always read from the TrainingCandidate side: the AI first-pass
            # writes entities back to the candidate, and the GoldLabel is a
            # downstream draft. The reviewer needs ai_first_pass_run_id and
            # entities_json_original on the dialog so the "AI suggested" chip
            # and "show original" toggle render correctly.
            ai_audit = {
                "ai_first_pass_run_id": candidate_row.get("ai_first_pass_run_id"),
                "ai_first_pass_at": candidate_row.get("ai_first_pass_at"),
                "entities_json_original": candidate_row.get("entities_json_original"),
            }

            row = session.run(
                GET_GOLD_LABEL_BY_CANDIDATE_ID,
                candidate_id=candidate_id,
            ).single()
            if row:
                return {**dict(row), **ai_audit}

            label_id = f"manual-{uuid.uuid4().hex}"
            session.run(
                UPSERT_GOLD_LABEL,
                label_id=label_id,
                text=candidate_row.get("text", ""),
                entities_json=candidate_row.get("entities_json") or "[]",
                quality_score=None,
                source="manual_gold_draft",
                verified_by="",
                candidate_id=candidate_id,
                schema_version=candidate_row.get("schema_version") or "v4",
            )
            _apply_gold_granularity_metadata(
                session,
                candidate_id=candidate_id,
                label_id=label_id,
                text=candidate_row.get("text", "") or "",
                entities_json=candidate_row.get("entities_json") or "[]",
            )
            created = session.run(GET_GOLD_LABEL_BY_ID, label_id=label_id).single()
            if not created:
                raise HTTPException(
                    status_code=500, detail="Failed to create GoldLabel"
                )
            return {**dict(created), **ai_audit}
    finally:
        client.close()


_DRY_RUN_SOURCE = "dry_run_correction"
_DRY_RUN_APPROVE_GOLD_SOURCE = "manual_gold_curated"
_DRY_RUN_APPROVED_VIA = "dry_run_quick_approve"
_DRY_RUN_SOURCE_HINT_MAX = 64

# Source tag for GoldLabels seeded from a live patient encounter.  Lets
# the reviewer dashboard surface "edited live encounter" provenance and
# lets retraining filters distinguish dry-run audits from real clinical
# corrections (the latter are higher-trust signal).
_LIVE_ENCOUNTER_SOURCE = "live_encounter_correction"


def _apply_gold_granularity_metadata(
    session: Any,
    *,
    candidate_id: str,
    label_id: str,
    text: str,
    entities_json: str,
) -> None:
    """Mark gold records that are unsafe for direct training export."""
    granularity = classify_gold_record(text, parse_entities_json(entities_json))
    if granularity.safe_for_training:
        completeness = granularity.classification
        quarantined = False
        reason = None
    else:
        completeness = granularity.classification
        quarantined = True
        reason = granularity.reason
    session.run(
        """
        MATCH (c:TrainingCandidate {candidate_id: $candidate_id})
        MATCH (g:GoldLabel {label_id: $label_id})
        SET c.training_quarantined = $training_quarantined,
            c.training_quarantine_reason = $reason,
            c.annotation_completeness = $annotation_completeness,
            g.training_quarantined = $training_quarantined,
            g.training_quarantine_reason = $reason,
            g.annotation_completeness = $annotation_completeness
        """,
        candidate_id=candidate_id,
        label_id=label_id,
        training_quarantined=quarantined,
        reason=reason,
        annotation_completeness=completeness,
    )


_SNOMED_TAG_TO_LABEL: dict[str, str] = {
    tag.lower(): label for label, tag in LABEL_TO_SNOMED_TAG.items()
}


def _ner_label_for_semantic_tag(semantic_tag: str | None) -> str:
    """Map a SNOMED semantic tag onto the NER stored label.

    Falls back to a sanitised lowercase form when the tag is not in the
    canonical map (e.g. a custom semantic_tag from a manual coding fix).
    Always returns a non-empty string so the gold label is loadable by
    the editor dialog without raising.
    """

    if not semantic_tag:
        return "concept"
    key = semantic_tag.strip().lower()
    if not key:
        return "concept"
    if key in _SNOMED_TAG_TO_LABEL:
        return _SNOMED_TAG_TO_LABEL[key]
    sanitised = (
        "".join(ch if ch.isalnum() else "_" for ch in key).strip("_") or "concept"
    )
    return sanitised


def _sanitise_live_links(
    deidentified_text: str,
    links: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Re-anchor live :DOCUMENTS links onto de-identified encounter text.

    Returns ``(entities, dropped_count)``.  Each surviving entity uses
    the GoldLabel entity shape consumed by the editor dialog, with
    SNOMED metadata (``snomed_concept_id``, ``snomed_term``,
    ``body_site_*``) copied from the live link and assertion lifted out
    of the per-link context blob.

    Drops links whose evidence text can no longer be located after
    de-identification (e.g. a PERSON token replaced a date inside the
    evidence sentence).  Reviewers can re-add those in the editor.
    """

    sanitised: list[dict[str, Any]] = []
    dropped = 0
    for raw in links or []:
        if not isinstance(raw, dict):
            dropped += 1
            continue
        concept_id = str(raw.get("concept_id") or "").strip()
        term = str(raw.get("term") or "").strip()
        if not concept_id or not term:
            dropped += 1
            continue
        # Prefer the evidence sentence the coder originally anchored on,
        # then the longer evidence span, then the canonical term.  The
        # span finder will normalise whitespace + casing.
        candidates = [
            str(raw.get("evidence_sentence") or "").strip(),
            str(raw.get("evidence") or "").strip(),
            term,
        ]
        span: tuple[int, int] | None = None
        anchor_text = ""
        for candidate in candidates:
            if not candidate:
                continue
            located = find_span(deidentified_text, candidate)
            if located is not None:
                span = located
                anchor_text = candidate
                break
        if span is None:
            dropped += 1
            continue
        start, end = span
        semantic_tag = str(raw.get("semantic_tag") or "").strip()
        ctx_raw = raw.get("context")
        if isinstance(ctx_raw, str):
            try:
                ctx = json.loads(ctx_raw) if ctx_raw else {}
            except json.JSONDecodeError:
                ctx = {}
        elif isinstance(ctx_raw, dict):
            ctx = ctx_raw
        else:
            ctx = {}
        assertion = str(ctx.get("assertion") or "").strip() or "present"
        entity: dict[str, Any] = {
            "text": deidentified_text[start:end],
            "label": _ner_label_for_semantic_tag(semantic_tag),
            "start": start,
            "end": end,
            "semantic_tag": semantic_tag,
            "snomed_concept_id": concept_id,
            "snomed_term": term,
            "assertion": assertion,
        }
        body_site_id = str(raw.get("body_site_concept_id") or "").strip()
        body_site_term = str(raw.get("body_site_term") or "").strip()
        if body_site_id:
            entity["body_site_concept_id"] = body_site_id
        if body_site_term:
            entity["body_site_term"] = body_site_term
        # Anchor evidence is useful for the dialog header chrome and for
        # the sync-from-gold endpoint to detect "the reviewer changed
        # what evidence backs this concept".
        if anchor_text and anchor_text != entity["text"]:
            entity["source_evidence"] = anchor_text
        sanitised.append(entity)
    return sanitised, dropped


def _sanitise_dry_run_entities(
    deidentified_text: str,
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Re-anchor dry-run entity offsets onto the de-identified text.

    Drops entities whose surface text can no longer be located after
    de-identification (e.g. a PERSON token replaced a date inside the
    span). The reviewer can re-add them in the editor.
    """

    sanitised: list[dict[str, Any]] = []
    for raw in entities or []:
        if not isinstance(raw, dict):
            continue
        text = str(raw.get("text") or "").strip()
        label = str(raw.get("label") or "").strip()
        if not text or not label:
            continue
        span = find_span(deidentified_text, text)
        if span is None:
            continue
        start, end = span
        cleaned: dict[str, Any] = {
            "text": deidentified_text[start:end],
            "label": label,
            "start": start,
            "end": end,
        }
        for optional_key in ("semantic_tag", "concept_id", "term", "assertion"):
            value = raw.get(optional_key)
            if value not in (None, ""):
                cleaned[optional_key] = value
        sanitised.append(cleaned)
    return sanitised


@router.post("/candidates/from-dry-run")
def candidate_from_dry_run(
    payload: DryRunCandidateRequest,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Create or fetch a TrainingCandidate + draft GoldLabel for a dry-run encounter.

    The reviewer is then deep-linked into the gold-label editor where
    they can correct the labels and add the encounter to gold training data.

    Idempotent: two reviewers clicking the same encounter land on the same
    draft because candidate_id = sha256(deidentified_text).
    """

    raw_text = (payload.encounter_text or "").strip()
    if not raw_text:
        raise HTTPException(status_code=400, detail="encounter_text must not be empty")

    deidentified = deidentify_text(raw_text, ner=True).strip()
    if not deidentified:
        raise HTTPException(
            status_code=400, detail="encounter_text is empty after de-identification"
        )

    candidate_id = hashlib.sha256(deidentified.encode("utf-8")).hexdigest()
    sanitised_entities = _sanitise_dry_run_entities(deidentified, payload.entities)
    entities_json = json.dumps(sanitised_entities, ensure_ascii=False)

    hint = (payload.source_hint or "").strip()[:_DRY_RUN_SOURCE_HINT_MAX]

    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            candidate_row = session.run(
                GET_TRAINING_CANDIDATE_BY_ID, candidate_id=candidate_id
            ).single()
            if candidate_row is None:
                session.run(
                    UPSERT_TRAINING_CANDIDATE,
                    candidate_id=candidate_id,
                    text=deidentified,
                    entities_json=entities_json,
                    relation_changes=None,
                    source=_DRY_RUN_SOURCE,
                    status="pending",
                    hitl_reason=hint or None,
                    hitl_guidance=None,
                    schema_version="v4",
                )
                candidate_row = session.run(
                    GET_TRAINING_CANDIDATE_BY_ID, candidate_id=candidate_id
                ).single()

            existing_label = session.run(
                GET_GOLD_LABEL_BY_CANDIDATE_ID, candidate_id=candidate_id
            ).single()
            if existing_label:
                label_id = existing_label.get("label_id")
            else:
                label_id = f"manual-{uuid.uuid4().hex}"
                session.run(
                    UPSERT_GOLD_LABEL,
                    label_id=label_id,
                    text=deidentified,
                    entities_json=entities_json,
                    quality_score=None,
                    source="manual_gold_draft",
                    verified_by="",
                    candidate_id=candidate_id,
                    schema_version="v4",
                )
                _apply_gold_granularity_metadata(
                    session,
                    candidate_id=candidate_id,
                    label_id=label_id,
                    text=deidentified,
                    entities_json=entities_json,
                )

            # -- Surface the full GoldLabel payload (DI-LEO-AI-222) --
            # Lets the Evaluate-stage UI mount the shared
            # GoldLabelEditorDialog inline without a second roundtrip.
            # Merge in AI first-pass audit fields the same way
            # ensure_gold_label_for_candidate does so the AI-suggested
            # chip / show-original toggle work for dry-run rows that
            # were already touched by an AI first pass.
            label_row = session.run(GET_GOLD_LABEL_BY_ID, label_id=label_id).single()
            if not label_row:
                raise HTTPException(
                    status_code=500, detail="Failed to load draft GoldLabel"
                )
            ai_audit: dict[str, Any] = {}
            if candidate_row is not None:
                ai_audit = {
                    "ai_first_pass_run_id": candidate_row.get("ai_first_pass_run_id"),
                    "ai_first_pass_at": candidate_row.get("ai_first_pass_at"),
                    "entities_json_original": candidate_row.get(
                        "entities_json_original"
                    ),
                }
            gold_label = {**dict(label_row), **ai_audit}
    finally:
        client.close()

    return {
        "candidate_id": candidate_id,
        "label_id": label_id,
        "source": _DRY_RUN_SOURCE,
        "entity_count": len(sanitised_entities),
        "dropped_entity_count": max(
            0, len(payload.entities or []) - len(sanitised_entities)
        ),
        "gold_label": gold_label,
    }


@router.post("/gold-labels/from-encounter")
def gold_label_from_encounter(
    payload: EncounterGoldLabelRequest,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Open the shared editor against a live patient encounter (DI-LEO-AI-220).

    Used by the EncounterCard "Edit codes" button on /care/patients and
    by the EncounterPreviewDialog on /care/encounters.  Returns a draft
    GoldLabel pre-populated from the live :DOCUMENTS links so the
    reviewer's edits can be saved both back to Neo4j (via
    sync-from-gold) and as a de-identified copy in the gold dataset.

    Idempotent: candidate_id = sha256(deidentified_text), so two
    reviewers opening the same encounter land on the same draft.
    """

    patient_id = payload.patient_id.strip()
    encounter_id = payload.encounter_id.strip()
    if not patient_id or not encounter_id:
        raise HTTPException(
            status_code=400,
            detail="patient_id and encounter_id must not be empty",
        )

    patient_client = PatientGraphClient()
    try:
        require_patient_in_scope(patient_client, scope, patient_id)
        with patient_client.session() as session:
            encounter_row = session.run(
                GET_ENCOUNTER,
                patient_id=patient_id,
                encounter_id=encounter_id,
            ).single()
            if encounter_row is None:
                raise HTTPException(status_code=404, detail="Encounter not found")
            raw_text = str(encounter_row.get("text") or "").strip()
            if not raw_text:
                raise HTTPException(
                    status_code=400, detail="Encounter has no text to label"
                )
            link_rows = list(
                session.run(
                    LIST_ENCOUNTER_CODED_LINKS,
                    patient_id=patient_id,
                    encounter_id=encounter_id,
                )
            )
    finally:
        patient_client.close()

    live_links: list[dict[str, Any]] = []
    baseline_concept_ids: list[str] = []
    for row in link_rows:
        record = dict(row)
        concept_id = str(record.get("concept_id") or "").strip()
        if not concept_id:
            # LIST_ENCOUNTER_CODED_LINKS emits a placeholder row when
            # the encounter has no DOCUMENTS edges -- skip it so the
            # editor opens cleanly on uncoded encounters.
            continue
        live_links.append(record)
        baseline_concept_ids.append(concept_id)

    deidentified = deidentify_text(raw_text, ner=True).strip()
    if not deidentified:
        raise HTTPException(
            status_code=400,
            detail="Encounter text is empty after de-identification",
        )

    sanitised_entities, dropped_link_count = _sanitise_live_links(
        deidentified, live_links
    )
    candidate_id = hashlib.sha256(deidentified.encode("utf-8")).hexdigest()
    entities_json = json.dumps(sanitised_entities, ensure_ascii=False)

    kg_client = KnowledgeGraphClient()
    try:
        with kg_client.session() as session:
            candidate_row = session.run(
                GET_TRAINING_CANDIDATE_BY_ID, candidate_id=candidate_id
            ).single()
            if candidate_row is None:
                session.run(
                    UPSERT_TRAINING_CANDIDATE,
                    candidate_id=candidate_id,
                    text=deidentified,
                    entities_json=entities_json,
                    relation_changes=None,
                    source=_LIVE_ENCOUNTER_SOURCE,
                    status="pending",
                    hitl_reason=None,
                    hitl_guidance=None,
                    schema_version="v4",
                )
                candidate_row = session.run(
                    GET_TRAINING_CANDIDATE_BY_ID, candidate_id=candidate_id
                ).single()

            existing_label = session.run(
                GET_GOLD_LABEL_BY_CANDIDATE_ID, candidate_id=candidate_id
            ).single()
            if existing_label:
                label_id = existing_label.get("label_id")
            else:
                label_id = f"manual-{uuid.uuid4().hex}"
                session.run(
                    UPSERT_GOLD_LABEL,
                    label_id=label_id,
                    text=deidentified,
                    entities_json=entities_json,
                    quality_score=None,
                    source=_LIVE_ENCOUNTER_SOURCE,
                    verified_by="",
                    candidate_id=candidate_id,
                    schema_version="v4",
                )
                _apply_gold_granularity_metadata(
                    session,
                    candidate_id=candidate_id,
                    label_id=label_id,
                    text=deidentified,
                    entities_json=entities_json,
                )

            label_row = session.run(GET_GOLD_LABEL_BY_ID, label_id=label_id).single()
            if not label_row:
                raise HTTPException(
                    status_code=500, detail="Failed to load draft GoldLabel"
                )
            ai_audit: dict[str, Any] = {}
            if candidate_row is not None:
                ai_audit = {
                    "ai_first_pass_run_id": candidate_row.get("ai_first_pass_run_id"),
                    "ai_first_pass_at": candidate_row.get("ai_first_pass_at"),
                    "entities_json_original": candidate_row.get(
                        "entities_json_original"
                    ),
                }
            # Always mirror the current live :DOCUMENTS state into the
            # returned entities_json. The stored GoldLabel can carry
            # stale entities from a prior coding of this encounter
            # (since reset and recoded) or from a different encounter
            # that shares the same de-identified text. Returning the
            # stored gold entities would open the editor pre-populated
            # against an uncoded encounter, making it look like the
            # encounter is already coded and letting a silent save
            # push those stale terms onto the live record. Dual save
            # on :DOCUMENTS sync overwrites the gold mirror, so no
            # stored gold data is lost without an explicit save.
            gold_label = {
                **dict(label_row),
                "entities_json": entities_json,
                **ai_audit,
            }
    finally:
        kg_client.close()

    return {
        "candidate_id": candidate_id,
        "label_id": label_id,
        "source": _LIVE_ENCOUNTER_SOURCE,
        "patient_id": patient_id,
        "encounter_id": encounter_id,
        "source_coded_links_count": len(live_links),
        "entity_count": len(sanitised_entities),
        "dropped_link_count": dropped_link_count,
        "baseline_concept_ids": baseline_concept_ids,
        "gold_label": gold_label,
    }


@router.post("/gold-labels/approve-from-dry-run")
def approve_dry_run_extraction_as_gold(
    payload: DryRunApproveRequest,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Approve a dry-run extraction directly as a verified GoldLabel.

    Two-click flow: the reviewer has already eyeballed the entity list
    on the dry-run row and confirmed via a modal. This endpoint
    refuses to write gold if any entity was dropped or merged during
    de-identification (the reviewer would not have seen the persisted
    set), forcing the reviewer back into the editor for those rows.
    """

    raw_text = (payload.encounter_text or "").strip()
    if not raw_text:
        raise HTTPException(status_code=400, detail="encounter_text must not be empty")

    deidentified = deidentify_text(raw_text, ner=True).strip()
    if not deidentified:
        raise HTTPException(
            status_code=400, detail="encounter_text is empty after de-identification"
        )

    candidate_id = hashlib.sha256(deidentified.encode("utf-8")).hexdigest()
    sanitised = _sanitise_dry_run_entities(deidentified, payload.entities)
    if not sanitised:
        raise HTTPException(
            status_code=409,
            detail=(
                "No entities survived de-identification. "
                "Open this encounter in the editor to add or fix labels first."
            ),
        )
    if len(sanitised) != payload.expected_entity_count:
        raise HTTPException(
            status_code=409,
            detail=(
                "Entity count changed during de-identification "
                f"(saw {payload.expected_entity_count}, "
                f"{len(sanitised)} can be saved). "
                "Open this encounter in the editor to review."
            ),
        )

    entities_json = json.dumps(sanitised, ensure_ascii=False)
    hint = (payload.source_hint or "").strip()[:_DRY_RUN_SOURCE_HINT_MAX]
    verified_by = (getattr(scope, "email", None) or "unknown").strip() or "unknown"

    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            existing_candidate = session.run(
                GET_TRAINING_CANDIDATE_BY_ID, candidate_id=candidate_id
            ).single()
            if existing_candidate is None:
                session.run(
                    UPSERT_TRAINING_CANDIDATE,
                    candidate_id=candidate_id,
                    text=deidentified,
                    entities_json=entities_json,
                    relation_changes=None,
                    source=_DRY_RUN_SOURCE,
                    status="pending",
                    hitl_reason=hint or None,
                    hitl_guidance=None,
                    schema_version="v4",
                )

            existing_label = session.run(
                GET_GOLD_LABEL_BY_CANDIDATE_ID, candidate_id=candidate_id
            ).single()
            label_id = (
                existing_label.get("label_id")
                if existing_label
                else f"manual-{uuid.uuid4().hex}"
            )
            session.run(
                UPSERT_GOLD_LABEL,
                label_id=label_id,
                text=deidentified,
                entities_json=entities_json,
                quality_score=float(payload.quality_score),
                source=_DRY_RUN_APPROVE_GOLD_SOURCE,
                verified_by=verified_by,
                candidate_id=candidate_id,
                schema_version="v4",
            )
            _apply_gold_granularity_metadata(
                session,
                candidate_id=candidate_id,
                label_id=label_id,
                text=deidentified,
                entities_json=entities_json,
            )
    finally:
        client.close()

    return {
        "candidate_id": candidate_id,
        "label_id": label_id,
        "source": _DRY_RUN_APPROVE_GOLD_SOURCE,
        "verified_by": verified_by,
        "entity_count": len(sanitised),
        "approved_via": _DRY_RUN_APPROVED_VIA,
    }


@router.post("/per-encounter-weights/lookup")
def lookup_per_encounter_weights(
    payload: PerEncounterWeightLookupRequest,
    _scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Map dry-run encounter rows to per-document error contribution.

    Reads ``per_document`` from the most recent completed canary job
    held in the model_registry router's in-memory store. Encounters
    that did not appear in the canary corpus return ``None`` so the
    UI can omit the badge cleanly.
    """

    from app.routers.model_registry import _canary_jobs, _canary_jobs_lock

    with _canary_jobs_lock:
        candidates = sorted(
            (
                job
                for job in _canary_jobs.values()
                if job.get("status") == "completed"
                and (payload.version is None or job.get("version") == payload.version)
                and isinstance((job.get("metrics") or {}).get("per_document"), list)
            ),
            key=lambda j: float(j.get("completed_at") or 0.0),
            reverse=True,
        )
    if not candidates:
        return {"job_id": None, "version": None, "weights": {}}

    job = candidates[0]
    per_doc_index: dict[str, dict[str, Any]] = {}
    for entry in (job.get("metrics") or {}).get("per_document") or []:
        cid = entry.get("candidate_id")
        if isinstance(cid, str) and cid:
            per_doc_index[cid] = entry

    weights: dict[str, dict[str, Any] | None] = {}
    for row in payload.encounters:
        text = (row.text or "").strip()
        if not text:
            weights[row.encounter_id] = None
            continue
        deid = deidentify_text(text, ner=True).strip()
        if not deid:
            weights[row.encounter_id] = None
            continue
        cid = hashlib.sha256(deid.encode("utf-8")).hexdigest()
        weights[row.encounter_id] = per_doc_index.get(cid)

    return {
        "job_id": job.get("job_id"),
        "version": job.get("version"),
        "completed_at": job.get("completed_at"),
        "weights": weights,
    }


@router.delete("/gold-labels/{label_id}")
def delete_gold_label_and_reset_candidate(
    label_id: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            row = session.run(
                DELETE_GOLD_LABEL_AND_RESET_CANDIDATE,
                label_id=label_id,
            ).single()
        if not row:
            raise HTTPException(
                status_code=404, detail=f"GoldLabel {label_id!r} not found"
            )
        return dict(row)
    finally:
        client.close()


@router.patch("/gold-labels/{label_id}/entities")
def update_gold_label_entities(
    label_id: str,
    body: UpdateEntitiesRequest,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Replace the entities_json of a GoldLabel node.

    Each entity must carry at minimum ``text`` and ``label``.
    ``label`` must be one of the canonical NER label types.
    """
    import json

    from libs.relations.policy import canonicalise_relations, is_relation_allowed

    validated: list[dict[str, Any]] = []
    for i, ent in enumerate(body.entities):
        label_val = ent.get("label", "")
        if label_val not in _VALID_ENTITY_LABELS:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Entity #{i}: label {label_val!r} is not valid. "
                    f"Allowed: {sorted(_VALID_ENTITY_LABELS)}"
                ),
            )
        if not ent.get("text", "").strip():
            raise HTTPException(
                status_code=422, detail=f"Entity #{i}: text must be non-empty"
            )
        row: dict[str, Any] = {
            "text": ent["text"].strip(),
            "label": label_val,
            **({"start": ent["start"]} if "start" in ent else {}),
            **({"end": ent["end"]} if "end" in ent else {}),
            **({"assertion": ent["assertion"]} if "assertion" in ent else {}),
            **({"confidence": ent["confidence"]} if "confidence" in ent else {}),
            **(
                {"snomed_concept_id": ent["snomed_concept_id"]}
                if "snomed_concept_id" in ent
                else {}
            ),
            **({"semantic_tag": ent["semantic_tag"]} if "semantic_tag" in ent else {}),
            **({"snomed_term": ent["snomed_term"]} if "snomed_term" in ent else {}),
            **({"body_site": ent["body_site"]} if "body_site" in ent else {}),
            **(
                {"body_site_concept_id": ent["body_site_concept_id"]}
                if "body_site_concept_id" in ent
                else {}
            ),
            **(
                {"body_site_term": ent["body_site_term"]}
                if "body_site_term" in ent
                else {}
            ),
        }
        # Canonical relation list support.
        if isinstance(ent.get("relations"), list):
            row["relations"] = ent.get("relations")
        validated.append(row)

    # Post-parse relation validation needs full entity list for target_idx checks.
    for idx, entity in enumerate(validated):
        raw_relations = list(entity.get("relations") or [])
        # Legacy single-site fields are mirrored to finding_site relation.
        legacy_site_text = str(
            entity.get("body_site_term") or entity.get("body_site") or ""
        ).strip()
        if legacy_site_text:
            target_idx = None
            for j, target in enumerate(validated):
                if j == idx:
                    continue
                target_text = str(target.get("text") or "").strip().lower()
                target_term = str(target.get("snomed_term") or "").strip().lower()
                if legacy_site_text.lower() in {target_text, target_term}:
                    target_idx = j
                    break
            if isinstance(target_idx, int):
                raw_relations.append(
                    {
                        "type": "finding_site",
                        "target_idx": target_idx,
                        "target_text": str(validated[target_idx].get("text") or ""),
                        "confidence": 1.0,
                    }
                )
        canonical_relations = canonicalise_relations(raw_relations, len(validated))
        for rel in canonical_relations:
            target_idx = int(rel["target_idx"])
            allowed, severity = is_relation_allowed(
                source_label=str(
                    entity.get("label") or entity.get("semantic_tag") or ""
                ),
                target_label=str(
                    validated[target_idx].get("label")
                    or validated[target_idx].get("semantic_tag")
                    or ""
                ),
                relation_type=str(rel.get("type") or ""),
            )
            if not allowed and severity == "error":
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Entity #{idx}: relation {rel.get('type')!r} to entity "
                        f"#{target_idx} is not allowed by relation policy"
                    ),
                )
        if canonical_relations:
            entity["relations"] = canonical_relations
            if not entity.get("body_site_term"):
                site_relation = next(
                    (
                        rel
                        for rel in canonical_relations
                        if str(rel.get("type") or "") == "finding_site"
                    ),
                    None,
                )
                if site_relation:
                    site_idx = int(site_relation["target_idx"])
                    site = validated[site_idx]
                    entity["body_site"] = str(site.get("text") or "")
                    entity["body_site_term"] = str(
                        site.get("snomed_term") or site.get("text") or ""
                    )
                    if site.get("snomed_concept_id"):
                        entity["body_site_concept_id"] = str(
                            site.get("snomed_concept_id") or ""
                        )

    entities_json = json.dumps(validated)
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            row = session.run(
                UPDATE_GOLD_LABEL_ENTITIES,
                label_id=label_id,
                entities_json=entities_json,
            ).single()
            if not row:
                raise HTTPException(
                    status_code=404, detail=f"GoldLabel {label_id!r} not found"
                )
        logger.info(
            "GoldLabel entities updated: %s count=%d", label_id[:8], len(validated)
        )
        return {"label_id": label_id, "entities": validated}
    finally:
        client.close()


class _GoldenSetFlagBody(BaseModel):
    frozen_golden_set: bool
    updated_by: str = Field(default="api")


@router.patch("/gold-labels/{label_id}/golden-set")
def set_golden_set_flag(
    label_id: str,
    body: _GoldenSetFlagBody,
    scope: CallerScope = Depends(get_caller_scope),
    _admin=Depends(require_admin),
) -> dict[str, Any]:
    """Toggle the frozen_golden_set flag on a GoldLabel node."""
    from libs.cypher.golden_set_queries import SET_GOLDEN_SET_FLAG

    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            row = session.run(
                SET_GOLDEN_SET_FLAG,
                label_id=label_id,
                value=body.frozen_golden_set,
                updated_by=body.updated_by,
            ).single()
        if row is None:
            raise HTTPException(status_code=404, detail="GoldLabel not found")
        return dict(row)
    finally:
        client.close()


@router.get("/gold-labels/golden-set/stats")
def golden_set_stats(
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Return count statistics for the frozen golden evaluation set."""
    from libs.cypher.golden_set_queries import COUNT_GOLDEN_SET, GET_GOLDEN_SET_STATS

    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            stats_row = session.run(GET_GOLDEN_SET_STATS).single()
            count_row = session.run(COUNT_GOLDEN_SET).single()
        return {
            "total": count_row["total"] if count_row else 0,
            "avg_quality_score": (
                round(float(stats_row["avg_quality_score"]), 4)
                if stats_row and stats_row["avg_quality_score"]
                else None
            ),
            "high_quality": stats_row["high_quality"] if stats_row else 0,
        }
    finally:
        client.close()
