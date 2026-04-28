"""Stage 3 silver-label generation logic.

Pure functions plus a pluggable LLM-callback Protocol. The orchestrating
script lives in scripts/ncda/build_silver_labels.py.

Core ideas:
  - LLM-at-curation only - never inference. Replaceable with any callable
    that conforms to LlmRelabelFn.
  - Deterministic fallback labeller (read codes + phrase patterns) is used
    when no LLM is provided; this is also useful for unit tests.
  - Output schema is fixed so the role/linkage classifiers can read it
    directly.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Callable, Iterable, Literal, Protocol

from libs.domains.read_code_ncda_lookup import (
    TREATMENT_DRUG_TOKENS,
    lookup_read_code,
)
from services.analysis_worker.app.ncda_detector.audit_rules import (
    extract_read_codes,
    text_supports_role,
)
from services.analysis_worker.app.ncda_detector.tidy_rules import (
    _infer_dx_outcome,
    _strip_problem_lines,
)

NcdaRole = Literal["ftr", "seen", "dx", "treatment", "none"]
DxOutcome = Literal["cancer_found", "cancer_excluded"]


@dataclass(frozen=True)
class SilverLabel:
    """One silver-labelled encounter row."""

    patient_id: str
    encounter_id: str
    encounter_date: str | None
    role: NcdaRole
    outcome: DxOutcome | None
    confidence: float
    rationale: str
    supporting_quote: str
    site_hint: str | None
    source: Literal["llm", "deterministic"]


class LlmRelabelFn(Protocol):
    """Callable that takes (text, flags) and returns a structured label."""

    def __call__(
        self, text: str, flags: str | None
    ) -> dict[str, object]:
        ...


def deterministic_label(
    *, patient_id: str, encounter_id: str, encounter_date: str | None,
    text: str, flags: str | None,
) -> SilverLabel:
    """Bootstrap labeller using only Read codes + curated phrases.

    Confidence scores are deliberately conservative (max 0.7) so LLM-driven
    labels can outweigh deterministic ones during training when both exist.

    Exclusion pass runs first: certain encounter structures are definitively
    ``none`` regardless of any 2WW/fast-track text they contain:
      - Auto-filed lab / radiology results (PSA, FIT, CXR, bloods).
      - Type-4 retrospective admin tracking notes ("2WW Clinic?:").
      - Scheduled task creation encounters.
      - Referral triage / rejection admin notes.
    These exclusions prevent the phrase matcher from firing on e.g.
    "refer as a 2WW" in a PSA advisory or "Seen in 2WW Clinic?" in an
    admin tracking note.
    """
    excluded, excl_rationale = _is_excluded_none(text)
    if excluded:
        return SilverLabel(
            patient_id=patient_id,
            encounter_id=encounter_id,
            encounter_date=encounter_date,
            role="none",
            outcome=None,
            confidence=0.85,
            rationale=excl_rationale,
            supporting_quote=(text or "").strip()[:160],
            site_hint=None,
            source="deterministic",
        )

    # PRISM questionnaire check: "- PRISM 2WW [Site] - questionnaire started"
    # is an unambiguous active FTR submission regardless of what other Read
    # codes appear in the questionnaire body text.
    if _PRISM_QUESTIONNAIRE.search(text or ""):
        return SilverLabel(
            patient_id=patient_id,
            encounter_id=encounter_id,
            encounter_date=encounter_date,
            role="ftr",
            outcome=None,
            confidence=0.85,
            rationale="PRISM 2WW questionnaire entry - active FTR submission.",
            supporting_quote=(text or "").strip()[:160],
            site_hint=_extract_site_hint(text),
            source="deterministic",
        )

    role, outcome = _best_role_from_codes(text)
    # Only call the phrase matcher when no codes were found at all (role is None).
    # When codes mapped to "none" are present (role == "none"), that code lookup
    # result is trusted - falling through to phrases would re-fire on incidental
    # 2WW/fast-track text present in many clinical consultations.
    if role is None:
        role, outcome = _best_role_from_phrases(text)
    if role is None:
        role = "none"
    if role == "dx" and outcome is None:
        outcome = _infer_dx_outcome(text or "")
    confidence = 0.7 if role != "none" else 0.5
    quote = (text or "").strip()[:160]
    return SilverLabel(
        patient_id=patient_id,
        encounter_id=encounter_id,
        encounter_date=encounter_date,
        role=role,
        outcome=outcome,
        confidence=confidence,
        rationale="Deterministic Read-code + phrase pattern label.",
        supporting_quote=quote,
        site_hint=_extract_site_hint(text),
        source="deterministic",
    )


_AUTO_FILED_LABS = re.compile(
    r"\bAuto-filed\b",
    re.IGNORECASE,
)
_ADMIN_TRACKING_2WW = re.compile(
    r"2WW\s+Seen in 2WW Clinic\?",
    re.IGNORECASE,
)
_ADMIN_OPA_DATE = re.compile(
    r"2WW\s+Date of First outpatient appointment:",
    re.IGNORECASE,
)
_SCHEDULED_TASK = re.compile(
    r"Scheduled Task Creation",
    re.IGNORECASE,
)
_TRIAGE_REJECTION = re.compile(
    r"(Referral Rejected|TRIAGE RESPONSE|Choose and book referral rejected"
    r"|Return to referrer with advice)",
    re.IGNORECASE,
)
# EMIS phlebotomy template marker.  These are nurse blood-draw monitoring
# encounters.  EMIS reuses several Read codes inside phlebotomy templates
# (e.g. XE1Sf labelled "Infectious disease: prevention/control") that
# collide with cancer Dx codes in our lookup.  Exclude the whole template.
_PHLEBOTOMY_TEMPLATE = re.compile(
    r"\bPhlebotomy\s+(?:Test|Service)\b",
    re.IGNORECASE,
)
_BENIGN_SKIN_LESION_REFERRAL_ADMIN = re.compile(
    r"\bBenign Skin Lesion PRISM to Unknown\b",
    re.IGNORECASE,
)

_SITE_TOKENS: dict[str, tuple[str, ...]] = {
    "prostate": ("prostate", "psa", "urology", "urological", "bladder", "haematuria"),
    "breast": ("breast", "mammogram", "mammography"),
    "lung": ("lung", "chest x-ray", "cxr", "thoracic", "respiratory"),
    "lower_gi": ("lower gi", "colorectal", "bowel", "rectal", "colon", "fit positive"),
    "upper_gi": ("upper gi", "oesophag", "stomach", "gastric", "dysphagia"),
    "skin": ("skin", "dermoscopy", "dermatology", "melanoma", "lesion"),
    "head_neck": ("head and neck", "head & neck", "thyroid", "larynx", "pharynx", "tongue"),
    "gynaecological": ("gynae", "gynaecolog", "cervix", "endometri", "ovari", "uterus"),
    "haematological": ("haematol", "lymphoma", "leukaemia", "myeloma", "sll", "cll"),
    "brain": ("brain", "cns", "neurosurg", "headache", "seizure"),
    "nss": ("non-site specific", "nss", "weight loss", "fatigue"),
}


def _is_excluded_none(text: str) -> tuple[bool, str]:
    """Return (True, rationale) if this encounter is definitively role=none.

    Covers four encounter structural types that contain 2WW language but are
    NOT active FTR submissions:
      1. Auto-filed lab/radiology results (PSA, FIT, CXR, bloods).
      2. Retrospective Type-4 admin tracking notes.
      3. Scheduled-task creation encounters.
      4. Triage/rejection admin notes.
    """
    t = text or ""
    if _AUTO_FILED_LABS.search(t):
        return True, "Auto-filed lab or radiology result - not an NCDA anchor."
    if _ADMIN_TRACKING_2WW.search(t):
        return True, "Retrospective 2WW clinic-attendance tracking note."
    if _ADMIN_OPA_DATE.search(t):
        return True, "2WW outpatient appointment date recording - admin note."
    if _SCHEDULED_TASK.search(t):
        return True, "Scheduled task creation encounter - admin only."
    if _TRIAGE_REJECTION.search(t):
        return True, "Referral triage response or rejection note."
    if _PHLEBOTOMY_TEMPLATE.search(t):
        return True, "Phlebotomy template encounter — monitoring visit, not an NCDA anchor."
    if _BENIGN_SKIN_LESION_REFERRAL_ADMIN.search(t):
        return True, "Benign skin lesion referral admin — not a cancer FTR."
    return False, ""


def _extract_site_hint(text: str) -> str | None:
    """Return a cancer site hint based on keyword signals in the encounter text."""
    lower = (text or "").lower()
    for site, tokens in _SITE_TOKENS.items():
        if any(tok in lower for tok in tokens):
            return site
    return None


_ROLE_PRIORITY: dict[str, int] = {
    "ftr": 5, "seen": 4, "dx": 3, "treatment": 2, "none": 0,
}


def _best_role_from_codes(text: str) -> tuple[NcdaRole | None, DxOutcome | None]:
    """Return the highest-priority role found among all Read codes in the text.

    Iterates ALL codes rather than stopping at the first match, so that a
    high-priority FTR code (XaMeC) beats a generic none-code (Xa1qL) even
    when the generic code appears earlier in the text.  ``none`` codes are
    only returned when no higher-priority match was found.

    Cancer-affirming "Problem: ..." header lines are stripped before code
    extraction so that EMIS problem-list recap codes (e.g. "Problem: Malignant
    tumour of breast (X78WM)" in a phlebotomy encounter) do not elevate a
    routine monitoring visit to dx/cancer_found role.
    """
    best_role: NcdaRole | None = None
    best_outcome: DxOutcome | None = None
    best_priority: int = -1

    # Strip cancer-affirming Problem headers before code lookup so that codes
    # recapping existing diagnoses (in phlebotomy / LTC review encounters) are
    # not found by extract_read_codes.
    code_text = _strip_problem_lines(text or "")

    for token in extract_read_codes(code_text):
        looked = lookup_read_code(token)
        if looked is None:
            continue
        role, outcome = looked
        priority = _ROLE_PRIORITY.get(role, 0)
        if role == "dx" and outcome is not None:
            priority = max(priority, _ROLE_PRIORITY["seen"] + 1)
        if priority > best_priority:
            best_role = role
            best_outcome = outcome
            best_priority = priority

    if best_role is not None and best_role != "none":
        return best_role, best_outcome
    if _bare_drug_token_present(text or ""):
        return ("treatment", None)
    if best_role == "none":
        return ("none", None)
    return (None, None)


def _bare_drug_token_present(text: str) -> bool:
    """Detect cancer drug tokens even when not wrapped in parens."""
    if not text:
        return False
    upper = text.upper()
    return any(drug in upper for drug in TREATMENT_DRUG_TOKENS)


_PRISM_QUESTIONNAIRE = re.compile(
    r"PRISM\s+2WW.*questionnaire\s+started",
    re.IGNORECASE,
)


def _best_role_from_phrases(text: str) -> tuple[NcdaRole | None, DxOutcome | None]:
    """Match NCDA role from free-text phrases.

    Note: PRISM questionnaire encounters are intercepted BEFORE this function
    is called (in deterministic_label), so "suspected lymphoma" in a PRISM
    questionnaire body will not cause this function to return "dx".
    The original ordering (dx > ftr) is preserved so that discharge notes
    ("Discharged from 2WW, no malignancy") return dx, not ftr.
    """
    t = text or ""
    for role in ("dx", "ftr", "seen", "treatment"):
        if text_supports_role(t, role):  # type: ignore[arg-type]
            outcome = _infer_dx_outcome(t) if role == "dx" else None
            return (role, outcome)  # type: ignore[return-value]
    return (None, None)


def label_with_llm(
    *,
    patient_id: str,
    encounter_id: str,
    encounter_date: str | None,
    text: str,
    flags: str | None,
    llm: LlmRelabelFn,
) -> SilverLabel:
    """Label one encounter via the supplied LLM callback.

    The callback returns a dict with keys role / outcome / confidence /
    rationale / supporting_quote / site_hint. Falls back to deterministic
    labels on any LLM error (logged by caller).
    """
    response = llm(text, flags)
    role = str(response.get("role", "none"))
    if role not in {"ftr", "seen", "dx", "treatment", "none"}:
        role = "none"
    outcome_raw = response.get("outcome")
    outcome: DxOutcome | None = None
    if role == "dx" and outcome_raw in ("cancer_found", "cancer_excluded"):
        outcome = outcome_raw  # type: ignore[assignment]
    return SilverLabel(
        patient_id=patient_id,
        encounter_id=encounter_id,
        encounter_date=encounter_date,
        role=role,  # type: ignore[arg-type]
        outcome=outcome,
        confidence=float(response.get("confidence", 0.5)),
        rationale=str(response.get("rationale", "")).strip()[:500],
        supporting_quote=str(response.get("supporting_quote", "")).strip()[:300],
        site_hint=response.get("site_hint"),  # type: ignore[arg-type]
        source="llm",
    )


def label_corpus(
    rows: Iterable[dict],
    *,
    llm: LlmRelabelFn | None = None,
) -> list[SilverLabel]:
    """Label every encounter row; LLM if provided, else deterministic."""
    out: list[SilverLabel] = []
    for r in rows:
        if llm is None:
            out.append(deterministic_label(**_kwargs_from_row(r)))
            continue
        try:
            out.append(label_with_llm(llm=llm, **_kwargs_from_row(r)))
        except Exception:
            out.append(deterministic_label(**_kwargs_from_row(r)))
    return out


def _kwargs_from_row(r: dict) -> dict:
    return {
        "patient_id": r["patient_id"],
        "encounter_id": r["encounter_id"],
        "encounter_date": r.get("encounter_date"),
        "text": r.get("text") or "",
        "flags": r.get("flags"),
    }


def labels_to_dicts(labels: Iterable[SilverLabel]) -> list[dict]:
    return [asdict(label) for label in labels]
