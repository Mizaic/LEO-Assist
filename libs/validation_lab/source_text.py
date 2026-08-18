"""Original letter text from a pipeline extract stage.

Atlas trace:
  DO: DO-3A70C3DD
  DI: DI-724CD8A5
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-3A70C3DD")

Atlas:
  DI: DI-562F2C9E / DI-C953EF73
  DO: DO-4FD76836
"""

from __future__ import annotations

import json
from typing import Any

_LETTER_KEYS = ("encounter_text", "referral_text", "source_text")


def source_text_from_stage_rows(stage_rows: list[dict[str, Any]]) -> str:
    """Prefer the extract step, then any stage that stored letter text."""
    rows = list(stage_rows or [])
    for row in rows:
        if not _is_extract_step(str(row.get("step_id") or "")):
            continue
        text = letter_from_extract_input(_as_dict(row.get("input_json")))
        if text:
            return text
    for row in rows:
        text = letter_from_extract_input(_as_dict(row.get("input_json")))
        if text:
            return text
    return ""


def letter_from_extract_input(payload: dict[str, Any]) -> str:
    blobs = [payload]
    nested = payload.get("context")
    if isinstance(nested, dict):
        blobs.append(nested)
    for blob in blobs:
        for key in _LETTER_KEYS:
            text = str(blob.get(key) or "").strip()
            if text:
                return text
        joined = _join_sentences(blob.get("sentences"))
        if joined:
            return joined
    return ""


def _is_extract_step(step_id: str) -> bool:
    sid = step_id.lower()
    return "extract" in sid


def _join_sentences(raw: Any) -> str:
    if not isinstance(raw, list):
        return ""
    parts: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            text = str(item.get("text") or "").strip()
        else:
            text = str(item or "").strip()
        if text:
            parts.append(text)
    return "\n\n".join(parts)


def _as_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw or not isinstance(raw, str):
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}
