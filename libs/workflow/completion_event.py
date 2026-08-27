"""Minimal Service Bus completion event payload for durable pipelines.

Atlas trace:
  DO: DO-CE65B1F2
  DI: DI-36F80B95
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-CE65B1F2")

External completion messages must not carry clinical record content or
patient identifiers beyond the referral UBRN. Host products fetch the
SBAR via the assessment id through authenticated APIs.
"""

from __future__ import annotations

from typing import Any

from libs.workflow.durable_steps import StepRequest, StepResult


def resolve_ubrn(request: StepRequest) -> str:
    """Return the referral UBRN when present on the step request context."""
    context = request.context or {}
    return str(context.get("ubrn") or "").strip()


def resolve_assessment_id(output: dict[str, Any] | None) -> str:
    """Return the persisted assessment id from durable step output."""
    raw = output or {}
    for key in ("sbar_assessment_id", "assessment_id"):
        value = str(raw.get(key) or "").strip()
        if value:
            return value
    return ""


def build_completion_event_body(
    *,
    event_type: str,
    request: StepRequest,
    result: StepResult,
) -> dict[str, Any]:
    """Build the external completion payload without clinical record content."""
    body: dict[str, Any] = {
        "event_type": event_type,
        "run_id": request.run_id,
    }
    ubrn = resolve_ubrn(request)
    if ubrn:
        body["ubrn"] = ubrn
    assessment_id = resolve_assessment_id(result.output)
    if assessment_id:
        body["assessment_id"] = assessment_id
    return body
