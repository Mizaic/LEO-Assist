"""Treat clinically equivalent lab unit spellings as the same unit.

GP notes often write FIT units as 'ug Hb/g faeces' or with a microgram
symbol. Guideline rules are authored as 'microgram/g'. An exact string
match then drops a real reading.

Atlas trace:
  DI: DI-D6AEFFBC
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-D6AEFFBC")
"""

from __future__ import annotations

import re

# Micro sign U+00B5 and Greek mu U+03BC, both seen in GP notes.
_MICRO_CHARS = ("\u00b5", "\u03bc")
_WORD_TO_UG = (
    ("micrograms", "ug"),
    ("microgram", "ug"),
    ("mcg", "ug"),
)
_NOISE_WORDS = (
    "haemoglobin",
    "hemoglobin",
    "faeces",
    "feces",
    "stool",
    "hb",
)
_NOISE_RE = re.compile(r"\b(" + "|".join(_NOISE_WORDS) + r")\b", re.IGNORECASE)
_KEEP_RE = re.compile(r"[^a-z0-9/*]")


def normalise_unit(unit: str) -> str:
    """Return a comparable unit token for equivalence checks."""
    text = (unit or "").strip().lower()
    if not text:
        return ""
    for char in _MICRO_CHARS:
        text = text.replace(char, "u")
    for src, dest in _WORD_TO_UG:
        text = text.replace(src, dest)
    text = _NOISE_RE.sub(" ", text)
    return _KEEP_RE.sub("", text)


def units_are_equivalent(patient_unit: str, rule_unit: str) -> bool:
    """Return True when the two unit strings mean the same quantity."""
    left = normalise_unit(patient_unit)
    right = normalise_unit(rule_unit)
    if not left or not right:
        return False
    return left == right
