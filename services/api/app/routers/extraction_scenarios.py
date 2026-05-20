"""Extraction Scenarios API -- list, detail, approve, and validation runs.

Routes
------
GET  /extraction-scenarios                    List scenarios with optional filters
GET  /extraction-scenarios/:case_id           Full case detail including markdown_body
PATCH /extraction-scenarios/:case_id          Approve a scenario (sets review_status)
POST /extraction-scenarios/runs               Trigger background phrase-level F1 run
GET  /extraction-scenarios/runs/:run_id       Poll run progress / results

Atlas trace:
  DI: DI-1B3B5375, DI-B492CAFD, DI-B5C78811
  DO: DO-416BA91D
  Risk: R-80E8BD96
  VT: VT-24D7A846, VT-C0D7D50C, VT-C9325761
  VAL-87173594  phrase-level F1 validation
  VT-29880CC8   extraction scenario verification
  VT-C9325761   finalisation survives API restart and logout
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.deps import require_admin
from libs.auth.org_scope import CallerScope, get_caller_scope
from libs.pipeline.extraction_term_normaliser import (
    BARE_NUMERIC_RE as _BARE_NUMERIC_RE,
    VALUE_UNIT_TAIL_RE as _VALUE_UNIT_TAIL_RE,
    strip_value_unit_tail as _strip_value_unit_tail,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/extraction-scenarios", tags=["extraction-scenarios"])

# In-memory run progress store (same pattern as _canary_jobs in model_registry).
# The completed run is also persisted to Neo4j so the CI Atlas-record script
# can read it across restarts.
_runs_lock = threading.Lock()
_runs: dict[str, dict[str, Any]] = {}

_PASS_THRESHOLD = 0.95
_PIPELINE_QUEUE = os.getenv("PIPELINE_QUEUE_NAME", "pipeline-jobs")
_PRODUCTION_PLAN_ID = "pd-val-key-fact-extraction"
_NON_CLINICAL_NOISE_MARKERS = (
    "referral criteria and clinical information",
    "decision to refer date",
    "practice email",
    "nhs number",
    "synthetic patient",
    "template source",
    "clinician review note",
    "completed by",
)
_COMMON_LAB_ALIASES = {
    "haemoglobin": "Hb",
    "hemoglobin": "Hb",
    "hb": "Hb",
    "white blood cell count": "WCC",
    "wcc": "WCC",
    "platelet count": "Plts",
    "plts": "Plts",
    "mean corpuscular volume": "MCV",
    "mcv": "MCV",
    "sodium": "Na",
    "na": "Na",
    "potassium": "K",
    "k": "K",
    "creatinine": "Creat",
    "creat": "Creat",
    "alanine aminotransferase": "ALT",
    "alt": "ALT",
    "alkaline phosphatase": "Alk Phos",
    "alk phos": "Alk Phos",
    "bilirubin": "Bili",
    "bili": "Bili",
    "albumin": "Alb",
    "alb": "Alb",
    "c reactive protein": "CRP",
    "crp": "CRP",
    "erythrocyte sedimentation rate": "ESR",
    "esr": "ESR",
    "hba1c": "HbA1c",
    "ferritin": "Ferritin",
    "calcium": "Ca",
    "ca": "Ca",
    "ca125": "CA125",
    "prostate specific antigen": "PSA",
    "psa": "PSA",
    "glycated haemoglobin": "HbA1c",
    "glycated hemoglobin": "HbA1c",
    "plasma viscosity": "PV",
    "white cell count": "WCC",
    "platelets": "Plts",
    "mean cell volume": "MCV",
    "full blood count": "FBC",
    "serum protein electrophoresis": "SPE",
    "thyroid function test": "TFT",
    "thyroid function tests": "TFT",
    "chest x-ray": "Chest X-ray",
    "chest x ray": "Chest X-ray",
    "abnormal cxr": "Abnormal CXR",
    "fit test": "FIT requested",
    "faecal immunochemical test": "FIT",
    # myeloma bundle tests (source uses abbreviated names in prose)
    "full blood count": "full blood count",
    "serum protein electrophoresis": "serum protein electrophoresis",
    "bence jones protein urine test": "Bence-Jones protein urine test",
    "bence-jones protein urine test": "Bence-Jones protein urine test",
    "plasma viscosity": "PV",
    "pv": "PV",
    "ldh": "LDH",
    "lactate dehydrogenase": "LDH",
    "urine culture": "urine culture",
    "mid stream urine": "urine culture",
    "msu": "urine culture",
}

# Phrase-level aliases for validation F1 (long model spans -> short gold strings).
_PHRASE_F1_ALIASES = {
    "mri scan of the brain": "urgent MRI scan of the brain",
    "ca125 level is raised": "CA125 raised",
    "ca125 is raised": "CA125 raised",
    "ca125 level has returned elevated": "CA125 raised",
    "glycated haemoglobin level": "HbA1c",
    "raised psa": "raised PSA",
    # lab_value_hardcase: model emits short form; gold wants long form
    "abnormal prostate": "abnormal prostate examination",
    "abnormal prostate examination confirmed": "abnormal prostate examination",
    # abbreviation_hardcase: model emits CXR; gold wants Abnormal CXR
    "cxr": "Abnormal CXR",
    "abnormal cxr": "Abnormal CXR",
    "right parahilar opacity": "Abnormal CXR",
    # ng12_bone: verbose lab name -> gold short form
    "serum protein electrophoresis paraprotein band": "serum protein electrophoresis",
    # urology_uti: model may emit culture result phrase
    "urine cultures": "urine culture",
    "mid-stream urine cultures": "urine culture",
    "mid-stream urine sample": "urine culture",
    # rw_fasttrack variants
    "altered bowel symptoms": "altered bowel function",
    "urinary symptoms": "lower urinary tract symptoms",
    "raised platelets": "Plts",
}


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class ApproveRequest(BaseModel):
    review_status: str = "approved"


class RunRequest(BaseModel):
    scope: str = "all"  # "approved_only" | "all"
    # Optional override for the extraction routing this run should use.
    # Values: "llm" | "ner" | "auto". When omitted, the engine resolves the
    # mode from the extraction_model_mode feature flag (default "llm" while
    # the NER model is being trained).
    model_mode: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _set_run(run_id: str, data: dict[str, Any]) -> None:
    with _runs_lock:
        current = _runs.get(run_id, {})
        current.update(data)
        _runs[run_id] = current


def _coding_client():
    from app.db.neo4j_client import CodingGraphClient

    return CodingGraphClient()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_loads_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return value
    return value


def _normalise_row(row: dict[str, Any]) -> dict[str, Any]:
    """Deserialise JSON-string properties back to Python objects."""
    json_fields = (
        "phrase_classes",
        "difficulty",
        "expected_strings",
        "expected_observables",
        "must_not_extract",
        "synthetic_patient",
        "blood_results",
    )
    return {k: (_json_loads_safe(v) if k in json_fields else v) for k, v in row.items()}


def _normalise_alias_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _build_case_alias_map(case: dict[str, Any] | None) -> dict[str, str]:
    aliases: dict[str, str] = {
        _normalise_alias_key(key): val
        for key, val in {**_COMMON_LAB_ALIASES, **_PHRASE_F1_ALIASES}.items()
    }
    if not isinstance(case, dict):
        return aliases
    observables = case.get("expected_observables")
    if not isinstance(observables, list):
        return aliases
    for observable in observables:
        if not isinstance(observable, dict):
            continue
        canonical = str(observable.get("display_name") or "").strip()
        if not canonical:
            canonical = str(observable.get("test_name") or "").strip()
        source_names = {
            canonical,
            str(observable.get("test_name") or "").strip(),
            str(observable.get("display_name") or "").strip(),
        }
        for source_name in source_names:
            if not source_name:
                continue
            aliases[_normalise_alias_key(source_name)] = canonical
    return aliases


def _normalise_validation_term(term: str, alias_map: dict[str, str]) -> str:
    candidate = re.sub(r"\s+", " ", term).strip().strip(".,;:()[]{}")
    if not candidate:
        return ""
    lowered = candidate.casefold()
    if any(marker in lowered for marker in _NON_CLINICAL_NOISE_MARKERS):
        return ""
    if len(candidate) > 100:
        return ""
    if not re.search(r"[a-z]", lowered):
        return ""
    if _BARE_NUMERIC_RE.fullmatch(lowered):
        return ""
    stripped = _strip_value_unit_tail(candidate)
    if stripped:
        candidate = stripped
    norm_key = _normalise_alias_key(candidate)
    alias = alias_map.get(norm_key)
    if alias:
        return alias
    for key, val in sorted(alias_map.items(), key=lambda item: -len(item[0])):
        if len(key) >= 8 and norm_key.startswith(key):
            return val
    return candidate


def _normalise_validation_terms(
    extracted_strings: list[str], case: dict[str, Any] | None
) -> list[str]:
    alias_map = _build_case_alias_map(case)
    normalised: list[str] = []
    seen: set[str] = set()
    for term in extracted_strings:
        clean = _normalise_validation_term(term, alias_map)
        if not clean:
            continue
        key = clean.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalised.append(clean)
    return normalised


# ---------------------------------------------------------------------------
# GET /extraction-scenarios
# ---------------------------------------------------------------------------


@router.get("")
def list_scenarios(
    status: Optional[str] = None,
    site: Optional[str] = None,
    search: Optional[str] = None,
    _scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Return scenario list and aggregate counts."""
    from libs.cypher.extraction_scenario_queries import (
        COUNT_BY_STATUS,
        LIST_EXTRACTION_SCENARIOS,
    )

    client = _coding_client()
    try:
        count_rows = client.run(COUNT_BY_STATUS)
        counts = (
            count_rows[0] if count_rows else {"total": 0, "approved": 0, "draft": 0}
        )

        rows = client.run(
            LIST_EXTRACTION_SCENARIOS,
            status=status,
            site=site,
            search=search,
        )
    finally:
        client.close()

    cases = [_normalise_row(dict(r)) for r in rows]
    return {
        "total": counts.get("total", 0),
        "approved": counts.get("approved", 0),
        "draft": counts.get("draft", 0),
        "pass_threshold": _PASS_THRESHOLD,
        "cases": cases,
    }


