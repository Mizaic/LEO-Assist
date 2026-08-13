"""Output token budget for one extraction LLM call.

GPT-5 thinking tokens share this budget. A short cap cuts the JSON off
and the parser then salvages a partial terms list.

Atlas trace:
  DI: DI-7B978C0C
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-7B978C0C")
"""

from __future__ import annotations

import os

_FLOOR = 8192
_CAP = 16384


def extraction_max_tokens(sentence_count: int) -> int:
    """Return the JSON output budget for one extraction window."""
    raw = os.getenv("EXTRACTION_MAX_TOKENS", "").strip()
    if raw.isdigit():
        return max(_FLOOR, min(int(raw), _CAP))
    scaled = 400 + 80 * max(int(sentence_count), 1)
    return max(_FLOOR, min(scaled, _CAP))
