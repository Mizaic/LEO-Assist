"""Parse persisted pipeline stage errors for Validation Lab inspector."""

from __future__ import annotations

import json
import re
from typing import Any

_LOW_CONF_RE = re.compile(
    r"^terminology_low_confidence:\s*(\d+)\s+entity/entities below "
    r"score threshold ([0-9.]+)\s*--\s*(.+)$",
    re.DOTALL,
)
_TERM_SCORE_RE = re.compile(r'"([^"]+)"\s*\(score\s*([0-9.]+)\)')


def _loads_json(raw: Any) -> Any:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    return None


def stage_errors_from_row(row: dict[str, Any]) -> list[str]:
    """Return error strings stored on a :PipelineStageRun row."""
    parsed = _loads_json(row.get("errors_json"))
    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    output = _loads_json(row.get("output_json"))
    if isinstance(output, dict):
        out_errors = output.get("errors")
        if isinstance(out_errors, list):
            return [str(item).strip() for item in out_errors if str(item).strip()]
    return []


def plain_english_pipeline_error(error: str) -> str:
    """Turn a machine error string into clinician-readable text."""
    text = str(error or "").strip()
    if not text:
        return ""

    if text.startswith("terminology_low_confidence:"):
        match = _LOW_CONF_RE.match(text)
        if match:
            count = int(match.group(1))
            threshold_pct = round(float(match.group(2)) * 100)
            terms_blob = match.group(3)
            terms = _TERM_SCORE_RE.findall(terms_blob)
            if terms:
                parts = [
                    f'"{term}" ({round(float(score) * 100)}% match)'
                    for term, score in terms
                ]
                joined = ", ".join(parts)
                noun = "term" if count == 1 else "terms"
                return (
                    f"Could not map {count} clinical {noun} to SNOMED codes "
                    f"with enough confidence (need at least {threshold_pct}%): "
                    f"{joined}. The run stopped so unsafe codes are not applied "
                    f"automatically."
                )
        return (
            "One or more clinical terms could not be mapped to SNOMED codes "
            "with enough confidence. The run stopped so unsafe codes are not "
            "applied automatically."
        )

    if text.startswith("terminology:"):
        detail = text.split(":", 1)[1].strip()
        if "connection" in detail.lower() or "refused" in detail.lower():
            return (
                "The terminology service could not be reached. "
                "Check that the terminology API is running."
            )
        if detail:
            return f"Terminology lookup failed: {detail}."
        return "Terminology lookup failed."

    if text.startswith("stage_poisoned"):
        return "This step failed too many times and was stopped."

    return text
