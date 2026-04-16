"""Pathway Explorer research endpoints.

Exposes graph algorithm missions, GDS projection management, and
async job dispatch for the Research Workspace UI.

Routes
------
GET  /research/missions                             -- list available missions
POST /research/missions/{mission_id}/run  -- start a run (async 202 or inline 200)
GET  /research/missions/{mission_id}/runs/{run_id} -- poll run status + results
GET  /research/runs/{run_id}/export                -- export results as CSV

GET  /research/projections                         -- list GDS projection status
POST /research/projections/{name}/refresh          -- create/refresh a projection
DELETE /research/projections/{name}                -- drop a projection
"""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, field_validator

from libs.auth.org_scope import CallerScope, get_caller_scope
from libs.neo4j_client.client import PatientGraphClient
from services.analytics_api.app.services.algorithm_runner import (
    AlgorithmResult,
    run_mission,
)
from services.analytics_api.app.services.gds_projection_manager import (
    PROJ_CONDITION_COOCCUR,
    PROJ_PATIENT_CONDITION,
    PROJ_PATIENT_JOURNEY,
    PROJ_REFERRAL_NETWORK,
    create_projection,
    drop_projection,
    list_projections,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# -- In-memory run store (replaced by Neo4j persistence in Phase 5) ----------

_runs: Dict[str, Dict[str, Any]] = {}
_runs_lock = threading.Lock()

# Fast missions run inline (< 5s expected); slow ones go async.
_ASYNC_MISSIONS = {"groups", "similar", "teams", "missing"}
_INLINE_MISSIONS = {"critical", "busiest", "bridges", "bottleneck", "gaps", "circles"}


# -- Pydantic models ----------------------------------------------------------


_DETAIL_BY_INDEX = {0: "summary", 1: "detailed", 2: "everything"}


class RunRequest(BaseModel):
    area: str = "all"
    period: str = "12m"
    detail: str = "summary"
    patient_id: Optional[str] = None
    confidence_min: float = 0.5
    context_filter: str = "current"  # "current" | "all"

    @field_validator("detail", mode="before")
    @classmethod
    def _coerce_detail(cls, v: Any) -> str:
        """Accept toggle indices (0-2) from older clients; API expects strings."""
        if v is None or v == "":
            return "summary"
        if isinstance(v, bool):
            return "summary"
        if isinstance(v, int):
            return _DETAIL_BY_INDEX.get(v, "summary")
        if isinstance(v, float) and v.is_integer():
            return _DETAIL_BY_INDEX.get(int(v), "summary")
        if isinstance(v, str):
            if v.isdigit():
                return _DETAIL_BY_INDEX.get(int(v), "summary")
            if v in ("summary", "detailed", "everything"):
                return v
        return "summary"


class RunResponse(BaseModel):
    run_id: str
    mission_id: str
    status: str
    created_at: str
    result: Optional[Dict[str, Any]] = None


class ProjectionStatusResponse(BaseModel):
    name: str
    exists: bool
    node_count: int = 0
    relationship_count: int = 0
    layer: str
    data_available: bool
    unavailable_reason: Optional[str] = None
    error: Optional[str] = None


class ProjectionSummaryResponse(BaseModel):
    projections: List[ProjectionStatusResponse]
    referral_data_available: bool
    referral_count: int


# -- Mission catalogue --------------------------------------------------------

_MISSION_CATALOGUE = [
    {
        "id": "bottleneck",
        "group": "problems",
        "group_title": "Find problems",
        "group_subtitle": "Spot delays, gaps and blockages",
        "tier": 1,
        "layer": "A",
        "data_gated": False,
        "titles": {
            "patients": "Where are patients waiting longest in their pathway?",
            "pathways": "Which pathway steps cause the biggest delays?",
            "capacity": "Where is the pathway under the most pressure?",
        },
        "descriptions": {
            "patients": (
                "Finds the steps in the pathway where patients wait the longest, "
                "and how many patients are affected."
            ),
            "pathways": (
                "Shows which pathway steps consistently take "
                "much longer than they should."
            ),
            "capacity": (
                "Highlights the points in the pathway that are under the most pressure."
            ),
        },
    },
    {
        "id": "gaps",
        "group": "problems",
        "group_title": "Find problems",
        "group_subtitle": "Spot delays, gaps and blockages",
        "tier": 1,
        "layer": "A",
        "data_gated": False,
        "titles": {
            "patients": "Which patients are falling through the gaps?",
            "pathways": "Are there broken links in the pathway?",
            "capacity": "Which practices have isolated patient groups?",
        },
        "descriptions": {
            "patients": (
                "Finds patients whose records are not connected to the rest of "
                "the pathway -- they may be missing follow-up."
            ),
            "pathways": (
                "Checks for pathway steps that do not connect to the wider system."
            ),
            "capacity": (
                "Identifies practices where patients appear to fall outside the "
                "main patient population."
            ),
        },
    },
    {
        "id": "circles",
        "group": "problems",
        "group_title": "Find problems",
        "group_subtitle": "Spot delays, gaps and blockages",
        "tier": 2,
        "layer": "A",
        "data_gated": False,
        "titles": {
            "patients": "Are patients going round in circles?",
            "pathways": "Do conditions keep recurring in the same patients?",
            "capacity": "Are there repeated encounter patterns?",
        },
        "descriptions": {
            "patients": (
                "Spots patients being sent back and forth through the pathway "
                "without making progress."
            ),
            "pathways": (
                "Finds patterns where conditions loop back on themselves "
                "across encounters."
            ),
            "capacity": (
                "Identifies repeated encounter sequences that may indicate "
                "unresolved pathway issues."
            ),
        },
    },
    {
        "id": "groups",
        "group": "patterns",
        "group_title": "Find patterns",
        "group_subtitle": "Discover groups, similarities and connections",
        "tier": 1,
        "layer": "A",
        "data_gated": False,
        "titles": {
            "patients": "Are there natural groups of similar patients?",
            "pathways": "Which conditions always appear together?",
            "capacity": "Which practices see similar patient mixes?",
        },
        "descriptions": {
            "patients": (
                "Automatically finds clusters of patients who share similar "
                "conditions, without you having to define the groups first."
            ),
            "pathways": (
                "Groups conditions that consistently appear together across "
                "patient records."
            ),
            "capacity": (
                "Clusters practices that see patients with similar combinations "
                "of conditions."
            ),
        },
    },
    {
        "id": "similar",
        "group": "patterns",
        "group_title": "Find patterns",
        "group_subtitle": "Discover groups, similarities and connections",
        "tier": 1,
        "layer": "A",
        "data_gated": False,
        "titles": {
            "patients": "Find patients like this one",
            "pathways": "Find conditions with a similar coding profile",
            "capacity": "Find practices with similar patterns",
        },
        "descriptions": {
            "patients": (
                "Pick a patient and find others with a similar mix of "
                "coded conditions and journey steps."
            ),
            "pathways": (
                "Select a condition and find others that appear in similar "
                "patient contexts."
            ),
            "capacity": (
                "Choose a practice and find others that handle similar "
                "patient populations."
            ),
        },
    },
    {
        "id": "teams",
        "group": "patterns",
        "group_title": "Find patterns",
        "group_subtitle": "Discover groups, similarities and connections",
        "tier": 2,
        "layer": "A",
        "data_gated": False,
        "titles": {
            "patients": "Which conditions are most tightly linked for my patients?",
            "pathways": "Which conditions form natural clusters?",
            "capacity": "Which services form natural referral hubs?",
        },
        "descriptions": {
            "patients": (
                "Shows which conditions almost always appear together in "
                "your patients' records."
            ),
            "pathways": "Finds the groups of conditions that are most tightly linked.",
            "capacity": (
                "Identifies which services consistently receive referrals "
                "together. Requires referral data."
            ),
        },
    },
    {
        "id": "critical",
        "group": "matters",
        "group_title": "Find what matters most",
        "group_subtitle": "Identify the most important conditions and services",
        "tier": 1,
        "layer": "A",
        "data_gated": False,
        "titles": {
            "patients": "Which conditions matter most for this patient?",
            "pathways": "Which conditions are most central to the population?",
            "capacity": "Which practices handle the most critical conditions?",
        },
        "descriptions": {
            "patients": (
                "Finds the conditions that have the most influence over a "
                "patient's overall health picture."
            ),
            "pathways": (
                "Identifies conditions that sit at the centre of the "
                "widest range of patient pathways."
            ),
            "capacity": (
                "Ranks practices by the complexity and centrality of the "
                "conditions they manage."
            ),
        },
    },
    {
        "id": "busiest",
        "group": "matters",
        "group_title": "Find what matters most",
        "group_subtitle": "Identify the most important conditions and services",
        "tier": 2,
        "layer": "A",
        "data_gated": False,
        "titles": {
            "patients": "Which patients have the most complex records?",
            "pathways": "Which conditions connect to the most others?",
            "capacity": "Which practices handle the highest volume?",
        },
        "descriptions": {
            "patients": (
                "Ranks patients by the number of distinct coded conditions "
                "and the connections between them."
            ),
            "pathways": (
                "Finds conditions that appear alongside the widest range "
                "of other conditions."
            ),
            "capacity": (
                "Ranks practices by the total number of patient-condition links."
            ),
        },
    },
    {
        "id": "missing",
        "group": "matters",
        "group_title": "Find what matters most",
        "group_subtitle": "Identify the most important conditions and services",
        "tier": 2,
        "layer": "A",
        "data_gated": False,
        "titles": {
            "patients": (
                "Are there likely conditions missing from this patient's record?"
            ),
            "pathways": (
                "Which conditions commonly co-occur but are not coded together?"
            ),
            "capacity": "Which services should be connected but are not?",
        },
        "descriptions": {
            "patients": (
                "Looks for conditions that commonly appear together in "
                "similar patients but are absent from this patient's record."
            ),
            "pathways": (
                "Finds pairs of conditions that frequently appear in the "
                "same patients but are rarely coded together."
            ),
            "capacity": (
                "Identifies services that share many patients but have no "
                "direct referral route. Requires referral data."
            ),
        },
    },
    {
        "id": "bridges",
        "group": "matters",
        "group_title": "Find what matters most",
        "group_subtitle": "Identify the most important conditions and services",
        "tier": 1,
        "layer": "A",
        "data_gated": False,
        "titles": {
            "patients": "Which conditions bridge different parts of the pathway?",
            "pathways": "Which conditions connect different disease areas?",
            "capacity": "Which conditions link different patient populations?",
        },
        "descriptions": {
            "patients": (
                "Finds conditions that act as connectors between otherwise "
                "separate parts of the pathway. Coding these correctly matters "
                "most for patients with complex needs."
            ),
            "pathways": (
                "Identifies conditions that sit between different disease "
                "groups and help connect the full pathway picture."
            ),
            "capacity": (
                "Shows which conditions create links between patient "
                "groups that might otherwise appear unconnected."
            ),
        },
    },
]


# -- Endpoints ----------------------------------------------------------------


@router.get("/research/missions")
def list_missions(
    scope: CallerScope = Depends(get_caller_scope),
) -> Dict[str, Any]:
    """Return the full mission catalogue with current data-availability status."""
    client = PatientGraphClient()
    try:
        referral_available, _ = _check_referral(client)
        missions = [
            {**m, "data_available": _mission_available(m, referral_available)}
            for m in _MISSION_CATALOGUE
        ]
        return {
            "missions": missions,
            "referral_data_available": referral_available,
        }
    finally:
        client.close()


@router.post("/research/missions/{mission_id}/run", status_code=202)
def run_mission_endpoint(
    mission_id: str,
    body: RunRequest = Body(default_factory=RunRequest),
    scope: CallerScope = Depends(get_caller_scope),
) -> RunResponse:
    """Start a mission run.

    Fast missions (< 5s) return 200 with results inline.
    Slow missions return 202 with a run_id for polling.
    """
    _validate_mission_id(mission_id)
    run_id = f"RUN_{uuid.uuid4().hex[:16]}"
    now = datetime.now(timezone.utc).isoformat()

    with _runs_lock:
        _runs[run_id] = {
            "run_id": run_id,
            "mission_id": mission_id,
            "status": "queued",
            "created_at": now,
            "result": None,
            "error": None,
        }

    if mission_id in _INLINE_MISSIONS:
        # Run synchronously and return immediately
        client = PatientGraphClient()
        try:
            result = run_mission(
                mission_id=mission_id,
                client=client,
                scope=scope,
                area=body.area,
                period=body.period,
                detail=body.detail,
                patient_id=body.patient_id,
                confidence_min=body.confidence_min,
                context_filter=body.context_filter,
            )
        finally:
            client.close()
        run_dict = _serialise_result(result)
        with _runs_lock:
            _runs[run_id].update({"status": "done", "result": run_dict})
        return RunResponse(
            run_id=run_id,
            mission_id=mission_id,
            status="done",
            created_at=now,
            result=run_dict,
        )

    # Async: dispatch to background thread
    threading.Thread(
        target=_run_async,
        args=(run_id, mission_id, body, scope),
        daemon=True,
        name=f"research-{run_id[:12]}",
    ).start()

    return RunResponse(
        run_id=run_id,
        mission_id=mission_id,
        status="queued",
        created_at=now,
    )


@router.get("/research/missions/{mission_id}/runs/{run_id}")
def get_run(
    mission_id: str,
    run_id: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> RunResponse:
    """Poll a mission run for status and results."""
    with _runs_lock:
        run = _runs.get(run_id)
    if run is None or run["mission_id"] != mission_id:
        raise HTTPException(status_code=404, detail="Run not found")
    return RunResponse(**run)


@router.get("/research/runs/{run_id}/export")
def export_run(
    run_id: str,
    scope: CallerScope = Depends(get_caller_scope),
):
    """Export mission results as CSV."""
    import csv
    import io

    from fastapi.responses import StreamingResponse

    with _runs_lock:
        run = _runs.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run["status"] != "done":
        raise HTTPException(status_code=409, detail="Run has not completed yet")

    result = run.get("result") or {}
    items = result.get("items") or []
    if not items:
        raise HTTPException(status_code=404, detail="No results to export")

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(items[0].keys()))
    writer.writeheader()
    writer.writerows(items)
    output.seek(0)

    mission_id = run.get("mission_id", "results")
    filename = f"pathway-explorer-{mission_id}-{run_id[:8]}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/research/projections")
