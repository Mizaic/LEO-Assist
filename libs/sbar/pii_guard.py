"""Deterministic guard against a leaked patient date-of-birth citation.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")

The Situation / Background / Recommendation prompts
(``libs/prompts/sbar_*_v1.py``) already instruct the model to never put a
direct patient identifier (name, NHS number, date of birth) in the
narrative, and to only attach an inline ``[date]`` citation when that date
is real evidence for the specific clause it follows.

In practice the model is handed the patient's ``birth_date`` as structured
context (so it can state the patient's age) and can still misuse it as the
inline citation for an unrelated clause, e.g.::

    "...the request conflicts between 2WW and the Serious Non-Specific
    Symptoms pathway [1955-04-09]."

where ``1955-04-09`` is simply the patient's date of birth -- not evidence
for that sentence, and a direct identifier that must never reach the
narrative (rule 9 of ``SBAR_SITUATION_SYSTEM_V1``).

This module is the deterministic backstop for that failure mode: strip any
inline ``[...]`` citation bracket that matches the patient's own date of
birth before a section is persisted, rather than relying solely on prompt
compliance. See ``tests/test_sbar_pii_guard.py``.
"""

from __future__ import annotations

import re
from datetime import date

_BRACKET_RE = re.compile(r"\[([^\[\]]{1,40})\]")

_MONTH_NAMES = [
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
]


def _dob_surface_forms(birth_date: str | None) -> list[str]:
    """Every plausible rendering of ``birth_date`` that could appear inside
    a bracketed inline citation, lower-cased and longest-first."""
    if not birth_date:
        return []
    raw = str(birth_date).strip()
    if not raw:
        return []
    forms = {raw}
    try:
        parsed: date | None = date.fromisoformat(raw[:10])
    except ValueError:
        parsed = None
    if parsed is not None:
        forms.add(parsed.isoformat())
        forms.add(f"{parsed.day:02d}/{parsed.month:02d}/{parsed.year}")
        forms.add(f"{parsed.month:02d}/{parsed.day:02d}/{parsed.year}")
        forms.add(f"{parsed.day}/{parsed.month}/{parsed.year}")
        month_name = _MONTH_NAMES[parsed.month - 1]
        forms.add(f"{parsed.day} {month_name} {parsed.year}")
        forms.add(f"{month_name} {parsed.day}, {parsed.year}")
        forms.add(f"{parsed.day} {month_name[:3]} {parsed.year}")
    return sorted({f.lower() for f in forms if f}, key=len, reverse=True)


def strip_dob_citations(markdown: str, birth_date: str | None) -> tuple[str, bool]:
    """Remove any inline ``[...]`` citation bracket that is actually the
    patient's own date of birth in disguise.

    Returns ``(cleaned_markdown, stripped)``. When ``stripped`` is True the
    caller should record a guard event: this indicates the model fabricated
    a citation from an identifier rather than real evidence, which is worth
    surfacing for review even though the returned markdown is now safe to
    persist.
    """
    if not markdown or not birth_date:
        return markdown, False
    forms = _dob_surface_forms(birth_date)
    if not forms:
        return markdown, False

    stripped = False

    def _replace(match: re.Match[str]) -> str:
        nonlocal stripped
        inner = match.group(1).strip().lower()
        if any(form in inner for form in forms):
            stripped = True
            return ""
        return match.group(0)

    cleaned = _BRACKET_RE.sub(_replace, markdown)
    if not stripped:
        return markdown, False
    # Tidy up whitespace left behind by the removed bracket, e.g.
    # "pathway ." -> "pathway." and doubled spaces/trailing line spaces.
    cleaned = re.sub(r"[ \t]+([.,;:])", r"\1", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    return cleaned.strip(), True
