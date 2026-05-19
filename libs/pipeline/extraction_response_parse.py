"""Parse LLM responses for clinical term extraction (JSON + safe fallbacks).

Atlas trace:
  DO: DO-16CE412B
  DI: DI-FE1BC901
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-16CE412B")

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

ParseSource = Literal[
    "empty_input", "json_ok", "json_salvaged", "prose_empty", "failed"
]


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


def _decode_json_string(value: str) -> str:
    try:
        return str(json.loads(f'"{value}"'))
    except json.JSONDecodeError:
        return value


def _term_from_fragment(fragment: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(fragment)
        if isinstance(parsed, dict) and str(parsed.get("text") or "").strip():
            return parsed
    except json.JSONDecodeError:
        pass

    term: dict[str, Any] = {}
    for key, value in re.findall(
        r'"(sentence_id|text|lookup_term|semantic_tag|assertion)"\s*:\s*"((?:\\.|[^"\\])*)"',
        fragment,
    ):
        term[key] = _decode_json_string(value)
    confidence = re.search(r'"confidence"\s*:\s*([0-9]+(?:\.[0-9]+)?)', fragment)
    if confidence:
        term["confidence"] = float(confidence.group(1))
    return term if str(term.get("text") or "").strip() else None


def _term_fragments(raw: str) -> list[str]:
    match = re.search(r'"terms"\s*:\s*\[', raw)
    if not match:
        return []
    fragments: list[str] = []
    start: int | None = None
    depth = 0
    in_string = False
    escaped = False
    for idx, char in enumerate(raw[match.end() :], start=match.end()):
        if in_string:
            escaped = char == "\\" and not escaped
            if char == '"' and not escaped:
                in_string = False
            elif char != "\\":
                escaped = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = idx
            depth += 1
        elif char == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                fragments.append(raw[start : idx + 1])
                start = None
    if start is not None:
        fragments.append(raw[start:])
    return fragments


def _salvage_terms_payload(raw: str) -> dict[str, Any] | None:
    terms = []
    for fragment in _term_fragments(raw):
        term = _term_from_fragment(fragment)
        if term is not None:
            terms.append(term)
    return {"terms": terms} if terms else None


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
    * ``json_salvaged`` -- recovered complete term fields from malformed JSON.
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
    salvaged = _salvage_terms_payload(cleaned)
    if salvaged is not None:
        logger.info("Recovered extraction terms from malformed LLM JSON")
        return salvaged, "json_salvaged"
    if _looks_like_no_entities_prose(original):
        logger.info("LLM returned prose instead of JSON; treating as empty extraction")
        return {"terms": []}, "prose_empty"
    return {}, "failed"
