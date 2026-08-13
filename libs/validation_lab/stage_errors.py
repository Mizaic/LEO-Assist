"""Parse persisted pipeline stage errors for Validation Lab inspector.

Auto-stamped Atlas trace.

Atlas trace:
  DO: DO-158BE606
  DI: DI-2289D095
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-158BE606")
"""

from __future__ import annotations

import json
import re
from typing import Any

from libs.sbar.error_messages import KNOWN_ERROR_CODES, SBAR_STAGE_NAMES

_LOW_CONF_RE = re.compile(
    r"^terminology_low_confidence:\s*(\d+)\s+entity/entities below "
    r"score threshold ([0-9.]+)\s*--\s*(.+)$",
    re.DOTALL,
)
_TERM_SCORE_RE = re.compile(r'"([^"]+)"\s*\(score\s*([0-9.]+)\)')
_NOT_CODEABLE_RE = re.compile(
    r"^coding_verifier:\s*(\d+)\s+(entity|entities)\s+classified not_codeable$"
)


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


def _strings_from_json_list(raw: Any) -> list[str]:
    parsed = _loads_json(raw)
    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    return []


def stage_errors_from_row(row: dict[str, Any]) -> list[str]:
    """Return error strings stored on a :PipelineStageRun row."""
    parsed = _strings_from_json_list(row.get("errors_json"))
    if parsed:
        return parsed
    output = _loads_json(row.get("output_json"))
    if isinstance(output, dict):
        return _strings_from_json_list(output.get("errors"))
    return []


def stage_warnings_from_row(row: dict[str, Any]) -> list[str]:
    """Return warning strings stored on a :PipelineStageRun row."""
    parsed = _strings_from_json_list(row.get("warnings_json"))
    if parsed:
        return parsed
    output = _loads_json(row.get("output_json"))
    if isinstance(output, dict):
        return _strings_from_json_list(output.get("warnings"))
    return []


def _sbar_pipeline_message(raw: str) -> str | None:
    """Strip SBAR stage prefixes and keep the classified reason."""
    stage, sep, rest = raw.partition(":")
    if not sep or stage not in SBAR_STAGE_NAMES:
        return None
    code, code_sep, message = rest.partition(":")
    if code_sep and code in KNOWN_ERROR_CODES:
        return message.strip() or rest.strip()
    return rest.strip() or raw


def plain_english_pipeline_message(text: str) -> str:
    """Turn a machine error or warning string into clinician-readable text."""
    raw = str(text or "").strip()
    if not raw:
        return ""

    sbar_text = _sbar_pipeline_message(raw)
    if sbar_text is not None:
        return sbar_text

    if raw.startswith("terminology_low_confidence:"):
        match = _LOW_CONF_RE.match(raw)
        if match:
            count = int(match.group(1))
            threshold_pct = round(float(match.group(2)) * 100)
            terms_blob = match.group(3)
            terms = _TERM_SCORE_RE.findall(terms_blob)
            if terms:
                parts = [
                    (
                        f'"{term}" ({round(float(score) * 100)}% match)'
                        if float(score) > 0
                        else f'"{term}" (no SNOMED match found)'
                    )
                    for term, score in terms
                ]
                joined = ", ".join(parts)
                noun = "term" if count == 1 else "terms"
                return (
                    f"Could not map {count} clinical {noun} to SNOMED codes "
                    f"with enough confidence (need at least {threshold_pct}%): "
                    f"{joined}. Those terms were left uncoded."
                )
        return (
            "One or more clinical terms could not be mapped to SNOMED codes "
            "with enough confidence. Those terms were left uncoded."
        )

    if raw.startswith("coding_verifier:") and "not_codeable" in raw:
        match = _NOT_CODEABLE_RE.match(raw)
        if match:
            count = int(match.group(1))
            noun = "term" if count == 1 else "terms"
            return (
                f"{count} extracted {noun} were not coded because they are "
                f"descriptors or overlap another finding."
            )
        return (
            "Some extracted terms were not coded because they are descriptors "
            "or overlap another finding."
        )

    if raw.startswith("terminology:"):
        detail = raw.split(":", 1)[1].strip()
        if "connection" in detail.lower() or "refused" in detail.lower():
            return (
                "The terminology service could not be reached. "
                "Check that the terminology API is running."
            )
        if detail:
            return f"Terminology lookup failed: {detail}."
        return "Terminology lookup failed."

    if raw.startswith("coding_verifier:") and "gate_failed" in raw:
        return (
            "The coding checker could not verify one or more SNOMED matches. "
            "Human review is required."
        )

    if raw.startswith("stage_poisoned"):
        return "This step failed too many times and was stopped."

    return raw


def plain_english_pipeline_error(error: str) -> str:
    """Backward-compatible alias for error strings."""
    return plain_english_pipeline_message(error)
