"""Pause the extraction step when a form is not recognised.

An unrecognised form needs a person to teach it, so the step pauses with
reason ``form_not_recognised``. A failed recognition lookup means a safety
layer could not run, so the step is marked ``degraded`` (fail-closed rule
1). Errors on the step never switch this check off (rule 4).

The state match is read as well as the per-document rows, so a run whose
evidence list went missing still fails closed.

Atlas trace: UN-AF530E8E -> DI-E21DF9EF -> DO-E458EEC5 -> VT-B13F7C48.
Risk R-B88CCFD6. Fail-closed: DI-B7A69F26, DI-02AB393F.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from libs.form_recognition.recogniser import RecognitionFailed, Unrecognised
from libs.pipeline.form_schema_store import MATCH_FAILED, MATCH_UNRECOGNISED

FORM_NOT_RECOGNISED = "form_not_recognised"


@dataclass(frozen=True)
class RecognitionVerdict:
    unrecognised: bool
    failed: bool


def recognition_verdict(payload: dict[str, Any]) -> RecognitionVerdict:
    """Read the bundle's recognition from the rows and the state match."""
    rows = payload.get("form_recognition") or []
    outcomes = {str(row.get("outcome") or "") for row in rows if isinstance(row, dict)}
    match = str(payload.get("form_schema_match") or "")
    return RecognitionVerdict(
        unrecognised=Unrecognised.kind in outcomes or match == MATCH_UNRECOGNISED,
        failed=RecognitionFailed.kind in outcomes or match == MATCH_FAILED,
    )


def _with_reason(quality: Any) -> dict[str, Any]:
    merged = dict(quality) if isinstance(quality, dict) else {}
    reasons = [r for r in merged.get("quality_reasons") or [] if r]
    if FORM_NOT_RECOGNISED not in reasons:
        reasons.insert(0, FORM_NOT_RECOGNISED)
    merged["quality_reasons"] = reasons
    return merged


def apply_recognition_gate(
    payload: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """Return (payload, form_not_recognised). A failed lookup degrades."""
    verdict = recognition_verdict(payload)
    gated = dict(payload)
    if verdict.failed:
        gated["degraded"] = True
    if verdict.unrecognised:
        gated["document_quality"] = _with_reason(gated.get("document_quality"))
        gated["extraction_gate"] = "pause"
    return gated, verdict.unrecognised
