"""SBAR generation HTTP endpoints.

Atlas trace:
  DO: DO-EC41233C
  DI: DI-9D0DF618
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-EC41233C")

Routes
------
POST /sbar/jobs                         -- enqueue an SBAR generation job
GET  /sbar/jobs/{run_id}/events         -- SSE relay of orchestrator progress
GET  /sbar/assessments/{assessment_id}  -- read back a persisted Assessment

The producer is the Admin AI Summarisation Playground but any service
that needs an SBAR (a referral writer, a future encounter hook) can hit
the same enqueue endpoint or publish directly to the pipeline-jobs
queue with the same payload.

See DI-LEO-AI-186, DI-LEO-AI-190.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError

from app.deps import require_admin
from libs.auth.org_scope import CallerScope, get_caller_scope
from libs.cypher.sbar_assessment_queries import (
    GET_ASSESSMENT,
    assessment_to_dict,
)
from libs.sbar.events import SBARRequestPayload

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sbar", tags=["sbar"])

PIPELINE_QUEUE = os.getenv("PIPELINE_QUEUE_NAME", "pipeline-jobs")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
_PROGRESS_IDLE_TIMEOUT_S = 300
_TERMINAL_EVENT_TYPES = frozenset({"sbar_completed", "sbar_failed", "pipeline_error"})


class SBARJobResponse(BaseModel):
    run_id: str
    assessment_id: str
    status: str = "queued"


class ScenarioRunRequest(BaseModel):
    case_ids: list[str] = Field(min_length=1, max_length=20)
    guideline_id: str = "NG12"
    completeness_domain: str = "cancer_referrals"
    completeness_subdomain: str = "lower_gi"
    plan_definition_id: str = "pd-referral-assessment"


class ScenarioRunResponse(BaseModel):
    run_id: str
    status: str = "queued"
    child_runs: dict[str, str]


@router.post("/jobs", response_model=SBARJobResponse)
async def enqueue_sbar_job(
    body: dict[str, Any],
    scope: CallerScope = Depends(get_caller_scope),
    _admin: None = Depends(require_admin),
) -> SBARJobResponse:
    """Validate, normalise, and publish an sbar_requested job."""
    run_id = str(body.get("run_id") or uuid.uuid4())
    body.setdefault("run_id", run_id)
    body.setdefault("event_type", "sbar_requested")
    body.setdefault("assessment_id", uuid.uuid4().hex)
    if scope and getattr(scope, "user_id", None) and not body.get("requested_by"):
        body["requested_by"] = scope.user_id
    if scope and getattr(scope, "tenant_id", None) and not body.get("tenant_id"):
        body["tenant_id"] = scope.tenant_id

    try:
        payload = SBARRequestPayload.model_validate(body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    from libs.message_bus.base import Message
    from libs.message_bus.factory import create_message_bus

    # Message.body is a Dict[str, Any] -- the adapter does its own
    # json.dumps when it places the message on the wire (Azure Service
    # Bus or the in-memory dev adapter). Passing pre-serialised bytes
    # here would cause the adapter to call json.dumps(<bytes>) and
    # raise TypeError: Object of type bytes is not JSON serializable.
    bus = create_message_bus()
    try:
        await bus.send(
            PIPELINE_QUEUE,
            Message(
                body=payload.model_dump(mode="json"),
                correlation_id=payload.run_id,
                subject="sbar-requested",
            ),
        )
    finally:
        await bus.close()

    return SBARJobResponse(
        run_id=payload.run_id,
        assessment_id=str(payload.assessment_id),
        status="queued",
    )


@router.get("/scenario-runs/scenarios")
def list_sbar_scenarios(
    status: str | None = None,
    search: str | None = None,
    _scope: CallerScope = Depends(get_caller_scope),
    _admin: None = Depends(require_admin),
) -> dict[str, Any]:
    """Return extraction scenarios selectable for end-to-end SBAR runs."""
    _ = _scope
    from libs.cypher.extraction_scenario_queries import (
        COUNT_BY_STATUS,
        LIST_EXTRACTION_SCENARIOS,
    )
    from libs.neo4j_client.client import KnowledgeGraphClient

    client = KnowledgeGraphClient()
    try:
        counts = client.run(COUNT_BY_STATUS)
        rows = client.run(
            LIST_EXTRACTION_SCENARIOS,
            status=status,
            site=None,
            search=search,
        )
    finally:
        client.close()
    totals = counts[0] if counts else {"total": 0, "approved": 0, "draft": 0}
    return {
        "total": totals.get("total", 0),
        "approved": totals.get("approved", 0),
        "draft": totals.get("draft", 0),
        "cases": [_normalise_scenario_row(dict(row)) for row in rows],
    }


@router.post("/scenario-runs", response_model=ScenarioRunResponse)
async def enqueue_scenario_run(
    body: ScenarioRunRequest,
    scope: CallerScope = Depends(get_caller_scope),
    _admin: None = Depends(require_admin),
) -> ScenarioRunResponse:
    """Queue durable referral assessment runs for selected scenarios."""
    run_id = str(uuid.uuid4())
    triggered_at = _now_iso()
    cases = _load_scenarios(body.case_ids)
    if len(cases) != len(set(body.case_ids)):
        found = {str(case.get("case_id")) for case in cases}
        missing = sorted(set(body.case_ids) - found)
        raise HTTPException(status_code=404, detail=f"Scenario(s) not found: {missing}")

    empty_md = [
        str(case.get("case_id"))
        for case in cases
        if not str(case.get("markdown_body") or "").strip()
    ]
    if empty_md:
        raise HTTPException(
            status_code=422,
            detail=f"Scenario(s) missing markdown_body: {empty_md}",
        )

    child_runs = {str(case["case_id"]): f"{run_id}:{case['case_id']}" for case in cases}
    _ensure_scenario_run_schema()
    try:
        chunk_ids_by_case = _scaffold_scenario_referrals(run_id, cases, child_runs)
    except Exception as exc:
        logger.exception("Scenario referral scaffold failed for run %s", run_id)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to scaffold referral graph: {exc}",
        ) from exc

    _create_scenario_run(
        run_id=run_id,
        body=body,
        child_runs=child_runs,
        triggered_at=triggered_at,
        triggered_by=getattr(scope, "user_email", None)
        or getattr(scope, "user_id", None)
        or "ui",
    )
    await _publish_scenario_children(
        run_id, body, cases, child_runs, scope, chunk_ids_by_case
    )
    return ScenarioRunResponse(run_id=run_id, child_runs=child_runs)


@router.get("/scenario-runs")
def list_scenario_runs(
    limit: int = 25,
    _scope: CallerScope = Depends(get_caller_scope),
    _admin: None = Depends(require_admin),
) -> dict[str, Any]:
    _ = _scope
    rows = _list_scenario_run_rows(max(1, min(limit, 100)))
    return {
        "runs": [_hydrate_scenario_run(row, include_children=False) for row in rows]
    }


@router.get("/scenario-runs/{run_id}")
def get_scenario_run(
    run_id: str,
    _scope: CallerScope = Depends(get_caller_scope),
    _admin: None = Depends(require_admin),
) -> dict[str, Any]:
    _ = _scope
    row = _get_scenario_run_row(run_id)
    if row is None:
        raise HTTPException(
            status_code=404, detail=f"Scenario run {run_id!r} not found"
        )
    return _hydrate_scenario_run(row, include_children=True)


@router.get("/jobs/{run_id}/events")
def stream_sbar_events(
    run_id: str,
    scope: CallerScope = Depends(get_caller_scope),
    _admin: None = Depends(require_admin),
):
    """Relay orchestrator progress events for *run_id* via Server-Sent Events.

    Connection auto-closes on a terminal event or after
    ``_PROGRESS_IDLE_TIMEOUT_S`` seconds of silence.
    """
    _ = scope
    events: queue.Queue[dict | None] = queue.Queue()

    def _redis_listener() -> None:
        try:
            import redis as _redis

            r = _redis.from_url(REDIS_URL)
            last_key = f"pipeline:last:{run_id}"
            last_raw = r.get(last_key)
            if last_raw:
                try:
                    if isinstance(last_raw, bytes):
                        last_raw = last_raw.decode("utf-8")
                    last_event = json.loads(last_raw)
                    if isinstance(last_event, dict):
                        events.put(last_event)
                        if last_event.get("type") in _TERMINAL_EVENT_TYPES:
                            return
                except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
                    pass
            ps = r.pubsub(ignore_subscribe_messages=True)
            channel = f"pipeline:{run_id}"
            ps.subscribe(channel)
            idle_s = 0.0
            while idle_s < _PROGRESS_IDLE_TIMEOUT_S:
                msg = ps.get_message(timeout=1.0)
                if msg is None:
                    idle_s += 1.0
                    continue
                idle_s = 0.0
                if msg.get("type") != "message":
                    continue
                try:
                    data: dict = json.loads(msg["data"])
                except (json.JSONDecodeError, TypeError):
                    continue
                events.put(data)
                if data.get("type") in _TERMINAL_EVENT_TYPES:
                    break
        except Exception as exc:
            events.put(
                {"type": "pipeline_error", "message": str(exc), "run_id": run_id}
            )
        finally:
            events.put(None)

    threading.Thread(target=_redis_listener, daemon=True).start()

    def _format_sse(event_type: str, data: dict[str, Any]) -> str:
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

    def _event_generator():
        idle_ticks = 0
        while True:
            try:
                event = events.get(timeout=2.0)
            except queue.Empty:
                idle_ticks += 1
                yield _format_sse(
                    "heartbeat",
                    {"type": "heartbeat", "ts": time.time(), "run_id": run_id},
                )
                if idle_ticks > (_PROGRESS_IDLE_TIMEOUT_S // 2):
                    break
                continue
            if event is None:
                break
            idle_ticks = 0
            yield _format_sse(str(event.get("type", "message")), event)

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/assessments/{assessment_id}")
def get_assessment(
    assessment_id: str,
    scope: CallerScope = Depends(get_caller_scope),
    _admin: None = Depends(require_admin),
) -> dict[str, Any]:
    _ = scope
    from libs.neo4j_client.client import PatientGraphClient

    client = PatientGraphClient()
    try:
        with client.session() as session:
            row = session.run(GET_ASSESSMENT, assessment_id=assessment_id).single()
    finally:
        client.close()

    if row is None:
        raise HTTPException(
            status_code=404, detail=f"Assessment {assessment_id!r} not found"
        )
    return assessment_to_dict(row)


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


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if hasattr(value, "iso_format"):
        return value.iso_format()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _normalise_scenario_row(row: dict[str, Any]) -> dict[str, Any]:
    json_fields = {
        "phrase_classes",
        "difficulty",
        "expected_strings",
        "expected_observables",
        "expected_analysis",
        "expected_sbar",
        "must_not_extract",
        "synthetic_patient",
        "blood_results",
    }
    return _json_safe(
        {
            key: (_json_loads_safe(value) if key in json_fields else value)
            for key, value in row.items()
        }
    )


def _ensure_scenario_run_schema() -> None:
    from libs.cypher.ai_summarisation_scenario_queries import (
        AI_SUMMARISATION_SCENARIO_CONSTRAINTS,
    )
    from libs.neo4j_client.client import KnowledgeGraphClient

    client = KnowledgeGraphClient()
    try:
        for query in AI_SUMMARISATION_SCENARIO_CONSTRAINTS:
            client.run(query)
    finally:
        client.close()


def _load_scenarios(case_ids: list[str]) -> list[dict[str, Any]]:
    from libs.cypher.extraction_scenario_queries import GET_EXTRACTION_SCENARIO
    from libs.neo4j_client.client import KnowledgeGraphClient

    client = KnowledgeGraphClient()
    by_id: dict[str, dict[str, Any]] = {}
    try:
        for case_id in dict.fromkeys(case_ids):
            rows = client.run(GET_EXTRACTION_SCENARIO, case_id=case_id)
            if rows:
                by_id[case_id] = _normalise_scenario_row(dict(rows[0]))
    finally:
        client.close()
    return [by_id[case_id] for case_id in case_ids if case_id in by_id]


def _create_scenario_run(
    *,
    run_id: str,
    body: ScenarioRunRequest,
    child_runs: dict[str, str],
    triggered_at: str,
    triggered_by: str,
) -> None:
    from libs.cypher.ai_summarisation_scenario_queries import CREATE_SCENARIO_RUN
    from libs.neo4j_client.client import KnowledgeGraphClient

    client = KnowledgeGraphClient()
    try:
        client.run(
            CREATE_SCENARIO_RUN,
            run_id=run_id,
            status="queued",
            case_ids_json=json.dumps(body.case_ids, sort_keys=True),
            child_runs_json=json.dumps(child_runs, sort_keys=True),
            guideline_id=body.guideline_id,
            completeness_domain=body.completeness_domain,
            completeness_subdomain=body.completeness_subdomain,
            plan_definition_id=body.plan_definition_id,
            triggered_by=triggered_by,
            triggered_at=triggered_at,
        )
    finally:
        client.close()


def _scaffold_scenario_referrals(
    parent_run_id: str,
    cases: list[dict[str, Any]],
    child_runs: dict[str, str],
) -> dict[str, list[str]]:
    """Materialise production-shaped referral graphs; return case_id -> chunk_ids."""
    from libs.referral_simulator.ids import (
        document_reference_id,
        encounter_id_for_referral,
        referral_id_for_child_run,
        scenario_patient_id,
    )
    from libs.referral_simulator.scaffold import SOURCE_SCENARIO, scaffold_referral

    chunk_ids_by_case: dict[str, list[str]] = {}
    for case in cases:
        case_id = str(case["case_id"])
        child_run_id = child_runs[case_id]
        referral_id = referral_id_for_child_run(child_run_id)
        dr_id = document_reference_id(referral_id)
        encounter_id = encounter_id_for_referral(referral_id)
        synthetic_patient = case.get("synthetic_patient") or {}
        patient_name = " ".join(
            part
            for part in (
                synthetic_patient.get("given_name"),
                synthetic_patient.get("family_name"),
            )
            if part
        )
        chunk_ids_by_case[case_id] = scaffold_referral(
            patient_id=scenario_patient_id(case_id),
            referral_id=referral_id,
            dr_id=dr_id,
            text=str(case.get("markdown_body") or ""),
            encounter_id=encounter_id,
            source=SOURCE_SCENARIO,
            patient_sex=synthetic_patient.get("gender"),
            patient_name=patient_name,
            nhs_number=str(synthetic_patient.get("synthetic_nhs_number") or ""),
            birth_date=str(synthetic_patient.get("date_of_birth") or ""),
            case_id=case_id,
            parent_run_id=parent_run_id,
            document_title=f"Scenario referral {case_id}",
        )
    return chunk_ids_by_case


async def _publish_scenario_children(
    parent_run_id: str,
    body: ScenarioRunRequest,
    cases: list[dict[str, Any]],
    child_runs: dict[str, str],
    scope: CallerScope,
    chunk_ids_by_case: dict[str, list[str]],
) -> None:
    from libs.message_bus.base import Message
    from libs.message_bus.factory import create_message_bus
    from libs.referral_simulator.ids import (
        document_reference_id,
        encounter_id_for_referral,
        referral_id_for_child_run,
        scenario_patient_id,
    )
    from libs.referral_simulator.message import build_referral_received_message
    from libs.referral_simulator.scaffold import SOURCE_SCENARIO

    bus = create_message_bus()
    try:
        for case in cases:
            case_id = str(case["case_id"])
            child_run_id = child_runs[case_id]
            referral_id = referral_id_for_child_run(child_run_id)
            msg_body = build_referral_received_message(
                patient_id=scenario_patient_id(case_id),
                encounter_id=encounter_id_for_referral(referral_id),
                referral_id=referral_id,
                document_reference_id=document_reference_id(referral_id),
                chunk_ids=chunk_ids_by_case[case_id],
                run_id=child_run_id,
                plan_definition_id=body.plan_definition_id,
                guideline_id=body.guideline_id,
                completeness_domain=body.completeness_domain,
                completeness_subdomain=body.completeness_subdomain,
                context={
                    "source": SOURCE_SCENARIO,
                    "case_id": case_id,
                    "parent_run_id": parent_run_id,
                    "site": case.get("site"),
                },
            )
            if getattr(scope, "user_id", None):
                msg_body["requested_by"] = scope.user_id
            if getattr(scope, "tenant_id", None):
                msg_body["tenant_id"] = scope.tenant_id
            await bus.send(
                PIPELINE_QUEUE,
                Message(
                    body=msg_body,
                    correlation_id=child_run_id,
                    subject="referral-received",
                ),
            )
    finally:
        await bus.close()
    _update_scenario_parent_status(parent_run_id)


def _list_scenario_run_rows(limit: int) -> list[dict[str, Any]]:
    from libs.cypher.ai_summarisation_scenario_queries import LIST_SCENARIO_RUNS
    from libs.neo4j_client.client import KnowledgeGraphClient

    _ensure_scenario_run_schema()
    client = KnowledgeGraphClient()
    try:
        return [dict(row) for row in client.run(LIST_SCENARIO_RUNS, limit=limit)]
    finally:
        client.close()


def _get_scenario_run_row(run_id: str) -> dict[str, Any] | None:
    from libs.cypher.ai_summarisation_scenario_queries import GET_SCENARIO_RUN
    from libs.neo4j_client.client import KnowledgeGraphClient

    client = KnowledgeGraphClient()
    try:
        rows = client.run(GET_SCENARIO_RUN, run_id=run_id)
    finally:
        client.close()
    return dict(rows[0]) if rows else None


def _hydrate_scenario_run(
    row: dict[str, Any],
    *,
    include_children: bool,
) -> dict[str, Any]:
    child_runs = _json_loads_safe(row.get("child_runs_json")) or {}
    case_ids = _json_loads_safe(row.get("case_ids_json")) or []
    children = _load_child_pipeline_runs(child_runs) if child_runs else []
    counts = _child_counts(children)
    status = _derive_parent_status(counts, len(child_runs), row.get("status"))
    _persist_parent_status_if_changed(row, status, counts)
    payload = {
        "run_id": row.get("run_id"),
        "status": status,
        "case_ids": case_ids,
        "child_runs": child_runs,
        "guideline_id": row.get("guideline_id"),
        "completeness_domain": row.get("completeness_domain"),
        "completeness_subdomain": row.get("completeness_subdomain"),
        "plan_definition_id": row.get("plan_definition_id"),
        "triggered_by": row.get("triggered_by"),
        "triggered_at": row.get("triggered_at"),
        "updated_at": row.get("updated_at"),
        "completed_at": row.get("completed_at"),
        "completed_count": counts["completed"],
        "failed_count": counts["failed"],
        "running_count": counts["running"],
        "case_count": len(child_runs),
    }
    if include_children:
        payload["children"] = children
    return _json_safe(payload)


def _load_child_pipeline_runs(child_runs: dict[str, str]) -> list[dict[str, Any]]:
    from libs.neo4j_client.client import PatientGraphClient

    client = PatientGraphClient()
    children: list[dict[str, Any]] = []
    try:
        for case_id, run_id in child_runs.items():
            run_rows = client.run(
                "MATCH (r:PipelineRun {id: $run_id}) "
                "RETURN r.id AS run_id, r.status AS status, "
                "       r.patient_id AS patient_id, r.encounter_id AS encounter_id, "
                "       r.assessment_id AS assessment_id, "
                "       r.created_at AS created_at, r.updated_at AS updated_at, "
                "       r.completed_at AS completed_at, "
                "       r.completion_event_json AS completion_event_json",
                run_id=run_id,
            )
            stages = client.run(
                "MATCH (:PipelineRun {id: $run_id})-[:HAS_STAGE]->(s:PipelineStageRun) "
                "RETURN s.step_id AS step_id, s.event_type AS event_type, "
                "       s.status AS status, s.output_json AS output_json, "
                "       s.errors_json AS errors_json, s.completed_at AS completed_at "
                "ORDER BY s.completed_at ASC",
                run_id=run_id,
            )
            audit_rows: list[dict[str, Any]] = []
            if not run_rows:
                audit_rows = client.run(
                    "MATCH (ae:AuditEvent) WHERE ae.id IN [$main_id, $sbar_id] "
                    "RETURN ae.id AS id, ae.status AS status, "
                    "       ae.patient_id AS patient_id, "
                    "       ae.encounter_id AS encounter_id, "
                    "       ae.assessment_id AS assessment_id, "
                    "       ae.created_at AS created_at, "
                    "       ae.error_count AS error_count, "
                    "       ae.first_error AS first_error",
                    main_id=f"audit-{run_id}",
                    sbar_id=f"audit-{run_id}:sbar",
                )
            child = _normalise_child_run(case_id, run_id, run_rows, stages, audit_rows)
            if child.get("assessment_id"):
                assessment = _load_assessment_for_history(str(child["assessment_id"]))
                if assessment and not assessment.get("completeness_result_json"):
                    assessment["completeness_result_json"] = (
                        _extract_completeness_json_from_stages(stages)
                    )
                child["assessment"] = assessment
            children.append(child)
    finally:
        client.close()
    return children


# Legacy WorkflowEngine statuses (libs/workflow/engine.py::_write_audit_event)
# mapped onto the three states the scenario-runs UI understands. Anything
# not in this map but non-empty is treated as "completed" -- the pipeline
# finished running, it just landed in a special terminal state (e.g.
# "empty_extraction", "needs_review") rather than a hard failure.
_AUDIT_STATUS_MAP = {"completed": "completed", "error": "failed"}


def _normalise_audit_fallback(
    run_id: str, audit_rows: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Build a PipelineRun-shaped dict from legacy :AuditEvent nodes.

    DurableStepRunner writes :PipelineRun/:PipelineStageRun for plans that
    declare ``workflowMode: durable_pubsub`` (see resolve_plan_workflow_mode).
    Older in-process WorkflowEngine runs only wrote :AuditEvent nodes; this
    fallback lets scenario-run polling show completed status for those rows.
    Without it, _load_child_pipeline_runs never finds a :PipelineRun node, so
    every child case is stuck showing "queued" forever (via the {"status":
    "queued"} default below) while the parent row is stuck showing "running"
    (via _child_counts treating non-terminal statuses as "running") -- even
    after the pipeline has completed. See audit-{run_id} (whole-run status,
    written by engine.py) and audit-{run_id}:sbar (assessment_id, written by
    sbar_orchestrator.py).
    """
    by_id = {str(row.get("id")): row for row in audit_rows}
    main = by_id.get(f"audit-{run_id}")
    sbar = by_id.get(f"audit-{run_id}:sbar")
    if not main and not sbar:
        return None

    status_raw = str((main or sbar or {}).get("status") or "")
    status = _AUDIT_STATUS_MAP.get(status_raw, "completed" if status_raw else "queued")
    created_at = (main or {}).get("created_at") or (sbar or {}).get("created_at")
    return {
        "run_id": run_id,
        "status": status,
        "patient_id": (main or {}).get("patient_id") or (sbar or {}).get("patient_id"),
        "encounter_id": (
            (main or {}).get("encounter_id") or (sbar or {}).get("encounter_id")
        ),
        "assessment_id": (sbar or {}).get("assessment_id"),
        "created_at": created_at,
        "updated_at": created_at,
        "completed_at": created_at if status in {"completed", "failed"} else None,
        "completion_event_json": None,
    }