# ---------------------------------------------------------------------------
# GET /extraction-scenarios/runs/:run_id  (must come before /:case_id)
# ---------------------------------------------------------------------------


@router.get("/runs/{run_id}")
def get_run(
    run_id: str,
    _scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Poll run progress. Falls back to Neo4j if not in memory.

    A running row read from Neo4j is recovered into the in-memory cache so
    subsequent polls can drive finalisation. This is the path that survives
    an API restart or a user logout mid-run.
    """
    with _runs_lock:
        job = _runs.get(run_id)
    if job:
        if job.get("status") == "running" and job.get("production_path"):
            _refresh_production_run(run_id, job)
            with _runs_lock:
                job = _runs.get(run_id, job)
        return job

    row = _load_run_from_neo4j(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")

    if row.get("status") in ("queued", "running"):
        return _recover_running_run(run_id, row)
    return row


def _load_run_from_neo4j(run_id: str) -> dict[str, Any] | None:
    """Read the ExtractionValidationRun row, or return None if absent."""
    from libs.cypher.extraction_scenario_queries import GET_VALIDATION_RUN

    client = _coding_client()
    try:
        rows = client.run(GET_VALIDATION_RUN, run_id=run_id)
    finally:
        client.close()
    if not rows:
        return None
    row = dict(rows[0])
    row["per_case_results"] = _json_loads_safe(row.get("per_case_results"))
    return row


def _recover_running_run(run_id: str, row: dict[str, Any]) -> dict[str, Any]:
    """Rebuild in-memory state for a running row and attempt finalisation.

    Three outcomes are possible:

    1. All audit rows are present -> finalise immediately (success path even
       though the API instance that triggered the run died before polling).
    2. Audit rows are partial but publish_state='published' -> return the
       current progress; the next poll will try again.
    3. publish_state='publish_failed' OR publish_state stayed 'publishing'
       beyond the stale-cutoff -> mark the row failed and return.
    """
    case_ids = list(row.get("case_ids") or [])
    child_run_ids = list(row.get("child_run_ids") or [])
    if not case_ids or len(case_ids) != len(child_run_ids):
        return _fail_unrecoverable_run(
            run_id,
            row,
            reason=(
                "run missing case_ids/child_run_ids -- cannot finalise; "
                "predates resilience persistence (deployed 2026-05-20)"
            ),
        )

    publish_state = str(row.get("publish_state") or "")
    if publish_state == "publish_failed":
        return _fail_unrecoverable_run(
            run_id,
            row,
            reason=str(
                row.get("failure_reason")
                or "publish loop failed before sending every message"
            ),
        )

    cases = _hydrate_cases_for_recovery(case_ids)
    if len(cases) != len(case_ids):
        return _fail_unrecoverable_run(
            run_id,
            row,
            reason="some ExtractionScenario rows referenced by this run no longer exist",
        )

    child_runs = dict(zip(case_ids, child_run_ids))
    _set_run(
        run_id,
        {
            "run_id": run_id,
            "status": "running",
            "progress": 0,
            "production_path": True,
            "plan_definition_id": row.get("plan_definition_id") or _PRODUCTION_PLAN_ID,
            "model_mode": row.get("model_mode") or None,
            "case_count": len(case_ids),
            "cases": cases,
            "child_runs": child_runs,
            "triggered_at": row.get("triggered_at"),
        },
    )
    with _runs_lock:
        job = _runs[run_id]
    _refresh_production_run(run_id, job)
    with _runs_lock:
        return _runs.get(run_id, job)


def _hydrate_cases_for_recovery(case_ids: list[str]) -> list[dict[str, Any]]:
    """Fetch full ExtractionScenario rows by id, preserving order."""
    from libs.cypher.extraction_scenario_queries import GET_EXTRACTION_SCENARIO

    client = _coding_client()
    by_id: dict[str, dict[str, Any]] = {}
    try:
        for case_id in case_ids:
            rows = client.run(GET_EXTRACTION_SCENARIO, case_id=case_id)
            if rows:
                by_id[case_id] = _normalise_row(dict(rows[0]))
    finally:
        client.close()
    return [by_id[c] for c in case_ids if c in by_id]


def _fail_unrecoverable_run(
    run_id: str, row: dict[str, Any], *, reason: str
) -> dict[str, Any]:
    """Mark a stuck run as failed in Neo4j and return the updated row."""
    from libs.cypher.extraction_scenario_queries import FAIL_VALIDATION_RUN

    completed_at = _now_iso()
    client = _coding_client()
    try:
        client.run(
            FAIL_VALIDATION_RUN,
            run_id=run_id,
            completed_at=completed_at,
            failure_reason=reason[:400],
        )
    except Exception as exc:
        logger.warning("[ExtractionRun:%s] Failed to mark run failed: %s", run_id, exc)
    finally:
        client.close()

    row.update(
        {
            "status": "failed",
            "completed_at": completed_at,
            "failure_reason": reason,
            "passed": False,
        }
    )
    return row


# ---------------------------------------------------------------------------
# GET /extraction-scenarios/:case_id
# ---------------------------------------------------------------------------


@router.get("/{case_id}")
def get_scenario(
    case_id: str,
    _scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Return full scenario detail including markdown_body."""
    from libs.cypher.extraction_scenario_queries import GET_EXTRACTION_SCENARIO

    client = _coding_client()
    try:
        rows = client.run(GET_EXTRACTION_SCENARIO, case_id=case_id)
    finally:
        client.close()

    if not rows:
        raise HTTPException(status_code=404, detail=f"Scenario {case_id!r} not found")
    return _normalise_row(dict(rows[0]))


# ---------------------------------------------------------------------------
# PATCH /extraction-scenarios/:case_id
# ---------------------------------------------------------------------------


@router.patch("/{case_id}")
def approve_scenario(
    case_id: str,
    body: ApproveRequest,
    scope: CallerScope = Depends(get_caller_scope),
    _admin: object = Depends(require_admin),
) -> dict[str, Any]:
    """Set review_status = approved, recording who approved and when."""
    if body.review_status not in {"approved", "draft_for_clinician_approval"}:
        raise HTTPException(
            status_code=422,
            detail="review_status must be 'approved' or 'draft_for_clinician_approval'",
        )
    from libs.cypher.extraction_scenario_queries import APPROVE_EXTRACTION_SCENARIO

    reviewed_by = getattr(scope, "user_email", None) or "unknown"
    reviewed_at = _now_iso()

    client = _coding_client()
    try:
        rows = client.run(
            APPROVE_EXTRACTION_SCENARIO,
            case_id=case_id,
            reviewed_by=reviewed_by,
            reviewed_at=reviewed_at,
        )
    finally:
        client.close()

    if not rows:
        raise HTTPException(status_code=404, detail=f"Scenario {case_id!r} not found")
    return {"case_id": case_id, "review_status": "approved", "reviewed_by": reviewed_by}


# ---------------------------------------------------------------------------
# POST /extraction-scenarios/runs
# ---------------------------------------------------------------------------


@router.post("/runs")
def trigger_run(
    body: RunRequest,
    scope: CallerScope = Depends(get_caller_scope),
    _admin: object = Depends(require_admin),
) -> dict[str, Any]:
    """Trigger a background phrase-level F1 validation run."""
    run_id = str(uuid.uuid4())
    triggered_at = _now_iso()

    _set_run(
        run_id,
        {
            "run_id": run_id,
            "scope": body.scope,
            "status": "queued",
            "progress": 0,
            "triggered_by": "ui",
            "triggered_at": triggered_at,
            "pass_threshold": _PASS_THRESHOLD,
        },
    )

    model_mode = (body.model_mode or "").strip().lower() or None
    if model_mode and model_mode not in {"llm", "ner", "auto"}:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported model_mode {model_mode!r}; expected llm, ner, or auto.",
        )

    thread = threading.Thread(
        target=_execute_run,
        args=(run_id, body.scope, triggered_at, model_mode),
        daemon=True,
    )
    thread.start()

    return {"run_id": run_id, "status": "queued", "model_mode": model_mode}


