"""Production-shaped Lab run helpers (bus message + real run polling).

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

from libs.cypher.sbar_assessment_queries import GET_ASSESSMENT
from libs.referral_simulator.message import (
    build_communication_assessment_message,
    build_referral_received_message,
)
from libs.validation_lab.gold import RunOutputs
from libs.validation_lab.models import PersistMode

logger = logging.getLogger(__name__)

PublishFn = Callable[[dict[str, Any], str], None]

_PIPELINE_QUEUE = os.getenv("PIPELINE_QUEUE_NAME", "pipeline-jobs")
_TERMINAL_STATUSES = {"completed", "failed"}

_GET_PIPELINE_RUN = """
MATCH (r:PipelineRun {id: $run_id})
RETURN r.status AS status, r.assessment_id AS assessment_id
"""

# Legacy fallback when DURABLE_ENGINE_ENABLED=false -- see
# services/api/app/routers/sbar.py::_normalise_audit_fallback for the
# full explanation of why :AuditEvent nodes are the only trace in that
# mode.
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


def poll_run_status(client: Any, run_id: str) -> dict[str, str]:
    """Read the real pipeline's status + assessment_id for a Lab run.

    Falls back to legacy :AuditEvent nodes when DurableStepRunner is
    disabled (DURABLE_ENGINE_ENABLED=false), same as the SBAR router's
    child-run polling.
    """
    rows = client.run(_GET_PIPELINE_RUN, run_id=run_id)
    if rows:
        row = rows[0]
        return {
            "status": str(row.get("status") or "queued"),
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


def _json_loads_safe(raw: Any) -> Any:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


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
        matching_rules=[str(r) for r in (row.get("assessment_rules") or [])],
        completeness=completeness if isinstance(completeness, dict) else {},
        sbar_assessment_id=assessment_id,
        sbar_markdown=str(row.get("content") or ""),
    )
