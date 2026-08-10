"""Durable store for pipeline run and stage outputs.

Atlas trace:
  DO: DO-CE65B1F2
  DI: DI-36F80B95
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-36F80B95")
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from datetime import datetime, timezone

from libs.cypher.pipeline_stage_queries import (
    ADMIT_PIPELINE_RUN,
    ADMIT_VALIDATION_LAB_PIPELINE_RUN,
    CLAIM_FIRST_STEP_ENQUEUE,
    CLAIM_OUTBOX_EVENT_FOR_SEND,
    CLAIM_PIPELINE_STAGE_RUN,
    CLEAR_FIRST_STEP_ENQUEUE,
    COMPLETE_PIPELINE_STAGE_RUN,
    COUNT_OUTBOX_FOR_STAGE,
    ENSURE_OUTBOX_EVENT_CONSTRAINT,
    ENSURE_PIPELINE_RUN_ADMISSION_KEY_CONSTRAINT,
    ENSURE_PIPELINE_RUN_CONSTRAINT,
    ENSURE_PIPELINE_STAGE_CONSTRAINT,
    ENSURE_PIPELINE_STAGE_OUTBOX,
    GET_PENDING_OUTBOX_FOR_STAGE,
    GET_PIPELINE_RUN_STATUS,
    GET_PIPELINE_STAGE_OUTPUTS,
    GET_SENT_OUTBOX_FOR_STAGE,
    GET_STUCK_COMPLETED_STAGE_FOR_RUN,
    GET_SUCCESSOR_STAGE_STATUSES,
    GET_ZERO_STAGE_RUNNING_RUN,
    RESET_FIRST_STEP_FOR_RECOVERY,
    HAS_ANY_OUTBOX_FOR_STAGE,
    HAS_PENDING_OUTBOX_FOR_STAGE,
    MARK_OUTBOX_EVENT_SENT,
    MARK_STAGE_NEXT_PUBLISHED,
    RENEW_PIPELINE_STAGE_LEASE,
    START_PIPELINE_STAGE_RUN,
    UPSERT_PIPELINE_RUN,
)
from libs.workflow.durable_steps import StepRequest, StepResult
from libs.workflow.pipeline_outbox import build_successor_outbox_events

logger = logging.getLogger(__name__)

ClaimOutcome = Literal["claimed", "already_completed", "busy", "poisoned"]
CompleteOutcome = Literal["completed", "stale_lease"]

_STAGE_LEASE_SECONDS = max(60, int(os.getenv("PIPELINE_STAGE_LEASE_SECONDS", "3600")))
_TERMINAL_RUN_STATUSES = frozenset(
    {"completed", "failed", "cancelled", "poisoned", "paused"}
)
_TERMINAL_STAGE_FAILURE = frozenset({"failed", "poisoned", "paused"})


def _stage_max_attempts() -> int:
    return max(1, int(os.getenv("PIPELINE_STAGE_MAX_ATTEMPTS", "5")))


def _outbox_repair_cooldown_seconds() -> int:
    return max(15, int(os.getenv("PIPELINE_OUTBOX_REPAIR_COOLDOWN_SECONDS", "45")))


def _parse_sent_at(raw: Any) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    text = str(raw).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass(frozen=True)
class StageClaimResult:
    """Result of an atomic durable-stage claim."""

    outcome: ClaimOutcome
    output: dict[str, Any] = field(default_factory=dict)
    next_action_ids: list[str] = field(default_factory=list)
    next_published: bool = False
    lease_owner: str = ""
    lease_generation: int = 0


@dataclass(frozen=True)
class RunAdmissionResult:
    """Result of atomic run admission."""

    run_id: str
    created: bool
    first_step_enqueued: bool
    status: str


@dataclass(frozen=True)
class StageCompleteResult:
    """Result of a fenced stage completion."""

    outcome: CompleteOutcome
    outbox_created: int = 0


def stage_run_id(run_id: str, step_id: str) -> str:
    return f"{run_id}:{step_id}"


def _parse_json_dict(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _parse_json_list(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(item) for item in raw]
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]


class PipelineStageStore:
    def __init__(self, client: Any) -> None:
        self._client = client

    def ensure_schema(self) -> None:
        self._client.run(ENSURE_PIPELINE_RUN_CONSTRAINT)
        self._client.run(ENSURE_PIPELINE_RUN_ADMISSION_KEY_CONSTRAINT)
        self._client.run(ENSURE_PIPELINE_STAGE_CONSTRAINT)
        self._client.run(ENSURE_OUTBOX_EVENT_CONSTRAINT)

    def admit_run(
        self,
        request: StepRequest,
        *,
        admission_key: str,
        plan_version_id: str = "",
        policy_version: str = "",
        version_selection_reason: str = "",
        execution_manifest_json: str = "",
    ) -> RunAdmissionResult:
        source = str(request.context.get("source") or "")
        admit_query = (
            ADMIT_VALIDATION_LAB_PIPELINE_RUN
            if source.startswith("validation-lab") or source == "patient-viewer"
            else ADMIT_PIPELINE_RUN
        )
        rows = self._client.run(
            admit_query,
            admission_key=admission_key,
            run_id=request.run_id,
            workflow_id=request.workflow_id,
            plan_definition_id=request.plan_definition_id,
            patient_id=request.patient_id,
            encounter_id=request.encounter_id,
            source=request.context.get("source"),
            case_id=request.context.get("case_id"),
            parent_run_id=request.context.get("parent_run_id"),
            plan_version_id=plan_version_id or request.plan_version_id or "",
            policy_version=policy_version or request.policy_version or "",
            version_selection_reason=version_selection_reason,
            execution_manifest_json=execution_manifest_json,
        )
        row = (rows or [{}])[0] if rows else {}
        return RunAdmissionResult(
            run_id=str(row.get("run_id") or request.run_id),
            created=bool(row.get("created")),
            first_step_enqueued=bool(row.get("first_step_enqueued")),
            status=str(row.get("status") or "running"),
        )

    def claim_first_step_enqueue(self, run_id: str) -> bool:
        rows = self._client.run(CLAIM_FIRST_STEP_ENQUEUE, run_id=run_id)
        row = (rows or [{}])[0] if rows else {}
        return bool(row.get("enqueued"))

    def get_run_status(self, run_id: str) -> str:
        rows = self._client.run(GET_PIPELINE_RUN_STATUS, run_id=run_id)
        row = (rows or [{}])[0] if rows else {}
        return str(row.get("status") or "running")

    def is_run_terminal(self, run_id: str) -> bool:
        return self.get_run_status(run_id) in _TERMINAL_RUN_STATUSES

    def upsert_run(self, request: StepRequest, *, status: str = "running") -> None:
        self._client.run(
            UPSERT_PIPELINE_RUN,
            run_id=request.run_id,
            workflow_id=request.workflow_id,
            plan_definition_id=request.plan_definition_id,
            patient_id=request.patient_id,
            encounter_id=request.encounter_id,
            source=request.context.get("source"),
            case_id=request.context.get("case_id"),
            parent_run_id=request.context.get("parent_run_id"),
            admission_key=None,
            status=status,
        )

    def start_stage(self, request: StepRequest, input_state: dict[str, Any]) -> None:
        """Legacy unconditional start -- prefer claim_stage for workers."""
        self._client.run(
            START_PIPELINE_STAGE_RUN,
            run_id=request.run_id,
            stage_run_id=stage_run_id(request.run_id, request.step_id),
            step_id=request.step_id,
            event_type=request.event_type,
            attempt=request.attempt,
            input_json=json.dumps(input_state, default=str, sort_keys=True),
        )

    def claim_stage(
        self,
        request: StepRequest,
        input_state: dict[str, Any],
        *,
        lease_owner: str | None = None,
        lease_seconds: int | None = None,
    ) -> StageClaimResult:
        """Atomically claim a stage or report already_completed / busy."""
        owner = lease_owner or str(uuid.uuid4())
        rows = self._client.run(
            CLAIM_PIPELINE_STAGE_RUN,
            run_id=request.run_id,
            stage_run_id=stage_run_id(request.run_id, request.step_id),
            step_id=request.step_id,
            event_type=request.event_type,
            attempt=request.attempt,
            input_json=json.dumps(input_state, default=str, sort_keys=True),
            lease_owner=owner,
            lease_seconds=lease_seconds or _STAGE_LEASE_SECONDS,
            max_attempts=_stage_max_attempts(),
        )
        row = (rows or [{}])[0] if rows else {}
        outcome = str(row.get("outcome") or "busy")
        if outcome not in {"claimed", "already_completed", "busy", "poisoned"}:
            logger.warning("Unexpected claim outcome %r -- treating as busy", outcome)
            outcome = "busy"
        return StageClaimResult(
            outcome=outcome,  # type: ignore[arg-type]
            output=_parse_json_dict(row.get("output_json")),
            next_action_ids=_parse_json_list(row.get("next_action_ids_json")),
            next_published=bool(row.get("next_published")),
            lease_owner=str(row.get("lease_owner") or owner),
            lease_generation=int(row.get("lease_generation") or 0),
        )

    def renew_stage_lease(
        self,
        request: StepRequest,
        *,
        lease_owner: str,
        lease_generation: int,
        lease_seconds: int | None = None,
    ) -> bool:
        rows = self._client.run(
            RENEW_PIPELINE_STAGE_LEASE,
            stage_run_id=stage_run_id(request.run_id, request.step_id),
            lease_owner=lease_owner,
            lease_generation=lease_generation,
            lease_seconds=lease_seconds or _STAGE_LEASE_SECONDS,
        )
        return bool(rows)

    def complete_stage(
        self,
        request: StepRequest,
        result: StepResult,
        *,
        next_action_ids: list[str] | None = None,
        successor_edges: list[dict[str, Any]] | None = None,
        queue_name: str = "pipeline-jobs",
        body_template: dict[str, Any] | None = None,
        next_published: bool = False,
        lease_owner: str = "",
        lease_generation: int = 0,
    ) -> StageCompleteResult:
        stage_status = result.status
        if stage_status == "completed" and result.errors:
            stage_status = "failed"
        stage_failed = (
            stage_status in _TERMINAL_STAGE_FAILURE or bool(result.errors)
        )
        effective_next: list[str] = [] if stage_failed else list(next_action_ids or [])
        if stage_failed:
            run_status = "paused" if stage_status == "paused" else "failed"
        elif not result.next_event_type and not effective_next:
            run_status = "completed"
        else:
            run_status = "running"
        stage_id = stage_run_id(request.run_id, request.step_id)
        outbox_events: list[dict[str, str]] = []
        if effective_next:
            template = body_template or request.to_message(
                "durable_step", request.step_id
            )
            outbox_events = build_successor_outbox_events(
                request,
                stage_run_id=stage_id,
                next_action_ids=effective_next,
                successor_edges=successor_edges or [],
                queue_name=queue_name,
                body_template=template,
            )
        rows = self._client.run(
            COMPLETE_PIPELINE_STAGE_RUN,
            run_id=request.run_id,
            stage_run_id=stage_id,
            status=stage_status,
            run_status=run_status,
            assessment_id=result.output.get("sbar_assessment_id"),
            output_json=json.dumps(result.output, default=str, sort_keys=True),
            output_refs_json=json.dumps(
                result.output_refs, default=str, sort_keys=True
            ),
            errors_json=json.dumps(result.errors, default=str),
            warnings_json=json.dumps(result.warnings, default=str),
            metrics_json=json.dumps(result.metrics, default=str, sort_keys=True),
            next_action_ids_json=json.dumps(effective_next, default=str),
            next_published=bool(next_published),
            outbox_events=outbox_events,
            lease_owner=lease_owner,
            lease_generation=lease_generation,
        )
        row = (rows or [{}])[0] if rows else {}
        outcome = str(row.get("outcome") or "stale_lease")
        if outcome not in {"completed", "stale_lease"}:
            logger.warning("Unexpected complete outcome %r -- stale", outcome)
            outcome = "stale_lease"
        return StageCompleteResult(
            outcome=outcome,  # type: ignore[arg-type]
            outbox_created=int(row.get("outbox_created") or 0),
        )

    def load_pending_outbox(self, request: StepRequest) -> list[dict[str, Any]]:
        rows = self._client.run(
            GET_PENDING_OUTBOX_FOR_STAGE,
            stage_run_id=stage_run_id(request.run_id, request.step_id),
        )
        return [dict(row) for row in rows or [] if isinstance(row, dict)]

    def mark_outbox_sent(self, outbox_id: str, request: StepRequest) -> None:
        self._client.run(MARK_OUTBOX_EVENT_SENT, outbox_id=outbox_id)

    def try_claim_outbox_for_send(
        self, outbox_id: str, request: StepRequest
    ) -> dict[str, Any] | None:
        """Atomically move one pending outbox row to sent; return row or None."""
        rows = self._client.run(
            CLAIM_OUTBOX_EVENT_FOR_SEND,
            stage_run_id=stage_run_id(request.run_id, request.step_id),
            outbox_id=outbox_id,
        )
        row = (rows or [{}])[0] if rows else {}
        if not row or not row.get("id"):
            return None
        return dict(row)

    def has_pending_outbox(self, request: StepRequest) -> bool:
        rows = self._client.run(
            HAS_PENDING_OUTBOX_FOR_STAGE,
            stage_run_id=stage_run_id(request.run_id, request.step_id),
        )
        row = (rows or [{}])[0] if rows else {}
        return bool(row.get("has_pending"))

    def mark_next_published(self, request: StepRequest) -> None:
        self._client.run(
            MARK_STAGE_NEXT_PUBLISHED,
            stage_run_id=stage_run_id(request.run_id, request.step_id),
        )

    def successors_need_enqueue(self, run_id: str, next_action_ids: list[str]) -> bool:
        """Return True when a successor stage has not started or finished."""
        if not next_action_ids:
            return False
        rows = self._client.run(
            GET_SUCCESSOR_STAGE_STATUSES,
            run_id=run_id,
            step_ids=next_action_ids,
        )
        by_step = {
            str(row.get("step_id")): str(row.get("status") or "")
            for row in rows or []
            if isinstance(row, dict)
        }
        for step_id in next_action_ids:
            status = by_step.get(step_id)
            if status not in {"running", "completed"}:
                return True
        return False

    def has_stage_outbox(self, request: StepRequest) -> bool:
        rows = self._client.run(
            HAS_ANY_OUTBOX_FOR_STAGE,
            stage_run_id=stage_run_id(request.run_id, request.step_id),
        )
        row = (rows or [{}])[0] if rows else {}
        return bool(row.get("has_outbox"))

    def should_dispatch_successor_outbox(
        self,
        request: StepRequest,
        next_action_ids: list[str],
    ) -> bool:
        """Return True when pending successor outbox rows should be sent."""
        if not self.successors_need_enqueue(request.run_id, next_action_ids):
            return False
        return bool(self.load_pending_outbox(request))

    def should_repair_successor_outbox(
        self,
        request: StepRequest,
        next_action_ids: list[str],
        *,
        next_published: bool,
    ) -> bool:
        """Return True when missing outbox rows must be recreated."""
        if not self.successors_need_enqueue(request.run_id, next_action_ids):
            return False
        if self.load_pending_outbox(request):
            return False
        if not next_published:
            return True
        return not self.has_stage_outbox(request)

    def load_sent_outbox(self, request: StepRequest) -> list[dict[str, Any]]:
        rows = self._client.run(
            GET_SENT_OUTBOX_FOR_STAGE,
            stage_run_id=stage_run_id(request.run_id, request.step_id),
        )
        return [dict(row) for row in rows or [] if isinstance(row, dict)]

    def outbox_count(self, request: StepRequest) -> int:
        rows = self._client.run(
            COUNT_OUTBOX_FOR_STAGE,
            stage_run_id=stage_run_id(request.run_id, request.step_id),
        )
        row = (rows or [{}])[0] if rows else {}
        return int(row.get("outbox_count") or 0)

    def should_requeue_sent_orphan_outbox(
        self,
        request: StepRequest,
        next_action_ids: list[str],
        *,
        next_published: bool,
        now: datetime | None = None,
    ) -> bool:
        """Return True when sent outbox exists but successor stage never ran.

        Cooldown prevents message storms on already_completed replay.
        """
        if not next_published or not next_action_ids:
            return False
        if not self.successors_need_enqueue(request.run_id, next_action_ids):
            return False
        if self.load_pending_outbox(request):
            return False
        sent = self.load_sent_outbox(request)
        if not sent:
            return False
        clock = now or datetime.now(timezone.utc)
        cooldown = _outbox_repair_cooldown_seconds()
        newest: datetime | None = None
        for row in sent:
            stamped = _parse_sent_at(row.get("sent_at"))
            if stamped is None:
                continue
            if newest is None or stamped > newest:
                newest = stamped
        if newest is None:
            return True
        age = (clock - newest).total_seconds()
        return age >= cooldown

    def ensure_successor_outbox(
        self,
        request: StepRequest,
        *,
        next_action_ids: list[str],
        successor_edges: list[dict[str, Any]] | None = None,
        queue_name: str = "pipeline-jobs",
        body_template: dict[str, Any] | None = None,
        repair_generation: int = 0,
    ) -> int:
        """Recreate missing outbox rows for a completed stage."""
        stage_id = stage_run_id(request.run_id, request.step_id)
        template = body_template or request.to_message("durable_step", request.step_id)
        outbox_events = build_successor_outbox_events(
            request,
            stage_run_id=stage_id,
            next_action_ids=next_action_ids,
            successor_edges=successor_edges or [],
            queue_name=queue_name,
            body_template=template,
            repair_generation=repair_generation,
        )
        rows = self._client.run(
            ENSURE_PIPELINE_STAGE_OUTBOX,
            run_id=request.run_id,
            stage_run_id=stage_id,
            outbox_events=outbox_events,
        )
        row = (rows or [{}])[0] if rows else {}
        return int(row.get("outbox_ensured") or 0)

    def ensure_repair_successor_outbox(
        self,
        request: StepRequest,
        *,
        next_action_ids: list[str],
        successor_edges: list[dict[str, Any]] | None = None,
        queue_name: str = "pipeline-jobs",
        body_template: dict[str, Any] | None = None,
    ) -> int:
        """Mint new pending outbox rows for a sent-orphan successor gap."""
        generation = self.outbox_count(request) + 1
        return self.ensure_successor_outbox(
            request,
            next_action_ids=next_action_ids,
            successor_edges=successor_edges,
            queue_name=queue_name,
            body_template=body_template,
            repair_generation=generation,
        )

    def clear_first_step_enqueue(self, run_id: str) -> bool:
        """Clear first-step claim when zero stages exist after a failed publish."""
        rows = self._client.run(CLEAR_FIRST_STEP_ENQUEUE, run_id=run_id)
        return bool(rows)

    def load_stuck_completed_stage(self, run_id: str) -> dict[str, Any] | None:
        rows = self._client.run(GET_STUCK_COMPLETED_STAGE_FOR_RUN, run_id=run_id)
        row = (rows or [None])[0]
        return dict(row) if isinstance(row, dict) else None

    def load_zero_stage_running_run(self, run_id: str) -> dict[str, Any] | None:
        retry_after = max(
            15,
            int(os.getenv("STUCK_ZERO_STAGE_RETRY_SECONDS", "60")),
        )
        rows = self._client.run(
            GET_ZERO_STAGE_RUNNING_RUN,
            run_id=run_id,
            retry_after_seconds=retry_after,
        )
        row = (rows or [None])[0]
        return dict(row) if isinstance(row, dict) else None

    def reset_first_step_for_recovery(self, run_id: str) -> int | None:
        """Clear enqueue guard and bump recovery generation for a fresh SB message_id."""
        rows = self._client.run(RESET_FIRST_STEP_FOR_RECOVERY, run_id=run_id)
        row = (rows or [{}])[0] if rows else {}
        if not row:
            return None
        generation = row.get("recovery_generation")
        if generation is None:
            return None
        return int(generation)

    def load_accumulated_state(self, run_id: str) -> dict[str, Any]:
        rows = self._client.run(GET_PIPELINE_STAGE_OUTPUTS, run_id=run_id)
        state: dict[str, Any] = {}
        for row in rows or []:
            raw = row.get("output_json") if isinstance(row, dict) else None
            if not raw:
                continue
            try:
                output = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(output, dict):
                _merge_state(state, output)
        return state


def _merge_state(target: dict[str, Any], output: dict[str, Any]) -> None:
    for key, value in output.items():
        if key == "errors" and value:
            existing = list(target.get("errors") or [])
            for item in value:
                if item not in existing:
                    existing.append(item)
            target["errors"] = existing
            continue
        target[key] = value