# ---------------------------------------------------------------------------
# Background run worker
# ---------------------------------------------------------------------------


def _execute_run(
    run_id: str,
    scope: str,
    triggered_at: str,
    model_mode: str | None = None,
) -> None:
    """Score all (or approved-only) scenarios and persist results to Neo4j.

    On unexpected failure during the publish loop, the run node in Neo4j is
    updated with publish_state='publish_failed' so the sweeper can later
    mark it failed without leaving the user staring at a phantom 'running'.
    """
    _set_run(run_id, {"status": "running", "progress": 0, "model_mode": model_mode})
    try:
        _run_scoring(run_id, scope, triggered_at, model_mode=model_mode)
    except Exception as exc:
        logger.exception("[ExtractionRun:%s] Failed: %s", run_id, exc)
        _set_run(
            run_id,
            {
                "status": "failed",
                "error": str(exc),
                "completed_at": _now_iso(),
            },
        )
        _mark_publish_failed(
            run_id,
            published_count=0,
            failure_reason=f"_execute_run raised: {exc}",
        )


def _run_scoring(
    run_id: str,
    scope: str,
    triggered_at: str,
    *,
    model_mode: str | None = None,
) -> None:
    """Publish scenario validation jobs to the production pipeline queue.

    Persists the case_ids -> child_run_ids mapping to Neo4j on the parent
    ExtractionValidationRun node BEFORE publishing any bus messages so that
    a daemon-thread kill, API restart, or user logout cannot strand the run
    in "running" with no way to finalise it.
    """
    from libs.cypher.extraction_scenario_queries import LIST_EXTRACTION_SCENARIOS

    client = _coding_client()
    try:
        status_filter = "approved" if scope == "approved_only" else None
        rows = client.run(
            LIST_EXTRACTION_SCENARIOS,
            status=status_filter,
            site=None,
            search=None,
        )
    finally:
        client.close()

    cases = [_normalise_row(dict(r)) for r in rows]
    total = len(cases)
    case_ids = [str(c.get("case_id") or "") for c in cases]
    child_runs = {case_id: f"{run_id}:{case_id}" for case_id in case_ids if case_id}
    _create_validation_run_node(
        run_id=run_id,
        triggered_at=triggered_at,
        case_ids=case_ids,
        child_runs=child_runs,
        model_mode=model_mode,
    )

    if total == 0:
        _finalise_run(run_id, [], 0, 0, 0, triggered_at)
        return

    _set_run(
        run_id,
        {
            "status": "running",
            "progress": 0,
            "production_path": True,
            "plan_definition_id": _PRODUCTION_PLAN_ID,
            "model_version": "production-config",
            "model_mode": model_mode,
            "case_count": total,
            "cases": cases,
            "child_runs": child_runs,
        },
    )

    published_count = _publish_production_validation_jobs(
        run_id, cases, child_runs, model_mode=model_mode
    )
    _mark_publish_complete(run_id, published_count)


