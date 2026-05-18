"""Extraction Scenarios API -- list, detail, approve, and validation runs.

Routes
------
GET  /extraction-scenarios                    List scenarios with optional filters
GET  /extraction-scenarios/:case_id           Full case detail including markdown_body
PATCH /extraction-scenarios/:case_id          Approve a scenario (sets review_status)
POST /extraction-scenarios/runs               Trigger background phrase-level F1 run
GET  /extraction-scenarios/runs/:run_id       Poll run progress / results

Atlas trace:
  DI: DI-1B3B5375, DI-B492CAFD
  DO: DO-416BA91D
  Risk: R-80E8BD96
  VT: VT-24D7A846
  VAL-87173594  phrase-level F1 validation
  VT-29880CC8   extraction scenario verification
"""

from __future__ import annotations

import json
import logging
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
    """Inner scorer -- separated from exception wrapper to keep depth <= 3."""
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

    per_case: list[dict[str, Any]] = []
    for idx, case in enumerate(cases):
        score = _score_case_from_node(case)
        per_case.append(score)
        _set_run(run_id, {"progress": int((idx + 1) / total * 100)})

    _finalise_run(run_id, per_case, total, cases, triggered_at)


def _score_case_from_node(case: dict[str, Any]) -> dict[str, Any]:
    """Score a single case node (no live extraction -- scores 0 until wired to LLM)."""
    from tests.helpers.clinical_extraction_scenario_loader import score_case

    rules = {
        "casefold": True,
        "trim": True,
        "collapse_whitespace": True,
        "strip_terminal_punctuation": True,
    }
    return score_case(case, [], rules)


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
    logger.info(
        "[ExtractionRun:%s] Completed. F1=%.3f passed=%s", run_id, f1, passed
    )
