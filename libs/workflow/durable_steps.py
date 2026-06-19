"""Reusable contract for durable pub/sub workflow steps.

Durable steps receive IDs and scope, reload their inputs from Neo4j, persist
their output, and publish the next event. They are intentionally small so the
same step can be reused by multiple PlanDefinitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

StepStatus = Literal["completed", "failed", "paused", "skipped"]


@dataclass(frozen=True)
class StepRequest:
    event_type: str
    run_id: str
    workflow_id: str
    step_id: str
    patient_id: str
    encounter_id: str = ""
    plan_definition_id: str = ""
    tenant_id: str | None = None
    requested_by: str | None = None
    source_node_type: str | None = None
    source_node_id: str | None = None
    source_text_property: str | None = None
    guideline_id: str | None = None
    guideline_ids: list[str] = field(default_factory=list)
    completeness_domain: str | None = None
    completeness_subdomain: str | None = None
    attempt: int = 1
    context: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_message(cls, body: dict[str, Any]) -> "StepRequest":
        from libs.pipeline.document_chunk_loader import merge_referral_message_fields

        context = merge_referral_message_fields(body)
        raw_ids = body.get("guideline_ids") or context.get("guideline_ids") or []
        guideline_ids = list(raw_ids) if isinstance(raw_ids, list) else []
        if not guideline_ids:
            legacy = body.get("guideline_id") or context.get("guideline_id")
            if legacy:
                guideline_ids = [str(legacy)]
        guideline_id = guideline_ids[0] if guideline_ids else None
        return cls(
            event_type=str(body.get("event_type") or ""),
            run_id=str(body.get("run_id") or context.get("run_id") or ""),
            workflow_id=str(
                body.get("workflow_id")
                or context.get("workflow_id")
                or body.get("plan_definition_id")
                or context.get("plan_definition_id")
                or ""
            ),
            step_id=str(body.get("step_id") or context.get("step_id") or ""),
            patient_id=str(body.get("patient_id") or context.get("patient_id") or ""),
            encounter_id=str(
                body.get("encounter_id") or context.get("encounter_id") or ""
            ),
            plan_definition_id=str(
                body.get("plan_definition_id")
                or context.get("plan_definition_id")
                or body.get("workflow_id")
                or context.get("workflow_id")
                or ""
            ),
            tenant_id=body.get("tenant_id") or context.get("tenant_id"),
            requested_by=body.get("requested_by") or context.get("requested_by"),
            source_node_type=body.get("source_node_type")
            or context.get("source_node_type"),
            source_node_id=body.get("source_node_id") or context.get("source_node_id"),
            source_text_property=body.get("source_text_property")
            or context.get("source_text_property"),
            guideline_id=guideline_id,
            guideline_ids=guideline_ids,
            completeness_domain=body.get("completeness_domain")
            or context.get("completeness_domain"),
            completeness_subdomain=body.get("completeness_subdomain")
            or context.get("completeness_subdomain"),
            attempt=int(body.get("attempt") or context.get("attempt") or 1),
            context=context,
        )

    def to_message(self, event_type: str, step_id: str) -> dict[str, Any]:
        return {
            "event_type": event_type,
            "run_id": self.run_id,
            "workflow_id": self.workflow_id,
            "plan_definition_id": self.plan_definition_id,
            "step_id": step_id,
            "patient_id": self.patient_id,
            "encounter_id": self.encounter_id,
            "tenant_id": self.tenant_id,
            "requested_by": self.requested_by,
            "source_node_type": self.source_node_type,
            "source_node_id": self.source_node_id,
            "source_text_property": self.source_text_property,
            "guideline_ids": list(self.guideline_ids),
            "guideline_id": self.guideline_id,
            "completeness_domain": self.completeness_domain,
            "completeness_subdomain": self.completeness_subdomain,
            "attempt": 1,
            "context": dict(self.context),
            "chunk_ids": list(self.context.get("chunk_ids") or []),
            "document_reference_id": self.context.get("document_reference_id"),
            "text_segmentation_mode": self.context.get("text_segmentation_mode"),
        }


@dataclass(frozen=True)
class StepResult:
    status: StepStatus
    output: dict[str, Any] = field(default_factory=dict)
    output_refs: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    next_event_type: str | None = None
    next_step_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "output": self.output,
            "output_refs": self.output_refs,
            "warnings": self.warnings,
            "errors": self.errors,
            "metrics": self.metrics,
            "next_event_type": self.next_event_type,
            "next_step_id": self.next_step_id,
        }


class DurableWorkflowStep(Protocol):
    step_id: str
    event_type: str

    def load(self, request: StepRequest) -> dict[str, Any]:
        """Load all inputs for this step from durable stores."""

    def run(self, request: StepRequest, loaded: dict[str, Any]) -> StepResult:
        """Run the clinical/business logic for this step."""

    def persist(self, request: StepRequest, result: StepResult) -> StepResult:
        """Persist the step output and return persisted refs."""
