"""Training data management router.

Atlas trace:
  DO: DO-236545C8
  Also implements: DO-2D2CE052, DO-54397CCD, DO-6CD07544, DO-94D87FA7, DO-A35D2D57, DO-B88D4941, DO-BA2B7A99
  DI: DI-2D9F5064, DI-37B3DC71, DI-3EA60D5A, DI-54D00E21, DI-6EFD68D0, DI-A0579B64, DI-AF5A1668, DI-D2D0117E
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-236545C8")

Exposes the TrainingLabel store — the single source of truth for all NER
training data — so reviewers can inspect, include, and exclude individual
labels before triggering a training run.

Routes
------
GET  /training/jobs                    — list training jobs (proxied to training worker)
POST /training/jobs                    — start a training run (proxied to training worker)
GET  /training/jobs/{job_id}           — job detail (proxied to training worker)
DELETE /training/jobs/{job_id}         — cancel a job (proxied to training worker)
GET  /training/labels/stats            — corpus statistics (total, by source)
GET  /training/labels                  — paginated label list with filters
GET  /training/labels/{label_id}       — single label detail
POST /training/labels/{label_id}/exclude  — mark excluded (with reason)
POST /training/labels/{label_id}/include  — re-include
POST /training/labels/bulk-import      — bulk upsert from scripts
POST /training/export-preview          — dry-run count of what would be exported
"""

from __future__ import annotations