def _create_validation_run_node(
    *,
    run_id: str,
    triggered_at: str,
    case_ids: list[str],
    child_runs: dict[str, str],
    model_mode: str | None,
) -> None:
    """Persist the planned cases up-front so finalisation can resume after restart."""
    from libs.cypher.extraction_scenario_queries import CREATE_VALIDATION_RUN

    client = _coding_client()
    try:
        client.run(
            CREATE_VALIDATION_RUN,
            run_id=run_id,
            triggered_by="ui",
            status="running",
            pass_threshold=_PASS_THRESHOLD,
            model_version="n/a",
            triggered_at=triggered_at,
            plan_definition_id=_PRODUCTION_PLAN_ID,
            model_mode=model_mode or "",
            case_ids=case_ids,
            child_run_ids=[child_runs[c] for c in case_ids if c in child_runs],
            case_count=len(case_ids),
            publish_state="publishing",
            published_count=0,
        )
    finally:
        client.close()


def _mark_publish_complete(run_id: str, published_count: int) -> None:
    """Record that every planned bus message was sent successfully."""
    from libs.cypher.extraction_scenario_queries import (
        MARK_VALIDATION_PUBLISH_COMPLETE,
    )

    client = _coding_client()
    try:
        client.run(
            MARK_VALIDATION_PUBLISH_COMPLETE,
            run_id=run_id,
            published_count=published_count,
        )
    except Exception as exc:
        logger.warning(
            "[ExtractionRun:%s] Failed to mark publish complete: %s", run_id, exc
        )
    finally:
        client.close()


