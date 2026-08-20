"""Pause and unlock referral extraction when document quality is low.

Atlas trace:
  DI: DI-4A012A59
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-4A012A59")
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from libs.pipeline.document_quality import DocumentQuality, form_fingerprint
from libs.pipeline.extraction_learning_store import persist_review_learning
from libs.utils.deidentify import deidentify_text

DEFAULT_QUALITY_THRESHOLD = 0.6
TASK_TYPE = "extraction_quality_review"


@dataclass(frozen=True)
class GateDecision:
    action: str
    draft_entities: list[dict[str, Any]] = field(default_factory=list)
    next_event_type: str | None = "post_processing_requested"


@dataclass(frozen=True)
class ReviewComplete:
    entities: list[dict[str, Any]]
    few_shot: dict[str, Any]
    form_fingerprint_id: str
    resume_once: bool = True
    next_event_type: str = "post_processing_requested"


def generic_hitl_resolve_allowed(task_type: str) -> bool:
    return task_type != TASK_TYPE


def is_stage_pause_not_failure(result: Any) -> bool:
    status = getattr(result, "status", "") or ""
    errors = getattr(result, "errors", None) or []
    return status == "paused" and not errors


def decide_extraction_gate(
    quality: DocumentQuality,
    *,
    draft_entities: list[dict[str, Any]] | None = None,
    threshold: float = DEFAULT_QUALITY_THRESHOLD,
) -> GateDecision:
    draft = list(draft_entities or [])
    if quality.document_quality_score >= threshold:
        return GateDecision(action="continue", draft_entities=draft)
    return GateDecision(action="pause", draft_entities=draft, next_event_type=None)


def complete_extraction_review(
    *,
    source_text: str,
    draft_entities: list[dict[str, Any]],
    reviewed_entities: list[dict[str, Any]],
    known_fingerprints: dict[str, str] | None = None,
) -> ReviewComplete:
    _ = draft_entities
    _ = known_fingerprints
    clean = deidentify_text(source_text or "")
    fingerprint = form_fingerprint(source_text or "")
    few_shot = {
        "input": clean,
        "output": json.dumps({"terms": reviewed_entities}, ensure_ascii=True),
        "deidentified": True,
        "category": "form:checkbox",
        "fingerprint": fingerprint,
    }
    persist_review_learning(
        fingerprint_name=f"learned-{fingerprint}",
        fingerprint=fingerprint,
        few_shot=few_shot,
    )
    return ReviewComplete(
        entities=list(reviewed_entities),
        few_shot=few_shot,
        form_fingerprint_id=fingerprint,
    )


def build_review_task(
    *,
    run_id: str,
    patient_id: str,
    quality: DocumentQuality,
    draft_entities: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "task_type": TASK_TYPE,
        "status": "pending",
        "run_id": run_id,
        "patient_id": patient_id,
        "reason": ",".join(quality.quality_reasons) or "low_document_quality",
        "priority": 10,
        "document_quality_score": quality.document_quality_score,
        "draft_count": len(draft_entities or []),
    }


def apply_gate_to_step_output(
    output: dict[str, Any],
    quality: DocumentQuality,
    *,
    threshold: float = DEFAULT_QUALITY_THRESHOLD,
) -> dict[str, Any]:
    decision = decide_extraction_gate(
        quality,
        draft_entities=list(output.get("entities") or []),
        threshold=threshold,
    )
    merged = dict(output)
    merged["document_quality"] = quality.to_dict()
    merged["extraction_gate"] = decision.action
    return {"decision": decision, "output": merged}
