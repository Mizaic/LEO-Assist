"""Stage 2 consolidation rules for tidying reviewed-episode milestones.

Pure functions that decide how non-canonical milestones map onto the
strict NCDA-4 vocabulary {referral, first_seen, diagnosis_confirmed,
treatment_started}, and whether a Dx encounter carries
outcome=cancer_found vs cancer_excluded.

The orchestrating script lives in scripts/ncda/tidy_reviewed_episodes.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from libs.domains.read_code_ncda_lookup import lookup_read_code

CANONICAL_MILESTONES: frozenset[str] = frozenset(
    {"referral", "first_seen", "diagnosis_confirmed", "treatment_started"}
)

DxOutcome = Literal["cancer_found", "cancer_excluded"]


@dataclass(frozen=True)
class ConsolidationDecision:
    """One row's outcome from the consolidation pass.

    Attributes:
        action: "rewrite" -> change milestone_type (and optionally set
            outcome_attribute), "delete" -> remove the IS_PART_OF
            relationship, "keep" -> already canonical, do nothing.
        new_milestone: Replacement milestone_type when action='rewrite'.
        outcome_attribute: Outcome to stamp on the IS_PART_OF when the
            new milestone is diagnosis_confirmed.
        rationale: Plain-English reason for the audit row.
    """

    action: Literal["keep", "rewrite", "delete"]
    new_milestone: str | None = None
    outcome_attribute: DxOutcome | None = None
    rationale: str = ""


def consolidate(milestone_type: str, text: str | None) -> ConsolidationDecision:
    """Decide how a single (milestone_type, text) row should consolidate."""
    if milestone_type in CANONICAL_MILESTONES:
        if milestone_type == "diagnosis_confirmed":
            return ConsolidationDecision(
                action="keep",
                outcome_attribute=_infer_dx_outcome(text or ""),
                rationale="Already canonical Dx; outcome attribute computed from text.",
            )
        return ConsolidationDecision(
            action="keep", rationale=f"Already canonical: {milestone_type}"
        )
    if milestone_type == "referral_sent":
        return ConsolidationDecision(
            action="rewrite",
            new_milestone="referral",
            rationale="Consolidate referral_sent into canonical 'referral'.",
        )
    if milestone_type == "benign_closure":
        return ConsolidationDecision(
            action="rewrite",
            new_milestone="diagnosis_confirmed",
            outcome_attribute="cancer_excluded",
            rationale=(
                "Consolidate benign_closure to diagnosis_confirmed with "
                "outcome=cancer_excluded (NCDA outcome reached)."
            ),
        )
    if milestone_type == "outcome_letter":
        outcome = _infer_dx_outcome(text or "")
        if outcome is None:
            return ConsolidationDecision(
                action="delete",
                rationale=(
                    "outcome_letter without diagnosis content; not an NCDA anchor."
                ),
            )
        return ConsolidationDecision(
            action="rewrite",
            new_milestone="diagnosis_confirmed",
            outcome_attribute=outcome,
            rationale=(
                f"Consolidate outcome_letter -> diagnosis_confirmed (outcome={outcome})."
            ),
        )
    return ConsolidationDecision(
        action="delete",
        rationale=f"Non-canonical milestone '{milestone_type}'; strict tidy removes.",
    )


import re as _re

# EMIS EMR signals for new vs recalled diagnoses.
# "Major: [cancer term]" = new diagnosis being added to the problem list.
# "Problem: [cancer term]" = existing problem recalled in header — NOT a new Dx.
_EMIS_MAJOR_CANCER = _re.compile(
    r"^Major:\s+(?:malignant|carcinoma|adenocarcinoma|lymphoma|melanoma"
    r"|sarcoma|mesothelioma)\b",
    _re.IGNORECASE | _re.MULTILINE,
)
_EMIS_MAJOR_BENIGN = _re.compile(
    r"^Major:\s+(?:benign|no malignancy|cyst|polyp|fibroadenoma)\b",
    _re.IGNORECASE | _re.MULTILINE,
)


_PROBLEM_CANCER_LINE = _re.compile(
    r"^Problem:\s+(?:malignant|carcinoma|adenocarcinoma|lymphoma|melanoma|sarcoma"
    r"|mesothelioma|tumour of|tumor of)\b",
    _re.IGNORECASE | _re.MULTILINE,
)

_NEGATIVE_BREAST_IMAGING = _re.compile(
    r"\b(?:us scan of breast|breast ultrasound|mammogram|mammography)\b"
    r".*\b(?:normal|nad|no change|no abnormality detected)\b"
    r"|\b(?:normal|nad|no change|no abnormality detected)\b"
    r".*\b(?:us scan of breast|breast ultrasound|mammogram|mammography)\b",
    _re.IGNORECASE,
)


def _strip_problem_lines(text: str) -> str:
    """Remove EMIS 'Problem: [cancer diagnosis]' header lines.

    Only strips problem lines that NAME a cancer (e.g. "Problem: Carcinoma of
    prostate") — these recap pre-existing diagnoses and contaminate outcome
    detection for routine phlebotomy / LTC encounters.

    Lines like "Problem: No malignancy confirmed" or "Problem: Pre-diabetes" are
    preserved because they either convey useful cancer-excluded language or are
    harmless non-cancer content.
    """
    lines = text.splitlines()
    clean = []
    for ln in lines:
        stripped = ln.strip()
        if stripped.startswith("Problem:") and _PROBLEM_CANCER_LINE.match(stripped):
            continue
        clean.append(ln)
    return "\n".join(clean)


def _infer_dx_outcome(text: str) -> DxOutcome | None:
    """Decide outcome for a Dx encounter from text + Read codes.

    Returns 'cancer_found', 'cancer_excluded', or None when ambiguous.

    EMIS-aware: strips 'Problem: ...' header lines first so that historical cancer
    entries copied into every encounter header (e.g. "Problem: Carcinoma of prostate"
    at the top of a routine phlebotomy note) do not contaminate keyword search.
    The 'Major: [cancer]' pattern remains in the keyword search on the clean text so
    it confirms new diagnoses without being a hard override (which caused cross-pathway
    false-positives when a patient has concurrent cancers on different pathways).
    """
    if not text:
        return None

    # Strip "Problem: ..." lines that recap existing conditions in the EMIS header.
    # "Major: ..." and "Minor: ..." lines from the CURRENT encounter are kept.
    clean = _strip_problem_lines(text)
    t = clean.lower()

    # cancer_excluded: explicit outcome language takes priority so that
    # "Major: Benign breast condition" or discharge text is not overridden by a
    # concurrent cancer note elsewhere in the clean text.
    excluded_phrases = (
        "no malignancy",
        "benign",
        "cancer ruled out",
        "cancer excluded",
        "all clear",
        "discharged from",
        "d/c from",
        "no evidence of cancer",
        "no evidence of malignancy",
        "dysplastic naevus",
        "atypical naevus",
        "compound naevus",
        "melanocytic naevi",
    )
    if any(p in t for p in excluded_phrases):
        return "cancer_excluded"
    if _NEGATIVE_BREAST_IMAGING.search(clean):
        return "cancer_excluded"

    # cancer_found: any strong cancer confirmation in the cleaned narrative,
    # including EMIS "Major: [cancer] (New Episode)" entries which appear here
    # because they start with "Major:" not "Problem:" and are not stripped.
    found_phrases = (
        "malignant",
        "carcinoma",
        "adenocarcinoma",
        "lymphoma",
        "melanoma",
        "sarcoma",
        "tumour confirmed",
        "new cancer diagnosis",
        "histology malignant",
    )
    if any(p in t for p in found_phrases):
        return "cancer_found"

    # Read-code fallback on the clean text.
    for token in _read_code_tokens(clean):
        looked = lookup_read_code(token)
        if looked is None:
            continue
        role, outcome = looked
        if role == "dx" and outcome is not None:
            return outcome
    return None


def _read_code_tokens(text: str) -> list[str]:
    import re

    return re.findall(r"\(([A-Za-z0-9.]+)\)", text)
