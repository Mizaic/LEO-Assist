"""Fail facts whose words are not in the golden letter.

Atlas trace:
  DI: DI-9D76A65C
  DO: DO-1E60B1D4
  VT: VT-12EBF8F0
  Risk: R-3B38CA10
"""

from __future__ import annotations

from typing import Any


def invented_facts(facts: list[dict[str, Any]], letter: str) -> list[str]:
    """Return fact texts that cannot be found in the letter."""
    haystack = " ".join(str(letter or "").lower().split())
    hits: list[str] = []
    for fact in facts:
        text = str(fact.get("evidence_text") or fact.get("text") or "").strip()
        if not text:
            continue
        needle = " ".join(text.lower().split())
        if needle not in haystack:
            hits.append(str(fact.get("text") or text))
    return hits
