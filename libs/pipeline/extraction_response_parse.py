"""Parse LLM responses for clinical term extraction (JSON + safe fallbacks).

Models sometimes return markdown prose (e.g. "No codable clinical entities")
instead of strict JSON. This module normalises those cases so callers can treat
an empty extraction consistently without logging spurious JSON errors.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal

logger = logging.getLogger(__name__)

ParseSource = Literal["empty_input", "json_ok", "prose_empty", "failed"]


def _strip_markdown_fences(raw: str) -> str:
    s = raw.strip()
    if s.startswith("```"):
        lines = s.splitlines()
        if len(lines) >= 2:
            inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
            return "\n".join(inner).strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", s)
    if m:
        return m.group(1).strip()
    return s


def _try_load_json_object(raw: str) -> dict[str, Any] | None:
    s = raw.strip()
    if not s.startswith("{"):
        idx = s.find("{")
        if idx >= 0:
            s = s[idx:]
    try:
        out = json.loads(s)
        return out if isinstance(out, dict) else None
    except json.JSONDecodeError:
        pass
    end = s.rfind("}")
    if end > 0:
        try:
            out = json.loads(s[: end + 1])
            return out if isinstance(out, dict) else None
        except json.JSONDecodeError:
            pass
    return None


def _looks_like_no_entities_prose(text: str) -> bool:
    low = text.lower()
    needles = (
        "no codable clinical entities",
        "no clinical entities identified",
        "no codable entities",
        "no entities to extract",
        "no extractable clinical",
        "no codable clinical entity",
    )
    return any(n in low for n in needles)


def parse_extraction_terms_response(raw: str) -> tuple[dict[str, Any], ParseSource]:
    """Return a terms payload dict and how it was obtained.

    * ``empty_input`` -- empty string; returns ``{}`` (legacy behaviour).
    * ``json_ok`` -- parsed JSON object; ``terms`` key added if missing.
    * ``prose_empty`` -- markdown / prose indicating nothing to code; ``{"terms": []}``.
    * ``failed`` -- unrecoverable; returns ``{}``.
    """
    if not raw:
        return {}, "empty_input"
    original = raw
    cleaned = _strip_markdown_fences(original)
    data = _try_load_json_object(cleaned)
    if data is not None:
        if "terms" not in data:
            data["terms"] = []
        return data, "json_ok"
    if _looks_like_no_entities_prose(original):
        logger.info("LLM returned prose instead of JSON; treating as empty extraction")
        return {"terms": []}, "prose_empty"
    return {}, "failed"
