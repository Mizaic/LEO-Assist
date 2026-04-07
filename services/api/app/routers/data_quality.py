"""Data Quality API router -- /admin/dq/*

All endpoints require platform admin access (require_admin).
Read-only endpoints use GET; mutation endpoints use POST with dry_run=True default.

DI-LEO-AI-089 / DO-LEO-AI-087 / VT-LEO-AI-089
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.deps import require_admin
from libs.auth.org_scope import CallerScope

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/dq", tags=["data-quality"])


# ---------------------------------------------------------------------------
# Request bodies for mutation endpoints
# ---------------------------------------------------------------------------

class DeletePatientBody(BaseModel):
    patient_id: str
    dry_run: bool = True


class DeleteEpisodesBody(BaseModel):
    status: Optional[str] = None
    site: Optional[str] = None
    dry_run: bool = True


class FixAssertionsBody(BaseModel):
    encounter_id: str
    old_assertion: str
    new_assertion: str
    dry_run: bool = True


class ResolveBatchBody(BaseModel):
    terms: list[str]


class PinVerifyBody(BaseModel):
    pins: list[dict[str, str]]  # [{phrase, concept_id}]


# ---------------------------------------------------------------------------
# Client helpers (lazy, per-request)
# ---------------------------------------------------------------------------

def _patient_client() -> Any:
    from libs.dq._clients import get_patient_client
    return get_patient_client()


def _kg_client() -> Any:
    from libs.dq._clients import get_kg_client
    return get_kg_client()


def _term_client() -> Any:
    from libs.dq._clients import get_term_client
    return get_term_client()


def _audit_db_path() -> str:
    return os.environ.get(
        "DQ_AUDIT_DB_PATH",
        "scripts/investigations/encounter_audit/encounter_audit.db",
    )


# ---------------------------------------------------------------------------
# Patient endpoints
# ---------------------------------------------------------------------------

@router.get("/patient/{patient_id}")
def get_patient(
    patient_id: str,
    since: Optional[str] = Query(None),
    until: Optional[str] = Query(None),
    with_text: bool = Query(False),
    _: CallerScope = Depends(require_admin),
) -> dict:
    from libs.dq.patient import get_patient_summary

    client = _patient_client()
    try:
        result = get_patient_summary(
            patient_id, client, since=since, until=until, with_text=with_text
        )
        return result.model_dump()
    finally:
        client.close()


@router.get("/patient/{patient_id}/encounters")
def get_patient_encounters(
    patient_id: str,
    since: Optional[str] = Query(None),
    until: Optional[str] = Query(None),
    with_text: bool = Query(False),
    limit: int = Query(200),
    _: CallerScope = Depends(require_admin),
) -> dict:
    from libs.dq.patient import get_patient_summary

    client = _patient_client()
    try:
        result = get_patient_summary(
            patient_id, client, since=since, until=until,
            with_text=with_text, limit=limit,
        )
        return {"encounters": [e.model_dump() for e in result.encounters]}
    finally:
        client.close()


@router.get("/patient/schema-audit")
def get_schema_audit(
    sample_size: int = Query(200),
    _: CallerScope = Depends(require_admin),
) -> dict:
    from libs.dq.patient import get_schema_audit

    client = _patient_client()
    try:
        return get_schema_audit(client, sample_size=sample_size)
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Episode endpoints
# ---------------------------------------------------------------------------

@router.get("/episodes/health")
def get_episode_health(
    _: CallerScope = Depends(require_admin),
) -> dict:
    from libs.dq.episodes import get_episode_health

    client = _patient_client()
    try:
        return get_episode_health(client).model_dump()
    finally:
        client.close()


@router.get("/episodes/stale")
def get_stale_episodes(
    site: Optional[str] = Query(None),
    threshold_days: int = Query(90),
    limit: int = Query(500),
    _: CallerScope = Depends(require_admin),
) -> dict:
    from libs.dq._filters import DQFilters
    from libs.dq.episodes import get_stale_episodes

    client = _patient_client()
    try:
        rows = get_stale_episodes(
            client,
            DQFilters(site=site, limit=limit),
            threshold_days=threshold_days,
        )
        return {"episodes": [r.model_dump() for r in rows]}
    finally:
        client.close()


@router.get("/episodes/completeness")
def get_episode_completeness(
    site: Optional[str] = Query(None),
    limit: int = Query(500),
    _: CallerScope = Depends(require_admin),
) -> dict:
    from libs.dq._filters import DQFilters
    from libs.dq.episodes import get_completeness

    client = _patient_client()
    try:
        rows = get_completeness(client, DQFilters(site=site, limit=limit))
        return {"episodes": [r.model_dump() for r in rows]}
    finally:
        client.close()


@router.get("/episodes/infer-outcome")
def infer_episode_outcomes(
    patient_id: Optional[str] = Query(None),
    site: Optional[str] = Query(None),
    threshold_days: int = Query(180),
    limit: int = Query(100),
    _: CallerScope = Depends(require_admin),
) -> dict:
    from libs.dq._filters import DQFilters
    from libs.dq.episodes import get_stale_episodes, infer_outcome

    client = _patient_client()
    try:
        stale = get_stale_episodes(
            client, DQFilters(patient_id=patient_id, site=site, limit=limit)
        )
        results = []
        for ep in stale:
            if not ep.referral_date:
                continue
            result = infer_outcome(
                patient_id=ep.patient_id,
                episode_id=ep.episode_id,
                site=ep.site,
                referral_date=ep.referral_date,
                specialist_date=ep.specialist_date,
                client=client,
                window_days=threshold_days,
            )
            results.append(result.model_dump())
        return {"results": results, "total": len(results)}
    finally:
        client.close()


@router.get("/episodes/{patient_id}/audit")
def get_episode_audit(
    patient_id: str,
    _: CallerScope = Depends(require_admin),
) -> dict:
    from libs.dq.patient import get_patient_summary

    client = _patient_client()
    try:
        summary = get_patient_summary(patient_id, client, with_text=True)
        return summary.model_dump()
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Terminology endpoints
# ---------------------------------------------------------------------------

@router.get("/terminology/sf/audit")
def get_sf_audit(
    limit: int = Query(5000),
    _: CallerScope = Depends(require_admin),
) -> dict:
    from libs.dq.terminology import get_surface_form_audit

    client = _kg_client()
    try:
        return get_surface_form_audit(client, limit=limit).model_dump()
    finally:
        client.close()


@router.get("/terminology/sf/duplicates")
def get_sf_duplicates(
    _: CallerScope = Depends(require_admin),
) -> dict:
    from libs.dq.terminology import get_surface_form_audit

    client = _kg_client()
    try:
        audit = get_surface_form_audit(client)
        dups = [f for f in audit.anomalous_forms if len(f.maps_to) > 1]
        return {"duplicates": [d.model_dump() for d in dups]}
    finally:
        client.close()


@router.get("/terminology/sf/{normalized_term}")
def inspect_sf(
    normalized_term: str,
    _: CallerScope = Depends(require_admin),
) -> dict:
    from libs.dq.terminology import inspect_surface_form

    client = _kg_client()
    try:
        result = inspect_surface_form(normalized_term, client)
        if not result:
            raise HTTPException(status_code=404, detail="Surface form not found")
        return result.model_dump()
    finally:
        client.close()


@router.post("/terminology/sf/resolve-test")
def resolve_test(
    body: ResolveBatchBody,
    _: CallerScope = Depends(require_admin),
) -> dict:
    from libs.dq.terminology import batch_resolve_test

    term_client = _term_client()
    results = batch_resolve_test(body.terms, term_client)
    return {"results": [r.model_dump() for r in results]}


@router.post("/terminology/sf/pin-verify")
def pin_verify(
    body: PinVerifyBody,
    _: CallerScope = Depends(require_admin),
) -> dict:
    from libs.dq.terminology import batch_pin_verify

    kg = _kg_client()
    term = _term_client()
    try:
        results = batch_pin_verify(body.pins, kg, term)
        return {"results": [r.model_dump() for r in results]}
    finally:
        kg.close()


@router.get("/terminology/concept/{concept_id}")
def get_concept(
    concept_id: str,
    _: CallerScope = Depends(require_admin),
) -> dict:
    from libs.dq.terminology import get_concept_status

    client = _kg_client()
    try:
        results = get_concept_status([concept_id], client)
        if not results:
            raise HTTPException(status_code=404, detail="Concept not found")
        return results[0].model_dump()
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Coding quality endpoints
# ---------------------------------------------------------------------------

@router.get("/coding/summary")
def get_coding_summary(
    db_path: Optional[str] = Query(None),
    _: CallerScope = Depends(require_admin),
) -> dict:
    from libs.dq.coding import get_coding_summary

    try:
        return get_coding_summary(db_path or _audit_db_path()).model_dump()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/coding/issues")
def get_coding_issues(
    severity: Optional[str] = Query(None),
    limit: int = Query(100),
    db_path: Optional[str] = Query(None),
    _: CallerScope = Depends(require_admin),
) -> dict:
    from libs.dq.coding import get_coding_issues

    try:
        rows = get_coding_issues(
            db_path or _audit_db_path(), severity=severity, limit=limit
        )
        return {"issues": [r.model_dump() for r in rows]}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/coding/progress")
def get_coding_progress(
    db_path: Optional[str] = Query(None),
    _: CallerScope = Depends(require_admin),
) -> dict:
    from libs.dq.coding import get_coding_progress

    try:
        return get_coding_progress(db_path or _audit_db_path())
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Domain coverage endpoints
# ---------------------------------------------------------------------------

@router.get("/domain/coverage")
def get_domain_coverage(
    domain_id: str = Query("ncda-cancer-types"),
    _: CallerScope = Depends(require_admin),
) -> dict:
    from libs.dq.domain import get_domain_coverage

    patient_client = _patient_client()
    kg = _kg_client()
    try:
        result = get_domain_coverage(domain_id, patient_client, kg)
        return result.model_dump()
    finally:
        patient_client.close()
        kg.close()


@router.get("/domain/orphans")
def get_domain_orphans(
    limit: int = Query(500),
    _: CallerScope = Depends(require_admin),
) -> dict:
    from libs.dq.domain import get_orphan_concepts

    client = _patient_client()
    try:
        rows = get_orphan_concepts(client, limit=limit)
        return {"orphans": [r.model_dump() for r in rows]}
    finally:
        client.close()


@router.get("/domain/gaps")
def get_domain_gaps(
    site: Optional[str] = Query(None),
    limit: int = Query(500),
    _: CallerScope = Depends(require_admin),
) -> dict:
    from libs.dq._filters import DQFilters
    from libs.dq.domain import get_pathway_gaps

    client = _patient_client()
    try:
        rows = get_pathway_gaps(client, DQFilters(site=site, limit=limit))
        return {"gaps": [r.model_dump() for r in rows]}
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

@router.get("/sitrep")
def get_sitrep(_: CallerScope = Depends(require_admin)) -> dict:
    from libs.dq.reports import get_sitrep

    client = _patient_client()
    try:
        return get_sitrep(client).model_dump()
    finally:
        client.close()


@router.get("/cohort")
def get_cohort(
    status: Optional[str] = Query(None),
    site: Optional[str] = Query(None),
    since: Optional[str] = Query(None),
    until: Optional[str] = Query(None),
    limit: int = Query(500),
    _: CallerScope = Depends(require_admin),
) -> dict:
    from libs.dq._filters import DQFilters
    from libs.dq.reports import get_cohort

    client = _patient_client()
    try:
        result = get_cohort(
            client,
            DQFilters(status=status, site=site, since=since, until=until, limit=limit),
        )
        return result.model_dump()
    finally:
        client.close()


@router.get("/rules/run")
def run_dq_rules(_: CallerScope = Depends(require_admin)) -> dict:
    from libs.dq.rules_engine import run_all_rules, scorecard_summary

    client = _patient_client()
    try:
        results = run_all_rules(client)
        return {
            "results": [r.model_dump() for r in results],
            "summary": scorecard_summary(results),
        }
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Remediation endpoints (mutations -- dry_run=True default)
# ---------------------------------------------------------------------------

@router.post("/remediation/delete-patient")
def remediation_delete_patient(
    body: DeletePatientBody,
    _: CallerScope = Depends(require_admin),
) -> dict:
    from libs.dq.remediation import delete_patient

    client = _patient_client()
    try:
        return delete_patient(
            body.patient_id, client, dry_run=body.dry_run
        ).model_dump()
    finally:
        client.close()


@router.post("/remediation/delete-episodes")
def remediation_delete_episodes(
    body: DeleteEpisodesBody,
    _: CallerScope = Depends(require_admin),
) -> dict:
    from libs.dq.remediation import delete_episodes

    client = _patient_client()
    try:
        return delete_episodes(
            client, status=body.status, site=body.site, dry_run=body.dry_run
        ).model_dump()
    finally:
        client.close()


@router.post("/remediation/fix-assertions")
def remediation_fix_assertions(
    body: FixAssertionsBody,
    _: CallerScope = Depends(require_admin),
) -> dict:
    from libs.dq.remediation import fix_assertions

    client = _patient_client()
    try:
        return fix_assertions(
            body.encounter_id,
            body.old_assertion,
            body.new_assertion,
            client,
            dry_run=body.dry_run,
        ).model_dump()
    finally:
        client.close()
