"""Configurable regex signal pattern sets for outcome inference.

Atlas trace:
  DO: DO-0998FAF5
  Also implements: DO-86800C9B
  DI: DI-FC80B65A
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-0998FAF5")

Promoted from scripts/investigations/_patient_180d_inference_scan.py.
Each pattern set is a list of (regex_pattern, human_label) tuples.

Signal sets are site-generic by default. Cancer-site-specific overrides
can be added by importing and extending these lists in calling code.
"""

from __future__ import annotations

import re
from typing import Optional

from libs.dq._models import SignalHit

# ---------------------------------------------------------------------------
# Cancer-confirming post-specialist signals
# ---------------------------------------------------------------------------

POST_CANCER: list[tuple[str, str]] = [
    (r"\bexcis", "excision"),
    (r"\bmohs\b", "mohs surgery"),
    (r"\bwide local excision\b", "wide local excision"),
    (r"\bsurgical removal\b", "surgical removal"),
    (r"\boncolog", "oncology"),
    (r"\bradiother", "radiotherapy"),
    (r"\bchemother", "chemotherapy"),
    (r"\bimmunother", "immunotherapy"),
    (r"\bsentinel node\b", "sentinel node biopsy"),
    (r"\blymph node\b", "lymph node"),
    (r"\bpatholog", "pathology result"),
    (r"\bhistolog", "histology result"),
    (r"\bbiopsy result\b", "biopsy result"),
    (r"\bstage [1-4ivi]+\b", "staging"),
    (r"\bdo not cancel\b", "urgent recall"),
    (r"\bpriority [ab1]\b", "high priority follow-up"),
    (r"\burgent.*follow", "urgent follow-up"),
    (r"\bcancer referral", "cancer referral"),
    (r"\bscc\b(?!.*suspected)", "SCC confirmed"),
    (r"\bbcc\b(?!.*suspected)", "BCC confirmed"),
    (r"\bmelanoma\b", "melanoma"),
    (r"\bcarcinoma\b", "carcinoma"),
    (r"\bmalign", "malignant"),
    (r"\bclinical trial", "clinical trial enrolment"),
    (r"\bcpms\b", "CPMS trial"),
]


# ---------------------------------------------------------------------------
# Benign-outcome post-specialist signals
# ---------------------------------------------------------------------------

POST_BENIGN: list[tuple[str, str]] = [
    (r"\befudix\b", "Efudix prescribed"),
    (r"\bfluorouracil\b", "fluorouracil prescribed"),
    (r"\b5[- ]?fu\b", "5-FU prescribed"),
    (r"\bimiquimod\b", "imiquimod prescribed"),
    (r"\bphotodynam", "photodynamic therapy"),
    (r"\bcryother", "cryotherapy"),
    (r"\bcurette\b", "curettage"),
    (r"\bak\b", "actinic keratosis (AK)"),
    (r"\bactinic keratosis\b", "actinic keratosis"),
    (r"\bsolar keratosis\b", "solar keratosis"),
    (r"\bseborrhoeic\b", "seborrhoeic keratosis"),
    (r"\bbenign\b", "benign"),
    (r"\bnot malign", "not malignant"),
    (r"\bnon[- ]?malign", "non-malignant"),
    (r"\bno evidence of cancer\b", "no cancer found"),
    (r"\bno further follow[- ]?up\b", "no further follow-up"),
    (r"\bdischarg", "discharged"),
    (r"\broutine.*follow", "routine follow-up"),
    (r"\b6 months?\b.*review", "6-month routine review"),
    (r"\breassur", "reassured"),
    (r"\bnot cancer\b", "not cancer"),
    (r"\bwait and see\b", "watchful waiting"),
]


# ---------------------------------------------------------------------------
# Private / blocked letter markers
# ---------------------------------------------------------------------------

PRIVATE_MARKERS: list[str] = [
    r"event has been made private",
    r"care started at.*uhl",
]


# ---------------------------------------------------------------------------
# Specialist attendance confirmation patterns
# ---------------------------------------------------------------------------

SPECIALIST_SEEN: list[str] = [
    r"seen in fast track",
    r"uhl dermatology",
    r"dermatology to .+medical centre",
    r"skin lesion photography",
    r"new lesion template",
    r"dermoscop",
]


# ---------------------------------------------------------------------------
# Core matching helpers
# ---------------------------------------------------------------------------


def match_signals(
    text: str,
    patterns: list[tuple[str, str]],
    date: str = "",
    context_chars: int = 85,
) -> list[SignalHit]:
    """Return SignalHit for each (pattern, label) that matches text."""
    tl = text.lower()
    hits: list[SignalHit] = []
    for pat, label in patterns:
        m = re.search(pat, tl)
        if not m:
            continue
        start = max(0, m.start() - context_chars // 2)
        end = min(len(tl), m.end() + context_chars // 2)
        snippet = tl[start:end].replace("\n", " ").strip()
        hits.append(SignalHit(date=date, label=label, snippet=snippet))
    return hits


def has_any(text: str, patterns: list[str]) -> bool:
    """Return True if any pattern in patterns matches text."""
    tl = text.lower()
    return any(re.search(p, tl) for p in patterns)
