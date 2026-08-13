"""Production-shaped Lab run helpers (bus message + real run polling).

Atlas trace:
  DO: DO-3A70C3DD
  DI: DI-724CD8A5
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-3A70C3DD")

Atlas: DI-2289D095

`execute_lab_run` only ever enqueues the real `referral-received` message
-- it never writes a stub Assessment or echoes gold back as "output".
`poll_run_status` / `read_real_outputs` read the *real* pipeline result
back once it lands, so gold scoring compares against genuine extraction,
not a self-fulfilling echo.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from libs.cypher.pipeline_stage_queries import LIST_PIPELINE_STAGE_RUNS
from libs.cypher.sbar_assessment_queries import GET_ASSESSMENT
from libs.referral_simulator.message import (
    build_communication_assessment_message,
    build_referral_received_message,
)
from libs.validation_lab.gold import RunOutputs
from libs.validation_lab.models import PersistMode
from libs.validation_lab.stage_errors import (
    plain_english_pipeline_error,
    plain_english_pipeline_message,
    stage_errors_from_row,
    stage_warnings_from_row,
)
from libs.validation_lab.tenant import VALIDATION_LAB_TENANT_ID

logger = logging.getLogger(__name__)

PublishFn = Callable[[dict[str, Any], str], None]

_PIPELINE_QUEUE = os.getenv("PIPELINE_QUEUE_NAME", "pipeline-jobs")
_TERMINAL_STATUSES = {"completed", "failed"}
_FAILED_RUN_STATUSES = frozenset({"failed", "poisoned", "cancelled", "paused"})


def _normalize_pipeline_status(status: str) -> str:
    if status in _FAILED_RUN_STATUSES:
        return "failed"
    return status


_LAB_EAGER_DURABLE_BOOTSTRAP = (
    os.getenv("VALIDATION_LAB_EAGER_DURABLE_BOOTSTRAP", "true").lower() != "false"
)

_GET_PIPELINE_RUN = """
MATCH (r:PipelineRun {id: $run_id})
RETURN r.status AS status, r.assessment_id AS assessment_id
"""

_GET_PIPELINE_RUN_BY_ADMISSION_KEY = """
MATCH (r:PipelineRun {admission_key: $admission_key})
RETURN r.id AS id
LIMIT 1
"""

# Legacy fallback for pre-cutover WorkflowEngine runs that only wrote
# :AuditEvent nodes. Durable plans use :PipelineRun via DurableStepRunner.
_GET_AUDIT_FALLBACK = """
MATCH (ae:AuditEvent) WHERE ae.id IN [$main_id, $sbar_id]
RETURN ae.id AS id, ae.status AS status, ae.assessment_id AS assessment_id
"""


def _wants_sbar(phase_ids: list[str]) -> bool:
    return any("sbar" in p.lower() or p.lower() == "summarisation" for p in phase_ids)


def build_pipeline_message(
    case: dict[str, Any],
    *,
    run_id: str,
    plan_id: str,
    dry_run: bool,
    ruleset_version: str | None = None,
) -> dict[str, Any]:
    """Build the same referral-received bus body real referrals use.

    `ruleset_version` is an optional per-run override so a candidate
    (unactivated) guideline ruleset can be tested against a real
    Validation Lab patient without touching the live "current version"
    pointer used by production traffic.
    """
    if case.get("case_type") == "ag" or case.get("communication_request_id"):
        body = build_communication_assessment_message(
            patient_id=case["patient_id"],
            communication_request_id=case.get("communication_request_id") or "",
            ubrn=case.get("ubrn") or case.get("case_id") or "",
            run_id=run_id,
            plan_definition_id=plan_id or "pd-referral-assessment",
            guideline_ruleset_version=ruleset_version,
            chunk_ids=list(case.get("chunk_ids") or []) or None,
            context={"case_id": case.get("id"), "source": "validation-lab"},
        )
        body["tenant_id"] = VALIDATION_LAB_TENANT_ID
        body["dry_run"] = dry_run
        body["capture_validation_output"] = True
        return body

    body = build_referral_received_message(
        patient_id=case["patient_id"],
        encounter_id=case.get("encounter_id") or "",
        referral_id=case.get("referral_id") or "",
        document_reference_id=case.get("document_reference_id") or "",
        chunk_ids=list(case.get("chunk_ids") or []),
        run_id=run_id,
        plan_definition_id=plan_id or "pd-referral-assessment",
        guideline_ruleset_version=ruleset_version,
        context={"case_id": case.get("id"), "source": "validation-lab"},
    )
    body["tenant_id"] = VALIDATION_LAB_TENANT_ID
    body["dry_run"] = dry_run
    body["capture_validation_output"] = True
    return body


def _run_coro_sync(coro_factory: Callable[[], Any]) -> Any:
    """Run a coroutine from sync code, even if an event loop is active."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro_factory())
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(lambda: asyncio.run(coro_factory())).result()