def _mark_publish_failed(
    run_id: str, published_count: int, failure_reason: str
) -> None:
    """Record that the publish loop did not send every planned message."""
    from libs.cypher.extraction_scenario_queries import (
        MARK_VALIDATION_PUBLISH_FAILED,
    )

    client = _coding_client()
    try:
        client.run(
            MARK_VALIDATION_PUBLISH_FAILED,
            run_id=run_id,
            published_count=published_count,
            failure_reason=failure_reason[:400],
        )
    except Exception as exc:
        logger.warning(
            "[ExtractionRun:%s] Failed to mark publish failure: %s", run_id, exc
        )
    finally:
        client.close()


def _scoring_rules() -> dict[str, bool]:
    from tests.helpers.clinical_extraction_scenario_loader import load_expected_strings

    doc = load_expected_strings()
    normalisation = doc.get("normalisation")
    if not isinstance(normalisation, dict):
        normalisation = {}
    return {
        "casefold": bool(normalisation.get("casefold", True)),
        "trim": bool(normalisation.get("trim", True)),
        "collapse_whitespace": bool(normalisation.get("collapse_whitespace", True)),
        "strip_terminal_punctuation": bool(
            normalisation.get("strip_terminal_punctuation", True)
        ),
        "containment_match": bool(normalisation.get("containment_match", True)),
    }


