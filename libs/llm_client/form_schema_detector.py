"""LLM-powered form structure detection for referral form schema teaching.

Sends the raw form text to the big-tier LLM once and returns proposed
FormSchema sections -- including clinical entity text for each checkbox item.

The clinician reviews and corrects the proposals in the UI before saving.

Atlas trace: DI-5C9CA57B, DO-D0C19842
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from libs.llm_client.factory import create_llm
from libs.llm_client.prompt_safety import (
    INJECTION_GUARD,
    cap_llm_response,
    sanitise_for_prompt,
)
from libs.pipeline.form_section_splitter import (
    is_incomplete_schema,
    split_form_sections,
)

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = INJECTION_GUARD + """
You are a clinical form structure analyser for NHS referral forms.
Given raw referral form text, identify every distinct section and classify it.

SECTION TYPES -- choose exactly one per section:
- checkbox_single  : Options where ONE is checked (e.g. cancer type tick-boxes)
- checkbox_yesno   : Each criterion has a Yes/No pair (e.g. B1 Yes [X] No [ ])
- scale            : Numbered/labelled scale, one item selected (Frailty, ECOG)
- free_text        : Narrative clinical prose -- ALWAYS PRESERVE for the LLM
- ordered_tests    : Table of test names with empty result fields -- SUPPRESS
- template_noise   : Admin decision trees, patient awareness boxes -- SUPPRESS
- admin            : Patient demographics, practice details -- SUPPRESS

ITEMS (only for checkbox_single, checkbox_yesno, scale):
For each option provide:
  "pattern"     : the exact label text before the box, e.g. "Cervix"
  "entity_text" : CLINICAL meaning when checked, e.g. "Cervical cancer suspected"
  "semantic_tag": always "finding"
  "assertion"   : always "present"

Use precise clinical language for entity_text. Examples:
  "Cervix"      in cancer referral  -> "Cervical cancer suspected"
  "Ovary"       in cancer referral  -> "Ovarian cancer suspected"
  "Endometrium" in cancer referral  -> "Endometrial cancer suspected"
  "1. Very Fit" in frailty scale    -> "Clinical Frailty Scale: 1 - Very Fit"
  B1 lesion suspicious...           -> "Suspicious lesion on cervix or vagina"

Return one JSON object matching the supplied schema. No prose.
"""

_MAX_FORM_CHARS = 6000
_MAX_RESPONSE_CHARS = 16000
_MAX_TOKENS = 2048

_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["sections"],
    "properties": {
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "section_id",
                    "label",
                    "section_type",
                    "start_pattern",
                    "items",
                ],
                "properties": {
                    "section_id": {"type": "string"},
                    "label": {"type": "string"},
                    "section_type": {"type": "string"},
                    "start_pattern": {"type": "string"},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": [
                                "pattern",
                                "entity_text",
                                "semantic_tag",
                                "assertion",
                            ],
                            "properties": {
                                "pattern": {"type": "string"},
                                "entity_text": {"type": "string"},
                                "semantic_tag": {"type": "string"},
                                "assertion": {"type": "string"},
                            },
                        },
                    },
                },
            },
        }
    },
}


def detect_form_sections(text: str) -> list[dict[str, Any]]:
    """Call the big-tier LLM once to detect form sections.

    If the model is missing, the parse is empty, or the result is only
    admin / skip sections, fall back to the deterministic splitter so
    Section A / B on a table-wrapped form still appear.
    """
    cleaned = sanitise_for_prompt(text, max_chars=_MAX_FORM_CHARS)
    sections: list[dict[str, Any]] = []
    try:
        response = _call_detector(cleaned)
        sections = _parse_response(response.text or "") or []
    except Exception:
        log.warning("form-detect: LLM call failed", exc_info=True)
    if is_incomplete_schema(sections):
        fallback = split_form_sections(text)
        if not is_incomplete_schema(fallback):
            log.info("form-detect: splitter fallback found %d sections", len(fallback))
            return fallback
    log.info("form-detect: %d sections detected by LLM", len(sections))
    return sections


def _call_detector(form_text: str) -> Any:
    client = create_llm(tier="big")
    return client.converse(
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": form_text}],
        temperature=0.0,
        max_tokens=_MAX_TOKENS,
        json_mode=True,
        structured_schema=_OUTPUT_SCHEMA,
        agent_task="form_schema_detect",
    )


def _parse_response(text: str) -> list[dict[str, Any]] | None:
    """Extract and validate the sections list from the LLM response."""
    cleaned = cap_llm_response(text, max_chars=_MAX_RESPONSE_CHARS)
    cleaned = re.sub(r"```(?:json)?|```", "", cleaned).strip()
    parsed = _load_json(cleaned)
    if parsed is None:
        return None
    sections = parsed.get("sections") if isinstance(parsed, dict) else parsed
    if not isinstance(sections, list) or not sections:
        return None
    return [_validate_section(s) for s in sections if isinstance(s, dict)]


def _load_json(cleaned: str) -> Any | None:
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}|\[.*\]", cleaned, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return None


def _validate_section(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "section_id": str(raw.get("section_id", "?")),
        "label": str(raw.get("label", "")),
        "section_type": str(raw.get("section_type", "free_text")),
        "start_pattern": str(raw.get("start_pattern", "")),
        "items": [
            _validate_item(i) for i in raw.get("items", []) if isinstance(i, dict)
        ],
    }


def _validate_item(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "pattern": str(raw.get("pattern", "")),
        "entity_text": str(raw.get("entity_text", "")),
        "semantic_tag": str(raw.get("semantic_tag", "finding")),
        "assertion": str(raw.get("assertion", "present")),
    }