def default_publish(body: dict[str, Any], run_id: str) -> None:
    """Publish to the coding pipeline queue (same queue as the worker)."""
    from libs.message_bus.base import Message
    from libs.message_bus.factory import create_message_bus

    async def _send() -> None:
        bus = create_message_bus()
        try:
            await bus.send(
                _PIPELINE_QUEUE,
                Message(
                    body=body,
                    correlation_id=run_id,
                    subject=body.get("event_type") or "validation-lab",
                ),
            )
        finally:
            try:
                await bus.close()
            except BaseException:
                logger.debug("message bus close failed after publish", exc_info=True)

    _run_coro_sync(_send)


def _is_eager_bootstrap_source(body: dict[str, Any]) -> bool:
    ctx = body.get("context") if isinstance(body.get("context"), dict) else {}
    source = str(ctx.get("source") or "").strip()
    return source.startswith("validation-lab") or source == "patient-viewer"


def _is_validation_lab_source(body: dict[str, Any]) -> bool:
    ctx = body.get("context") if isinstance(body.get("context"), dict) else {}
    return str(ctx.get("source") or "").strip().startswith("validation-lab")


def bootstrap_durable_lab_run(body: dict[str, Any]) -> str | None:
    """Admit a Lab :PipelineRun immediately after publish.

    Before the durable cutover, the legacy WorkflowEngine handled
    ``referral-received`` in-process on the worker, so the UI saw progress
    within seconds. Durable plans defer admission to ``DurableStepRunner.start``,
    which only runs when the Service Bus consumer picks up the trigger message.
    On validation, a backed-up ``pipeline-jobs`` queue left Lab runs stuck at
    ``queued`` with empty ``stage_progress``.

    Core-api calls this right after enqueue so the Lab ``run_id`` gets a
    :PipelineRun before the first UI poll. The worker still consumes the
    trigger message idempotently (``claim_first_step_enqueue`` no-ops).

    Returns an error string on failure, or None when bootstrap ran or was skipped.
    """
    if not _LAB_EAGER_DURABLE_BOOTSTRAP:
        return None
    if not _is_eager_bootstrap_source(body):
        return None
    plan_id = str(body.get("plan_definition_id") or body.get("workflow_id") or "")
    from libs.workflow.durable_step_runner import (
        DurableStepRunner,
        is_durable_runner_enabled,
    )
    from libs.validation_lab.trace_events import build_trace_event, publish_run_trace

    if not is_durable_runner_enabled(plan_id):
        return None

    run_id = str(body.get("run_id") or "")
    publish_run_trace(
        run_id,
        build_trace_event(
            "lab.bootstrap.started",
            run_id,
            service="core-api",
            plan_id=plan_id,
            patient_id=str(body.get("patient_id") or ""),
        ),
    )

    async def _start() -> None:
        from libs.message_bus.factory import create_message_bus

        bus = create_message_bus()
        try:
            await DurableStepRunner.start(body, bus=bus, queue_name=_PIPELINE_QUEUE)
        finally:
            try:
                await bus.close()
            except BaseException:
                logger.debug(
                    "message bus close failed after lab durable bootstrap",
                    exc_info=True,
                )

    try:
        _run_coro_sync(_start)
        publish_run_trace(
            run_id,
            build_trace_event(
                "lab.bootstrap.completed",
                run_id,
                service="core-api",
                status="running",
                plan_id=plan_id,
                patient_id=str(body.get("patient_id") or ""),
            ),
        )
    except Exception as exc:
        logger.warning("validation_lab.durable_bootstrap failed: %s", exc)
        publish_run_trace(
            run_id,
            build_trace_event(
                "lab.bootstrap.failed",
                run_id,
                service="core-api",
                status="failed",
                plan_id=plan_id,
                error=str(exc),
            ),
        )
        return str(exc)
    return None