def _normalise_child_run(
    case_id: str,
    run_id: str,
    run_rows: list[dict[str, Any]],
    stages: list[dict[str, Any]],
    audit_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    run = dict(run_rows[0]) if run_rows else None
    if run is None:
        run = _normalise_audit_fallback(run_id, audit_rows or []) or {
            "run_id": run_id,
            "status": "queued",
        }
    stage_payloads = []
    assessment_id = run.get("assessment_id")
    for stage in stages:
        output = _json_loads_safe(stage.get("output_json")) or {}
        if not assessment_id and isinstance(output, dict):
            assessment_id = output.get("sbar_assessment_id")
        stage_payloads.append(
            {
                "step_id": stage.get("step_id"),
                "event_type": stage.get("event_type"),
                "status": stage.get("status"),
                "errors": _json_loads_safe(stage.get("errors_json")) or [],
                "output": output,
                "completed_at": stage.get("completed_at"),
            }
        )
    completion_event = _json_loads_safe(run.get("completion_event_json"))
    return {
        "case_id": case_id,
        "run_id": run_id,
        "status": run.get("status") or "queued",
        "patient_id": run.get("patient_id"),
        "encounter_id": run.get("encounter_id"),
        "assessment_id": assessment_id,
        "created_at": run.get("created_at"),
        "updated_at": run.get("updated_at"),
        "completed_at": run.get("completed_at"),
        "completion_event": completion_event,
        "stages": stage_payloads,
    }


def _load_assessment_for_history(assessment_id: str) -> dict[str, Any] | None:
    from libs.neo4j_client.client import PatientGraphClient

    client = PatientGraphClient()
    try:
        with client.session() as session:
            row = session.run(GET_ASSESSMENT, assessment_id=assessment_id).single()
    finally:
        client.close()
    return assessment_to_dict(row) if row else None


def _extract_completeness_json_from_stages(
    stages: list[dict[str, Any]],
) -> str | None:
    """Pull completeness_result from stage outputs when not on the Assessment node.

    The pipeline worker writes completeness_result_json to the Assessment node
    during the sbar_requested step, but this can silently fail. This function
    provides a reliable fallback by reading directly from the stage output that
    the completeness_requested step persisted to Neo4j.
    """
    for stage in stages or []:
        if stage.get("event_type") != "completeness_requested":
            continue
        raw = stage.get("output_json")
        if not raw:
            continue
        try:
            output = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        result = output.get("completeness_result") if isinstance(output, dict) else None
        if isinstance(result, dict) and result.get("configured"):
            return json.dumps(result)
    return None


def _child_counts(children: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"completed": 0, "failed": 0, "running": 0}
    for child in children:
        status = str(child.get("status") or "queued")
        if status == "completed":
            counts["completed"] += 1
        elif status == "failed":
            counts["failed"] += 1
        else:
            counts["running"] += 1
    return counts


def _derive_parent_status(
    counts: dict[str, int],
    total: int,
    current: Any,
) -> str:
    if total == 0:
        return "completed"
    if counts["failed"] > 0 and counts["completed"] + counts["failed"] == total:
        return "failed"
    if counts["completed"] == total:
        return "completed"
    if counts["running"] > 0:
        return "running"
    return str(current or "queued")


def _persist_parent_status_if_changed(
    row: dict[str, Any],
    status: str,
    counts: dict[str, int],
) -> None:
    if status == row.get("status") and counts["running"] == row.get("running_count"):
        return
    _update_scenario_parent_status(
        str(row.get("run_id")),
        status=status,
        counts=counts,
    )


def _update_scenario_parent_status(
    run_id: str,
    *,
    status: str = "running",
    counts: dict[str, int] | None = None,
) -> None:
    from libs.cypher.ai_summarisation_scenario_queries import (
        UPDATE_SCENARIO_RUN_STATUS,
    )
    from libs.neo4j_client.client import KnowledgeGraphClient

    counts = counts or {"completed": 0, "failed": 0, "running": 0}
    completed_at = _now_iso() if status in {"completed", "failed"} else None
    client = KnowledgeGraphClient()
    try:
        client.run(
            UPDATE_SCENARIO_RUN_STATUS,
            run_id=run_id,
            status=status,
            completed_count=counts["completed"],
            failed_count=counts["failed"],
            running_count=counts["running"],
            updated_at=_now_iso(),
            completed_at=completed_at,
        )
    finally:
        client.close()
