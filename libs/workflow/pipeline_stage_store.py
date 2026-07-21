"""Durable store for pipeline run and stage outputs.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")
"""

from __future__ import annotations

import json
from typing import Any

from libs.cypher.pipeline_stage_queries import (
    COMPLETE_PIPELINE_STAGE_RUN,
    ENSURE_PIPELINE_RUN_CONSTRAINT,
    ENSURE_PIPELINE_STAGE_CONSTRAINT,
    GET_PIPELINE_STAGE_OUTPUTS,
    START_PIPELINE_STAGE_RUN,
    UPSERT_PIPELINE_RUN,
)
from libs.workflow.durable_steps import StepRequest, StepResult


def stage_run_id(run_id: str, step_id: str) -> str:
    return f"{run_id}:{step_id}"


class PipelineStageStore:
    def __init__(self, client: Any) -> None:
        self._client = client

    def ensure_schema(self) -> None:
        self._client.run(ENSURE_PIPELINE_RUN_CONSTRAINT)
        self._client.run(ENSURE_PIPELINE_STAGE_CONSTRAINT)

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
            status=status,
        )

    def start_stage(self, request: StepRequest, input_state: dict[str, Any]) -> None:
        self._client.run(
            START_PIPELINE_STAGE_RUN,
            run_id=request.run_id,
            stage_run_id=stage_run_id(request.run_id, request.step_id),
            step_id=request.step_id,
            event_type=request.event_type,
            attempt=request.attempt,
            input_json=json.dumps(input_state, default=str, sort_keys=True),
        )

    def complete_stage(self, request: StepRequest, result: StepResult) -> None:
        run_status = "completed" if not result.next_event_type else "running"
        if result.status in {"failed", "paused"}:
            run_status = result.status
        self._client.run(
            COMPLETE_PIPELINE_STAGE_RUN,
            run_id=request.run_id,
            stage_run_id=stage_run_id(request.run_id, request.step_id),
            status=result.status,
            run_status=run_status,
            assessment_id=result.output.get("sbar_assessment_id"),
            output_json=json.dumps(result.output, default=str, sort_keys=True),
            output_refs_json=json.dumps(
                result.output_refs, default=str, sort_keys=True
            ),
            errors_json=json.dumps(result.errors, default=str),
            warnings_json=json.dumps(result.warnings, default=str),
            metrics_json=json.dumps(result.metrics, default=str, sort_keys=True),
        )

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