def first_pipeline_error(outputs: RunOutputs) -> str:
    """Return the first phase pipeline_error, if enqueue failed."""
    for row in outputs.phase_outputs or []:
        err = str(row.get("pipeline_error") or "").strip()
        if err:
            return err
    return ""


def execute_lab_run(
    client: Any,
    *,
    case: dict[str, Any],
    run_id: str,
    plan_id: str,
    phase_ids: list[str],
    persist_mode: PersistMode,
    publish: PublishFn | None = None,
    ruleset_version: str | None = None,
) -> RunOutputs:
    """Enqueue the real referral pipeline. Never fabricates output.

    Production mode: enqueues the real bus message and returns
    immediately with status "queued" phase rows -- the caller polls
    `poll_run_status` / `read_real_outputs` for the genuine result once
    the pipeline finishes.
    Dry-run mode: no enqueue, no graph writes -- phases are marked
    "skipped_persist" and there is nothing to poll.
    """
    _ = client  # kept for signature symmetry with other Lab entry points
    phases = [str(p) for p in phase_ids]
    dry = persist_mode is PersistMode.dry_run
    phase_outputs = [
        {
            "phase_id": p,
            "status": "skipped_persist" if dry else "queued",
            "persist_mode": persist_mode.value,
            "headline": f"Phase {p} ({persist_mode.value})",
        }
        for p in phases
    ]
    if not dry:
        body = build_pipeline_message(
            case,
            run_id=run_id,
            plan_id=plan_id,
            dry_run=False,
            ruleset_version=ruleset_version,
        )
        sender = publish if publish is not None else default_publish
        try:
            sender(body, run_id)
            for row in phase_outputs:
                row["pipeline_enqueued"] = True
        except Exception as exc:
            logger.warning("validation_lab.publish failed: %s", exc)
            for row in phase_outputs:
                row["pipeline_enqueued"] = False
                row["pipeline_error"] = str(exc)
    return RunOutputs(phase_outputs=phase_outputs)


def resolve_pipeline_run_id(
    client: Any,
    *,
    case: dict[str, Any],
    run: dict[str, Any],
    run_id: str,
) -> str:
    """Map a ValidationLabRun id to the live :PipelineRun id when they differ."""
    rows = client.run(_GET_PIPELINE_RUN, run_id=run_id)
    if rows:
        return run_id
    try:
        body = build_pipeline_message(
            case,
            run_id=run_id,
            plan_id=str(
                run.get("plan_id") or case.get("plan_id") or "pd-referral-assessment"
            ),
            dry_run=False,
            ruleset_version=run.get("ruleset_version"),
        )
        from libs.workflow.run_admission import build_admission_key

        admission_key = build_admission_key(body)
    except Exception:
        logger.debug(
            "resolve_pipeline_run_id failed for run_id=%s", run_id, exc_info=True
        )
        return run_id
    keyed = client.run(
        _GET_PIPELINE_RUN_BY_ADMISSION_KEY,
        admission_key=admission_key,
    )
    if keyed:
        resolved = str(keyed[0].get("id") or run_id)
        if resolved != run_id:
            logger.warning(
                "Validation Lab run_id=%s mapped to PipelineRun id=%s via admission_key",
                run_id,
                resolved,
            )
        return resolved
    return run_id


def poll_run_status(client: Any, run_id: str) -> dict[str, str]:
    """Read the real pipeline's status + assessment_id for a Lab run.

    Prefers :PipelineRun rows written by DurableStepRunner. Falls back to
    legacy :AuditEvent nodes for older in-process WorkflowEngine runs.
    """
    rows = client.run(_GET_PIPELINE_RUN, run_id=run_id)
    if rows:
        row = rows[0]
        return {
            "status": _normalize_pipeline_status(str(row.get("status") or "queued")),
            "assessment_id": str(row.get("assessment_id") or ""),
        }
    audit_rows = client.run(
        _GET_AUDIT_FALLBACK,
        main_id=f"audit-{run_id}",
        sbar_id=f"audit-{run_id}:sbar",
    )
    if not audit_rows:
        return {"status": "queued", "assessment_id": ""}
    by_id = {str(r.get("id")): r for r in audit_rows}
    main = by_id.get(f"audit-{run_id}") or {}
    sbar = by_id.get(f"audit-{run_id}:sbar") or {}
    return {
        "status": str(main.get("status") or sbar.get("status") or "queued"),
        "assessment_id": str(sbar.get("assessment_id") or ""),
    }


