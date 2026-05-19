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
  VT: VT-24D7A846, VT-C0D7D50C
  VAL-87173594  phrase-level F1 validation
  VT-29880CC8   extraction scenario verification
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
_VALUE_UNIT_TAIL_RE = re.compile(
    r"""
    \s*[:=-]?\s*
    [<>]?\d+(?:\.\d+)?\s*
    (?:
      x10\^?\d+/?l|
      mmol/?l|
      umol/?l|
      g/?l|
      mg/?l|
      ng/?ml|
      iu/?l|
      u/?l|
      ml/?min(?:/1\.73m2)?|
      f(?:l|L)|
      pg|
      %
    )
    (?:\s*\([^)]*\))?
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)
_COMMON_LAB_ALIASES = {
    "haemoglobin": "hb",
    "hemoglobin": "hb",
    "white blood cell count": "wcc",
    "platelet count": "plts",
    "mean corpuscular volume": "mcv",
    "sodium": "na",
    "potassium": "k",
    "creatinine": "creat",
    "alanine aminotransferase": "alt",
    "alkaline phosphatase": "alk phos",
    "bilirubin": "bili",
    "albumin": "alb",
    "c reactive protein": "crp",
    "erythrocyte sedimentation rate": "esr",
    "hba1c": "hba1c",
    "ferritin": "ferritin",
    "calcium": "ca",
}


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class ApproveRequest(BaseModel):
    review_status: str = "approved"


class RunRequest(BaseModel):
    scope: str = "all"  # "approved_only" | "all"


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
        _normalise_alias_key(key): val for key, val in _COMMON_LAB_ALIASES.items()
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
    if re.fullmatch(r"[<>]?\d+(?:\.\d+)?(?:\s*[%/\-\^0-9a-z]+)?", lowered):
        return ""
    stripped = _VALUE_UNIT_TAIL_RE.sub("", candidate).strip().strip(".,;:()[]{}")
    if stripped:
        candidate = stripped
    alias = alias_map.get(_normalise_alias_key(candidate))
    if alias:
        return alias
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
    """Poll run progress. Falls back to Neo4j if not in memory."""
    with _runs_lock:
        job = _runs.get(run_id)
    if job:
        if job.get("status") == "running" and job.get("production_path"):
            _refresh_production_run(run_id, job)
            with _runs_lock:
                job = _runs.get(run_id, job)
        return job

    # Completed runs may have been evicted from memory; read from Neo4j.
    from libs.cypher.extraction_scenario_queries import GET_VALIDATION_RUN

    client = _coding_client()
    try:
        rows = client.run(GET_VALIDATION_RUN, run_id=run_id)
    finally:
        client.close()

    if not rows:
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")

    row = dict(rows[0])
    row["per_case_results"] = _json_loads_safe(row.get("per_case_results"))
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

    thread = threading.Thread(
        target=_execute_run,
        args=(run_id, body.scope, triggered_at),
        daemon=True,
    )
    thread.start()

    return {"run_id": run_id, "status": "queued"}


# ---------------------------------------------------------------------------
# Background run worker
# ---------------------------------------------------------------------------


def _execute_run(run_id: str, scope: str, triggered_at: str) -> None:
    """Score all (or approved-only) scenarios and persist results to Neo4j."""
    _set_run(run_id, {"status": "running", "progress": 0})
    try:
        _run_scoring(run_id, scope, triggered_at)
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


def _run_scoring(run_id: str, scope: str, triggered_at: str) -> None:
    """Publish scenario validation jobs to the production pipeline queue."""
    from libs.cypher.extraction_scenario_queries import (
        CREATE_VALIDATION_RUN,
        LIST_EXTRACTION_SCENARIOS,
    )

    client = _coding_client()
    try:
        status_filter = "approved" if scope == "approved_only" else None
        rows = client.run(
            LIST_EXTRACTION_SCENARIOS,
            status=status_filter,
            site=None,
            search=None,
        )
        client.run(
            CREATE_VALIDATION_RUN,
            run_id=run_id,
            triggered_by="ui",
            status="running",
            pass_threshold=_PASS_THRESHOLD,
            model_version="n/a",
            triggered_at=triggered_at,
        )
    finally:
        client.close()

    cases = [_normalise_row(dict(r)) for r in rows]
    total = len(cases)
    if total == 0:
        _finalise_run(run_id, [], 0, 0, 0, triggered_at)
        return

    child_runs = _publish_production_validation_jobs(run_id, cases)
    _set_run(
        run_id,
        {
            "status": "running",
            "progress": 0,
            "production_path": True,
            "plan_definition_id": _PRODUCTION_PLAN_ID,
            "model_version": "production-config",
            "case_count": total,
            "cases": cases,
            "child_runs": child_runs,
        },
    )


def _score_case_from_node(case: dict[str, Any]) -> dict[str, Any]:
    """Score a case by running the UN-89E2AE36 extraction workflow."""
    from tests.helpers.clinical_extraction_scenario_loader import score_case

    rules = {
        "casefold": True,
        "trim": True,
        "collapse_whitespace": True,
        "strip_terminal_punctuation": True,
    }
    extracted_strings = _extract_terms_for_validation(case)
    return score_case(case, extracted_strings, rules)


def _score_case_from_terms(case: dict[str, Any], extracted_strings: list[str]) -> dict:
    from tests.helpers.clinical_extraction_scenario_loader import score_case

    cleaned_terms = _normalise_validation_terms(extracted_strings, case)
    return score_case(
        case,
        cleaned_terms,
        {
            "casefold": True,
            "trim": True,
            "collapse_whitespace": True,
            "strip_terminal_punctuation": True,
        },
    )


def _publish_production_validation_jobs(
    run_id: str,
    cases: list[dict[str, Any]],
) -> dict[str, str]:
    import asyncio

    return asyncio.run(_publish_production_validation_jobs_async(run_id, cases))


async def _publish_production_validation_jobs_async(
    run_id: str,
    cases: list[dict[str, Any]],
) -> dict[str, str]:
    from libs.message_bus.base import Message
    from libs.message_bus.factory import create_message_bus

    bus = create_message_bus()
    child_runs: dict[str, str] = {}
    try:
        for case in cases:
            case_id = str(case.get("case_id") or "")
            child_run_id = f"{run_id}:{case_id}"
            child_runs[case_id] = child_run_id
            await bus.send(
                _PIPELINE_QUEUE,
                Message(
                    body={
                        "event_type": "validation-run-requested",
                        "patient_id": f"validation-{case_id}",
                        "encounter_id": case_id,
                        "run_id": child_run_id,
                        "plan_definition_id": _PRODUCTION_PLAN_ID,
                        "context": {
                            "case_id": case_id,
                            "source_node_type": "ExtractionScenario",
                            "source_node_id": case_id,
                            "source_text_property": "markdown_body",
                            "dry_run": True,
                            "capture_validation_output": True,
                            "validation_parent_run_id": run_id,
                            "validation_un_id": "UN-89E2AE36",
                            "validation_val_id": "VAL-87173594",
                        },
                    },
                    correlation_id=child_run_id,
                    subject="validation-run-requested",
                ),
            )
    finally:
        await bus.close()
    return child_runs


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


def _extract_terms_for_validation(case: dict[str, Any]) -> list[str]:
    from app.services.validation_workflow_runner import execute_validation_workflow_sync

    text = str(case.get("markdown_body") or case.get("source_text") or "")
    result = execute_validation_workflow_sync(
        un_id="UN-89E2AE36",
        initial_state={
            "case_id": case.get("case_id"),
            "encounter_text": text,
            "source_text": text,
        },
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