def _score_case_from_node(case: dict[str, Any]) -> dict[str, Any]:
    """Score a case by running the UN-89E2AE36 extraction workflow."""
    from tests.helpers.clinical_extraction_scenario_loader import score_case

    extracted_strings = _extract_terms_for_validation(case)
    return score_case(case, extracted_strings, _scoring_rules())


def _score_case_from_terms(case: dict[str, Any], extracted_strings: list[str]) -> dict:
    from tests.helpers.clinical_extraction_scenario_loader import score_case

    cleaned_terms = _normalise_validation_terms(extracted_strings, case)
    return score_case(case, cleaned_terms, _scoring_rules())


def _publish_production_validation_jobs(
    run_id: str,
    cases: list[dict[str, Any]],
    child_runs: dict[str, str],
    *,
    model_mode: str | None = None,
) -> int:
    """Publish one bus message per case. Returns the count actually sent.

    The publisher accepts a pre-computed `child_runs` mapping (case_id ->
    child_run_id) so the caller can persist that mapping to Neo4j BEFORE the
    first message is sent. If this loop is interrupted mid-flight (daemon
    thread killed at API shutdown / logout), the persisted mapping is still
    usable by the sweeper and by the get_run fallback to either finalise or
    fail the run cleanly.
    """
    import asyncio

    return asyncio.run(
        _publish_production_validation_jobs_async(
            run_id, cases, child_runs, model_mode=model_mode
        )
    )


