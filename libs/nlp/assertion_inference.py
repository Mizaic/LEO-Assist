"""Canonical assertion inference from clinical text.

Atlas trace:
  DO: DO-CD6408D3
  DI: DI-CF5162BF
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-CD6408D3")

Consolidates the duplicated _infer_assertion() implementations from
mine_all_domains.py, normalize_training.py, and semantic_exclusion_search.py.
All pipeline code should import from here — do NOT duplicate.
"""

from __future__ import annotations

import re

_NEGATED_RE = re.compile(
    r"\b("
    r"no evidence of|no fam|rule out|ruled out|unlikely|excluded|not |negative|"
    r"no malignancy|all clear|benign|non.malignant|no recurrence|"
    r"normal result|no suspicious|no sinister|no cancer"
    r")\b",
    re.IGNORECASE,
)

_FAMILY_RE = re.compile(
    r"\b(family history|fam hx|fam hist|maternal|paternal|FH )\b",
    re.IGNORECASE,
)

_HISTORICAL_RE = re.compile(
    r"\b("
    r"history of|past medical history|previous|previously|had|"
    r"remission|in remission|prior|former|PMH|PMHx|hx of"
    r")\b",
    re.IGNORECASE,
)


def infer_assertion(text: str, record: dict | None = None) -> str:
    """Infer assertion type from clinical text.

    Returns one of: ``absent``, ``family``, ``historical``, ``present``.

    If *record* is supplied and contains ``disambiguation == "historical"``,
    that takes precedence over regex matching.
    """
    if record and record.get("disambiguation") == "historical":
        return "historical"

    if _NEGATED_RE.search(text):
        return "absent"
    if _FAMILY_RE.search(text):
        return "family"
    if _HISTORICAL_RE.search(text):
        return "historical"
    return "present"