import json
import hashlib
import logging
import os
import re
import subprocess
import sys
import threading
import uuid
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from libs.auth.org_scope import (
    CallerScope,
    get_caller_scope,
    require_patient_in_scope,
)
from libs.auth.service_auth import get_service_auth_header
from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient
from app.deps import require_admin
from libs.cypher.training_label_queries import (
    COUNT_EXPORTABLE_LABELS,
    COUNT_TRAINING_LABELS_PAGE,
    EXCLUDE_TRAINING_LABEL,
    GET_TRAINING_LABEL_BY_ID,
    GET_TRAINING_LABEL_STATS,
    GET_TRAINING_LABELS_PAGE,
    INCLUDE_TRAINING_LABEL,
    LABEL_ENTITY_TYPE_BREAKDOWN,
    UPDATE_TRAINING_LABEL_ENTITIES,
)
from libs.cypher.coding_review_queries import (
    AUTO_RESOLVE_CODING_REVIEW,
    BATCH_RESOLVE_BY_ENTITY_TEXT,
    COUNT_CODING_REVIEW_GROUPS,
    COUNT_CODING_REVIEW_PENDING,
    DEACTIVATE_CODING_IGNORE_RULE,
    DELETE_ALL_CODING_REVIEWS_UNCONDITIONAL,
    GET_ALL_CODING_IGNORE_RULES,
    GET_CODING_IGNORE_RULES,
    GET_CODING_REVIEW_FOR_ENTITY,
    GET_CODING_REVIEW_QUEUE,
    GET_CODING_REVIEW_STATS,
    GET_ENCOUNTER_SIBLINGS,
    GET_PENDING_FOR_RECHECK,
    GROUP_CODING_REVIEWS_BY_ENTITY,
    IGNORE_CODING_REVIEW,
    RESOLVE_CODING_REVIEW,
    UPDATE_CODING_REVIEW_FIELDS,
    DEACTIVATE_CONTEXT_RULE,
    GET_CONTEXT_RULES,
    UPDATE_ASSERTION_FOR_REVIEW,
    UPDATE_ENTITY_LABEL_FOR_TEXT,
    UPSERT_CODING_IGNORE_RULE,
    UPSERT_CONTEXT_RULE,
    GET_TIER_OVERRIDE_STATS,
    DELETE_RESOLVED_CODING_REVIEWS,
)
from libs.cypher.exclusion_queries import DELETE_ALL_HITL_TASKS
from libs.cypher.training_candidate_queries import (
    COUNT_TRAINING_CANDIDATES_PAGE,
    DELETE_TRAINING_CANDIDATE_AND_ARTIFACTS,
    GET_TRAINING_CANDIDATE_BY_ID,
    GET_TRAINING_CANDIDATE_STATS,
    GET_TRAINING_CANDIDATES_PAGE,
    MARK_TRAINING_CANDIDATE_DUPLICATES,
    UPSERT_TRAINING_CANDIDATE,
    UPDATE_TRAINING_CANDIDATE_STATUS,
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
from libs.cypher.synthetic_candidate_queries import (
    GET_ALL_VALUESETS_RAW_JSON,
    GET_CONCEPTS_WITHOUT_SURFACE_FORMS_FOR_IDS,
    GET_ENCOUNTER_CONTEXT_CANDIDATES,
    GET_GOLD_OUTPUT_EXAMPLE_CANDIDATES,
    GET_SURFACE_FORMS_FOR_CONCEPT_IDS,
    GET_SURFACE_FORMS_FOR_GENERATION,
    GET_SURFACE_FORM_TAG_COUNTS,
    GET_SYNTHETIC_GOLD_STATS,
    GET_SYNTHETIC_GOLD_TAG_BREAKDOWN,
    GET_VALUESET_RAW_JSON,
)
from libs.cypher.phrase_consistency_queries import (
    DELETE_PHRASE_MULTILABEL_APPROVAL,
    LIST_PHRASE_MULTILABEL_APPROVALS,
    UPSERT_PHRASE_MULTILABEL_APPROVAL,
)
from libs.cypher.surface_form_task_queries import (
    COUNT_SURFACE_FORM_TASKS,
    CREATE_REVOCATION_CASCADE_REVIEW,
    DELETE_ALL_SURFACE_FORM_TASKS,
    GET_ENCOUNTERS_FOR_REVOKED_CONCEPT,
    GET_SURFACE_FORM_TASK_BY_ID,
    LIST_PENDING_SURFACE_FORM_TASKS,
    RESOLVE_SURFACE_FORM_TASK,
    REVOKE_SURFACE_FORM,
    UPSERT_SURFACE_FORM_TASK,
    make_surface_form_task_id,
)
from services.terminology_api.app.queries.terminology import (
    APPROVE_SURFACE_FORM,
)
from libs.cypher.label_verification_queries import (
    COUNT_VERIFICATION_HISTORY,
    COUNT_VERIFICATION_QUEUE_PENDING,
    GET_VERIFICATION_HISTORY,
    GET_LABEL_VERIFIER_SCORECARD,
    GET_LABEL_VERIFIER_SCORECARD_BREAKDOWN,
    GET_VERIFICATION_QUEUE,
    GET_VERIFICATION_STATS,
    RESOLVE_LABEL_VERIFICATION_REVIEW,
)
from libs.cypher.post_processor_rule_queries import (
    GET_POST_PROCESSOR_RULES,
    UPSERT_POST_PROCESSOR_RULE,
    UPDATE_POST_PROCESSOR_RULE_ACTIVE,
)
from libs.cypher.documents_queries import LIST_ENCOUNTER_CODED_LINKS
from app.models.neo4j_schema import GET_ENCOUNTER
from libs.ner.schema_mapper import LABEL_TO_SNOMED_TAG
from libs.ner.training_label_writer import bulk_upsert_training_labels
from libs.ner.span_finder import find_span
from libs.nlp.sentence_splitter import (
    SentenceSplitter,
    filter_header_sentences,
    is_header_sentence,
    is_non_evidence_line,
    is_referral_procedure_phrase,
)
from libs.training_data.gold_granularity import (
    classify_gold_record,
    parse_entities_json,
)
from libs.prompts.synthetic_ner_sentences import (
    build_synthetic_sentence_prompts,
    _strip_snomed_qualifier,
)
from libs.terminology.client import TerminologyClient, get_always_ignore_patterns
from libs.terminology.preferred_terms import (
    hydrate_entities_json_items_with_pt_cache,
)
from libs.pipeline.post_processing import run_post_processing
from libs.ner.deid_validator import DeIdValidator
from libs.utils.deidentify import deidentify_text
from libs.utils.logging import logging_context

logger = logging.getLogger(__name__)

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


router = APIRouter(prefix="/training", tags=["training"])
PIPELINE_WORKER_BASE = os.getenv("PIPELINE_WORKER_URL", "http://localhost:8006").rstrip(
    "/"
)
TRAINING_WORKER_BASE = os.getenv("TRAINING_WORKER_URL", "http://localhost:8005").rstrip(
    "/"
)

from app.routers._training_askleo import register_askleo_routes
from app.routers._training_ai_first_pass import register_ai_first_pass_routes

register_askleo_routes(router)
register_ai_first_pass_routes(router)


def _enrich_items_entities_with_pt_cache(
    session: Any,
    items: list[dict[str, Any]],
) -> None:
    hydrate_entities_json_items_with_pt_cache(session=session, items=items)


async def _proxy_pipeline_worker_json(
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = f"{PIPELINE_WORKER_BASE}{path}"
    headers = {**get_service_auth_header()}
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.request(method, url, json=json_body, headers=headers)

    if resp.status_code >= 400:
        detail: Any
        try:
            payload = resp.json()
            detail = payload.get("detail", payload)
        except ValueError:
            detail = resp.text or f"Pipeline worker error ({resp.status_code})"
        raise HTTPException(status_code=resp.status_code, detail=detail)

    try:
        return resp.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=502, detail="Pipeline worker returned invalid JSON"
        ) from exc


async def _proxy_training_worker(
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Forward a request to the training worker service."""
    url = f"{TRAINING_WORKER_BASE}{path}"
    headers = {**get_service_auth_header()}
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.request(method, url, json=json_body, headers=headers)
    except httpx.ConnectError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Training worker unavailable at {TRAINING_WORKER_BASE}",
        ) from exc

    if resp.status_code >= 400:
        detail: Any
        try:
            payload = resp.json()
            detail = payload.get("detail", payload)
        except ValueError:
            detail = resp.text or f"Training worker error ({resp.status_code})"
        raise HTTPException(status_code=resp.status_code, detail=detail)

    try:
        return resp.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=502, detail="Training worker returned invalid JSON"
        ) from exc


# ---------------------------------------------------------------------------
# Training job management — proxied to the training worker service
# ---------------------------------------------------------------------------


class _StartJobBody(BaseModel):
    base_model_version: str = ""
    notes: str = ""
    triggered_by: str = "api"


@router.get("/jobs")
async def list_training_jobs(
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """List all NER training jobs (most recent first).

    Proxied to the training worker at GET /train/jobs.
    """
    return await _proxy_training_worker("GET", "/train/jobs")


@router.post("/jobs")
async def start_training_job(
    body: _StartJobBody,
    scope: CallerScope = Depends(get_caller_scope),
    _admin: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Queue a new NER training run.

    Proxied to the training worker at POST /train/jobs.
    Returns immediately with job_id; subscribe to the SSE progress stream
    at GET /train/progress/{job_id} on the training worker directly.
    """
    return await _proxy_training_worker(
        "POST", "/train/jobs", json_body=body.model_dump()
    )


@router.get("/jobs/{job_id}")
async def get_training_job(
    job_id: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Return full detail for a single training job.

    Proxied to the training worker at GET /train/jobs/{job_id}.
    """
    return await _proxy_training_worker("GET", f"/train/jobs/{job_id}")


@router.delete("/jobs/{job_id}")
async def cancel_training_job(
    job_id: str,
    scope: CallerScope = Depends(get_caller_scope),
    _admin: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Cancel a queued training job.

    Proxied to the training worker at DELETE /train/jobs/{job_id}.
    """
    return await _proxy_training_worker("DELETE", f"/train/jobs/{job_id}")


# ---------------------------------------------------------------------------
# Regex safety helper (GAP-016 — ReDoS + injection via user-supplied patterns)
# ---------------------------------------------------------------------------

# Probe strings used by the ReDoS subprocess to trigger catastrophic backtracking.
# - _REDOS_PROBE_LOWER: all-lowercase; fails patterns requiring uppercase (email-style).
# - _REDOS_PROBE_SIMPLE: classic probe for nested-quantifier patterns.
_REDOS_PROBE_LOWER = "a" * 38
_REDOS_PROBE_SIMPLE = "a" * 50 + "b"


def _validate_regex(pattern: str, max_length: int = 200) -> None:
    """Validate a user-supplied regex for safety before persisting.

    Raises HTTPException(422) if:
    - The pattern exceeds max_length characters.
    - The pattern contains a regex syntax error.
    - The pattern exhibits catastrophic backtracking (ReDoS).

    Uses a subprocess for the ReDoS probe so the GIL cannot block the timeout.
    The subprocess is killed at the OS level if it does not complete within 0.5s.
    """
    if len(pattern) > max_length:
        raise HTTPException(
            status_code=422,
            detail=f"context_regex must not exceed {max_length} characters",
        )
    try:
        re.compile(pattern)
    except re.error as exc:
        raise HTTPException(status_code=422, detail=f"Invalid regex: {exc}") from exc

    probe_code = (
        "import re, sys\n"
        f"compiled = re.compile({pattern!r})\n"
        f"compiled.search({_REDOS_PROBE_LOWER!r})\n"
        f"compiled.search({_REDOS_PROBE_SIMPLE!r})\n"
        "sys.exit(0)\n"
    )
    try:
        subprocess.run(
            [sys.executable, "-c", probe_code],
            timeout=0.5,
            capture_output=True,
        )
    except subprocess.TimeoutExpired:
        logger.warning("ReDoS probe timed out for regex: %r", pattern[:80])
        raise HTTPException(
            status_code=422,
            detail="context_regex exhibits catastrophic backtracking and is not permitted",
        )


# ------------------------------------------------------------------
# Request models
# ------------------------------------------------------------------


class ExcludeLabelRequest(BaseModel):
    reason: str


class UpdateEntitiesRequest(BaseModel):
    entities: list[dict[str, Any]]


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


class ResolveVerificationRequest(BaseModel):
    resolved_label: str
    resolved_text: str | None = None
    remove_entity: bool = False
    resolve_only: bool = False
    reviewer: str = "unknown"


class BulkImportRecord(BaseModel):
    encounter_id: str
    patient_id: str
    text: str
    entities: list[dict[str, Any]]
    quality_score: float = 1.0


class BulkImportRequest(BaseModel):
    records: list[BulkImportRecord]
    source: str = "anchor_mining"
    source_ref: str = ""


class PostProcessorRuleRequest(BaseModel):
    action: str  # suppress | rewrite | relabel
    match_text: str | None = None
    match_label: str | None = None
    context_regex: str | None = None
    window_chars: int = 40
    rewrite_text: str | None = None
    rewrite_label: str | None = None
    priority: int = 100
    active: bool = True
    notes: str = ""
    created_by: str = "operations_ui"


class UpdatePostProcessorRuleRequest(BaseModel):
    active: bool


class VerifyAllRequest(BaseModel):
    mode: str = "all"  # all | hitl_only | re_extract
    reset_pending: bool = False


class ResolveSurfaceFormTaskRequest(BaseModel):
    status: str  # approved | rejected | modified
    resolved_concept: str | None = None
    resolved_by: str = "operations_ui"


class SyntheticGenerationRequest(BaseModel):
    limit: int = Field(default=50, ge=1, le=50)
    sentences_per_form: int = Field(default=10, ge=1, le=10)
    semantic_tags: list[str] | None = None
    valueset_ids: list[str] | None = None
    use_derived_forms: bool = False


class SyntheticQueueRequest(BaseModel):
    limit: int = Field(default=200, ge=1, le=500)
    sentences_per_form: int = Field(default=10, ge=1, le=10)
    semantic_tags: list[str] | None = None
    valueset_ids: list[str] | None = None
    use_derived_forms: bool = False


class CandidateDedupeRequest(BaseModel):
    status: str | None = "completed"
    source: str | None = None
    search: str | None = None
    max_candidates: int = Field(default=1200, ge=50, le=3000)
    similarity_threshold: float = Field(default=0.85, ge=0.5, le=0.99)


class SimilarCandidatesByEntityRequest(BaseModel):
    candidate_id: str
    limit: int = Field(default=20, ge=1, le=100)
    similarity_threshold: float = Field(default=0.65, ge=0.3, le=0.99)


# ------------------------------------------------------------------
# GET /training/labels/stats
# ------------------------------------------------------------------


@router.get("/labels/stats")
def get_label_stats(scope: CallerScope = Depends(get_caller_scope)) -> dict[str, Any]:
    """Return corpus statistics: total, included, excluded, broken down by source."""
    client = PatientGraphClient()
    try:
        with client.session() as session:
            row = session.run(GET_TRAINING_LABEL_STATS).single()
            stats = dict(row) if row else {}

            # Per-label-type breakdown (only for included labels)
            type_rows = session.run(LABEL_ENTITY_TYPE_BREAKDOWN)
            by_label = {r["label"]: r["n"] for r in type_rows}

        return {
            "total": stats.get("total", 0),
            "included": stats.get("included", 0),
            "excluded": stats.get("excluded", 0),
            "by_source": {
                "hitl_approval": stats.get("hitl", 0),
                "coding_correction": stats.get("coding_correction", 0),
                "anchor_mining": stats.get("anchor_mining", 0),
                "seed": stats.get("seed", 0),
            },
            "by_label_type": by_label,
        }
    finally:
        client.close()


# ------------------------------------------------------------------
# GET /training/labels
# ------------------------------------------------------------------


@router.get("/labels")
def list_labels(
    scope: CallerScope = Depends(get_caller_scope),
    source: Optional[str] = Query(default=None),
    include: Optional[bool] = Query(default=None),
    search: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, le=200),
) -> dict[str, Any]:
    """Return a paginated list of training labels with optional filters."""
    skip = (page - 1) * page_size
    client = PatientGraphClient()
    try:
        with client.session() as session:
            rows = session.run(
                GET_TRAINING_LABELS_PAGE,
                source=source,
                include=include,
                search=search,
                skip=skip,
                limit=page_size,
            )
            labels = [dict(r) for r in rows]

            total_row = session.run(
                COUNT_TRAINING_LABELS_PAGE,
                source=source,
                include=include,
                search=search,
            ).single()
            total = total_row["total"] if total_row else 0

        return {
            "labels": labels,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": max(1, -(-total // page_size)),
        }
    finally:
        client.close()


# POST /training/labels/{label_id}/exclude
# ------------------------------------------------------------------


@router.post("/labels/{label_id}/exclude")
def exclude_label(
    label_id: str,
    body: ExcludeLabelRequest,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Mark a training label as excluded (soft delete — preserves the record)."""
    if not body.reason or not body.reason.strip():
        raise HTTPException(status_code=422, detail="reason must be non-empty")
    client = PatientGraphClient()
    try:
        with client.session() as session:
            row = session.run(
                EXCLUDE_TRAINING_LABEL, label_id=label_id, reason=body.reason.strip()
            ).single()
            if not row:
                raise HTTPException(
                    status_code=404, detail=f"Label {label_id!r} not found"
                )
        logger.info("TrainingLabel excluded: %s reason=%r", label_id[:8], body.reason)
        return {
            "label_id": label_id,
            "include": False,
            "excluded_reason": body.reason.strip(),
        }
    finally:
        client.close()


# ------------------------------------------------------------------
# POST /training/labels/{label_id}/include
# ------------------------------------------------------------------


@router.post("/labels/{label_id}/include")
def include_label(
    label_id: str, scope: CallerScope = Depends(get_caller_scope)
) -> dict[str, Any]:
    """Re-include a previously excluded training label."""
    client = PatientGraphClient()
    try:
        with client.session() as session:
            row = session.run(INCLUDE_TRAINING_LABEL, label_id=label_id).single()
            if not row:
                raise HTTPException(
                    status_code=404, detail=f"Label {label_id!r} not found"
                )
        logger.info("TrainingLabel re-included: %s", label_id[:8])
        return {"label_id": label_id, "include": True}
    finally:
        client.close()


# ------------------------------------------------------------------
# PATCH /training/labels/{label_id}/entities
# ------------------------------------------------------------------

_VALID_ENTITY_LABELS: frozenset[str] = frozenset(
    {
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
        "X_TEMPORAL",
        "X_DOSAGE",
        "X_FREQUENCY",
        "X_ROUTE",
    }
)


@router.patch("/labels/{label_id}/entities")
def update_label_entities(
    label_id: str,
    body: UpdateEntitiesRequest,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Replace the entities_json of a training label.

    Each entity must carry at minimum ``text`` and ``label``.  ``label`` must
    be one of the canonical NER label types.  ``start`` / ``end`` offsets are
    optional — if omitted they are inferred by substring search or default to 0.
    """
    import json

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
        validated.append(
            {
                "text": ent["text"].strip(),
                "label": label_val,
                "start": ent.get("start", 0),
                "end": ent.get("end", 0),
                **({"assertion": ent["assertion"]} if "assertion" in ent else {}),
                **({"confidence": ent["confidence"]} if "confidence" in ent else {}),
            }
        )

    entities_json = json.dumps(validated)
    client = PatientGraphClient()
    try:
        with client.session() as session:
            row = session.run(
                UPDATE_TRAINING_LABEL_ENTITIES,
                label_id=label_id,
                entities_json=entities_json,
            ).single()
            if not row:
                raise HTTPException(
                    status_code=404, detail=f"Label {label_id!r} not found"
                )
        logger.info(
            "TrainingLabel entities updated: %s count=%d", label_id[:8], len(validated)
        )
        return {"label_id": label_id, "entities": validated}
    finally:
        client.close()


# ------------------------------------------------------------------
# POST /training/labels/verify-all
# GET  /training/labels/verify-all/status
# ------------------------------------------------------------------


@router.post("/labels/verify-all")
async def verify_all_labels(
    body: VerifyAllRequest | None = None,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Trigger background dual-model verification over included labels."""
    _ = scope
    payload = (
        {"mode": "all", "reset_pending": False} if body is None else body.model_dump()
    )
    return await _proxy_pipeline_worker_json(
        "POST", "/label-verify/start", json_body=payload
    )


@router.post("/labels/verify-all/cancel")
async def cancel_verify_all(
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Request graceful cancellation of running label verification job."""
    _ = scope
    return await _proxy_pipeline_worker_json("POST", "/label-verify/stop")


@router.get("/labels/verify-all/status")
async def verification_status(
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Return current background verification status plus corpus stats."""
    _ = scope
    return await _proxy_pipeline_worker_json("GET", "/label-verify/status")


# ------------------------------------------------------------------
# POST /training/labels/agentic-audit
# Agentic auditor endpoints removed — replaced by verification subgraph
# in libs/pipeline_graph/subgraphs/verification.py


# ------------------------------------------------------------------
# GET /training/labels/verification-queue
# POST /training/labels/verification-queue/{review_id}/resolve
# ------------------------------------------------------------------


@router.get("/labels/verification-queue")
def get_verification_queue(
    scope: CallerScope = Depends(get_caller_scope),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, le=500),
) -> dict[str, Any]:
    """Return unresolved label-verification disagreements for human review."""
    skip = (page - 1) * page_size
    client = PatientGraphClient()
    try:
        with client.session() as session:
            rows = session.run(GET_VERIFICATION_QUEUE, skip=skip, limit=page_size)
            reviews = [dict(r) for r in rows]
            pending_row = session.run(COUNT_VERIFICATION_QUEUE_PENDING).single()
            stats_row = session.run(GET_VERIFICATION_STATS).single()
        total = pending_row["pending"] if pending_row else 0
        return {
            "reviews": reviews,
            "total": total,
            "pending": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, -(-total // page_size)),
            "stats": dict(stats_row) if stats_row else {},
        }
    finally:
        client.close()


@router.get("/labels/verification-history")
def get_verification_history(
    scope: CallerScope = Depends(get_caller_scope),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, le=500),
) -> dict[str, Any]:
    """Return resolved label-verification reviews so users can audit past decisions."""
    skip = (page - 1) * page_size
    client = PatientGraphClient()
    try:
        with client.session() as session:
            rows = session.run(GET_VERIFICATION_HISTORY, skip=skip, limit=page_size)
            reviews = [dict(r) for r in rows]
            total_row = session.run(COUNT_VERIFICATION_HISTORY).single()
        total = int(total_row["total"] if total_row else 0)
        return {
            "reviews": reviews,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, -(-total // page_size)),
        }
    finally:
        client.close()


@router.post("/labels/verification-queue/{review_id}/resolve")
def resolve_verification_review(
    review_id: str,
    body: ResolveVerificationRequest,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Resolve a disagreement and write the chosen entity label into TrainingLabel.

    Records which model(s) were correct so per-model accuracy stats can be
    calculated via GET /training/labels/verifier-scorecard.
    """
    if not body.remove_entity and body.resolved_label not in _VALID_ENTITY_LABELS:
        raise HTTPException(
            status_code=422,
            detail=f"resolved_label must be one of {sorted(_VALID_ENTITY_LABELS)}",
        )

    client = PatientGraphClient()
    try:
        with client.session() as session:
            review_row = session.run(
                """
                MATCH (r:LabelVerificationReview {review_id: $review_id})
                WHERE coalesce(r.resolved, false) = false
                RETURN r.label_id       AS label_id,
                       r.entity_index   AS entity_index,
                       r.entity_text    AS entity_text,
                       r.current_label  AS current_label,
                       r.model_a_label  AS model_a_label,
                       r.model_b_label  AS model_b_label
                """,
                review_id=review_id,
            ).single()
            if not review_row:
                raise HTTPException(
                    status_code=404, detail=f"Review {review_id!r} not found"
                )

            label_row = session.run(
                GET_TRAINING_LABEL_BY_ID,
                label_id=review_row["label_id"],
            ).single()
            if not label_row:
                raise HTTPException(
                    status_code=404,
                    detail=f"Label {review_row['label_id']!r} not found",
                )

            if body.resolve_only:
                entities_json = label_row["entities_json"] or "[]"
                model_a_was_correct = review_row["model_a_label"] == body.resolved_label
                model_b_was_correct = review_row["model_b_label"] == body.resolved_label
                result_row = session.run(
                    RESOLVE_LABEL_VERIFICATION_REVIEW,
                    review_id=review_id,
                    resolved_label=body.resolved_label,
                    reviewer=body.reviewer,
                    entities_json=entities_json,
                    model_a_was_correct=model_a_was_correct,
                    model_b_was_correct=model_b_was_correct,
                ).single()
                if not result_row:
                    raise HTTPException(
                        status_code=404, detail=f"Review {review_id!r} not found"
                    )
                return {
                    "review_id": result_row["review_id"],
                    "label_id": result_row["label_id"],
                    "resolved_label": result_row["resolved_label"],
                    "model_a_was_correct": result_row["model_a_was_correct"],
                    "model_b_was_correct": result_row["model_b_was_correct"],
                    "resolved_only": True,
                }

            entities = json.loads(label_row["entities_json"] or "[]")
            idx = int(review_row["entity_index"])
            if idx < 0 or idx >= len(entities):
                # Index can drift if another entity was removed first. Fallback by matching
                # review snapshot (entity_text + current_label) against current entities.
                fallback_idx = next(
                    (
                        i
                        for i, ent in enumerate(entities)
                        if str(ent.get("text", ""))
                        == str(review_row.get("entity_text", ""))
                        and str(ent.get("label", ""))
                        == str(review_row.get("current_label", ""))
                    ),
                    -1,
                )
                if fallback_idx == -1:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Invalid entity index {idx} for this label",
                    )
                idx = fallback_idx

            if body.remove_entity:
                # Allow UI to target removal of any entity in the record by passing
                # resolved_text (+ optional resolved_label). Falls back to review idx.
                target_text = (body.resolved_text or "").strip()
                target_label = (body.resolved_label or "").strip()
                remove_idx = idx
                if target_text:
                    candidates = [
                        i
                        for i, ent in enumerate(entities)
                        if str(ent.get("text", "")).strip() == target_text
                        and (
                            not target_label
                            or str(ent.get("label", "")) == target_label
                        )
                    ]
                    if candidates:
                        remove_idx = min(candidates, key=lambda i: abs(i - idx))

                entities.pop(remove_idx)
                entities_json = json.dumps(entities)
                if entities:
                    session.run(
                        UPDATE_TRAINING_LABEL_ENTITIES,
                        label_id=review_row["label_id"],
                        entities_json=entities_json,
                    )
                else:
                    session.run(
                        EXCLUDE_TRAINING_LABEL,
                        label_id=review_row["label_id"],
                        reason="No valid entities after verifier HITL span removal",
                    )

                result_row = session.run(
                    RESOLVE_LABEL_VERIFICATION_REVIEW,
                    review_id=review_id,
                    resolved_label="__REMOVED__",
                    reviewer=body.reviewer,
                    entities_json=entities_json,
                    model_a_was_correct=False,
                    model_b_was_correct=False,
                ).single()
                if not result_row:
                    raise HTTPException(
                        status_code=404, detail=f"Review {review_id!r} not found"
                    )
                return {
                    "review_id": result_row["review_id"],
                    "label_id": result_row["label_id"],
                    "resolved_label": result_row["resolved_label"],
                    "model_a_was_correct": result_row["model_a_was_correct"],
                    "model_b_was_correct": result_row["model_b_was_correct"],
                    "removed_entity": True,
                    "remaining_entities": len(entities),
                }

            existing_text = str(entities[idx].get("text", ""))
            resolved_text = (body.resolved_text or existing_text).strip()
            if not resolved_text:
                raise HTTPException(
                    status_code=422, detail="resolved_text must be non-empty"
                )

            encounter_text = str(label_row.get("text", ""))
            old_start = int(entities[idx].get("start", 0) or 0)

            # 1) Exact substring (case-sensitive), choosing the closest occurrence
            # to previous offset if the span appears multiple times.
            exact_positions: list[int] = []
            scan_pos = encounter_text.find(resolved_text)
            while scan_pos != -1:
                exact_positions.append(scan_pos)
                scan_pos = encounter_text.find(resolved_text, scan_pos + 1)

            best_start: int | None = None
            if exact_positions:
                best_start = min(exact_positions, key=lambda p: abs(p - old_start))
            else:
                # 2) Case-insensitive fallback.
                hay = encounter_text.lower()
                needle = resolved_text.lower()
                ci_positions: list[int] = []
                scan_pos = hay.find(needle)
                while scan_pos != -1:
                    ci_positions.append(scan_pos)
                    scan_pos = hay.find(needle, scan_pos + 1)
                if ci_positions:
                    best_start = min(ci_positions, key=lambda p: abs(p - old_start))
                else:
                    # 3) Whitespace-normalized + case-insensitive fallback.
                    def _collapse_ws_with_map(s: str) -> tuple[str, list[int]]:
                        chars: list[str] = []
                        idx_map: list[int] = []
                        prev_space = False
                        for i, ch in enumerate(s):
                            if ch.isspace():
                                if prev_space:
                                    continue
                                chars.append(" ")
                                idx_map.append(i)
                                prev_space = True
                            else:
                                chars.append(ch)
                                idx_map.append(i)
                                prev_space = False
                        return "".join(chars), idx_map

                    norm_hay, map_hay = _collapse_ws_with_map(encounter_text)
                    norm_needle = re.sub(r"\s+", " ", resolved_text)
                    norm_pos = norm_hay.lower().find(norm_needle.lower())
                    if norm_pos != -1:
                        best_start = map_hay[norm_pos]

            if best_start is None:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "resolved_text not found in encounter text; try copying exact text "
                        "from the encounter, including punctuation/spacing."
                    ),
                )

            entities[idx]["label"] = body.resolved_label
            entities[idx]["text"] = resolved_text
            entities[idx]["start"] = best_start
            entities[idx]["end"] = best_start + len(resolved_text)
            entities_json = json.dumps(entities)

            # Determine which model(s) were correct — mirrors classification vote pattern.
            model_a_was_correct = review_row["model_a_label"] == body.resolved_label
            model_b_was_correct = review_row["model_b_label"] == body.resolved_label

            result_row = session.run(
                RESOLVE_LABEL_VERIFICATION_REVIEW,
                review_id=review_id,
                resolved_label=body.resolved_label,
                reviewer=body.reviewer,
                entities_json=entities_json,
                model_a_was_correct=model_a_was_correct,
                model_b_was_correct=model_b_was_correct,
            ).single()
            if not result_row:
                raise HTTPException(
                    status_code=404, detail=f"Review {review_id!r} not found"
                )

        return {
            "review_id": result_row["review_id"],
            "label_id": result_row["label_id"],
            "resolved_label": result_row["resolved_label"],
            "model_a_was_correct": result_row["model_a_was_correct"],
            "model_b_was_correct": result_row["model_b_was_correct"],
        }
    finally:
        client.close()


@router.get("/labels/verifier-scorecard")
def get_verifier_scorecard(
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Per-model accuracy scorecard across all resolved label verification reviews."""
    client = PatientGraphClient()
    try:
        with client.session() as session:
            row = session.run(GET_LABEL_VERIFIER_SCORECARD).single()
            breakdown_rows = [
                dict(r) for r in session.run(GET_LABEL_VERIFIER_SCORECARD_BREAKDOWN)
            ]
        if not row:
            return {"total_resolved": 0}
        data = dict(row)
        total = data.get("total_resolved") or 0
        by_label: dict[str, dict[str, Any]] = {}
        by_resolver: dict[str, dict[str, Any]] = {}
        for r in breakdown_rows:
            label = str(r.get("label") or "__UNKNOWN__")
            resolver = str(r.get("resolved_by") or "human")
            n = int(r.get("n") or 0)
            model_a_correct = int(r.get("model_a_correct") or 0)
            model_b_correct = int(r.get("model_b_correct") or 0)
            label_bucket = by_label.setdefault(
                label, {"total": 0, "model_a_correct": 0, "model_b_correct": 0}
            )
            label_bucket["total"] += n
            label_bucket["model_a_correct"] += model_a_correct
            label_bucket["model_b_correct"] += model_b_correct
            bucket = by_resolver.setdefault(
                resolver, {"total": 0, "model_a_correct": 0, "model_b_correct": 0}
            )
            bucket["total"] += n
            bucket["model_a_correct"] += model_a_correct
            bucket["model_b_correct"] += model_b_correct

        label_accuracy = {
            k: {
                "total": v["total"],
                "model_a_accuracy": (
                    round(v["model_a_correct"] / v["total"], 4) if v["total"] else None
                ),
                "model_b_accuracy": (
                    round(v["model_b_correct"] / v["total"], 4) if v["total"] else None
                ),
            }
            for k, v in by_label.items()
        }
        resolver_accuracy = {
            k: {
                "total": v["total"],
                "model_a_accuracy": (
                    round(v["model_a_correct"] / v["total"], 4) if v["total"] else None
                ),
                "model_b_accuracy": (
                    round(v["model_b_correct"] / v["total"], 4) if v["total"] else None
                ),
            }
            for k, v in by_resolver.items()
        }
        auto_rows = [v for k, v in by_resolver.items() if k.startswith("auto_triage:")]
        auto_total = sum(v["total"] for v in auto_rows)
        auto_a_correct = sum(v["model_a_correct"] for v in auto_rows)
        auto_b_correct = sum(v["model_b_correct"] for v in auto_rows)
        return {
            **data,
            "model_a_accuracy": (
                round(data["model_a_correct"] / total, 4) if total else None
            ),
            "model_b_accuracy": (
                round(data["model_b_correct"] / total, 4) if total else None
            ),
            "per_label": label_accuracy,
            "by_resolved_by": resolver_accuracy,
            "auto_triage_accuracy": {
                "total": auto_total,
                "model_a_accuracy": (
                    round(auto_a_correct / auto_total, 4) if auto_total else None
                ),
                "model_b_accuracy": (
                    round(auto_b_correct / auto_total, 4) if auto_total else None
                ),
            },
        }
    finally:
        client.close()


# ------------------------------------------------------------------
# Post-processor rules
# ------------------------------------------------------------------


@router.get("/post-processor-rules")
def list_post_processor_rules(
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """List all persisted post-processor rules."""
    client = PatientGraphClient()
    try:
        with client.session() as session:
            rows = session.run(GET_POST_PROCESSOR_RULES)
            rules = [dict(r) for r in rows]
        return {"rules": rules, "total": len(rules)}
    finally:
        client.close()


@router.post("/post-processor-rules")
def create_post_processor_rule(
    body: PostProcessorRuleRequest,
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Create or update a post-processor rule used by export and runtime pipeline."""
    valid_actions = {"suppress", "rewrite", "relabel"}
    if body.action not in valid_actions:
        raise HTTPException(
            status_code=422, detail=f"action must be one of {sorted(valid_actions)}"
        )
    if body.context_regex:
        _validate_regex(body.context_regex)
    if body.action in {"rewrite", "relabel"} and not body.rewrite_label:
        raise HTTPException(
            status_code=422,
            detail="rewrite_label is required for rewrite/relabel actions",
        )
    if body.action == "rewrite" and not body.rewrite_text:
        raise HTTPException(
            status_code=422, detail="rewrite_text is required for rewrite action"
        )
    if not body.match_text and not body.match_label and not body.context_regex:
        raise HTTPException(
            status_code=422, detail="at least one matcher must be provided"
        )

    rule_id = str(uuid.uuid4())
    client = PatientGraphClient()
    try:
        with client.session() as session:
            row = session.run(
                UPSERT_POST_PROCESSOR_RULE,
                rule_id=rule_id,
                active=body.active,
                priority=body.priority,
                action=body.action,
                match_text=body.match_text,
                match_label=body.match_label,
                context_regex=body.context_regex,
                window_chars=body.window_chars,
                rewrite_text=body.rewrite_text,
                rewrite_label=body.rewrite_label,
                created_by=body.created_by,
                notes=body.notes,
            ).single()
        return {"rule_id": row["rule_id"], "status": "created"}
    finally:
        client.close()


@router.patch("/post-processor-rules/{rule_id}")
def update_post_processor_rule(
    rule_id: str,
    body: UpdatePostProcessorRuleRequest,
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Toggle active status for an existing post-processor rule."""
    client = PatientGraphClient()
    try:
        with client.session() as session:
            row = session.run(
                UPDATE_POST_PROCESSOR_RULE_ACTIVE,
                rule_id=rule_id,
                active=body.active,
            ).single()
            if not row:
                raise HTTPException(
                    status_code=404, detail=f"Rule {rule_id!r} not found"
                )
        return {"rule_id": row["rule_id"], "active": row["active"]}
    finally:
        client.close()


# ------------------------------------------------------------------
# GET /training/labels/{label_id}
# ------------------------------------------------------------------


@router.get("/labels/{label_id}")
def get_label(
    label_id: str, scope: CallerScope = Depends(get_caller_scope)
) -> dict[str, Any]:
    """Return full detail for a single training label."""
    client = PatientGraphClient()
    try:
        with client.session() as session:
            row = session.run(GET_TRAINING_LABEL_BY_ID, label_id=label_id).single()
            if not row:
                raise HTTPException(
                    status_code=404, detail=f"Label {label_id!r} not found"
                )
            return dict(row)
    finally:
        client.close()


# ------------------------------------------------------------------
# POST /training/labels/bulk-import
# ------------------------------------------------------------------


@router.post("/labels/bulk-import")
def bulk_import_labels(
    body: BulkImportRequest, scope: CallerScope = Depends(get_caller_scope)
) -> dict[str, Any]:
    """Bulk-upsert training labels from offline scripts (anchor mining, QA).

    Called by ``scripts/qa_all_domains_ner.py`` after a QA pass to ingest
    mined domain entities into Neo4j as TrainingLabel nodes.
    """
    valid_sources = {"anchor_mining", "seed", "hitl_approval", "coding_correction"}
    if body.source not in valid_sources:
        raise HTTPException(
            status_code=422,
            detail=f"source must be one of {sorted(valid_sources)}",
        )
    records = [r.model_dump() for r in body.records]
    label_ids = bulk_upsert_training_labels(
        records,
        source=body.source,
        source_ref=body.source_ref,
    )
    logger.info(
        "bulk-import: %d labels ingested source=%s ref=%s",
        len(label_ids),
        body.source,
        body.source_ref,
    )
    return {
        "imported": len(label_ids),
        "source": body.source,
        "label_ids": label_ids[:20],  # truncate for response size
    }


# ------------------------------------------------------------------
# POST /training/export-preview
# ------------------------------------------------------------------


@router.post("/export-preview")
def export_preview(scope: CallerScope = Depends(get_caller_scope)) -> dict[str, Any]:
    """Dry-run: count how many labels would be used in the next training run.

    Returns label counts broken down by source and label type so the user
    can verify the corpus before triggering a training job.
    """
    client = PatientGraphClient()
    try:
        with client.session() as session:
            total_row = session.run(COUNT_EXPORTABLE_LABELS).single()
            total = total_row["total"] if total_row else 0

            type_rows = session.run(LABEL_ENTITY_TYPE_BREAKDOWN)
            by_label = {r["label"]: r["n"] for r in type_rows}

        return {
            "exportable_label_count": total,
            "ready_to_train": total
            >= int(__import__("os").getenv("TRAINING_MIN_LABEL_COUNT", "50")),
            "min_required": int(
                __import__("os").getenv("TRAINING_MIN_LABEL_COUNT", "50")
            ),
            "by_label_type": by_label,
        }
    finally:
        client.close()


# ------------------------------------------------------------------
# Coding Review endpoints
# ------------------------------------------------------------------


@router.get("/coding-review/queue")
def coding_review_queue(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=500),
    entity_text: Optional[str] = Query(default=None),
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Paginated queue of entities with missing or low-confidence SNOMED coding.

    When entity_text is provided, returns only records for that specific term
    so callers can inspect all encounter contexts before assigning a code.
    """
    client = PatientGraphClient()
    try:
        with client.session() as session:
            if entity_text:
                rows = session.run(
                    GET_CODING_REVIEW_FOR_ENTITY,
                    entity_text=entity_text,
                )
                items = [dict(r) for r in rows]
                return {
                    "items": items,
                    "page": 1,
                    "page_size": len(items),
                    "total_pages": 1,
                    "pending": len(items),
                    "stats": {},
                }

            skip = (page - 1) * page_size
            rows = session.run(GET_CODING_REVIEW_QUEUE, skip=skip, limit=page_size)
            items = [dict(r) for r in rows]

            pending_row = session.run(COUNT_CODING_REVIEW_PENDING).single()
            pending = pending_row["pending"] if pending_row else 0

            stats_row = session.run(GET_CODING_REVIEW_STATS).single()
            stats = dict(stats_row) if stats_row else {}

        total_pages = max(1, (pending + page_size - 1) // page_size)
        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "pending": pending,
            "stats": stats,
        }
    finally:
        client.close()


@router.post("/coding-review/encounter-siblings")
def coding_review_encounter_siblings(
    body: dict[str, Any],
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Return all CodingReview nodes for the same TrainingLabels.

    Accepts ``{"label_ids": ["id1", "id2", ...]}``.
    Groups results by label_id so the UI can show what other entities
    share the same encounter text.
    """
    label_ids = body.get("label_ids") or []
    if not label_ids or len(label_ids) > 500:
        return {"siblings": {}}

    client = PatientGraphClient()
    try:
        with client.session() as session:
            rows = session.run(GET_ENCOUNTER_SIBLINGS, label_ids=label_ids)
            grouped: dict[str, list[dict]] = {}
            for r in rows:
                rec = dict(r)
                lid = rec.pop("label_id")
                grouped.setdefault(lid, []).append(rec)
        return {"siblings": grouped}
    finally:
        client.close()


class CorrectEntityLabelRequest(BaseModel):
    entity_text: str
    entity_label: str
    corrected_by: str = "operations_ui"


@router.patch("/coding-review/entity-label")
def correct_entity_label(
    body: CorrectEntityLabelRequest,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Correct the NER entity label on all pending reviews for a given entity text.

    Called when a reviewer notices the model assigned the wrong semantic type
    (e.g. 'situation' instead of 'finding').  Updates all unresolved
    CodingReview nodes so subsequent searches and recheck runs use the right label.
    """
    if body.entity_label not in _VALID_ENTITY_LABELS:
        raise HTTPException(
            status_code=422,
            detail=f"entity_label must be one of {sorted(_VALID_ENTITY_LABELS)}",
        )
    client = PatientGraphClient()
    try:
        with client.session() as session:
            row = session.run(
                UPDATE_ENTITY_LABEL_FOR_TEXT,
                entity_text=body.entity_text,
                entity_label=body.entity_label,
            ).single()
        updated = row["updated_count"] if row else 0
        logger.info(
            "Entity label corrected: %r -> %r by %s (%d reviews updated)",
            body.entity_text,
            body.entity_label,
            body.corrected_by,
            updated,
        )
        return {
            "entity_text": body.entity_text,
            "entity_label": body.entity_label,
            "updated_count": updated,
        }
    finally:
        client.close()


_VALID_ASSERTIONS = frozenset(
    {
        "present",
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
)


class CorrectAssertionRequest(BaseModel):
    assertion: str
    corrected_by: str = "operations_ui"


@router.patch("/coding-review/{review_id}/assertion")
def correct_assertion(
    review_id: str,
    body: CorrectAssertionRequest,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Override the ConText assertion for a single CodingReview record.

    Sets assertion_override=true so re-processing never overwrites
    a human correction.
    """
    if body.assertion not in _VALID_ASSERTIONS:
        raise HTTPException(
            status_code=422,
            detail=f"assertion must be one of {sorted(_VALID_ASSERTIONS)}",
        )
    client = PatientGraphClient()
    try:
        with client.session() as session:
            row = session.run(
                UPDATE_ASSERTION_FOR_REVIEW,
                review_id=review_id,
                assertion=body.assertion,
            ).single()
        if not row:
            raise HTTPException(
                status_code=404, detail=f"Review {review_id!r} not found"
            )
        logger.info(
            "Assertion overridden: review=%s assertion=%r by %s",
            review_id[:12],
            body.assertion,
            body.corrected_by,
        )
        return {"review_id": review_id, "assertion": body.assertion}
    finally:
        client.close()


@router.get("/coding-review/grouped")
def coding_review_grouped(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Pending reviews grouped by entity_text.

    Returns one row per unique entity_text with the count of affected reviews,
    the best score, and a sample review_id.  This lets the HITL operator
    resolve an entire root cause (e.g. missing surface form) in one action
    instead of clicking through N identical items.
    """
    client = PatientGraphClient()
    try:
        with client.session() as session:
            skip = (page - 1) * page_size
            rows = session.run(
                GROUP_CODING_REVIEWS_BY_ENTITY,
                skip=skip,
                limit=page_size,
            )
            groups = [dict(r) for r in rows]

            count_row = session.run(COUNT_CODING_REVIEW_GROUPS).single()
            total_groups = count_row["group_count"] if count_row else 0

        total_pages = max(1, (total_groups + page_size - 1) // page_size)
        return {
            "groups": groups,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "total_groups": total_groups,
        }
    finally:
        client.close()


@router.get("/coding-review/tier-calibration")
def coding_review_tier_calibration(
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Override rate per decision tier -- used to calibrate safety layer thresholds.

    Returns the count of resolved items and the override rate (%) for each
    tier so quality leads can monitor whether the Tier 1 auto-code threshold
    is too permissive or the Tier 3 gate is blocking codeable items.
    """
    client = PatientGraphClient()
    try:
        with client.session() as session:
            rows = session.run(GET_TIER_OVERRIDE_STATS)
            stats = [dict(r) for r in rows]
        return {"tiers": stats}
    finally:
        client.close()


class ResolveCodingReviewRequest(BaseModel):
    resolved_concept_id: str
    resolved_term: str
    resolved_entity_text: str | None = None
    reviewer: str = "operations_ui"
    # Assertion to record on the resolved code. "declined", "cancelled", or
    # "refuted" when LEO detected the patient declined/cancelled or an initial
    # impression was overridden by subsequent investigation.
    resolved_assertion: str = "present"


class IgnoreCodingReviewRequest(BaseModel):
    reviewer: str = "operations_ui"
    reason: str = ""


@router.post("/coding-review/{review_id}/resolve")
def resolve_coding_review(
    review_id: str,
    body: ResolveCodingReviewRequest,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Manually assign a SNOMED concept to an uncoded entity.

    CSO-001 two-reviewer gate:
    - When the reviewer picks a DIFFERENT concept, we fix this one record
      immediately but do NOT create a live MAPS_TO mapping. Instead we
      create a SurfaceFormTask so a second reviewer can confirm before the
      mapping goes live.
    - When the reviewer CONFIRMS the original concept (same ID), we upsert
      the SurfaceForm mapping directly because the mapping already exists
      and is simply being validated.
    """
    from services.api.app.db.neo4j_client import CodingGraphClient
    from services.api.app.models.neo4j_schema import UPSERT_SURFACE_FORM_MAPPING

    client = PatientGraphClient()
    try:
        with client.session() as session:
            cr_row = session.run(
                "MATCH (cr:CodingReview {review_id: $review_id}) "
                "RETURN cr.entity_text AS entity_text, "
                "cr.snomed_concept_id AS original_concept_id",
                review_id=review_id,
            ).single()
            entity_text = str(cr_row["entity_text"]) if cr_row else ""
            original_concept_id = (
                str(cr_row["original_concept_id"] or "") if cr_row else ""
            )
            resolved_entity_text = (body.resolved_entity_text or "").strip()
            if resolved_entity_text:
                entity_text = resolved_entity_text

            result = session.run(
                RESOLVE_CODING_REVIEW,
                review_id=review_id,
                resolved_concept_id=body.resolved_concept_id,
                resolved_term=body.resolved_term,
                reviewer=body.reviewer,
                resolved_assertion=body.resolved_assertion,
            ).single()
        if not result:
            raise HTTPException(status_code=404, detail="Coding review not found")
    finally:
        client.close()

    concept_changed = body.resolved_concept_id != original_concept_id
    surface_form_task_created = False

    if entity_text:
        if concept_changed:
            surface_form_task_created = _create_surface_form_task_for_correction(
                entity_text=entity_text,
                original_concept_id=original_concept_id,
                resolved_concept_id=body.resolved_concept_id,
                resolved_term=body.resolved_term,
                reviewer=body.reviewer,
            )
        else:
            normalized = re.sub(r"\s+", " ", entity_text.strip().lower())
            try:
                coding_client = CodingGraphClient()
                coding_client.run(
                    UPSERT_SURFACE_FORM_MAPPING,
                    normalized=normalized,
                    form=entity_text.strip(),
                    concept_id=body.resolved_concept_id,
                    confidence=1.0,
                    source="coding_review",
                    provenance="coding_review_resolution",
                    created_by="coding_review",
                )
                coding_client.close()
                logger.info(
                    "Confirmed surface form mapping: %r -> %s (%s)",
                    entity_text,
                    body.resolved_concept_id,
                    body.resolved_term,
                )
            except Exception:
                logger.warning(
                    "Failed to upsert surface form mapping for %r",
                    entity_text,
                    exc_info=True,
                )

    cascade_count = 0
    if entity_text:
        cascade_client = PatientGraphClient()
        try:
            with cascade_client.session() as session:
                cascade_row = session.run(
                    BATCH_RESOLVE_BY_ENTITY_TEXT,
                    entity_text=entity_text,
                    resolved_concept_id=body.resolved_concept_id,
                    resolved_term=body.resolved_term,
                    reviewer=f"cascade:{body.reviewer}",
                    resolved_assertion=body.resolved_assertion,
                ).single()
                cascade_count = cascade_row["resolved_count"] if cascade_row else 0
        except Exception:
            logger.warning("Cascade resolve failed for %r", entity_text, exc_info=True)
        finally:
            cascade_client.close()
        if cascade_count:
            logger.info(
                "Cascade-resolved %d additional reviews for %r",
                cascade_count,
                entity_text,
            )

    return {
        "review_id": result["review_id"],
        "status": "resolved",
        "concept_changed": concept_changed,
        "surface_form_task_created": surface_form_task_created,
        "surface_form_created": not concept_changed and bool(entity_text),
        "cascade_resolved": cascade_count,
    }


def _create_surface_form_task_for_correction(
    entity_text: str,
    original_concept_id: str,
    resolved_concept_id: str,
    resolved_term: str,
    reviewer: str,
) -> bool:
    """Queue a SurfaceFormTask for second-reviewer approval (CSO-001).

    Returns True if the task was created successfully.
    """
    normalized = re.sub(r"\s+", " ", entity_text.strip().lower())
    task_id = make_surface_form_task_id(
        candidate_id=reviewer or "unknown",
        entity_text=normalized,
        current_concept=original_concept_id,
    )
    try:
        client = PatientGraphClient()
        with client.session() as session:
            session.run(
                UPSERT_SURFACE_FORM_TASK,
                task_id=task_id,
                entity_text=entity_text.strip(),
                current_concept=original_concept_id,
                current_term="",
                suggested_concept=resolved_concept_id,
                suggested_term=resolved_term or "",
                candidates_json="[]",
                context_text="",
                candidate_id="",
                confidence=0.9,
                source="reviewer_correction",
            )
        client.close()
        logger.info(
            "SurfaceFormTask queued for second review: %r -> %s (task=%s)",
            entity_text,
            resolved_concept_id,
            task_id,
        )
        return True
    except Exception:
        logger.warning(
            "Failed to create SurfaceFormTask for %r",
            entity_text,
            exc_info=True,
        )
        return False


class BatchResolveCodingReviewRequest(BaseModel):
    entity_text: str
    entity_label: str = ""
    resolved_concept_id: str
    resolved_term: str
    reviewer: str = "operations_ui"
    resolved_assertion: str = "present"


@router.post("/coding-review/batch-resolve")
def batch_resolve_coding_review(
    body: BatchResolveCodingReviewRequest,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Resolve all pending coding reviews for a given entity_text at once.

    Also creates a surface form mapping so the terminology API resolves
    this term in future pipeline runs.
    """
    from services.api.app.db.neo4j_client import CodingGraphClient
    from services.api.app.models.neo4j_schema import UPSERT_SURFACE_FORM_MAPPING

    client = PatientGraphClient()
    try:
        with client.session() as session:
            row = session.run(
                BATCH_RESOLVE_BY_ENTITY_TEXT,
                entity_text=body.entity_text,
                resolved_concept_id=body.resolved_concept_id,
                resolved_term=body.resolved_term,
                reviewer=body.reviewer,
                resolved_assertion=body.resolved_assertion,
            ).single()
            resolved_count = row["resolved_count"] if row else 0
    finally:
        client.close()

    if not resolved_count:
        raise HTTPException(
            status_code=404,
            detail="No pending coding reviews found for this entity text",
        )

    normalized = re.sub(r"\s+", " ", body.entity_text.strip().lower())
    try:
        coding_client = CodingGraphClient()
        coding_client.run(
            UPSERT_SURFACE_FORM_MAPPING,
            normalized=normalized,
            form=body.entity_text.strip(),
            concept_id=body.resolved_concept_id,
            confidence=1.0,
            source="batch_coding_review",
            provenance="batch_coding_review_resolution",
            created_by="batch_coding_review",
        )
        coding_client.close()
    except Exception:
        logger.warning(
            "Failed to create surface form mapping for %r",
            body.entity_text,
            exc_info=True,
        )

    # Suppress this entity_text in future pipeline runs so it is not re-queued
    # even if entity index shifts or a new label is processed.
    _write_coding_ignore_rule(
        entity_text=body.entity_text,
        entity_label=body.entity_label,
        reason=f"resolved via batch coding review -> {body.resolved_concept_id}",
        created_by=body.reviewer,
    )

    return {
        "entity_text": body.entity_text,
        "resolved_count": resolved_count,
        "surface_form_created": True,
    }


# Ask LEO endpoints (ask_leo_coding, ask_leo_rank_candidates, ask_leo_smart)
# are registered via _training_askleo.register_askleo_routes(router) above.


@router.post("/coding-review/{review_id}/ignore")
def ignore_coding_review(
    review_id: str,
    body: IgnoreCodingReviewRequest,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Mark a coding review as ignored and create a persistent ignore rule.

    Future verification runs will skip this term automatically.
    """
    client = PatientGraphClient()
    try:
        with client.session() as session:
            cr_row = session.run(
                "MATCH (cr:CodingReview {review_id: $rid}) "
                "RETURN cr.entity_text AS entity_text, cr.entity_label AS entity_label",
                rid=review_id,
            ).single()
            result = session.run(
                IGNORE_CODING_REVIEW,
                review_id=review_id,
                reviewer=body.reviewer,
            ).single()
        if not result:
            raise HTTPException(status_code=404, detail="Coding review not found")
    finally:
        client.close()

    if cr_row:
        _write_coding_ignore_rule(
            entity_text=str(cr_row["entity_text"] or ""),
            entity_label=str(cr_row["entity_label"] or ""),
            reason=body.reason,
            created_by=body.reviewer,
        )

    return {"review_id": result["review_id"], "status": "ignored"}


def _write_coding_ignore_rule(
    entity_text: str,
    entity_label: str,
    reason: str,
    created_by: str,
) -> None:
    """Upsert a CodingIgnoreRule so the term is suppressed in future runs."""
    normalized = re.sub(r"\s+", " ", entity_text.strip().lower())
    if not normalized:
        return
    rule_id = str(uuid.uuid4())
    client = PatientGraphClient()
    try:
        with client.session() as session:
            session.run(
                UPSERT_CODING_IGNORE_RULE,
                rule_id=rule_id,
                entity_text=normalized,
                entity_label=entity_label or None,
                reason=reason or "ignored via coding review",
                created_by=created_by,
            )
        logger.info(
            "Coding ignore rule created: %r (label=%r)", normalized, entity_label
        )
    except Exception:
        logger.warning(
            "Failed to write coding ignore rule for %r", normalized, exc_info=True
        )
    finally:
        client.close()


@router.get("/coding-ignore-rules")
def list_coding_ignore_rules(
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """List all coding ignore rules (active and inactive)."""
    client = PatientGraphClient()
    try:
        with client.session() as session:
            rows = [dict(r) for r in session.run(GET_ALL_CODING_IGNORE_RULES)]
        return {"rules": rows, "total": len(rows)}
    finally:
        client.close()


@router.delete("/coding-ignore-rules/{rule_id}")
def delete_coding_ignore_rule(
    rule_id: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Deactivate a coding ignore rule so the term can re-enter review."""
    client = PatientGraphClient()
    try:
        with client.session() as session:
            result = session.run(
                DEACTIVATE_CODING_IGNORE_RULE,
                rule_id=rule_id,
            ).single()
        if not result:
            raise HTTPException(status_code=404, detail="Ignore rule not found")
        return {"rule_id": result["rule_id"], "status": "deactivated"}
    finally:
        client.close()


_RECHECK_BATCH_LIMIT = 500
_RECHECK_TERM_CHUNK = int(__import__("os").getenv("RECHECK_TERM_CHUNK", "50"))
_RECHECK_THRESHOLD = float(
    __import__("os").getenv("CODING_REVIEW_SCORE_THRESHOLD", "0.70")
)
_RECHECK_ALT_LOW = float(__import__("os").getenv("CODING_ALT_THRESHOLD_LOW", "0.3"))

# ---------------------------------------------------------------------------
# Recheck job state (module-level, updated by background thread)
# ---------------------------------------------------------------------------
_recheck_lock = threading.Lock()
_recheck_state: dict[str, Any] = {"status": "idle"}


def _get_recheck_state() -> dict[str, Any]:
    with _recheck_lock:
        return dict(_recheck_state)


def _set_recheck_state(**kwargs: Any) -> None:
    with _recheck_lock:
        _recheck_state.update(kwargs)


def _call_terminology_chunk(
    terms: list[str],
    expected_tags: dict[str, str] | None = None,
) -> dict[str, list]:
    """Resolve a chunk of terms via cached shared terminology client."""
    chunk_tags = None
    if expected_tags:
        subset = {t: expected_tags[t] for t in terms if t in expected_tags}
        if subset:
            chunk_tags = subset

    try:
        raw = TerminologyClient(timeout=60, max_retries=1).resolve_raw(
            terms=terms,
            expected_tags=chunk_tags,
        )
        normalised: dict[str, list[dict[str, Any]]] = {}
        for term, candidates in raw.items():
            term_candidates: list[dict[str, Any]] = []
            for candidate in candidates or []:
                if not isinstance(candidate, dict):
                    continue
                term_candidates.append(
                    {
                        "snomed_concept_id": (
                            candidate.get("snomed_concept_id")
                            or candidate.get("concept_id")
                            or candidate.get("conceptId")
                            or ""
                        ),
                        "snomed_term": (
                            candidate.get("snomed_term")
                            or candidate.get("term")
                            or candidate.get("preferredTerm")
                            or ""
                        ),
                        "semantic_tag": (
                            candidate.get("semantic_tag")
                            or candidate.get("semanticTag")
                            or ""
                        ),
                        "score": candidate.get("score"),
                    }
                )
            normalised[str(term)] = term_candidates
        return normalised
    except Exception:
        logger.warning(
            "Terminology chunk call failed (%d terms)", len(terms), exc_info=True
        )
        return {}


def _call_terminology_batch(
    terms: list[str],
    expected_tags: dict[str, str] | None = None,
) -> dict[str, list]:
    """POST terms to the terminology resolve endpoint in chunks to avoid timeouts."""
    merged: dict[str, list] = {}
    for i in range(0, len(terms), _RECHECK_TERM_CHUNK):
        chunk = terms[i : i + _RECHECK_TERM_CHUNK]
        merged.update(_call_terminology_chunk(chunk, expected_tags=expected_tags))
    return merged


def _load_ignore_texts(session) -> frozenset[str]:
    """Return a frozenset of normalised entity texts from active CodingIgnoreRules."""
    return frozenset(
        str(r["entity_text"])
        for r in session.run(GET_CODING_IGNORE_RULES)
        if r.get("entity_text")
    )


def _writeback_recheck_surface_form(
    *,
    entity_text: str,
    concept_id: str,
    resolved_by: str,
) -> bool:
    """Persist an auto-resolved LLM term as a SurfaceForm mapping."""
    if not entity_text.strip() or not concept_id.strip():
        return False
    normalized = re.sub(r"\s+", " ", entity_text.strip().lower())
    if not normalized:
        return False
    try:
        from services.api.app.db.neo4j_client import CodingGraphClient
        from services.api.app.models.neo4j_schema import UPSERT_SURFACE_FORM_MAPPING
    except Exception:
        logger.warning(
            "RECHECK: [WRITEBACK_FAIL] term=%r concept=%r -- import failure",
            entity_text,
            concept_id,
            exc_info=True,
        )
        return False

    coding_client = CodingGraphClient()
    try:
        coding_client.run(
            UPSERT_SURFACE_FORM_MAPPING,
            normalized=normalized,
            form=entity_text.strip(),
            concept_id=concept_id,
            confidence=1.0,
            source="coding_review_recheck",
            provenance="coding_review_recheck_llm_alt",
            created_by="coding_review_recheck",
        )
        logger.info(
            "RECHECK: [WRITEBACK_OK] term=%r -> concept=%r provenance=%s",
            entity_text,
            concept_id,
            "coding_review_recheck_llm_alt",
        )
        return True
    except Exception:
        logger.warning(
            "RECHECK: [WRITEBACK_FAIL] term=%r concept=%r -- upsert failed",
            entity_text,
            concept_id,
            exc_info=True,
        )
        return False
    finally:
        coding_client.close()


def _recheck_suggest_alts(term: str, entity_label: str) -> list[str]:
    """Ask a small LLM for SNOMED-friendly alternative phrasings of a near-miss term.

    The prompt explicitly allows an empty response so the LLM does not hallucinate
    alternatives when none exist.
    """
    import json as _json

    from libs.llm_client.factory import create_llm

    system = (
        "You are a UK primary care clinical terminology assistant. "
        "Your job is to suggest alternative phrasings that would match SNOMED CT concepts. "
        "If the term is too vague, ambiguous, or product-specific to have useful SNOMED "
        "alternatives, you MUST return an empty array []. "
        "Respond ONLY with a valid JSON array of strings -- no explanation, no markdown."
    )
    user = (
        f'Term: "{term}" (type: {entity_label})\n'
        "Suggest up to 3 alternatives: the preferred SNOMED term, a common abbreviation, "
        "and one synonym a UK GP might write. "
        "If you cannot suggest meaningful alternatives, return []. "
        'Output format: ["phrase1", "phrase2"] or []'
    )
    try:
        response = create_llm(tier="small").converse(
            system=system,
            messages=[{"role": "user", "content": user}],
            max_tokens=256,
            temperature=0.2,
            agent_task="training_alt_term_suggester",
        )
        raw_text = response.text.strip()
        match = re.search(r"\[.*\]", raw_text, re.DOTALL)
        if not match:
            logger.info(
                "RECHECK: [LLM_SUGGEST] term=%r label=%s -- no JSON array in response: %s",
                term,
                entity_label,
                raw_text[:120],
            )
            return []
        raw = _json.loads(match.group())
        seen = term.strip().lower()
        alts = [
            s.strip() for s in raw if isinstance(s, str) and s.strip().lower() != seen
        ][:4]
        logger.info(
            "RECHECK: [LLM_SUGGEST] term=%r label=%s -> alts=%r",
            term,
            entity_label,
            alts,
        )
        return alts
    except Exception:
        logger.warning(
            "RECHECK: [LLM_SUGGEST] LLM call failed for term=%r", term, exc_info=True
        )
        return []


def _recheck_alt_coding(term: str, entity_label: str) -> tuple[dict, str] | None:
    """Try LLM-suggested alternatives for a near-miss term.

    Returns (best_candidate, alt_term_used) if any alternative scores >= threshold,
    else None. Logs all alternatives tried and their scores for audit.
    """
    alt_terms = _recheck_suggest_alts(term, entity_label)
    if not alt_terms:
        logger.info(
            "RECHECK: [LLM_ALT] term=%r label=%s -- LLM returned no alternatives",
            term,
            entity_label,
        )
        return None

    results = _call_terminology_batch(alt_terms)
    best: dict | None = None
    best_alt = ""
    best_score = 0.0

    for alt in alt_terms:
        candidates = results.get(alt) or []
        top = candidates[0] if candidates and isinstance(candidates[0], dict) else {}
        score = float(top.get("score") or 0)
        concept_id = top.get("snomed_concept_id", "")
        snomed_term = top.get("snomed_term", "")
        logger.info(
            "RECHECK: [LLM_ALT_PROBE] original=%r alt=%r -> concept=%r snomed=%r score=%.4f",
            term,
            alt,
            concept_id,
            snomed_term,
            score,
        )
        if score >= _RECHECK_THRESHOLD and score > best_score:
            best_score = score
            best = top
            best_alt = alt

    if best:
        logger.info(
            "RECHECK: [LLM_ALT_RESOLVED] term=%r via alt=%r -> concept=%r snomed=%r score=%.4f",
            term,
            best_alt,
            best.get("snomed_concept_id"),
            best.get("snomed_term"),
            best_score,
        )
        return best, best_alt

    logger.info(
        "RECHECK: [LLM_ALT_NO_MATCH] term=%r -- no alternative cleared threshold=%.2f",
        term,
        _RECHECK_THRESHOLD,
    )
    return None


def _apply_recheck_item(
    session,
    item: dict,
    results_map: dict,
    ignore_texts: frozenset[str],
    try_alternatives: bool,
) -> tuple[str, bool]:
    """Process one pending review item.

    Returns:
        (outcome, llm_writeback_ok)
    """
    entity_text = item.get("entity_text", "")
    entity_label = item.get("entity_label", "")
    review_id = item.get("review_id", "")
    normalized = re.sub(r"\s+", " ", entity_text.lower())

    if normalized in ignore_texts:
        logger.info(
            "RECHECK: [IGNORED] term=%r label=%s review=%s -- matched ignore rule",
            entity_text,
            entity_label,
            review_id,
        )
        session.run(
            AUTO_RESOLVE_CODING_REVIEW,
            review_id=review_id,
            concept_id="__ignored__",
            term="__ignored_by_rule__",
            resolved_by="ignore_rule",
        )
        return "ignored", False

    candidates = results_map.get(entity_text) or []
    top = candidates[0] if candidates and isinstance(candidates[0], dict) else {}
    concept_id = str(top.get("snomed_concept_id") or "")
    term = str(top.get("snomed_term") or "")
    score = float(top.get("score") or 0) if top.get("score") is not None else None
    semantic_tag = str(top.get("semantic_tag") or "")
    coded = bool(concept_id)
    resolved_by = "auto_recheck"

    if not coded:
        logger.info(
            "RECHECK: [UNCODED] term=%r label=%s review=%s -- terminology returned no concept",
            entity_text,
            entity_label,
            review_id,
        )
    elif score is not None and score >= _RECHECK_THRESHOLD:
        logger.info(
            "RECHECK: [DIRECT] term=%r label=%s -> concept=%r snomed=%r score=%.4f review=%s",
            entity_text,
            entity_label,
            concept_id,
            term,
            score,
            review_id,
        )
    elif try_alternatives and score is not None and score >= _RECHECK_ALT_LOW:
        logger.info(
            "RECHECK: [NEAR_MISS] term=%r label=%s score=%.4f -- trying LLM alternatives review=%s",
            entity_text,
            entity_label,
            score,
            review_id,
        )
        alt_result = _recheck_alt_coding(entity_text, entity_label)
        if alt_result:
            best, alt_term = alt_result
            top = best
            concept_id = str(best.get("snomed_concept_id") or "")
            term = str(best.get("snomed_term") or "")
            score = float(best.get("score") or 0)
            semantic_tag = str(best.get("semantic_tag") or "")
            coded = bool(concept_id)
            resolved_by = f"llm_alt:{alt_term[:80]}"
    else:
        logger.info(
            "RECHECK: [LOW_SCORE] term=%r label=%s score=%s -- below alt threshold, staying in queue review=%s",
            entity_text,
            entity_label,
            f"{score:.4f}" if score is not None else "None",
            review_id,
        )

    session.run(
        UPDATE_CODING_REVIEW_FIELDS,
        review_id=review_id,
        coded=coded,
        snomed_concept_id=concept_id if coded else None,
        snomed_term=term if coded else None,
        score=score if coded else None,
        semantic_tag=semantic_tag if coded else None,
    )

    if coded and score is not None and score >= _RECHECK_THRESHOLD:
        session.run(
            AUTO_RESOLVE_CODING_REVIEW,
            review_id=review_id,
            concept_id=concept_id,
            term=term,
            resolved_by=resolved_by,
        )
        # Write surface form for all auto-resolved paths so future pipeline
        # runs hit the Tier-1 fast path instead of re-querying the terminology API.
        writeback_ok = _writeback_recheck_surface_form(
            entity_text=entity_text,
            concept_id=concept_id,
            resolved_by=resolved_by,
        )
        logger.info(
            "RECHECK: [FINALISED] term=%r -> concept=%r snomed=%r score=%.4f"
            " method=%r review=%s writeback=%s",
            entity_text,
            concept_id,
            term,
            score,
            resolved_by,
            review_id,
            writeback_ok,
        )
        if resolved_by.startswith("llm_alt:"):
            return "resolved_llm", writeback_ok
        return "resolved_direct", writeback_ok

    # Last resort: model escalation (small -> big -> max) for unresolved items
    if try_alternatives:
        from libs.llm_client.escalation import escalate_coding

        esc = escalate_coding(
            entity_text=entity_text,
            entity_label=entity_label,
            encounter_text="",
            confidence_threshold=0.85,
            start_tier="big",
        )
        if esc.resolved and esc.concept_id and esc.concept_term:
            resolved_by_esc = f"escalation:{esc.model_tier}"
            logger.info(
                "RECHECK: [ESCALATED] term=%r -> concept=%r tier=%s conf=%.2f review=%s",
                entity_text,
                esc.concept_id,
                esc.model_tier,
                esc.confidence,
                review_id,
            )
            session.run(
                AUTO_RESOLVE_CODING_REVIEW,
                review_id=review_id,
                concept_id=esc.concept_id,
                term=esc.concept_term,
                resolved_by=resolved_by_esc,
            )
            esc_writeback_ok = _writeback_recheck_surface_form(
                entity_text=entity_text,
                concept_id=esc.concept_id,
                resolved_by=resolved_by_esc,
            )
            return "resolved_llm", esc_writeback_ok

    logger.info(
        "RECHECK: [PENDING] term=%r label=%s -- not resolved, remains in queue review=%s",
        entity_text,
        entity_label,
        review_id,
    )
    if not coded:
        return "pending_uncoded", False
    if score is not None and score < _RECHECK_ALT_LOW:
        return "pending_low_score", False
    return "pending_unresolved", False


def _run_recheck_job(
    *,
    job_id: str,
    try_alternatives: bool,
    ignore_texts: frozenset[str],
    item_limit: int = 0,
) -> None:
    """Background worker: process pending coding review items in batches.

    item_limit: max total items to process across all batches (0 = no limit).
    """
    total_rechecked = 0
    total_auto_resolved = 0
    batch_num = 0
    counters: dict[str, int] = {
        "resolved_direct": 0,
        "resolved_llm": 0,
        "ignored_by_rule": 0,
        "pending_uncoded": 0,
        "pending_low_score": 0,
        "pending_unresolved": 0,
        "writeback_llm_success": 0,
        "writeback_llm_failed": 0,
    }

    with logging_context(correlation_id=job_id):
        logger.info(
            "RECHECK: [START] job=%s mode=%s ignore_rules=%d item_limit=%s",
            job_id,
            "llm_assisted" if try_alternatives else "quick",
            len(ignore_texts),
            item_limit if item_limit > 0 else "none",
        )
        try:
            while True:
                client = PatientGraphClient()
                try:
                    with client.session() as session:
                        remaining_budget = (
                            (item_limit - total_rechecked)
                            if item_limit > 0
                            else _RECHECK_BATCH_LIMIT
                        )
                        fetch_limit = min(_RECHECK_BATCH_LIMIT, remaining_budget)
                        rows = session.run(GET_PENDING_FOR_RECHECK, limit=fetch_limit)
                        pending = [dict(r) for r in rows]
                finally:
                    client.close()

                if not pending:
                    break

                batch_num += 1
                unique_terms = list(
                    {r["entity_text"] for r in pending if r.get("entity_text")}
                )
                tag_map: dict[str, str] = {}
                for r in pending:
                    txt = str(r.get("entity_text", ""))
                    if txt and txt not in tag_map:
                        snomed_tag = LABEL_TO_SNOMED_TAG.get(
                            str(r.get("entity_label", ""))
                        )
                        if snomed_tag:
                            tag_map[txt] = snomed_tag
                logger.info(
                    "RECHECK: [BATCH %d] fetched=%d items, unique_terms=%d -- requesting terminology API",
                    batch_num,
                    len(pending),
                    len(unique_terms),
                )

                results_map = _call_terminology_batch(
                    unique_terms, expected_tags=tag_map or None
                )
                logger.info(
                    "RECHECK: [BATCH %d] terminology returned %d results",
                    batch_num,
                    len(results_map),
                )

                batch_resolved = 0
                client = PatientGraphClient()
                try:
                    with client.session() as session:
                        for item in pending:
                            outcome, llm_writeback_ok = _apply_recheck_item(
                                session,
                                item,
                                results_map,
                                ignore_texts,
                                try_alternatives,
                            )
                            if outcome in {
                                "resolved_direct",
                                "resolved_llm",
                                "ignored",
                            }:
                                batch_resolved += 1
                            if outcome == "resolved_direct":
                                counters["resolved_direct"] += 1
                            elif outcome == "resolved_llm":
                                counters["resolved_llm"] += 1
                                if llm_writeback_ok:
                                    counters["writeback_llm_success"] += 1
                                else:
                                    counters["writeback_llm_failed"] += 1
                            elif outcome == "ignored":
                                counters["ignored_by_rule"] += 1
                            elif outcome == "pending_uncoded":
                                counters["pending_uncoded"] += 1
                            elif outcome == "pending_low_score":
                                counters["pending_low_score"] += 1
                            else:
                                counters["pending_unresolved"] += 1
                finally:
                    client.close()

                total_rechecked += len(pending)
                total_auto_resolved += batch_resolved
                _set_recheck_state(
                    rechecked=total_rechecked,
                    auto_resolved=total_auto_resolved,
                    ignored_by_rule=counters["ignored_by_rule"],
                    resolved_llm=counters["resolved_llm"],
                    resolved_direct=counters["resolved_direct"],
                    writeback_llm_success=counters["writeback_llm_success"],
                    writeback_llm_failed=counters["writeback_llm_failed"],
                )
                logger.info(
                    "RECHECK: [BATCH %d DONE] resolved=%d/%d (running total: %d/%d resolved)",
                    batch_num,
                    batch_resolved,
                    len(pending),
                    total_auto_resolved,
                    total_rechecked,
                )

                if item_limit > 0 and total_rechecked >= item_limit:
                    logger.info(
                        "RECHECK: [LIMIT_REACHED] job=%s processed=%d limit=%d -- stopping",
                        job_id,
                        total_rechecked,
                        item_limit,
                    )
                    break

                if len(pending) < _RECHECK_BATCH_LIMIT:
                    break

            report = {
                "processed": total_rechecked,
                "resolved_total": total_auto_resolved,
                "resolved_direct": counters["resolved_direct"],
                "resolved_llm": counters["resolved_llm"],
                "ignored_by_rule": counters["ignored_by_rule"],
                "pending_uncoded": counters["pending_uncoded"],
                "pending_low_score": counters["pending_low_score"],
                "pending_unresolved": counters["pending_unresolved"],
                "writeback_llm_success": counters["writeback_llm_success"],
                "writeback_llm_failed": counters["writeback_llm_failed"],
            }
            _set_recheck_state(
                status="done",
                report=report,
                rechecked=total_rechecked,
                auto_resolved=total_auto_resolved,
                ignored_by_rule=counters["ignored_by_rule"],
                resolved_llm=counters["resolved_llm"],
                resolved_direct=counters["resolved_direct"],
                writeback_llm_success=counters["writeback_llm_success"],
                writeback_llm_failed=counters["writeback_llm_failed"],
            )
            logger.info(
                "RECHECK: [COMPLETE] job=%s batches=%d report=%s",
                job_id,
                batch_num,
                report,
            )

        except Exception as exc:
            logger.exception(
                "RECHECK: [FAILED] job=%s raised an unhandled exception", job_id
            )
            _set_recheck_state(status="failed", last_error=str(exc))


@router.post("/coding-review/recheck")
def recheck_coding_review(
    try_alternatives: bool = False,
    item_limit: int = 0,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Start a background coding review recheck.

    Returns immediately with status 'started'. Poll
    GET /training/coding-review/recheck/status for progress.
    Set try_alternatives=true to enable the LLM alternative-term loop for near-misses.
    Set item_limit > 0 to cap total items processed (useful for testing).
    """
    with _recheck_lock:
        if _recheck_state.get("status") == "running":
            return {"status": "already_running", **_recheck_state}

    client = PatientGraphClient()
    try:
        with client.session() as session:
            ignore_texts = _load_ignore_texts(session)
    finally:
        client.close()

    job_id = str(uuid.uuid4())
    _set_recheck_state(
        job_id=job_id,
        status="running",
        try_alternatives=try_alternatives,
        item_limit=item_limit,
        rechecked=0,
        auto_resolved=0,
        ignored_by_rule=0,
        resolved_llm=0,
        resolved_direct=0,
        writeback_llm_success=0,
        writeback_llm_failed=0,
        report={},
        last_error=None,
    )

    thread = threading.Thread(
        target=_run_recheck_job,
        kwargs={
            "job_id": job_id,
            "try_alternatives": try_alternatives,
            "ignore_texts": ignore_texts,
            "item_limit": item_limit,
        },
        daemon=True,
    )
    thread.start()
    return {
        "status": "started",
        "job_id": job_id,
        "try_alternatives": try_alternatives,
        "item_limit": item_limit,
    }


@router.get("/coding-review/recheck/status")
def recheck_status(scope: CallerScope = Depends(get_caller_scope)) -> dict[str, Any]:
    """Return the current state of the background coding review recheck job."""
    return _get_recheck_state()


@router.get("/coding-review/stats")
def coding_review_stats(
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Summary statistics for coding review."""
    client = PatientGraphClient()
    try:
        with client.session() as session:
            row = session.run(GET_CODING_REVIEW_STATS).single()
        return (
            dict(row)
            if row
            else {
                "total": 0,
                "coded": 0,
                "uncoded": 0,
                "resolved": 0,
                "pending": 0,
                "low_confidence": 0,
                "assertion_flagged": 0,
            }
        )
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Context rules -- user-defined ConText rules stored in Neo4j.
# ---------------------------------------------------------------------------

_VALID_CATEGORIES = frozenset(
    {
        "NEGATED_EXISTENCE",
        "POSSIBLE_EXISTENCE",
        "HISTORICAL",
        "HYPOTHETICAL",
        "FAMILY",
        "DECLINED",
    }
)
_VALID_DIRECTIONS = frozenset({"FORWARD", "BACKWARD", "BIDIRECTIONAL"})


class ContextRuleRequest(BaseModel):
    literal: str
    category: str
    direction: str = "FORWARD"
    max_scope: int = 6
    description: str = ""
    example: str = ""
    created_by: str = "operations_ui"


@router.get("/context-rules")
def list_context_rules(
    active_only: bool = True,
    include_builtin: bool = True,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """List ConText rules: user-defined (Neo4j) plus optionally the shipped built-ins.

    Custom rules are scoped to the caller's org; platform admins see all orgs.
    Built-in rules (source='builtin') are read-only and global.
    """
    from libs.ner.context_engine import get_builtin_rules

    org_id = None if scope.is_admin else scope.primary_org_id

    client = PatientGraphClient()
    try:
        with client.session() as session:
            rows = session.run(
                GET_CONTEXT_RULES, active_only=active_only, org_id=org_id
            )
            custom = [{**dict(r), "source": "custom"} for r in rows]
    finally:
        client.close()

    builtin = get_builtin_rules() if include_builtin else []
    return {"rules": builtin + custom}


@router.post("/context-rules")
def create_context_rule(
    body: ContextRuleRequest,
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Create a new user-defined ConText rule, scoped to the caller's org.

    The rule is picked up by the coding worker on the next pipeline restart.
    Only platform admins may create rules (GAP-015).
    """
    if not body.literal.strip():
        raise HTTPException(status_code=422, detail="literal must not be empty")
    if len(body.literal) > 200:
        raise HTTPException(
            status_code=422, detail="literal must not exceed 200 characters"
        )
    if body.category not in _VALID_CATEGORIES:
        raise HTTPException(
            status_code=422,
            detail=f"category must be one of {sorted(_VALID_CATEGORIES)}",
        )
    if body.direction.upper() not in _VALID_DIRECTIONS:
        raise HTTPException(
            status_code=422,
            detail=f"direction must be one of {sorted(_VALID_DIRECTIONS)}",
        )
    rule_id = str(uuid.uuid4())
    org_id = scope.primary_org_id  # None for platform admins (platform-wide rule)
    client = PatientGraphClient()
    try:
        with client.session() as session:
            session.run(
                UPSERT_CONTEXT_RULE,
                rule_id=rule_id,
                literal=body.literal.strip().lower(),
                category=body.category.upper(),
                direction=body.direction.upper(),
                max_scope=max(1, min(20, body.max_scope)),
                description=body.description.strip(),
                example=body.example.strip(),
                created_by=scope.email,
                org_id=org_id,
            )
        logger.info(
            "ContextRule created: %s %r -> %s by %s (org=%s)",
            rule_id[:8],
            body.literal,
            body.category,
            scope.email,
            org_id,
        )
        return {
            "rule_id": rule_id,
            "literal": body.literal,
            "category": body.category,
            "org_id": org_id,
        }
    finally:
        client.close()

    # Rebuild the ConText NLP pipeline so the new rule takes effect immediately.
    try:
        from libs.ner.context_engine import reload_nlp

        reload_nlp()
    except Exception:
        logger.warning(
            "ConText pipeline reload failed after rule creation (non-fatal)",
            exc_info=True,
        )


@router.patch("/context-rules/{rule_id}/deactivate")
def deactivate_context_rule(
    rule_id: str,
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Soft-delete a user-defined ConText rule."""
    client = PatientGraphClient()
    try:
        with client.session() as session:
            row = session.run(DEACTIVATE_CONTEXT_RULE, rule_id=rule_id).single()
        if not row:
            raise HTTPException(status_code=404, detail=f"Rule {rule_id!r} not found")
        logger.info("ContextRule deactivated: %s", rule_id[:8])
        return {"rule_id": rule_id, "active": False}
    finally:
        client.close()

    # Rebuild the ConText NLP pipeline so the removed rule is no longer applied.
    try:
        from libs.ner.context_engine import reload_nlp

        reload_nlp()
    except Exception:
        logger.warning(
            "ConText pipeline reload failed after rule deactivation (non-fatal)",
            exc_info=True,
        )


# -- Surface form approval --------------------------------------------------


@router.delete("/surface-forms/{normalized}/revoke")
def revoke_surface_form(
    normalized: str,
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Revoke a surface form mapping and cascade to affected encounters.

    Steps:
    1. Remove the MAPS_TO relationship and mark SurfaceForm / SurfaceFormTask
       as 'revoked'.
    2. Query DOCUMENTS relationships coded via this concept after first use.
    3. Create a CodingReview node (type=revocation_cascade, priority=urgent)
       for each affected encounter so reviewers are alerted.

    Returns the count of affected encounters.
    """
    kg_client = KnowledgeGraphClient()
    pg_client = PatientGraphClient()
    try:
        with kg_client.session() as session:
            row = session.run(REVOKE_SURFACE_FORM, normalized=normalized).single()
        if not row:
            raise HTTPException(
                status_code=404,
                detail=f"No surface form found for {normalized!r}",
            )
        concept_id = ""
        first_used_at = row.get("first_used_at")

        with pg_client.session() as pg_session:
            enc_rows = pg_session.run(
                GET_ENCOUNTERS_FOR_REVOKED_CONCEPT,
                concept_id=concept_id,
                first_used_at=first_used_at,
            )
            encounter_ids = [r["encounter_id"] for r in enc_rows]

            for enc_id in encounter_ids:
                review_id = str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"revoke:{normalized}:{enc_id}",
                    )
                )
                pg_session.run(
                    CREATE_REVOCATION_CASCADE_REVIEW,
                    review_id=review_id,
                    encounter_id=enc_id,
                    concept_id=concept_id,
                )

        logger.info(
            "SurfaceForm revoked: %r  cascade_encounters=%d  by=%s",
            normalized,
            len(encounter_ids),
            scope.email,
        )
        return {
            "normalized": normalized,
            "status": "revoked",
            "affected_encounters": len(encounter_ids),
        }
    finally:
        kg_client.close()
        pg_client.close()


@router.patch("/surface-forms/{normalized}/approve")
def approve_surface_form(
    normalized: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Promote a pending surface form to approved after second confirmation.

    Surface forms are created as 'pending' on first writeback. This endpoint
    confirms the mapping so the resolver treats it as a trusted Tier 1 match.
    """
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            row = session.run(
                APPROVE_SURFACE_FORM,
                normalized=normalized,
            ).single()
        if not row:
            raise HTTPException(
                status_code=404,
                detail=f"No pending surface form found for {normalized!r}",
            )
        logger.info("SurfaceForm approved: %s", normalized[:40])
        return {"normalized": row["normalized"], "status": row["status"]}
    finally:
        client.close()


# -- Queue maintenance ------------------------------------------------------


@router.delete("/coding-review/resolved")
def delete_resolved_coding_reviews(
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Delete resolved CodingReview queue items."""
    client = PatientGraphClient()
    try:
        with client.session() as session:
            summary = session.run(DELETE_RESOLVED_CODING_REVIEWS).consume()
        return {"deleted": summary.counters.nodes_deleted}
    finally:
        client.close()


@router.delete("/review-queue/all")
def delete_all_review_queue_items(
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Delete all review queue items (CodingReview, SurfaceFormTask, HITLTask).
    Use when clearing items from an old pipeline before running the new one."""
    pg_client = PatientGraphClient()
    kg_client = KnowledgeGraphClient()
    try:
        with pg_client.session() as session:
            cr_summary = session.run(DELETE_ALL_CODING_REVIEWS_UNCONDITIONAL).consume()
            hitl_summary = session.run(DELETE_ALL_HITL_TASKS).consume()
        with kg_client.session() as session:
            sf_summary = session.run(DELETE_ALL_SURFACE_FORM_TASKS).consume()
        return {
            "coding_reviews_deleted": cr_summary.counters.nodes_deleted,
            "surface_form_tasks_deleted": sf_summary.counters.nodes_deleted,
            "hitl_tasks_deleted": hitl_summary.counters.nodes_deleted,
            "total_deleted": (
                cr_summary.counters.nodes_deleted
                + sf_summary.counters.nodes_deleted
                + hitl_summary.counters.nodes_deleted
            ),
        }
    finally:
        pg_client.close()
        kg_client.close()


# -- GDPR-isolated learning loop (Knowledge Graph) -------------------------
# TrainingCandidate, GoldLabel and SurfaceFormTask are de-identified model
# knowledge and belong in the Knowledge Graph, not the Patient Graph.

_SYNTHETIC_SOURCE = "synthetic_llm"
_SYNTHETIC_VERIFIED_BY = "llm:claude-sonnet-4-6"
_PIPELINE_QUEUE = os.getenv("PIPELINE_QUEUE_NAME", "pipeline-jobs")
_VALID_ASSERTIONS = {
    "present",
    "absent",
    "historical",
    "possible",
    "planned",
    "hypothetical",
    "family",
    "uncertain",
    "refuted",
    "declined",
    "cancelled",
}
_CONTEXT_SPLITTER = SentenceSplitter()
_OBS_VALUE_RE = re.compile(
    r"\b(?:[<>]?\s*\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)?)\b",
    re.IGNORECASE,
)
_INTERPRETATION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"\bwithin\s+(?:normal|reference)\s+(?:range|limits)\b",
            re.IGNORECASE,
        ),
        "within",
    ),
    (re.compile(r"\b(?:above|high|raised|elevated)\b", re.IGNORECASE), "above"),
    (re.compile(r"\b(?:below|low|reduced)\b", re.IGNORECASE), "below"),
    (
        re.compile(
            r"\b(?:outside\s+reference\s+range|out\s+of\s+reference\s+range)\b",
            re.IGNORECASE,
        ),
        "outside",
    ),
]
_SPECULATIVE_HEDGE_RE = re.compile(
    r"\b(?:may|might|could|possibly|potentially|likely|unlikely|suggests?|indicates?|warrants?)\b",
    re.IGNORECASE,
)
_SPECULATIVE_MODAL_RE = re.compile(
    r"\b(?:may|might|could)\s+(?:suggest|indicate|reflect|represent|imply|be|rise|increase|decrease|elevate)\b",
    re.IGNORECASE,
)
_CONDITIONAL_RE = re.compile(r"\bif\b.{0,120}(?:,|\bthen\b)", re.IGNORECASE)
_EDUCATIONAL_FRAMING_RE = re.compile(
    r"\b(?:given\s+the\s+clinical\s+picture|in\s+the\s+context\s+of|depending\s+on)\b",
    re.IGNORECASE,
)
_FUTURE_TRIGGER_RE = re.compile(
    r"\b(?:develops?|worsens?|deteriorates?|later|future|risk|review)\b",
    re.IGNORECASE,
)
_ABSENT_CUE_RE = re.compile(
    r"\b(?:no|not|without|denies?|denied|negative\s+for|free\s+of|absence\s+of)\b",
    re.IGNORECASE,
)
# Explicit past-time markers that genuinely indicate a historical assertion.
# "following" and "after" are intentionally excluded — they describe temporal
# sequencing of a procedure and do not make the coded entity historical.
_HISTORICAL_CUE_RE = re.compile(
    r"\b(?:"
    r"history\s+of"
    r"|previous(?:ly)?"
    r"|prior\s+(?:to\s+)?(?:this\s+)?"
    r"|background\s+of"
    r"|known\s+(?:history\s+of\s+)?"
    r"|formerly"
    r"|(?:was|were)\s+diagnosed\s+with"
    r"|(?:diagnosed|treated)\s+in\s+\d{4}"
    r"|\d+\s+(?:year|month|week)s?\s+ago"
    r"|in\s+(?:19|20)\d{2}"
    r")\b",
    re.IGNORECASE,
)
_PLANNED_PROCEDURE_CUE_RE = re.compile(
    r"\b(?:to\s+be\s+rechecked|to\s+be\s+repeated|for\s+repeat|repeat\s+test|recheck(?:ed)?|retest)\b",
    re.IGNORECASE,
)


def _normalise_semantic_tag(tag: str | None) -> str:
    raw = str(tag or "finding").strip().lower()
    if not raw:
        return "finding"
    return raw.replace("-", "_").replace(" ", "_").replace("/", "_")


def _extract_concept_ids_from_valuesets(
    client: Any, valueset_ids: list[str]
) -> list[str]:
    """Return deduplicated SNOMED concept IDs for all given valueset IDs.

    ValueSet concept lists live in the rawJson FHIR compose block; we parse
    them in Python because Cypher has no native JSON-parsing support.
    """
    import json as _json

    ids: list[str] = [v for v in valueset_ids if v]
    if not ids:
        return []
    with client.session() as session:
        rows = [dict(r) for r in session.run(GET_VALUESET_RAW_JSON, valueset_ids=ids)]
    seen: set[str] = set()
    concept_ids: list[str] = []
    for row in rows:
        raw = row.get("raw_json") or "{}"
        try:
            parsed = _json.loads(raw)
        except Exception:
            continue
        includes = (parsed.get("compose") or parsed).get("include") or []
        for inc in includes:
            for c in inc.get("concept") or []:
                code = str(c.get("code") or "").strip()
                if code and code not in seen:
                    seen.add(code)
                    concept_ids.append(code)
    return concept_ids


def _load_valueset_prompt_context(
    client: Any, valueset_ids: list[str]
) -> tuple[list[str], list[str]]:
    """Return (valueset titles, domain PT strings) for prompt conditioning."""
    import json as _json

    ids = [v for v in valueset_ids if v]
    if not ids:
        return [], []
    with client.session() as session:
        rows = [dict(r) for r in session.run(GET_VALUESET_RAW_JSON, valueset_ids=ids)]
    titles_by_id: dict[str, str] = {}
    terms: set[str] = set()
    for row in rows:
        vid = str(row.get("id") or "").strip()
        if vid and vid not in titles_by_id:
            titles_by_id[vid] = str(row.get("title") or vid).strip()
        raw = row.get("raw_json") or "{}"
        try:
            parsed = _json.loads(raw)
        except Exception:
            continue
        includes = (parsed.get("compose") or parsed).get("include") or []
        for inc in includes:
            for c in inc.get("concept") or []:
                display = str(c.get("display") or "").strip()
                if display:
                    cleaned = _strip_snomed_qualifier(display)
                    if cleaned and len(cleaned) > 1:
                        terms.add(cleaned)
    return list(titles_by_id.values()), sorted(terms)


def _count_exact_phrase(text: str, phrase: str) -> int:
    if not text or not phrase:
        return 0
    pattern = re.compile(rf"(?<!\w){re.escape(phrase)}(?!\w)", re.IGNORECASE)
    return len(pattern.findall(text))


def _safe_parse_json_array(raw_text: str) -> list[dict[str, Any]]:
    text = str(raw_text or "").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [x for x in parsed if isinstance(x, dict)]
    except Exception:
        pass
    match = re.search(r"\[\s*\{.*\}\s*\]", text, re.DOTALL)
    if not match:
        return []
    try:
        parsed = json.loads(match.group(0))
        if isinstance(parsed, list):
            return [x for x in parsed if isinstance(x, dict)]
    except Exception:
        return []
    return []


def _is_synthetic_non_evidence_sentence(text: str) -> bool:
    sentence = str(text or "").strip()
    if not sentence:
        return True
    # Only apply the specific high-precision phrase blocklist here — NOT the
    # broad structural patterns from is_non_evidence_line (e.g.
    # "^(Discussed|Advised|Counselled)") which are designed for runtime
    # encounter parsing and are too aggressive for synthetic sentence validation.
    return any(pattern.search(sentence) for pattern in get_always_ignore_patterns())


def _has_observation_value(text: str) -> bool:
    return bool(_OBS_VALUE_RE.search(str(text or "")))


def _is_speculative_or_educational(sentence: str) -> bool:
    text = str(sentence or "").strip()
    if not text:
        return False
    has_hedge = bool(_SPECULATIVE_HEDGE_RE.search(text))
    has_conditional = bool(_CONDITIONAL_RE.search(text))
    has_educational_framing = bool(_EDUCATIONAL_FRAMING_RE.search(text))
    has_future_trigger = bool(_FUTURE_TRIGGER_RE.search(text))
    has_value = _has_observation_value(text)
    if has_conditional and has_hedge:
        return True
    if _SPECULATIVE_MODAL_RE.search(text):
        return True
    if has_educational_framing and has_hedge:
        return True
    if has_future_trigger and has_hedge and has_value:
        return True
    # Broad catch-all for speculative/value statements (e.g. "possibly around 90 U/L").
    if has_hedge and has_value:
        return True
    return False


def _has_absent_evidence(sentence: str) -> bool:
    return bool(_ABSENT_CUE_RE.search(str(sentence or "")))


def _has_historical_evidence(sentence: str) -> bool:
    """Return True only when the sentence contains an explicit past-time marker.

    Words like 'following' and 'after' are excluded because they describe
    procedural sequencing, not temporal distance from the present.
    """
    return bool(_HISTORICAL_CUE_RE.search(str(sentence or "")))


def _is_invalid_observable_assertion(semantic_tag: str, assertion: str) -> bool:
    tag = _normalise_semantic_tag(semantic_tag)
    val = str(assertion or "").strip().lower()
    return tag == "observable_entity" and val == "planned"


def _is_mismatched_semantic_sentence(semantic_tag: str, sentence: str) -> bool:
    tag = _normalise_semantic_tag(semantic_tag)
    text = str(sentence or "")
    if tag in {"finding", "disorder"} and (
        is_referral_procedure_phrase(text) or _PLANNED_PROCEDURE_CUE_RE.search(text)
    ):
        return True
    return False


def _detect_interpretation_phrase(sentence: str) -> tuple[str, int, int, str] | None:
    raw = str(sentence or "")
    for pattern, key in _INTERPRETATION_PATTERNS:
        match = pattern.search(raw)
        if match:
            return match.group(0), match.start(), match.end(), key
    return None


def _pick_related_finding(
    interpreted_by_findings: list[dict[str, Any]],
    interpretation_key: str,
) -> dict[str, Any] | None:
    key = interpretation_key.strip().lower()
    if not interpreted_by_findings:
        return None
    if key == "within":
        preferred_tokens = (
            "within reference range",
            "within normal range",
            "within normal limits",
            "level (finding)",
            "normal",
        )
    elif key == "above":
        preferred_tokens = (
            "above reference range",
            "above upper limit of normal",
            "upper limit of normal",
            "high",
            "raised",
            "elevated",
            "outside reference range",
            "out of reference range",
            "abnormal",
        )
    elif key == "below":
        preferred_tokens = (
            "below reference range",
            "below lower limit of normal",
            "lower limit of normal",
            "low",
            "reduced",
            "outside reference range",
            "out of reference range",
            "abnormal",
        )
    else:
        preferred_tokens = (
            "outside reference range",
            "out of reference range",
            "abnormal",
            "high",
            "low",
        )

    def _score(item: dict[str, Any]) -> tuple[int, int]:
        fsn = str(item.get("fsn") or "").lower()
        best = 0
        for idx, token in enumerate(preferred_tokens):
            if token in fsn:
                best = max(best, len(preferred_tokens) - idx)
        # Secondary preference for finding-tagged concepts only.
        sem = _normalise_semantic_tag(str(item.get("semantic_tag") or ""))
        if sem != "finding":
            best = 0
        return (best, len(fsn))

    ranked = sorted(interpreted_by_findings, key=_score, reverse=True)
    if not ranked:
        return None
    top = ranked[0]
    if _score(top)[0] <= 0:
        return None
    return top


def _extract_context_snippet(encounter_text: str, max_chars: int = 500) -> str | None:
    """Extract a clinically useful snippet while dropping admin/header noise."""
    if not encounter_text:
        return None
    deid = deidentify_text(encounter_text, ner=True).strip()
    if not deid:
        return None
    # First pass: strip clearly administrative lines before sentence splitting.
    cleaned_lines = []
    for raw_line in deid.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if is_header_sentence(line):
            continue
        if is_non_evidence_line(line):
            continue
        cleaned_lines.append(line)
    if not cleaned_lines:
        return None
    cleaned_text = "\n".join(cleaned_lines)
    chunks = _CONTEXT_SPLITTER.split(cleaned_text)
    if not chunks:
        return None
    chunks = filter_header_sentences(chunks)
    clinical_lines = [
        c.text.strip()
        for c in chunks
        if c.text.strip() and not is_non_evidence_line(c.text)
    ]
    if not clinical_lines:
        return None
    snippet = " ".join(clinical_lines[:3])
    snippet = re.sub(r"\s+", " ", snippet).strip()
    if len(snippet) < 40:
        return None
    return snippet[:max_chars].strip()


def _pick_diverse_context_examples(
    rows: list[dict[str, Any]], cap: int = 10
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen_patients: set[str] = set()
    seen_months: set[str] = set()

    # Pass 1: maximise patient + month diversity.
    for row in rows:
        pid = str(row.get("patient_id") or "")
        month = str(row.get("month_bucket") or "")
        if pid in seen_patients or month in seen_months:
            continue
        selected.append(row)
        seen_patients.add(pid)
        seen_months.add(month)
        if len(selected) >= cap:
            return selected

    # Pass 2: patient diversity only.
    for row in rows:
        if len(selected) >= cap:
            return selected
        pid = str(row.get("patient_id") or "")
        if pid in seen_patients:
            continue
        if row in selected:
            continue
        selected.append(row)
        seen_patients.add(pid)

    # Pass 3: fill remaining.
    for row in rows:
        if len(selected) >= cap:
            break
        if row in selected:
            continue
        selected.append(row)
    return selected


def _pick_similarity_context_examples(
    rows: list[dict[str, Any]],
    query_terms: list[str],
    cap: int = 10,
) -> list[str]:
    """Pick encounter snippets most similar to the target terms.

    Uses full de-identified encounter text for lexical matching so prompt
    examples reflect real note phrasing for this specific term/domain.
    """
    cleaned_terms = [str(t).strip().lower() for t in query_terms if str(t).strip()]
    if not cleaned_terms:
        return []
    token_stop = {
        "the",
        "and",
        "with",
        "from",
        "that",
        "this",
        "was",
        "were",
        "for",
        "has",
        "have",
        "had",
        "of",
        "in",
        "on",
        "to",
    }
    tokens: set[str] = set()
    for term in cleaned_terms:
        for tok in re.findall(r"[a-z0-9]{3,}", term):
            if tok not in token_stop:
                tokens.add(tok)
    ranked: list[tuple[int, str]] = []
    for row in rows:
        snippet = str(row.get("_context_snippet") or "").strip()
        text_l = str(row.get("_text_lower") or "").strip()
        if not snippet or not text_l:
            continue
        score = 0
        for phrase in cleaned_terms:
            if len(phrase) >= 4 and phrase in text_l:
                score += 12
        for tok in tokens:
            if tok in text_l:
                score += 1
        if score <= 0:
            continue
        ranked.append((score, snippet))
    if not ranked:
        return []
    ranked.sort(key=lambda x: x[0], reverse=True)
    picked: list[str] = []
    seen: set[str] = set()
    for _, snippet in ranked:
        k = snippet.lower()
        if k in seen:
            continue
        seen.add(k)
        picked.append(snippet)
        if len(picked) >= cap:
            break
    return picked


def _extract_gold_output_examples(
    rows: list[dict[str, Any]],
    cap: int = 5,
) -> list[dict[str, str]]:
    examples: list[dict[str, str]] = []
    seen_sentences: set[str] = set()
    for row in rows:
        sentence = deidentify_text(str(row.get("text") or ""), ner=True).strip()
        if not sentence:
            continue
        sentence_key = sentence.lower()
        if sentence_key in seen_sentences:
            continue
        if _is_synthetic_non_evidence_sentence(sentence):
            continue
        if _is_speculative_or_educational(sentence):
            continue
        entities = _safe_parse_json_array(str(row.get("entities_json") or "[]"))
        assertion = "present"
        for entity in entities:
            raw_assertion = str(entity.get("assertion") or "").strip().lower()
            if raw_assertion in _VALID_ASSERTIONS:
                assertion = raw_assertion
                break
        examples.append({"sentence": sentence, "assertion": assertion})
        seen_sentences.add(sentence_key)
        if len(examples) >= cap:
            break
    return examples


@router.get("/synthetic-gold/stats")
def get_synthetic_gold_stats(
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            stats_row = session.run(GET_SYNTHETIC_GOLD_STATS).single()
            tag_rows = [dict(r) for r in session.run(GET_SYNTHETIC_GOLD_TAG_BREAKDOWN)]
            option_rows = [dict(r) for r in session.run(GET_SURFACE_FORM_TAG_COUNTS)]
            labels_row = session.run(
                """
                MATCH (g:GoldLabel)
                WHERE g.source = $source
                RETURN count(g) AS total
                """,
                source=_SYNTHETIC_SOURCE,
            ).single()
        stats_payload = dict(stats_row) if stats_row else {}
        return {
            "total_surface_forms": int(stats_payload.get("total_surface_forms") or 0),
            "covered_surface_forms": int(
                stats_payload.get("covered_surface_forms") or 0
            ),
            "synthetic_gold_labels": int((labels_row or {}).get("total") or 0),
            "tag_breakdown": tag_rows,
            "tag_options": option_rows,
        }
    finally:
        client.close()


@router.get("/synthetic-gold/valuesets")
def get_synthetic_gold_valuesets(
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Return all NCDA value sets with concept count and surface-form coverage."""
    import json as _json

    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            vs_rows = [dict(r) for r in session.run(GET_ALL_VALUESETS_RAW_JSON)]
            sf_count_rows = session.run("""
                MATCH (sf:SurfaceForm)-[:MAPS_TO]->(c:Concept)
                WHERE coalesce(sf.status, 'active') = 'active'
                RETURN toString(c.id) AS concept_id, count(sf) AS sf_count
                """)
            sf_map: dict[str, int] = {
                str(r["concept_id"]): int(r["sf_count"]) for r in sf_count_rows
            }
    finally:
        client.close()

    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for row in vs_rows:
        vid = str(row.get("id") or "")
        if vid in seen:
            continue
        seen.add(vid)
        raw = row.get("raw_json") or "{}"
        try:
            parsed = _json.loads(raw)
        except Exception:
            parsed = {}
        includes = (parsed.get("compose") or parsed).get("include") or []
        concepts: list[str] = []
        for inc in includes:
            for c in inc.get("concept") or []:
                code = str(c.get("code") or "").strip()
                if code:
                    concepts.append(code)
        with_sf = [code for code in concepts if sf_map.get(code, 0) > 0]
        result.append(
            {
                "id": vid,
                "title": str(row.get("title") or vid),
                "concept_count": len(concepts),
                "sf_count": len(with_sf),
                "no_sf_count": len(concepts) - len(with_sf),
                "derivable_count": len(concepts) - len(with_sf),
            }
        )
    result.sort(key=lambda x: x["id"])
    return {"valuesets": result}


@router.post("/synthetic-candidates")
def generate_synthetic_candidates(
    body: SyntheticGenerationRequest,
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    from libs.llm_client.factory import create_llm

    semantic_tags = [
        _normalise_semantic_tag(str(tag))
        for tag in (body.semantic_tags or [])
        if str(tag).strip()
    ]

    validator = DeIdValidator()
    llm = create_llm(provider="aws", tier="big")
    terminology = TerminologyClient()

    counts = {
        "forms_processed": 0,
        "candidates_written": 0,
        "gold_labels_written": 0,
        "forms_zero_written": 0,
        "context_examples_sampled": 0,
        "context_examples_used": 0,
        "context_examples_preview": [],
        "skipped_phi": 0,
        "skipped_no_match": 0,
        "skipped_both_forms": 0,
        "enriched_multi_entity": 0,
        "derived_forms_used": 0,
        "skipped_non_evidence": 0,
        "skipped_speculative": 0,
        "skipped_planned_observable": 0,
        "skipped_observable_no_value": 0,
        "skipped_semantic_mismatch": 0,
        "skipped_empty": 0,
        "errors": [],
    }

    client = KnowledgeGraphClient()
    pg_client = PatientGraphClient()
    related_finding_cache: dict[str, list[dict[str, Any]]] = {}
    gold_examples_cache: dict[str, list[dict[str, str]]] = {}
    try:
        with pg_client.session() as pg_session:
            raw_context_rows = [
                dict(r)
                for r in pg_session.run(
                    GET_ENCOUNTER_CONTEXT_CANDIDATES,
                    limit=5000,
                )
            ]
        prepared_context_rows: list[dict[str, Any]] = []
        for row in raw_context_rows:
            text = str(row.get("encounter_text") or "").strip()
            if not text:
                continue
            snippet = _extract_context_snippet(text, max_chars=500)
            if not snippet:
                continue
            enriched = dict(row)
            enriched["_text_lower"] = text.lower()
            enriched["_context_snippet"] = snippet
            prepared_context_rows.append(enriched)

        picked_rows = _pick_diverse_context_examples(prepared_context_rows, cap=10)
        fallback_context_examples = [
            str(r.get("_context_snippet") or "").strip()
            for r in picked_rows
            if str(r.get("_context_snippet") or "").strip()
        ][:10]
        counts["context_examples_sampled"] = len(fallback_context_examples)
        counts["context_examples_used"] = len(fallback_context_examples)
        counts["context_examples_preview"] = fallback_context_examples[:2]

        # Resolve valueset concept IDs so we can filter surface forms.
        valueset_concept_ids: list[str] | None = None
        valueset_scope_titles: list[str] = []
        domain_preferred_terms: list[str] = []
        if body.valueset_ids:
            valueset_concept_ids = _extract_concept_ids_from_valuesets(
                client, body.valueset_ids
            )
            valueset_scope_titles, domain_preferred_terms = (
                _load_valueset_prompt_context(client, body.valueset_ids)
            )

        with client.session() as session:
            if valueset_concept_ids is not None:
                form_rows = [
                    dict(r)
                    for r in session.run(
                        GET_SURFACE_FORMS_FOR_CONCEPT_IDS,
                        concept_ids=valueset_concept_ids,
                        limit=body.limit,
                        semantic_tags=semantic_tags,
                    )
                ]
                # For valueset concepts that have no surface forms, derive a
                # form from the concept's preferred term so generation still
                # produces training data for those concepts.
                if body.use_derived_forms:
                    remaining = max(0, body.limit - len(form_rows))
                    if remaining > 0:
                        derived_rows = [
                            dict(r)
                            for r in session.run(
                                GET_CONCEPTS_WITHOUT_SURFACE_FORMS_FOR_IDS,
                                concept_ids=valueset_concept_ids,
                                limit=remaining,
                                semantic_tags=semantic_tags,
                            )
                        ]
                        form_rows = form_rows + derived_rows
                        counts["derived_forms_used"] = len(derived_rows)
            else:
                form_rows = [
                    dict(r)
                    for r in session.run(
                        GET_SURFACE_FORMS_FOR_GENERATION,
                        limit=body.limit,
                        semantic_tags=semantic_tags,
                    )
                ]
            # Build a lookup so secondary entity metadata is available when a
            # generated sentence contains more than one known surface form.
            form_to_row: dict[str, dict] = {
                str(r.get("form") or "").strip(): dict(r)
                for r in form_rows
                if str(r.get("form") or "").strip()
            }
            known_forms = list(form_to_row.keys())
            for row in form_rows:
                counts["forms_processed"] += 1
                form = str(row.get("form") or "").strip()
                if not form:
                    counts["skipped_empty"] += 1
                    continue
                preferred_term = str(row.get("preferred_term") or "")
                concept_id = str(row.get("concept_id") or "")
                semantic_tag = _normalise_semantic_tag(
                    str(row.get("semantic_tag") or "")
                )
                gold_output_examples = gold_examples_cache.get(semantic_tag)
                if gold_output_examples is None:
                    semantic_tag_token = f'"semantic_tag": "{semantic_tag}"'.lower()
                    gold_rows = [
                        dict(r)
                        for r in session.run(
                            GET_GOLD_OUTPUT_EXAMPLE_CANDIDATES,
                            semantic_tag_token=semantic_tag_token,
                            limit=120,
                        )
                    ]
                    gold_output_examples = _extract_gold_output_examples(
                        gold_rows, cap=5
                    )
                    gold_examples_cache[semantic_tag] = gold_output_examples

                similarity_context = _pick_similarity_context_examples(
                    prepared_context_rows,
                    query_terms=[form, preferred_term],
                    cap=10,
                )
                context_examples = (
                    similarity_context
                    if similarity_context
                    else fallback_context_examples
                )

                system_prompt, user_prompt, clean_preferred_term = (
                    build_synthetic_sentence_prompts(
                        surface_form=form,
                        preferred_term=preferred_term,
                        concept_id=concept_id,
                        semantic_tag=semantic_tag,
                        n_sentences=body.sentences_per_form,
                        context_examples=context_examples,
                        gold_output_examples=gold_output_examples,
                        valueset_scope_titles=valueset_scope_titles,
                        domain_preferred_terms=domain_preferred_terms,
                    )
                )
                target_count = body.sentences_per_form
                accepted_for_form = 0
                max_attempts = 3
                for attempt_idx in range(max_attempts):
                    if accepted_for_form >= target_count:
                        break
                    corrective_block = ""
                    if attempt_idx > 0:
                        corrective_block = (
                            "\n\nRETRY INSTRUCTIONS:\n"
                            "- Previous outputs were filtered by deterministic guards.\n"
                            "- Avoid administrative/template lines.\n"
                            "- Avoid referral, recheck, repeat-test, or planned-action wording unless semantic tag is procedure.\n"
                            "- Keep semantic meaning aligned to the target semantic tag.\n"
                            "- Only produce definitive clinical evidence statements.\n"
                        )
                    attempt_prompt = f"{user_prompt}{corrective_block}"
                    try:
                        response = llm.converse(
                            system=system_prompt,
                            messages=[{"role": "user", "content": attempt_prompt}],
                            max_tokens=2200,
                            temperature=0.4,
                            agent_task="training_synthetic_sentence_generator",
                        )
                        sentences = _safe_parse_json_array(response.text)
                    except Exception as exc:
                        counts["errors"].append(f"llm:{form[:40]}: {exc}")
                        break

                    for item in sentences[:target_count]:
                        if accepted_for_form >= target_count:
                            break
                        sentence = str(item.get("sentence") or "").strip()
                        if not sentence:
                            counts["skipped_empty"] += 1
                            continue
                        assertion = (
                            str(item.get("assertion") or "present").strip().lower()
                        )
                        if assertion not in _VALID_ASSERTIONS:
                            assertion = "present"
                        if _is_invalid_observable_assertion(semantic_tag, assertion):
                            counts["skipped_planned_observable"] += 1
                            continue

                        deid_sentence = deidentify_text(sentence, ner=True)
                        if assertion == "absent" and not _has_absent_evidence(
                            deid_sentence
                        ):
                            assertion = "present"
                        if assertion == "historical" and not _has_historical_evidence(
                            deid_sentence
                        ):
                            assertion = "present"
                        if _is_mismatched_semantic_sentence(
                            semantic_tag, deid_sentence
                        ):
                            counts["skipped_semantic_mismatch"] += 1
                            continue
                        if _is_synthetic_non_evidence_sentence(deid_sentence):
                            counts["skipped_non_evidence"] += 1
                            continue
                        if _is_speculative_or_educational(deid_sentence):
                            counts["skipped_speculative"] += 1
                            continue
                        if semantic_tag == "observable_entity" and (
                            not _has_observation_value(deid_sentence)
                            or is_referral_procedure_phrase(deid_sentence)
                        ):
                            counts["skipped_observable_no_value"] += 1
                            continue
                        # Hard guard: exactly one occurrence of the target mention.
                        mention_count = _count_exact_phrase(deid_sentence, form)
                        if mention_count != 1:
                            counts["skipped_no_match"] += 1
                            continue
                        # Reject "AG - Atrophic gastritis..." style sentences where
                        # the model has written BOTH the abbreviation and the full
                        # preferred term in the same sentence.
                        if (
                            clean_preferred_term
                            and clean_preferred_term.lower() != form.lower()
                            and _count_exact_phrase(deid_sentence, clean_preferred_term)
                            > 0
                            and _count_exact_phrase(deid_sentence, form) > 0
                        ):
                            counts["skipped_both_forms"] += 1
                            continue
                        span = find_span(deid_sentence, form, clean_preferred_term)
                        if span is None:
                            counts["skipped_no_match"] += 1
                            continue
                        start, end = span
                        mention_text = deid_sentence[start:end]

                        entities_payload: list[dict[str, Any]] = [
                            {
                                "text": mention_text,
                                "label": semantic_tag,
                                "semantic_tag": semantic_tag,
                                "start": start,
                                "end": end,
                                "assertion": assertion,
                                "snomed_concept_id": concept_id,
                            }
                        ]

                        # Co-occurring known surface forms: label them all so the
                        # NER model is never trained with an unlabelled entity in
                        # the same sentence (which would be a false negative).
                        has_co_occurrence = False
                        for other in known_forms:
                            if other.lower() == form.lower():
                                continue
                            if _count_exact_phrase(deid_sentence, other) != 1:
                                continue
                            other_row = form_to_row.get(other) or {}
                            other_tag = _normalise_semantic_tag(
                                str(other_row.get("semantic_tag") or "")
                            )
                            other_concept = str(other_row.get("concept_id") or "")
                            if not other_tag or not other_concept:
                                continue
                            # Skip observable co-occurrences without a numeric value
                            if (
                                other_tag == "observable_entity"
                                and not _has_observation_value(deid_sentence)
                            ):
                                continue
                            other_span = find_span(deid_sentence, other)
                            if other_span is None:
                                continue
                            os_, oe_ = other_span
                            other_assertion = (
                                "absent"
                                if _has_absent_evidence(deid_sentence)
                                else "present"
                            )
                            entities_payload.append(
                                {
                                    "text": deid_sentence[os_:oe_],
                                    "label": other_tag,
                                    "semantic_tag": other_tag,
                                    "start": os_,
                                    "end": oe_,
                                    "assertion": other_assertion,
                                    "snomed_concept_id": other_concept,
                                }
                            )
                            has_co_occurrence = True
                        if has_co_occurrence:
                            counts["enriched_multi_entity"] = (
                                counts.get("enriched_multi_entity", 0) + 1
                            )

                        interpretation = _detect_interpretation_phrase(deid_sentence)
                        if semantic_tag == "observable_entity":
                            if interpretation:
                                phrase_text, i_start, i_end, qualifier = interpretation
                                related = related_finding_cache.get(concept_id)
                                if related is None:
                                    related_resp = terminology.get_related(concept_id)
                                    related = list(
                                        related_resp.get("interpreted_by_findings")
                                        or []
                                    )
                                    related_finding_cache[concept_id] = related
                                finding = _pick_related_finding(related, qualifier)
                                if finding:
                                    entities_payload.append(
                                        {
                                            "text": phrase_text,
                                            "label": "finding",
                                            "semantic_tag": "finding",
                                            "start": i_start,
                                            "end": i_end,
                                            "assertion": assertion,
                                            "snomed_concept_id": str(
                                                finding.get("id") or ""
                                            ),
                                        }
                                    )
                        elif (
                            semantic_tag in {"finding", "disorder"}
                            and interpretation
                            and _has_observation_value(deid_sentence)
                        ):
                            # If LLM anchored on finding/disorder for a measurable lab
                            # statement, add an observable companion entity too.
                            try:
                                resolved_obs = terminology.resolve_one(
                                    mention_text or form,
                                    label="observable_entity",
                                )
                            except Exception:
                                resolved_obs = None
                            if (
                                resolved_obs
                                and str(resolved_obs.concept_id or "").strip()
                            ):
                                entities_payload.append(
                                    {
                                        "text": mention_text,
                                        "label": "observable_entity",
                                        "semantic_tag": "observable_entity",
                                        "start": start,
                                        "end": end,
                                        "assertion": "present",
                                        "snomed_concept_id": str(
                                            resolved_obs.concept_id
                                        ),
                                    }
                                )

                        try:
                            entities_payload = run_post_processing(
                                deid_sentence,
                                entities_payload,
                                rules=None,
                                enable_disorder_gate=False,
                                coding_mode="hitl",
                            )
                        except Exception as exc:
                            counts["errors"].append(f"post_process:{form[:40]}: {exc}")
                            continue
                        if not entities_payload:
                            counts["skipped_non_evidence"] += 1
                            continue

                        record_issues = validator.check_record(
                            {
                                "text": deid_sentence,
                                "entities": [
                                    {
                                        "entity_id": str(i),
                                        "text": str(e.get("text") or ""),
                                    }
                                    for i, e in enumerate(entities_payload)
                                ],
                                "metadata": {},
                            }
                        )
                        if record_issues:
                            counts["skipped_phi"] += 1
                            continue

                        candidate_id = hashlib.sha256(
                            deid_sentence.encode("utf-8")
                        ).hexdigest()
                        label_id = f"synthetic-{uuid.uuid4().hex}"
                        entities_json = json.dumps(
                            entities_payload,
                            ensure_ascii=False,
                        )

                        session.run(
                            UPSERT_TRAINING_CANDIDATE,
                            candidate_id=candidate_id,
                            text=deid_sentence,
                            entities_json=entities_json,
                            source=_SYNTHETIC_SOURCE,
                            status="completed",
                            schema_version="v4",
                        )
                        session.run(
                            UPSERT_GOLD_LABEL,
                            label_id=label_id,
                            text=deid_sentence,
                            entities_json=entities_json,
                            quality_score=0.85,
                            source=_SYNTHETIC_SOURCE,
                            verified_by=_SYNTHETIC_VERIFIED_BY,
                            candidate_id=candidate_id,
                            schema_version="v4",
                        )
                        counts["candidates_written"] += 1
                        counts["gold_labels_written"] += 1
                        accepted_for_form += 1
                if accepted_for_form == 0:
                    counts["forms_zero_written"] += 1
    finally:
        pg_client.close()
        client.close()

    return counts


@router.delete("/synthetic-candidates")
def delete_synthetic_candidates(
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            row = session.run(
                """
                MATCH (g:GoldLabel {source: $source})
                WITH collect(g) AS labels
                RETURN size(labels) AS gold_labels
                """,
                source=_SYNTHETIC_SOURCE,
            ).single()
            gold_labels = int((row or {}).get("gold_labels") or 0)
            row = session.run(
                """
                MATCH (c:TrainingCandidate {source: $source})
                RETURN count(c) AS candidates
                """,
                source=_SYNTHETIC_SOURCE,
            ).single()
            candidates = int((row or {}).get("candidates") or 0)
            session.run(
                """
                MATCH (g:GoldLabel {source: $source})
                DETACH DELETE g
                """,
                source=_SYNTHETIC_SOURCE,
            )
            session.run(
                """
                MATCH (c:TrainingCandidate {source: $source})
                DETACH DELETE c
                """,
                source=_SYNTHETIC_SOURCE,
            )
        return {
            "deleted_gold_labels": gold_labels,
            "deleted_candidates": candidates,
        }
    finally:
        client.close()


@router.post("/synthetic-candidates/queue")
async def queue_synthetic_candidates(
    body: SyntheticQueueRequest,
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    from libs.message_bus.base import Message
    from libs.message_bus.factory import create_message_bus

    semantic_tags = [
        _normalise_semantic_tag(str(tag))
        for tag in (body.semantic_tags or [])
        if str(tag).strip()
    ]
    client = KnowledgeGraphClient()
    valueset_concept_ids: list[str] | None = None
    if body.valueset_ids:
        valueset_concept_ids = _extract_concept_ids_from_valuesets(
            client, body.valueset_ids
        )
    try:
        with client.session() as session:
            if valueset_concept_ids is not None:
                rows = [
                    dict(r)
                    for r in session.run(
                        GET_SURFACE_FORMS_FOR_CONCEPT_IDS,
                        concept_ids=valueset_concept_ids,
                        limit=body.limit,
                        semantic_tags=semantic_tags,
                    )
                ]
                if body.use_derived_forms:
                    remaining = max(0, body.limit - len(rows))
                    if remaining > 0:
                        derived = [
                            dict(r)
                            for r in session.run(
                                GET_CONCEPTS_WITHOUT_SURFACE_FORMS_FOR_IDS,
                                concept_ids=valueset_concept_ids,
                                limit=remaining,
                                semantic_tags=semantic_tags,
                            )
                        ]
                        rows = rows + derived
            else:
                rows = [
                    dict(r)
                    for r in session.run(
                        GET_SURFACE_FORMS_FOR_GENERATION,
                        limit=body.limit,
                        semantic_tags=semantic_tags,
                    )
                ]
    finally:
        client.close()

    if not rows:
        return {"queued": False, "estimated_forms": 0, "queued_batches": 0}

    batches = [rows[i : i + 50] for i in range(0, len(rows), 50)]
    bus = create_message_bus()
    try:
        for idx, batch in enumerate(batches):
            message = Message(
                body={
                    "event_type": "synthetic-gold-generate",
                    "batch_index": idx,
                    "payload": {
                        "surface_forms": batch,
                        "sentences_per_form": body.sentences_per_form,
                        "semantic_tags": semantic_tags,
                    },
                },
                correlation_id=f"synthetic-{uuid.uuid4().hex}",
                subject="synthetic-gold-generate",
            )
            await bus.send(_PIPELINE_QUEUE, message)
    finally:
        await bus.close()

    return {
        "queued": True,
        "estimated_forms": len(rows),
        "queued_batches": len(batches),
    }


_DEDUPE_STOP_WORDS = {
    "and",
    "the",
    "with",
    "from",
    "that",
    "this",
    "have",
    "has",
    "for",
    "into",
    "was",
    "were",
    "are",
    "had",
    "not",
    "you",
    "your",
    "their",
    "they",
    "she",
    "him",
    "her",
    "his",
}


def _normalise_candidate_text(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", str(text).lower())
    return " ".join(cleaned.split())


def _tokenise_candidate_text(text: str) -> set[str]:
    tokens = _normalise_candidate_text(text).split()
    return {t for t in tokens if len(t) > 2 and t not in _DEDUPE_STOP_WORDS}


def _candidate_similarity(left: str, right: str) -> float:
    left_norm = _normalise_candidate_text(left)
    right_norm = _normalise_candidate_text(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm == right_norm:
        return 1.0

    left_tokens = _tokenise_candidate_text(left_norm)
    right_tokens = _tokenise_candidate_text(right_norm)
    intersection = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    jaccard = (intersection / union) if union else 0.0
    sequence = SequenceMatcher(None, left_norm, right_norm).ratio()
    containment = min(len(left_tokens), len(right_tokens)) / max(
        1, max(len(left_tokens), len(right_tokens))
    )
    overlap = intersection / max(1, min(len(left_tokens), len(right_tokens)))
    substring_bonus = 0.0
    if left_norm in right_norm or right_norm in left_norm:
        substring_bonus = 0.10
    score = (
        (0.40 * jaccard)
        + (0.25 * sequence)
        + (0.20 * containment)
        + (0.15 * overlap)
        + substring_bonus
    )
    score = min(1.0, score)
    return round(float(score), 6)


def _candidate_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": row.get("candidate_id"),
        "status": row.get("status"),
        "source": row.get("source"),
        "updated_at": row.get("updated_at"),
        "text_preview": str(row.get("text") or "")[:220],
    }


def _find_root(parent: dict[int, int], node: int) -> int:
    while parent[node] != node:
        parent[node] = parent[parent[node]]
        node = parent[node]
    return node


def _union_roots(parent: dict[int, int], left: int, right: int) -> None:
    root_left = _find_root(parent, left)
    root_right = _find_root(parent, right)
    if root_left != root_right:
        parent[root_right] = root_left


def _build_candidate_pairs(rows: list[dict[str, Any]]) -> set[tuple[int, int]]:
    """Build likely duplicate pairs using token-overlap canopies.

    Previous fixed-prefix blocking missed obvious near-duplicates when one row had
    an extra prefix fragment (for example "Seen in 2WW clinic: ...").
    """
    token_index: dict[str, set[int]] = defaultdict(set)
    token_sets: list[set[str]] = []

    for idx, row in enumerate(rows):
        tokens = _tokenise_candidate_text(str(row.get("text") or ""))
        token_sets.append(tokens)
        for token in tokens:
            token_index[token].add(idx)

    pairs: set[tuple[int, int]] = set()
    for left_idx, left_tokens in enumerate(token_sets):
        if not left_tokens:
            continue
        neighbour_overlap: dict[int, int] = defaultdict(int)
        for token in left_tokens:
            for right_idx in token_index[token]:
                if right_idx <= left_idx:
                    continue
                neighbour_overlap[right_idx] += 1
        min_overlap = 1 if len(left_tokens) < 4 else 2
        for right_idx, overlap in neighbour_overlap.items():
            if overlap >= min_overlap:
                pairs.add((left_idx, right_idx))

    # Small candidate pools can afford exhaustive comparison.
    if len(rows) <= 250:
        for left_idx in range(len(rows)):
            for right_idx in range(left_idx + 1, len(rows)):
                pairs.add((left_idx, right_idx))
    return pairs


def _cluster_candidates(
    rows: list[dict[str, Any]], threshold: float
) -> tuple[dict[int, list[int]], dict[tuple[int, int], float]]:
    parent: dict[int, int] = {i: i for i in range(len(rows))}
    edge_scores: dict[tuple[int, int], float] = {}
    for left_idx, right_idx in _build_candidate_pairs(rows):
        score = _candidate_similarity(
            str(rows[left_idx].get("text") or ""),
            str(rows[right_idx].get("text") or ""),
        )
        if score < threshold:
            continue
        pair = tuple(sorted((left_idx, right_idx)))
        edge_scores[pair] = max(score, edge_scores.get(pair, 0.0))
        _union_roots(parent, left_idx, right_idx)
    grouped: dict[int, list[int]] = defaultdict(list)
    for idx in range(len(rows)):
        grouped[_find_root(parent, idx)].append(idx)
    return grouped, edge_scores


def _build_candidate_similarity_groups(
    rows: list[dict[str, Any]], threshold: float
) -> list[dict[str, Any]]:
    if len(rows) < 2:
        return []
    grouped, edge_scores = _cluster_candidates(rows, threshold)
    groups: list[dict[str, Any]] = []
    for members in grouped.values():
        if len(members) < 2:
            continue
        sorted_members = sorted(
            members,
            key=lambda i: (
                -len(str(rows[i].get("text") or "")),
                str(rows[i].get("updated_at") or ""),
                str(rows[i].get("candidate_id") or ""),
            ),
        )
        canonical_idx = sorted_members[0]
        duplicates: list[dict[str, Any]] = []
        for member_idx in sorted_members[1:]:
            pair = tuple(sorted((canonical_idx, member_idx)))
            similarity = edge_scores.get(
                pair,
                _candidate_similarity(
                    str(rows[canonical_idx].get("text") or ""),
                    str(rows[member_idx].get("text") or ""),
                ),
            )
            payload = _candidate_payload(rows[member_idx])
            payload["similarity"] = round(float(similarity), 6)
            duplicates.append(payload)
        groups.append(
            {
                "canonical": _candidate_payload(rows[canonical_idx]),
                "duplicates": duplicates,
            }
        )
    groups.sort(key=lambda g: len(g.get("duplicates", [])), reverse=True)
    return groups


def _extract_candidate_entity_terms(entities_json: Any) -> set[str]:
    if not entities_json:
        return set()
    try:
        parsed = json.loads(entities_json)
    except Exception:
        return set()
    if not isinstance(parsed, list):
        return set()
    terms: set[str] = set()
    for row in parsed:
        if not isinstance(row, dict):
            continue
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        normalised = _normalise_candidate_text(text)
        if normalised:
            terms.add(normalised)
    return terms


def _entity_similarity(left_terms: set[str], right_terms: set[str]) -> float:
    if not left_terms or not right_terms:
        return 0.0
    exact = len(left_terms & right_terms)
    if exact:
        return min(1.0, 0.7 + (exact / max(1, len(left_terms))))
    best = 0.0
    for left in left_terms:
        for right in right_terms:
            best = max(best, _candidate_similarity(left, right))
    return round(float(best), 6)


def _fetch_dedupe_candidates(
    *,
    status: str | None,
    source: str | None,
    search: str | None,
    max_candidates: int,
) -> list[dict[str, Any]]:
    terms = expand_search_terms(search)
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            rows = session.run(
                GET_TRAINING_CANDIDATES_PAGE,
                skip=0,
                limit=max_candidates,
                status=status,
                exclude_completed=False,
                source=source,
                search=search,
                terms=terms,
            )
            return [dict(r) for r in rows]
    finally:
        client.close()


@router.post("/candidates/dedupe/preview")
def preview_training_candidate_dedupe(
    body: CandidateDedupeRequest,
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    rows = _fetch_dedupe_candidates(
        status=body.status,
        source=body.source,
        search=body.search,
        max_candidates=body.max_candidates,
    )
    groups = _build_candidate_similarity_groups(rows, body.similarity_threshold)
    duplicate_count = sum(len(g.get("duplicates", [])) for g in groups)
    return {
        "candidate_pool_size": len(rows),
        "group_count": len(groups),
        "duplicate_count": duplicate_count,
        "similarity_threshold": body.similarity_threshold,
        "groups": groups,
    }


@router.post("/candidates/dedupe/apply")
def apply_training_candidate_dedupe(
    body: CandidateDedupeRequest,
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    rows = _fetch_dedupe_candidates(
        status=body.status,
        source=body.source,
        search=body.search,
        max_candidates=body.max_candidates,
    )
    groups = _build_candidate_similarity_groups(rows, body.similarity_threshold)
    updates: list[dict[str, Any]] = []
    for group in groups:
        canonical_id = str(group["canonical"]["candidate_id"])
        for duplicate in group.get("duplicates", []):
            duplicate_id = str(duplicate.get("candidate_id") or "")
            if not duplicate_id or duplicate_id == canonical_id:
                continue
            updates.append(
                {
                    "canonical_id": canonical_id,
                    "duplicate_id": duplicate_id,
                    "score": float(duplicate.get("similarity") or 0.0),
                    "method": "token_jaccard+sequence",
                }
            )

    if not updates:
        return {
            "candidate_pool_size": len(rows),
            "duplicates_marked": 0,
            "group_count": 0,
            "run_id": None,
            "message": "No duplicates met the similarity threshold.",
        }

    run_id = f"dedupe-{uuid.uuid4().hex}"
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            result_row = session.run(
                MARK_TRAINING_CANDIDATE_DUPLICATES,
                updates=updates,
                run_id=run_id,
            ).single()
        duplicates_marked = int(result_row["duplicates_marked"] if result_row else 0)
    finally:
        client.close()

    logger.info(
        "TrainingCandidate dedupe apply run=%s groups=%s duplicates=%s actor=%s",
        run_id,
        len(groups),
        duplicates_marked,
        getattr(scope, "email", "unknown"),
    )
    return {
        "candidate_pool_size": len(rows),
        "duplicates_marked": duplicates_marked,
        "group_count": len(groups),
        "run_id": run_id,
        "similarity_threshold": body.similarity_threshold,
    }


@router.post("/candidates/find-similar-by-entity")
def find_similar_candidates_by_entity(
    body: SimilarCandidatesByEntityRequest,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    # Fetch all candidates (no status filter) so the source candidate is found
    # regardless of its current status (it may not be "pending" any more).
    rows = _fetch_dedupe_candidates(
        status=None,
        source=None,
        search=None,
        max_candidates=3000,
    )
    source_row = next(
        (
            row
            for row in rows
            if str(row.get("candidate_id") or "") == body.candidate_id
        ),
        None,
    )
    if not source_row:
        raise HTTPException(status_code=404, detail="Candidate not found")
    source_terms = _extract_candidate_entity_terms(source_row.get("entities_json"))
    if not source_terms:
        return {"source_candidate_id": body.candidate_id, "count": 0, "items": []}

    matches: list[dict[str, Any]] = []
    for row in rows:
        candidate_id = str(row.get("candidate_id") or "")
        if not candidate_id or candidate_id == body.candidate_id:
            continue
        # Only surface pending candidates as bulk-labelling targets.
        if str(row.get("status") or "") != "pending":
            continue
        terms = _extract_candidate_entity_terms(row.get("entities_json"))
        similarity = _entity_similarity(source_terms, terms)
        if similarity < body.similarity_threshold:
            continue
        matches.append(
            {
                "candidate_id": candidate_id,
                "text": str(row.get("text") or ""),
                "source": row.get("source"),
                "status": row.get("status"),
                "updated_at": row.get("updated_at"),
                "entities_json": row.get("entities_json"),
                "similarity": similarity,
            }
        )
    matches.sort(key=lambda row: row.get("similarity", 0.0), reverse=True)
    limited = matches[: body.limit]
    return {
        "source_candidate_id": body.candidate_id,
        "count": len(limited),
        "items": limited,
    }


@router.get("/candidates/stats")
def get_training_candidate_stats(
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            row = session.run(GET_TRAINING_CANDIDATE_STATS).single()
        return (
            dict(row)
            if row
            else {
                "total": 0,
                "pending": 0,
                "processing": 0,
                "completed": 0,
                "failed": 0,
            }
        )
    finally:
        client.close()


@router.get("/candidates")
def list_training_candidates(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    status: str | None = None,
    source: str | None = None,
    search: str | None = None,
    exclude_completed: bool = Query(False),
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    skip = (page - 1) * page_size
    # DI-LEO-AI-526 -- expand the reviewer's free-text query into the
    # same typo-corrected, synonym-expanded term list used by the host
    # encounter search so the dry-run review queue surfaces matching
    # rows for "lump" via "mass" / "swelling" / "nodule" too. Empty list
    # means the cypher falls back to the legacy `search` substring.
    terms = expand_search_terms(search)
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            rows = session.run(
                GET_TRAINING_CANDIDATES_PAGE,
                skip=skip,
                limit=page_size,
                status=status,
                exclude_completed=exclude_completed,
                source=source,
                search=search,
                terms=terms,
            )
            items = [dict(r) for r in rows]
            _enrich_items_entities_with_pt_cache(session, items)
            count_row = session.run(
                COUNT_TRAINING_CANDIDATES_PAGE,
                status=status,
                exclude_completed=exclude_completed,
                source=source,
                search=search,
                terms=terms,
            ).single()
        total = count_row["total"] if count_row else 0
        return {"items": items, "page": page, "page_size": page_size, "total": total}
    finally:
        client.close()


@router.get("/candidates/active-learning-queue")
def active_learning_queue(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Return pending TrainingCandidates ranked by a blended priority score.

    priority_score = 0.6 * rarity_score + 0.4 * normalised_uncertainty

    rarity_score is derived from the current gold label distribution: labels
    with fewer gold examples produce a higher score so the reviewer is guided
    toward filling dataset gaps.  This works even before the first model is
    promoted because it reads entities_json directly from each candidate node.

    MUST be declared before /candidates/{candidate_id} so FastAPI does not
    treat the literal path segment as a candidate_id parameter.
    """
    from libs.cypher.training_candidate_queries import (
        GET_ALL_PENDING_FOR_RANKING,
        COUNT_ACTIVE_LEARNING_QUEUE,
    )

    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            all_rows = [dict(r) for r in session.run(GET_ALL_PENDING_FOR_RANKING)]
            count_row = session.run(COUNT_ACTIVE_LEARNING_QUEUE).single()
        total = count_row["total"] if count_row else 0
    finally:
        client.close()

    label_counts = _fetch_label_counts_for_scoring()
    _enrich_and_sort(all_rows, label_counts)

    skip = (page - 1) * page_size
    items = all_rows[skip : skip + page_size]
    return {"items": items, "page": page, "page_size": page_size, "total": total}


def _enrich_and_sort(
    rows: list[dict],
    label_counts: dict[str, int],
) -> None:
    """Mutate rows in-place: add rarity/priority fields and sort DESC."""
    for row in rows:
        r_score, r_labels = _rarity_for_candidate(
            row.get("entities_json"), label_counts
        )
        u_raw = float(row.get("uncertainty_score") or 0.0)
        norm_u = min(u_raw / 3.0, 1.0)
        row["rarity_score"] = r_score
        row["rare_labels"] = r_labels
        row["priority_score"] = round(0.6 * r_score + 0.4 * norm_u, 4)
    rows.sort(key=lambda r: r["priority_score"], reverse=True)


@router.post("/candidates/score")
def score_candidates_for_active_learning(
    scope: CallerScope = Depends(get_caller_scope),
    _admin=Depends(require_admin),
) -> dict[str, Any]:
    """Score pending candidates by NER uncertainty and store on the node.

    Runs in a background thread. Returns immediately with job metadata.
    Uncertainty = sum of -p*log(p) across token NER label distributions,
    using the currently promoted model from the registry.
    """
    job_id = str(uuid.uuid4())
    t = threading.Thread(
        target=_run_active_learning_scoring,
        args=(job_id,),
        daemon=True,
        name=f"al-score-{job_id[:8]}",
    )
    t.start()
    return {"job_id": job_id, "status": "started"}


@router.get("/candidates/{candidate_id}")
def get_training_candidate(
    candidate_id: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            row = session.run(
                GET_TRAINING_CANDIDATE_BY_ID, candidate_id=candidate_id
            ).single()
        if not row:
            raise HTTPException(
                status_code=404, detail=f"Candidate {candidate_id!r} not found"
            )
        return dict(row)
    finally:
        client.close()


@router.delete("/candidates/{candidate_id}")
def delete_training_candidate(
    candidate_id: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            row = session.run(
                DELETE_TRAINING_CANDIDATE_AND_ARTIFACTS,
                candidate_id=candidate_id,
            ).single()
        if not row:
            raise HTTPException(
                status_code=404, detail=f"Candidate {candidate_id!r} not found"
            )
        payload = dict(row)
        logger.info(
            "TrainingCandidate deleted id=%s gold_labels=%s surface_form_tasks=%s actor=%s",
            candidate_id[:12],
            payload.get("gold_labels_deleted", 0),
            payload.get("surface_form_tasks_deleted", 0),
            getattr(scope, "email", "unknown"),
        )
        return payload
    finally:
        client.close()


# --------------------------------------------------------------------------
# Confidence-gated TrainingCandidate auto-prune (DI-LEO-AI-196 / UN-LEO-AI-083)
#
# Two-phase contract:
#   POST /training/candidates/prune/preview  -- read-only verdict ladder
#   POST /training/candidates/prune/execute  -- delete the explicit IDs only
#
# Both endpoints are admin-only. The execute path re-checks status before
# deleting (TOCTOU guard) and never touches status='completed'.
# --------------------------------------------------------------------------


class PrunePreviewRequest(BaseModel):
    min_surface_match: float = Field(default=0.7, ge=0.0, le=1.0)
    semantic_vector_floor: float = Field(default=0.92, ge=0.0, le=1.0)
    semantic_min_surface: float = Field(default=0.66, ge=0.0, le=1.0)
    statuses: list[str] = Field(
        default_factory=lambda: ["pending", "processing", "failed"]
    )
    limit: int = Field(default=500, ge=1, le=2000)


class PruneExecuteRequest(BaseModel):
    candidate_ids: list[str] = Field(default_factory=list)


@router.post("/candidates/prune/preview")
def prune_training_candidates_preview(
    body: PrunePreviewRequest,
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Dry-run the verdict ladder over non-completed TrainingCandidates.

    Returns a per-candidate assessment plus aggregate summary so the
    reviewer can sample before invoking ``/prune/execute`` with the
    explicit candidate_ids returned here.
    """
    from app.services.candidate_prune import (
        PruneParams,
        assess_candidates,
        summarise,
    )

    params = PruneParams(
        min_surface_match=float(body.min_surface_match),
        semantic_vector_floor=float(body.semantic_vector_floor),
        semantic_min_surface=float(body.semantic_min_surface),
        statuses=tuple(body.statuses or []),
        limit=int(body.limit),
    )

    kg = KnowledgeGraphClient()
    terminology = TerminologyClient()
    try:
        assessments = assess_candidates(kg, terminology, params)
    finally:
        kg.close()

    summary = summarise(assessments)
    payload = {
        "params": {
            "min_surface_match": params.min_surface_match,
            "semantic_vector_floor": params.semantic_vector_floor,
            "semantic_min_surface": params.semantic_min_surface,
            "statuses": list(params.statuses),
            "limit": params.limit,
        },
        "summary": summary,
        "candidates": [a.to_dict() for a in assessments],
    }
    logger.info(
        "candidate_prune.preview actor=%s scanned=%d delete=%d review=%d keep=%d",
        getattr(scope, "email", "unknown"),
        summary["candidate_count"],
        summary["by_verdict"].get("delete", 0),
        summary["by_verdict"].get("review", 0),
        summary["by_verdict"].get("keep", 0),
    )
    return payload


@router.post("/candidates/prune/execute")
def prune_training_candidates_execute(
    body: PruneExecuteRequest,
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Delete the explicitly-supplied TrainingCandidate IDs.

    Re-fetches each candidate before deletion and skips
    ``status='completed'`` to defend against TOCTOU drift between a
    prior preview and this execute call.
    """
    from app.services.candidate_prune import execute_prune

    if not body.candidate_ids:
        raise HTTPException(
            status_code=400,
            detail="candidate_ids must be non-empty",
        )

    kg = KnowledgeGraphClient()
    try:
        outcome = execute_prune(kg, body.candidate_ids)
    finally:
        kg.close()

    logger.info(
        "candidate_prune.execute actor=%s requested=%d deleted=%d "
        "skipped_completed=%d not_found=%d",
        getattr(scope, "email", "unknown"),
        len(outcome.requested),
        len(outcome.deleted),
        len(outcome.skipped_completed),
        len(outcome.not_found),
    )
    return {
        "requested": len(outcome.requested),
        "deleted": len(outcome.deleted),
        "skipped_completed": len(outcome.skipped_completed),
        "not_found": len(outcome.not_found),
        "deleted_ids": outcome.deleted,
        "skipped_completed_ids": outcome.skipped_completed,
        "not_found_ids": outcome.not_found,
        "cascade_counts": outcome.cascade_counts,
    }


@router.post("/candidates/{candidate_id}/mark-completed")
def mark_training_candidate_completed(
    candidate_id: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
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

            gold_row = session.run(
                GET_GOLD_LABEL_BY_CANDIDATE_ID,
                candidate_id=candidate_id,
            ).single()
            if not gold_row:
                raise HTTPException(
                    status_code=409,
                    detail="Cannot mark completed until a linked gold label exists.",
                )

            text = gold_row.get("text", "") or candidate_row.get("text", "")
            entities_json = (
                gold_row.get("entities_json")
                or candidate_row.get("entities_json")
                or "[]"
            )
            label_id = gold_row.get("label_id") or f"manual-{uuid.uuid4().hex}"
            session.run(
                UPSERT_GOLD_LABEL,
                label_id=label_id,
                text=text,
                entities_json=entities_json,
                quality_score=gold_row.get("quality_score"),
                source="manual_gold_editor",
                verified_by=getattr(scope, "email", "operations_ui"),
                candidate_id=candidate_id,
                schema_version=gold_row.get("schema_version")
                or candidate_row.get("schema_version")
                or "v4",
            )
            _apply_gold_granularity_metadata(
                session,
                candidate_id=candidate_id,
                label_id=label_id,
                text=text,
                entities_json=entities_json,
            )
            update_row = session.run(
                UPDATE_TRAINING_CANDIDATE_STATUS,
                candidate_id=candidate_id,
                status="completed",
            ).single()
            if not update_row:
                raise HTTPException(
                    status_code=500, detail="Failed to update candidate status"
                )

        logger.info(
            "TrainingCandidate marked completed id=%s label=%s actor=%s",
            candidate_id[:12],
            str(gold_row.get("label_id", ""))[:12],
            getattr(scope, "email", "unknown"),
        )
        return {
            "candidate_id": update_row["candidate_id"],
            "status": update_row["status"],
            "gold_label_id": gold_row.get("label_id"),
        }
    finally:
        client.close()


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
            rows = session.run("""
                MATCH (c:TrainingCandidate)-[:PRODUCED]->(g:GoldLabel)
                WHERE c.status = 'completed'
                  AND g.entities_json IS NOT NULL
                RETURN g.entities_json AS entities_json
                """)
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
            rows = [dict(r) for r in session.run("""
                    MATCH (c:TrainingCandidate)-[:PRODUCED]->(g:GoldLabel)
                    WHERE c.status = 'completed'
                      AND g.entities_json IS NOT NULL
                    RETURN
                      g.label_id AS label_id,
                      g.text AS text,
                      g.entities_json AS entities_json,
                      g.source AS source
                    ORDER BY g.updated_at DESC
                    """)]
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


# Reverse lookup: SNOMED semantic tag (as stored on the concept node /
# coded link, e.g. "disorder", "observable entity") -> NER stored label
# (e.g. "disorder", "observable_entity").  Built once at import time so
# the live -> gold mapping does not allocate a dict per call.
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


# -- Golden set flag management --------------------------------------------


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


def _run_active_learning_scoring(job_id: str) -> None:
    """Background: score pending candidates and write uncertainty_score."""
    import math
    import logging as _log

    log = _log.getLogger(__name__)
    log.info("[active-learning] Scoring job %s started", job_id)

    try:
        import spacy
        from libs.model_registry import ModelRegistry
        from libs.neo4j_client.client import KnowledgeGraphClient
        from libs.cypher.training_candidate_queries import (
            GET_PENDING_CANDIDATES_FOR_SCORING,
            SET_UNCERTAINTY_SCORE,
        )

        registry = ModelRegistry()
        promoted = registry.get_promoted_version()
        if not promoted:
            log.warning("[active-learning] No promoted model — skipping scoring")
            return

        from libs.model_store import ModelStore

        store = ModelStore()
        model_dir = store.download(promoted)
        nlp = spacy.load(str(model_dir))

        kg = KnowledgeGraphClient()
        try:
            with kg.session() as session:
                rows = list(session.run(GET_PENDING_CANDIDATES_FOR_SCORING))
        finally:
            kg.close()

        log.info("[active-learning] Scoring %d candidates", len(rows))

        for row in rows:
            text = str(row.get("text") or "")
            cid = str(row.get("candidate_id") or "")
            if not text or not cid:
                continue
            doc = nlp(text)
            score = _token_entropy(doc)
            kg2 = KnowledgeGraphClient()
            try:
                with kg2.session() as session:
                    session.run(SET_UNCERTAINTY_SCORE, candidate_id=cid, score=score)
            finally:
                kg2.close()

        log.info("[active-learning] Scoring job %s complete", job_id)
    except Exception as exc:
        log.exception("[active-learning] Scoring job %s failed: %s", job_id, exc)


def _token_entropy(doc) -> float:
    """Compute mean per-token NER entropy as an uncertainty measure."""
    import math

    if not doc or not hasattr(doc, "_"):
        return 0.0

    total = 0.0
    count = 0
    for token in doc:
        probs = getattr(token, "_.trf_data", None)
        if probs is None:
            continue
        for p in probs:
            if p > 0:
                total -= p * math.log(p + 1e-12)
            count += 1

    return round(total / count, 6) if count else 0.0


def _fetch_label_counts_for_scoring() -> dict[str, int]:
    """Return {LABEL: count} from verified gold labels for rarity scoring."""
    import json as _json
    from collections import Counter

    counter: Counter = Counter()
    kg = KnowledgeGraphClient()
    try:
        with kg.session() as session:
            rows = session.run("""
                MATCH (c:TrainingCandidate)-[:PRODUCED]->(g:GoldLabel)
                WHERE c.status = 'completed' AND g.entities_json IS NOT NULL
                RETURN g.entities_json AS entities_json
                """)
            for row in rows:
                for ent in _json.loads(row["entities_json"] or "[]"):
                    raw = str(ent.get("label") or ent.get("semantic_tag") or "").upper()
                    if raw:
                        counter[raw] += 1
    finally:
        kg.close()
    return dict(counter)


def _rarity_for_candidate(
    entities_json: str | None,
    label_counts: dict[str, int],
) -> tuple[float, list[str]]:
    """Compute a [0,1] rarity score and list of rare labels for one candidate.

    Rarity = 1 / (1 + gold_count) for each entity label.  Labels with fewer
    gold examples produce a higher score.  A label never seen in gold gets
    the maximum score of 1.0.
    """
    import json as _json

    if not entities_json:
        return 0.0, []
    best = 0.0
    rare: list[str] = []
    for ent in _json.loads(entities_json or "[]"):
        label = str(ent.get("label") or ent.get("semantic_tag") or "").upper()
        if not label:
            continue
        count = label_counts.get(label, 0)
        r = 1.0 / (1.0 + count)
        if r > 0.1:
            rare.append(label)
        best = max(best, r)
    return round(best, 4), sorted(set(rare))


# -- Surface form review tasks (Knowledge Graph) ---------------------------


@router.get("/surface-form-tasks")
def list_surface_form_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    status: str | None = Query(default="pending"),
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    skip = (page - 1) * page_size
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            rows = session.run(
                LIST_PENDING_SURFACE_FORM_TASKS,
                skip=skip,
                limit=page_size,
                status=status,
            )
            items = [dict(r) for r in rows]
            count_row = session.run(COUNT_SURFACE_FORM_TASKS, status=status).single()
        total = count_row["total"] if count_row else 0
        return {"items": items, "page": page, "page_size": page_size, "total": total}
    finally:
        client.close()


@router.get("/surface-form-tasks/stats")
def surface_form_task_stats(
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            pending = session.run(COUNT_SURFACE_FORM_TASKS, status="pending").single()
            resolved = session.run(COUNT_SURFACE_FORM_TASKS, status="approved").single()
        return {
            "pending": pending["total"] if pending else 0,
            "approved": resolved["total"] if resolved else 0,
        }
    finally:
        client.close()


@router.get("/surface-form-tasks/{task_id}")
def get_surface_form_task(
    task_id: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            row = session.run(GET_SURFACE_FORM_TASK_BY_ID, task_id=task_id).single()
        if not row:
            raise HTTPException(
                status_code=404, detail=f"SurfaceFormTask {task_id!r} not found"
            )
        return dict(row)
    finally:
        client.close()


@router.post("/surface-form-tasks/{task_id}/resolve")
def resolve_surface_form_task(
    task_id: str,
    body: ResolveSurfaceFormTaskRequest,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    if body.status not in {"approved", "rejected", "modified"}:
        raise HTTPException(
            status_code=422, detail="status must be approved|rejected|modified"
        )
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            row = session.run(
                RESOLVE_SURFACE_FORM_TASK,
                task_id=task_id,
                status=body.status,
                resolved_concept=body.resolved_concept or "",
                resolved_by=body.resolved_by or "operations_ui",
            ).single()
        if not row:
            raise HTTPException(
                status_code=404, detail=f"SurfaceFormTask {task_id!r} not found"
            )
        return {"task_id": row["task_id"], "status": row["status"]}
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Corpus statistics endpoint (Sprint 4)
# ---------------------------------------------------------------------------

_Q_CORPUS_STATS_BY_SOURCE = """
MATCH (e:Encounter)-[r:DOCUMENTS]->(s)
WHERE r.evidence_sentence IS NOT NULL
RETURN
    r.source                                    AS source,
    r.holdout                                   AS holdout,
    coalesce(toString(s.semanticTag), 'other')  AS semantic_tag,
    coalesce(r.context, '{}')                   AS context_json,
    count(r)                                    AS cnt
"""

_Q_NEGATIVE_SENTENCES = """
MATCH (e:Encounter)
WHERE e.text IS NOT NULL AND trim(e.text) <> ''
AND NOT EXISTS {
    MATCH (e)-[r:DOCUMENTS]->()
    WHERE r.evidence_sentence IS NOT NULL
}
RETURN count(e) AS negative_count
"""

_Q_CORPUS_LAST_UPDATED = """
MATCH (e:Encounter)-[r:DOCUMENTS]->()
WHERE r.evidence_sentence IS NOT NULL
RETURN toString(max(r.coded_at)) AS last_updated
"""

_GOLD_SOURCES = {"reviewer_correction", "approved", "gold"}
_SILVER_SOURCES = {"provisional", "terminology_api", "llm_auto_detected"}
_SAFETY_TAGS = {"cancer", "oncology", "safeguarding", "mental_health", "suicide"}
_SAFETY_MIN = 20
_IMBALANCE_MIN = 50
_GOLD_MINIMUM = 5000


@router.get("/corpus/stats")
def get_corpus_stats(
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Return NER corpus statistics grouped by source, semantic tag and assertion.

    Used by CorpusCard in the Train section to show progress toward the
    5,000 gold label minimum and flag imbalance or safety-critical gaps.
    """
    import json as _json
    from collections import Counter

    client = PatientGraphClient()
    try:
        with client.session() as session:
            rows = [dict(r) for r in session.run(_Q_CORPUS_STATS_BY_SOURCE)]
            neg_row = session.run(_Q_NEGATIVE_SENTENCES).single()
            updated_row = session.run(_Q_CORPUS_LAST_UPDATED).single()
    finally:
        client.close()

    gold_count = 0
    silver_count = 0
    holdout_count = 0
    entity_type_breakdown: Counter = Counter()
    assertion_breakdown: Counter = Counter()
    safety_counts: Counter = Counter()

    for row in rows:
        source = str(row.get("source") or "")
        holdout = bool(row.get("holdout"))
        tag = str(row.get("semantic_tag") or "other").lower()
        cnt = int(row.get("cnt") or 0)

        try:
            ctx = _json.loads(str(row.get("context_json") or "{}"))
            assertion = str(ctx.get("assertion") or "present")
        except Exception:
            assertion = "present"

        entity_type_breakdown[tag] += cnt
        assertion_breakdown[assertion] += cnt

        for kw in _SAFETY_TAGS:
            if kw in tag and assertion in ("present", "historical"):
                safety_counts[tag] += cnt

        if holdout:
            holdout_count += cnt
        elif source in _GOLD_SOURCES:
            gold_count += cnt
        else:
            silver_count += cnt

    negative_sentence_count = int(neg_row["negative_count"]) if neg_row else 0
    last_updated = str(updated_row["last_updated"]) if updated_row else None

    imbalance_warnings: list[str] = [
        f"Low examples for '{tag}': {cnt} (need {_IMBALANCE_MIN})"
        for tag, cnt in entity_type_breakdown.items()
        if cnt < _IMBALANCE_MIN
    ]
    safety_critical_blocked = any(cnt < _SAFETY_MIN for cnt in safety_counts.values())

    return {
        "gold_count": gold_count,
        "silver_count": silver_count,
        "holdout_count": holdout_count,
        "negative_sentence_count": negative_sentence_count,
        "entity_type_breakdown": dict(entity_type_breakdown),
        "assertion_breakdown": dict(assertion_breakdown),
        "imbalance_warnings": imbalance_warnings,
        "safety_critical_blocked": safety_critical_blocked,
        "training_ready": gold_count >= _GOLD_MINIMUM and not safety_critical_blocked,
        "minimum_gold_met": gold_count >= _GOLD_MINIMUM,
        "last_updated": last_updated,
    }


# ── Source node sample preview ──────────────────────────────────────────────


# Allowlist of source-configurator node labels the sample-node endpoint will
# query. node_label flows directly into a Cypher MATCH clause, so we MUST
# refuse anything that is not a known training-pipeline label. The list is
# kept narrow on purpose -- training authors only need a handful of source
# labels to design new pathways.
_SAMPLE_NODE_LABEL_ALLOWLIST = frozenset(
    {
        "Encounter",
        "EncounterCandidate",
        "Patient",
        "Document",
        "Observation",
        "Condition",
        "MedicationRequest",
        "MedicationStatement",
        "Procedure",
        "DiagnosticReport",
        "AllergyIntolerance",
        "Immunization",
        "Concept",
        "ConceptDescription",
        "ValueSetMember",
        "GuidelineRule",
    }
)
_SAMPLE_NODE_GRAPH_ALLOWLIST = frozenset({"patient", "knowledge"})


@router.get("/schema/sample-node")
def get_sample_node(
    node_label: str = Query(
        ..., description="Node label to sample (e.g. EncounterCandidate)"
    ),
    graph: str = Query(
        "patient", description="Which graph to query: 'patient' or 'knowledge'"
    ),
    text_property: str = Query(
        "text", description="Property to highlight as the main text field"
    ),
    scope: CallerScope = Depends(require_admin),
):
    """Return one sample node so users can verify field names in the source configurator.

    Admin-only: the source configurator inspects raw graph nodes and is
    only used by training authors who already have admin scope. Restricting
    here removes a Cypher-injection style surface from non-admin sessions.

    Sanitises the result: sensitive fields are redacted, long text is truncated to
    300 characters, and Neo4j datetime objects are converted to ISO strings.
    The selected text_property is surfaced first in the response.
    """
    _ = scope
    if graph not in _SAMPLE_NODE_GRAPH_ALLOWLIST:
        raise HTTPException(
            status_code=400,
            detail="graph must be 'patient' or 'knowledge'",
        )
    if node_label not in _SAMPLE_NODE_LABEL_ALLOWLIST:
        raise HTTPException(
            status_code=400,
            detail="Unsupported node_label",
        )

    _REDACT = {
        "nhs_number",
        "date_of_birth",
        "dob",
        "birthdate",
        "birthDate",
        "postcode",
    }
    _MAX_TEXT = 300

    try:
        client: Any = (
            KnowledgeGraphClient() if graph == "knowledge" else PatientGraphClient()
        )
        try:
            with client.session() as session:
                rows = list(
                    session.run(
                        f"MATCH (n:{node_label}) RETURN properties(n) AS props LIMIT 1"
                    )
                )
        finally:
            client.close()

        if not rows:
            from fastapi.responses import JSONResponse as _JSONResponse

            return _JSONResponse(
                status_code=404,
                content={
                    "detail": f"No {node_label} nodes found in the {graph} graph."
                },
            )

        raw: dict = dict(rows[0]["props"])

        def _sanitise(k: str, v: Any) -> Any:
            if k.lower() in _REDACT:
                return "***redacted***"
            if isinstance(v, str) and len(v) > _MAX_TEXT:
                return v[:_MAX_TEXT] + "..."
            if hasattr(v, "iso_format"):
                return v.iso_format()
            return v

        preview = {k: _sanitise(k, v) for k, v in raw.items()}
        ordered: dict = {}
        if text_property in preview:
            ordered[text_property] = preview.pop(text_property)
        ordered.update(preview)

        return {
            "nodeLabel": node_label,
            "graph": graph,
            "textProperty": text_property,
            "properties": ordered,
        }

    except HTTPException:
        raise
    except Exception as exc:
        from fastapi.responses import JSONResponse as _JSONResponse

        logger.warning("sample-node error for %s/%s: %s", graph, node_label, exc)
        return _JSONResponse(
            status_code=500,
            content={"detail": "sample-node lookup failed"},
        )