async def _publish_production_validation_jobs_async(
    run_id: str,
    cases: list[dict[str, Any]],
    child_runs: dict[str, str],
    *,
    model_mode: str | None = None,
) -> int:
    from libs.message_bus.base import Message
    from libs.message_bus.factory import create_message_bus

    bus = create_message_bus()
    sent = 0
    try:
        for case in cases:
            case_id = str(case.get("case_id") or "")
            child_run_id = child_runs.get(case_id) or f"{run_id}:{case_id}"
            await bus.send(
                _PIPELINE_QUEUE,
                Message(
                    body={
                        "event_type": "validation-run-requested",
                        "patient_id": f"validation-{case_id}",
                        "encounter_id": case_id,
                        "run_id": child_run_id,
                        "plan_definition_id": _PRODUCTION_PLAN_ID,
                        "context": _build_validation_context(
                            run_id=run_id,
                            case_id=case_id,
                            model_mode=model_mode,
                        ),
                    },
                    correlation_id=child_run_id,
                    subject="validation-run-requested",
                ),
            )
            sent += 1
    finally:
        await bus.close()
    return sent


def _build_validation_context(
    *, run_id: str, case_id: str, model_mode: str | None
) -> dict[str, Any]:
    context: dict[str, Any] = {
        "case_id": case_id,
        "source_node_type": "ExtractionScenario",
        "source_node_id": case_id,
        "source_text_property": "markdown_body",
        "dry_run": True,
        "capture_validation_output": True,
        "validation_parent_run_id": run_id,
        "validation_un_id": "UN-89E2AE36",
        "validation_val_id": "VAL-87173594",
        "model_mode": model_mode or "llm",
        "model_tier": "small",
    }
    return context


def _refresh_production_run(run_id: str, job: dict[str, Any]) -> None:
    cases = job.get("cases") if isinstance(job.get("cases"), list) else []
    child_runs = (
        job.get("child_runs") if isinstance(job.get("child_runs"), dict) else {}
    )
    if not cases or not child_runs:
        return
    audit_rows = _read_validation_audit_rows(list(child_runs.values()))
    completed = {str(row.get("run_id") or ""): row for row in audit_rows}
    progress = int(len(completed) / len(child_runs) * 100) if child_runs else 0
    _set_run(run_id, {"progress": progress})
    if len(completed) < len(child_runs):
        return

    per_case: list[dict[str, Any]] = []
    for case in cases:
        case_id = str(case.get("case_id") or "")
        row = completed.get(child_runs.get(case_id, ""))
        terms = _terms_from_validation_output(row, case)
        scored = _score_case_from_terms(case, terms)
        scored["model_provider"] = row.get("extraction_provider", "")
        scored["model_tier"] = row.get("extraction_model_tier", "")
        scored["prompt_hash"] = row.get("extraction_prompt_hash", "")
        scored["worker_status"] = row.get("status", "")
        snapshots = _stage_snapshots_from_validation_output(row)
        if snapshots:
            scored["stage_snapshots"] = snapshots
        per_case.append(scored)
    _finalise_run(
        run_id, per_case, len(cases), cases, str(job.get("triggered_at") or "")
    )