def get_projections(
    scope: CallerScope = Depends(get_caller_scope),
) -> ProjectionSummaryResponse:
    """List GDS projections and their status."""
    client = PatientGraphClient()
    try:
        summary = list_projections(client, scope)
        return ProjectionSummaryResponse(
            projections=[
                ProjectionStatusResponse(
                    name=p.name,
                    exists=p.exists,
                    node_count=p.node_count,
                    relationship_count=p.relationship_count,
                    layer=p.layer,
                    data_available=p.data_available,
                    unavailable_reason=p.unavailable_reason,
                    error=p.error,
                )
                for p in summary.projections
            ],
            referral_data_available=summary.referral_data_available,
            referral_count=summary.referral_count,
        )
    finally:
        client.close()


@router.post("/research/projections/{name}/refresh")
def refresh_projection(
    name: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> ProjectionStatusResponse:
    """Create or refresh a named GDS projection."""
    _validate_projection_name(name)
    client = PatientGraphClient()
    try:
        status = create_projection(client, scope, name)
        return ProjectionStatusResponse(
            name=status.name,
            exists=status.exists,
            node_count=status.node_count,
            relationship_count=status.relationship_count,
            layer=status.layer,
            data_available=status.data_available,
            unavailable_reason=status.unavailable_reason,
            error=status.error,
        )
    finally:
        client.close()


@router.delete("/research/projections/{name}")
def delete_projection(
    name: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> Dict[str, Any]:
    """Drop a named GDS projection."""
    _validate_projection_name(name)
    client = PatientGraphClient()
    try:
        dropped = drop_projection(client, name)
        return {"name": name, "dropped": dropped}
    finally:
        client.close()


# -- Helpers ------------------------------------------------------------------

_VALID_PROJECTION_NAMES = {
    PROJ_PATIENT_CONDITION,
    PROJ_CONDITION_COOCCUR,
    PROJ_PATIENT_JOURNEY,
    PROJ_REFERRAL_NETWORK,
}

_VALID_MISSION_IDS = {m["id"] for m in _MISSION_CATALOGUE}


def _validate_mission_id(mission_id: str) -> None:
    if mission_id not in _VALID_MISSION_IDS:
        raise HTTPException(
            status_code=404,
            detail=f"Mission {mission_id!r} not found. "
            f"Valid missions: {sorted(_VALID_MISSION_IDS)}",
        )


def _validate_projection_name(name: str) -> None:
    if name not in _VALID_PROJECTION_NAMES:
        raise HTTPException(
            status_code=404,
            detail=f"Projection {name!r} not found. "
            f"Valid projections: {sorted(_VALID_PROJECTION_NAMES)}",
        )


def _check_referral(client: PatientGraphClient) -> tuple[bool, int]:
    """Check referral data availability, returning (available, count)."""
    from services.analytics_api.app.services.gds_projection_manager import (
        check_referral_data_available,
    )

    try:
        return check_referral_data_available(client)
    except Exception:
        return False, 0


def _mission_available(mission: Dict[str, Any], referral_available: bool) -> bool:
    """Return True if mission data is available right now."""
    if mission.get("layer") == "B" and not referral_available:
        return False
    return not mission.get("data_gated", False)


def _serialise_result(result: AlgorithmResult) -> Dict[str, Any]:
    """Convert AlgorithmResult dataclass to a plain dict."""
    coverage = result.coverage
    return {
        "mission_id": result.mission_id,
        "headline": result.headline,
        "items": result.items,
        "total_count": result.total_count,
        "coverage": {
            "patient_count": coverage.patient_count,
            "practice_count": coverage.practice_count,
            "confidence": coverage.confidence,
            "confidence_note": coverage.confidence_note,
        },
        "method_plain": result.method_plain,
        "method_technical": result.method_technical,
        "next_steps": result.next_steps,
        "detail_level": result.detail_level,
        "data_available": result.data_available,
        "unavailable_reason": result.unavailable_reason,
        "error": result.error,
    }


def _run_async(
    run_id: str,
    mission_id: str,
    body: RunRequest,
    scope: CallerScope,
) -> None:
    """Execute a mission run in a background thread."""
    with _runs_lock:
        if run_id in _runs:
            _runs[run_id]["status"] = "running"

    client = PatientGraphClient()
    try:
        result = run_mission(
            mission_id=mission_id,
            client=client,
            scope=scope,
            area=body.area,
            period=body.period,
            detail=body.detail,
            patient_id=body.patient_id,
            confidence_min=body.confidence_min,
            context_filter=body.context_filter,
        )
        run_dict = _serialise_result(result)
        with _runs_lock:
            if run_id in _runs:
                _runs[run_id].update(
                    {
                        "status": "done" if not result.error else "failed",
                        "result": run_dict,
                        "error": result.error,
                    }
                )
    except Exception as exc:
        logger.error("Async run %s failed: %s", run_id, exc, exc_info=True)
        with _runs_lock:
            if run_id in _runs:
                _runs[run_id].update({"status": "failed", "error": str(exc)})
    finally:
        client.close()