def list_stage_progress(client: Any, run_id: str) -> list[dict[str, str]]:
    """Return live :PipelineStageRun rows for a Lab / durable pipeline run."""
    rows = client.run(LIST_PIPELINE_STAGE_RUNS, run_id=run_id)
    out: list[dict[str, str]] = []
    for row in rows or []:
        step_id = str(row.get("step_id") or "").strip()
        if not step_id:
            continue
        errors = stage_errors_from_row(row)
        warnings = stage_warnings_from_row(row)
        out.append(
            {
                "step_id": step_id,
                "event_type": str(row.get("event_type") or ""),
                "status": str(row.get("status") or "pending"),
                "worker_id": str(row.get("worker_id") or ""),
                "started_at": str(row.get("started_at") or ""),
                "completed_at": str(row.get("completed_at") or ""),
                "errors": errors,
                "warnings": warnings,
                "error_summary": plain_english_pipeline_error(errors[0])
                if errors
                else "",
                "warning_summary": plain_english_pipeline_message(warnings[0])
                if warnings
                else "",
            }
        )
    return out


def attach_stage_progress(
    client: Any,
    packed: dict[str, Any],
    run_id: str,
    *,
    pipeline_run_id: str | None = None,
) -> dict[str, Any]:
    """Attach live durable stage rows onto a get_run / refresh payload."""
    progress_id = pipeline_run_id or run_id
    packed["run"]["stage_progress"] = list_stage_progress(client, progress_id)
    return packed


def _json_loads_safe(raw: Any) -> Any:
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


def _matching_rule_ids(raw: Any) -> list[str]:
    """Extract rule id strings from Assessment.assessment_rules.

    `sbar_orchestrator.py` persists this property as a single JSON string
    encoding a list of full rule objects (`json.dumps(narrative.rules)`),
    not a Neo4j string list. Treating it as an already-iterable list of
    strings silently iterates the JSON text character by character.
    """
    parsed = _json_loads_safe(raw)
    if not isinstance(parsed, list):
        return []
    ids: list[str] = []
    for rule in parsed:
        if isinstance(rule, dict):
            rule_id = str(rule.get("rule_id") or "").strip()
            if rule_id:
                ids.append(rule_id)
        else:
            candidate = str(rule).strip()
            if candidate:
                ids.append(candidate)
    return ids


def _llm_usage_from_assessment(row: dict[str, Any]) -> dict[str, Any]:
    """Copy real Assessment telemetry only when cost or tokens are present."""
    cost = float(row.get("llm_cost_usd") or 0.0)
    total_tokens = int(row.get("llm_total_tokens") or 0)
    calls = int(row.get("llm_calls") or 0)
    if cost <= 0 and total_tokens <= 0 and calls <= 0:
        return {}
    return {
        "input_tokens": int(row.get("llm_input_tokens") or 0),
        "output_tokens": int(row.get("llm_output_tokens") or 0),
        "cached_input_tokens": int(row.get("llm_cached_tokens") or 0),
        "total_tokens": total_tokens,
        "llm_calls": calls,
        "cost_usd": round(cost, 6),
        "latency_ms": int(row.get("llm_latency_ms") or 0),
        "model_id": str(row.get("llm_model_id") or ""),
        "model_provider": str(row.get("llm_model_provider") or ""),
    }


def read_real_outputs(client: Any, assessment_id: str) -> RunOutputs:
    """Read genuine extracted codes/rules/SBAR back from a real Assessment.

    Only fields that are honestly persisted by the real pipeline are
    populated. There is no structured "entities" readback today, so
    that gold group is intentionally left out of RunOutputs -- scoring
    against it would otherwise be ungrounded.
    """
    if not assessment_id:
        return RunOutputs()
    rows = client.run(GET_ASSESSMENT, assessment_id=assessment_id)
    if not rows:
        return RunOutputs()
    row = rows[0]
    completeness = _json_loads_safe(row.get("completeness_result_json"))
    return RunOutputs(
        snomed_codes=[str(c) for c in (row.get("assessment_codes") or [])],
        matching_rules=_matching_rule_ids(row.get("assessment_rules")),
        completeness=completeness if isinstance(completeness, dict) else {},
        sbar_assessment_id=assessment_id,
        sbar_markdown=str(row.get("content") or ""),
        llm_usage=_llm_usage_from_assessment(row),
    )