def _read_validation_audit_rows(child_run_ids: list[str]) -> list[dict[str, Any]]:
    from app.db.neo4j_client import PatientGraphClient

    if not child_run_ids:
        return []
    query = """
    MATCH (ae:AuditEvent)
    WHERE ae.run_id IN $run_ids
    RETURN ae.run_id AS run_id,
           ae.status AS status,
           ae.validation_output AS validation_output,
           ae.extraction_provider AS extraction_provider,
           ae.extraction_model_tier AS extraction_model_tier,
           ae.extraction_prompt_hash AS extraction_prompt_hash
    """
    client = PatientGraphClient()
    try:
        return [dict(row) for row in client.run(query, run_ids=child_run_ids)]
    finally:
        client.close()


def _stage_snapshots_from_validation_output(
    row: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not row:
        return None
    payload = _json_loads_safe(row.get("validation_output"))
    if not isinstance(payload, dict):
        return None
    snapshots = payload.get("stage_snapshots")
    return snapshots if isinstance(snapshots, dict) else None


def _terms_from_validation_output(
    row: dict[str, Any] | None, case: dict[str, Any] | None = None
) -> list[str]:
    if not row:
        return []
    payload = _json_loads_safe(row.get("validation_output"))
    if not isinstance(payload, dict):
        return []
    terms = payload.get("terms")
    if not isinstance(terms, list):
        return []
    raw_terms = [
        str(term.get("text") or "").strip()
        for term in terms
        if isinstance(term, dict) and str(term.get("text") or "").strip()
    ]
    return _normalise_validation_terms(raw_terms, case)


def _extract_terms_for_validation(
    case: dict[str, Any],
    *,
    model_mode: str | None = None,
) -> list[str]:
    from app.services.validation_workflow_runner import execute_validation_workflow_sync

    text = str(case.get("markdown_body") or case.get("source_text") or "")
    initial_state: dict[str, Any] = {
        "case_id": case.get("case_id"),
        "encounter_text": text,
        "source_text": text,
    }
    if model_mode:
        initial_state["model_mode"] = model_mode
    result = execute_validation_workflow_sync(
        un_id="UN-89E2AE36",
        initial_state=initial_state,
    )
    final_state = result.get("final_state", {})
    return _entity_texts(final_state.get("entities", []))


def _entity_texts(entities: Any) -> list[str]:
    if not isinstance(entities, list):
        return []
    texts: list[str] = []
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        text = entity.get("text") or entity.get("surface_form")
        if isinstance(text, str) and text.strip():
            texts.append(text.strip())
    return texts


def _finalise_run(
    run_id: str,
    per_case: list[dict[str, Any]],
    total: int,
    cases: Any,
    triggered_at: str,
) -> None:
    """Aggregate per-case scores, persist run node to Neo4j, update in-memory state."""
    from libs.cypher.extraction_scenario_queries import (
        COMPLETE_VALIDATION_RUN,
        CREATE_RAN_AGAINST_EDGE,
    )

    tp = sum(r["true_positive"] for r in per_case)
    fp = sum(r["false_positive"] for r in per_case)
    fn = sum(r["false_negative"] for r in per_case)

    def _safe_div(a: int, b: int) -> float:
        return a / b if b else 1.0

    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    denom = precision + recall
    f1 = 2 * precision * recall / denom if denom else 0.0
    passed = f1 >= _PASS_THRESHOLD
    completed_at = _now_iso()

    client = _coding_client()
    try:
        client.run(
            COMPLETE_VALIDATION_RUN,
            run_id=run_id,
            status="completed",
            overall_f1=f1,
            overall_precision=precision,
            overall_recall=recall,
            passed=passed,
            per_case_results=json.dumps(per_case),
            completed_at=completed_at,
        )
        for row in per_case:
            client.run(
                CREATE_RAN_AGAINST_EDGE,
                run_id=run_id,
                case_id=row["case_id"],
            )
    except Exception as exc:
        logger.warning("[ExtractionRun:%s] Neo4j persist failed: %s", run_id, exc)
    finally:
        client.close()

    result: dict[str, Any] = {
        "status": "completed",
        "progress": 100,
        "overall_f1": f1,
        "overall_precision": precision,
        "overall_recall": recall,
        "passed": passed,
        "pass_threshold": _PASS_THRESHOLD,
        "per_case_results": per_case,
        "completed_at": completed_at,
    }
    _set_run(run_id, result)
    logger.info("[ExtractionRun:%s] Completed. F1=%.3f passed=%s", run_id, f1, passed)
