"""Shared privacy and prompt-injection guards for clinical extraction LLM calls.

Atlas trace:
  DO: DO-728930A1
  DI: DI-06D98139, DI-EFEB21A1
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-728930A1")
"""

from __future__ import annotations

import logging

from libs.llm_client.prompt_safety import (
    INJECTION_GUARD,
    cap_llm_response,
    sanitise_for_prompt,
)
from libs.utils.deidentify import deidentify_text

logger = logging.getLogger(__name__)

DEFAULT_USER_TEXT_MAX_CHARS = 16_000
EXTRACTION_LLM_RESPONSE_MAX_CHARS = 65_536


def deidentify_encounter_text(text: str) -> str:
    """Return de-identified encounter text safe for extraction processing."""
    if not text:
        return ""
    return deidentify_text(text, ner=True)


def guard_system_prompt(instructions: str) -> str:
    """Prepend INJECTION_GUARD when not already present."""
    body = (instructions or "").strip()
    if not body:
        return INJECTION_GUARD.strip()
    if body.startswith(INJECTION_GUARD):
        return body
    return INJECTION_GUARD + body


def guard_user_clinical_text(text: str, *, max_chars: int = DEFAULT_USER_TEXT_MAX_CHARS) -> str:
    """De-identify then sanitise clinical text before embedding in an LLM user message."""
    deid = deidentify_encounter_text(text)
    return sanitise_for_prompt(deid, max_chars=max_chars)


def guard_llm_extraction_response(
    raw: str,
    *,
    max_chars: int = EXTRACTION_LLM_RESPONSE_MAX_CHARS,
) -> str:
    """Cap raw LLM extraction output before JSON parsing."""
    return cap_llm_response(raw or "", max_chars=max_chars)
