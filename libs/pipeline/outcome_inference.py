"""Auto-stamped Atlas trace.

Atlas trace:
  DO: DO-11A2361E
  DI: DI-F46D7A68
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-11A2361E")

Post-specialist outcome inference engine.

Scans the 180-day window of encounters following a specialist visit and
determines from textual signals whether the likely outcome was cancer or
benign.  Returns an InferenceResult with verdict, inferred_outcome,
inferred_outcome_date (earliest triggering encounter date), and
inferred_confidence.

Design controls: DI-LEO-AI-088, R-LEO-AI-062, VT-LEO-AI-088
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Sequence

# DI-LEO-AI-159: defence-in-depth Read/CTV3 code recognition.
from libs.domains.code_inventories import (
    BENIGN_EXPLANATION_READ_CODES,
    BENIGN_INVESTIGATION_PHRASES,
    MALIGNANCY_READ_CODES,
)

# ---------------------------------------------------------------------------
# Encounter-level exclusion contexts.
#
# If an encounter matches ANY of these patterns it is skipped entirely during
# signal scoring.  These represent care that is definitively unrelated to the
# cancer investigation pathway so that incidental clinical terms (excision,
# pathology) in those encounters do not contaminate the inference.
# ---------------------------------------------------------------------------

ENCOUNTER_EXCLUSIONS: list[str] = [
    # Ophthalmology -- cataract surgery
    r"\bcataract\b",
    r"\bphakoemulsification\b",
    # Hand / peripheral vascular surgery
    r"\bvascular malformation\b",
    r"\bcarpal tunnel\b",
    # Unscheduled / minor-injury care (not the cancer pathway clinic)
    r"\bminor injuries unit\b",
    r"\burgent treatment centre\b",
    r"\butc attend",
    # Dental (not cancer pathway unless specifically an oral cancer 2WW)
    r"\bdental extraction\b",
    r"\bdental surgery\b",
]

# ---------------------------------------------------------------------------
# Signal pattern tables
# Each entry: (regex, human-readable label)
#
# POST_CANCER patterns are intentionally specific to avoid false positives
# from routine monitoring of established non-cancer conditions.
# ---------------------------------------------------------------------------

POST_CANCER: list[tuple[str, str]] = [
    # Excision -- require cancer-relevant object so hand/eye surgery is excluded
    (
        r"\bexcision of (?:lesion|tumour|tumor|cancer|carcinoma|melanoma|bcc|scc|lymph node|lump)\b",
        "excision of lesion",
    ),
    (r"\bsurgical excision\b", "surgical excision"),
    (r"\bwide local excision\b", "wide local excision"),
    (r"\bmohs\b", "mohs surgery"),
    (r"\bsurgical removal\b", "surgical removal"),
    # Systemic / specialist cancer treatment
    (r"\boncolog", "oncology"),
    (r"\bradiother", "radiotherapy"),
    (r"\bchemother", "chemotherapy"),
    (r"\bimmunother", "immunotherapy"),
    # Lymph node workup (sentinel biopsy implies confirmed malignancy)
    (r"\bsentinel node\b", "sentinel node"),
    (r"\blymph node biopsy\b", "lymph node biopsy"),
    (r"\baxillary node\b", "axillary node"),
    # Pathology / histology -- require result context (not just a request)
    (
        r"\bpathology (?:result|report|confirm|specimen|showed|returned|received)\b",
        "pathology result",
    ),
    (
        r"\bhistology (?:result|report|confirm|showed|returned|received)\b",
        "histology result",
    ),
    (r"\bbiopsy (?:result|report|confirm|showed|returned|received)\b", "biopsy result"),
    (r"\bhistolog(?:ically)? confirm", "histologically confirmed"),
    # Staging / MDT
    (r"\bstage [1-4ivi]+\b", "staging"),
    (r"\bmdt (?:meeting|referral|discussion)\b", "MDT referral"),
    # Urgent / high-priority recalls that imply active cancer management
    (r"\bdo not cancel\b", "urgent recall"),
    (r"\bpriority [ab1]\b", "high priority f/u"),
    (r"\burgent.*follow", "urgent follow-up"),
    (r"\boncology referral\b", "oncology referral"),
    (r"\bcancer referral", "cancer referral"),
    # Confirmed cancer terminology
    (r"\bcarcinoma\b", "carcinoma"),
    (r"\bmalign(?:ant)?\b", "malignant"),
    (r"\bmalignancy\b", "malignancy"),
    # Clinical trial enrolment implies confirmed malignancy
    (r"\bcpms\b", "CPMS trial"),
    (r"\bclinical trial", "clinical trial"),
]

POST_BENIGN: list[tuple[str, str]] = [
    # ---- Topical / ablative treatments for pre-malignant skin lesions ----
    (r"\befudix\b", "Efudix"),
    (r"\bfluorouracil\b", "fluorouracil"),
    (r"\b5[- ]?fu\b", "5-FU"),
    (r"\bimiquimod\b", "imiquimod"),
    (r"\bphotodynam", "photodynamic therapy"),
    (r"\bcryother", "cryotherapy"),
    (r"\bcurette\b", "curettage"),
    # ---- Benign skin conditions ----
    (r"\bak\b", "AK"),
    (r"\bactinic keratosis\b", "actinic keratosis"),
    (r"\bsolar keratosis\b", "solar keratosis"),
    (r"\bseborrhoeic\b", "seborrhoeic keratosis"),
    # ---- Explicit no-cancer language ----
    (r"\bbenign\b", "benign"),
    (r"\bnot malign", "not malignant"),
    (r"\bnon[- ]?malign", "non-malignant"),
    (r"\bno evidence of (?:cancer|malign)", "no cancer"),
    (r"\bno (?:cancer|malignancy) found\b", "no cancer found"),
    (r"\bnot cancer\b", "not cancer"),
    (r"\bno cancer\b", "no cancer"),
    # ---- Pathway closure language ----
    (r"\bno further follow[- ]?up\b", "no further f/u"),
    (r"\bdischarg", "discharged"),
    (r"\broutine.*follow", "routine f/u"),
    (r"\breassur", "reassured"),
    # ---- ENT / head and neck benign outcomes ----
    (r"\bnormal larynx\b", "normal larynx"),
    (r"\bnormal nasendoscopy\b", "normal nasendoscopy"),
    (r"\bnasendoscopy.*normal\b", "normal nasendoscopy"),
    (r"\blaryngeal.{0,20}normal\b", "normal larynx"),
    (r"\blaryngopharyngeal reflux\b", "laryngopharyngeal reflux"),
    (r"\blpr\b", "LPR"),
    (r"\bchronic rhinitis\b", "chronic rhinitis"),
    (r"\boccipital lymph node\b", "occipital lymph node"),
    (r"\baphthous\b", "aphthous ulcer"),
    (r"\bthyroid nodule\b", "thyroid nodule"),
    (r"\bbenign thyroid\b", "benign thyroid"),
    (r"\bthymic cyst\b", "thymic cyst"),
    # ---- Respiratory / lung benign outcomes ----
    (r"\bemphysema\b", "emphysema"),
    (r"\bcopd\b", "COPD"),
    (r"\bpleural effusion\b", "pleural effusion"),
    (r"\bno (?:lung|pulmonary) (?:cancer|mass|tumou?r)\b", "no lung cancer"),
    (r"\bno (?:lung|pulmonary) malign", "no lung malignancy"),
    # ---- GI benign outcomes ----
    (r"\bfibroadenoma\b", "fibroadenoma"),
    (r"\birritabl\w+ bowel\b", "IBS"),
    (r"\bibs\b", "IBS"),
    (r"\bpolyp\b", "polyp"),
    (r"\bdiverticul", "diverticular disease"),
    (r"\bhaemorrhoid", "haemorrhoids"),
    (r"\bbarrett", "Barrett's oesophagus"),
]

# ---------------------------------------------------------------------------
# DI-LEO-AI-159: extend POST_CANCER / POST_BENIGN with curated Read/CTV3
# code tokens and benign-investigation phrases pulled from the deep-read
# corpus of stale episodes. _match_labels lowercases the encounter text
# before matching, so the patterns below use the lowercased form of each
# code (e.g. "(x78wm)" not "(X78WM)").
#
# We add ONLY signals that the legacy patterns above cannot see.
# Adding a pattern that overlaps with an existing one would double-count
# the same signal and break the HITL_REQUIRED tie-break the inference
# engine relies on (a single "discharged from clinic" mention must
# produce one hit, not two).
# ---------------------------------------------------------------------------

# Phrase labels (case-insensitive) that the legacy POST_BENIGN already
# matches via a more general regex. Skip these to avoid double-counting.
_LEGACY_BENIGN_LABELS_OVERLAP: frozenset[str] = frozenset({
    "discharged from care",
    "discharged from clinic",
    "discharged from 2WW pathway",
    "no evidence of malignancy",
    "negative for malignancy",
    "no further action",
    "cancer excluded - discharge to GP",
})

POST_CANCER += [
    (rf"\({re.escape(code.lower())}\)", f"malignancy code {code}")
    for code in sorted(MALIGNANCY_READ_CODES)
]
POST_BENIGN += [
    (rf"\({re.escape(code.lower())}\)", f"benign explanation code {code}")
    for code in sorted(BENIGN_EXPLANATION_READ_CODES)
]
POST_BENIGN += [
    (rx.pattern.lower(), label)
    for rx, label in BENIGN_INVESTIGATION_PHRASES
    if label not in _LEGACY_BENIGN_LABELS_OVERLAP
]

# Confidence constants
_CLEAR_BASE = 0.60
_CLEAR_STEP = 0.05
_CLEAR_CAP = 0.95
_WEAK_BASE = 0.50
_WEAK_STEP = 0.05
_WEAK_CAP = 0.85


@dataclass
class InferenceResult:
    verdict: str  # INFERRED_CANCER | INFERRED_BENIGN | *_WEAK | HITL_REQUIRED
    inferred_outcome: str | None  # 'cancer' | 'benign' | None
    inferred_outcome_date: str | None  # ISO date of earliest triggering encounter
    inferred_confidence: float | None  # 0.0-0.95 or None for HITL_REQUIRED
    inference_signals: list[str] = field(default_factory=list)


def _match_labels(text: str, patterns: list[tuple[str, str]]) -> list[str]:
    """Return labels for all matching patterns in *text*."""
    tl = text.lower()
    return [label for pat, label in patterns if re.search(pat, tl)]


def _confidence(majority: int, is_clear: bool) -> float:
    if is_clear:
        return min(_CLEAR_CAP, _CLEAR_BASE + _CLEAR_STEP * majority)
    return min(_WEAK_CAP, _WEAK_BASE + _WEAK_STEP * majority)


def _is_excluded(text: str) -> bool:
    """Return True if the encounter is definitively unrelated to the cancer pathway."""
    tl = text.lower()
    return any(re.search(pat, tl) for pat in ENCOUNTER_EXCLUSIONS)


def score_post_specialist_encounters(
    phase2_rows: Sequence[dict],
) -> InferenceResult:
    """
    Score a sequence of post-specialist encounter dicts.

    Each row must have at least:
      - 'date': ISO date string (str | None)
      - 'text': encounter text (str | None)
      - 'flags': encounter flags (str | None)

    Encounters that match ENCOUNTER_EXCLUSIONS are skipped to prevent
    cross-pathway contamination from unrelated clinical events.

    Returns an InferenceResult.
    """
    cancer_hits: list[tuple[str, str]] = []  # (date, label)
    benign_hits: list[tuple[str, str]] = []

    for row in phase2_rows:
        combined = (row.get("text") or "") + " " + (row.get("flags") or "")
        if _is_excluded(combined):
            continue
        date = row.get("date") or ""
        for label in _match_labels(combined, POST_CANCER):
            cancer_hits.append((date, label))
        for label in _match_labels(combined, POST_BENIGN):
            benign_hits.append((date, label))

    nc = len(cancer_hits)
    nb = len(benign_hits)

    if nc == 0 and nb == 0:
        return InferenceResult(
            verdict="HITL_REQUIRED",
            inferred_outcome=None,
            inferred_outcome_date=None,
            inferred_confidence=None,
            inference_signals=[],
        )

    all_signal_dates = [d for d, _ in (cancer_hits + benign_hits) if d]
    earliest_date = min(all_signal_dates) if all_signal_dates else None
    all_labels = sorted({lbl for _, lbl in (cancer_hits + benign_hits)})

    if nc > 0 and nb == 0:
        return InferenceResult(
            verdict="INFERRED_CANCER",
            inferred_outcome="cancer",
            inferred_outcome_date=earliest_date,
            inferred_confidence=_confidence(nc, is_clear=True),
            inference_signals=all_labels,
        )

    if nb > 0 and nc == 0:
        return InferenceResult(
            verdict="INFERRED_BENIGN",
            inferred_outcome="benign",
            inferred_outcome_date=earliest_date,
            inferred_confidence=_confidence(nb, is_clear=True),
            inference_signals=all_labels,
        )

    if nc > nb:
        return InferenceResult(
            verdict="INFERRED_CANCER_WEAK",
            inferred_outcome="cancer",
            inferred_outcome_date=earliest_date,
            inferred_confidence=_confidence(nc, is_clear=False),
            inference_signals=all_labels,
        )

    if nb > nc:
        return InferenceResult(
            verdict="INFERRED_BENIGN_WEAK",
            inferred_outcome="benign",
            inferred_outcome_date=earliest_date,
            inferred_confidence=_confidence(nb, is_clear=False),
            inference_signals=all_labels,
        )

    # Equal signals - ambiguous
    return InferenceResult(
        verdict="HITL_REQUIRED",
        inferred_outcome=None,
        inferred_outcome_date=None,
        inferred_confidence=None,
        inference_signals=all_labels,
    )
