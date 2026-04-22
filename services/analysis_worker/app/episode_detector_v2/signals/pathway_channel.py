"""Pathway-channel signal extractor.

Atlas trace:
  DI: DI-8A5FCF4F

REAL implementation. Uses ``referral_form`` data (urgency, source,
form_type) on each :class:`TimelineEvent` to emit signals for any
recognised pathway. Site is inferred from the form's ``form_type``
field where possible; otherwise from explicit site hints in
``reason``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from ..site_keys import (
    ALL_SITES,
    SITE_BREAST,
    SITE_LOWER_GI,
    SITE_LUNG,
    SITE_UPPER_GI,
    SITE_GYNAE,
    SITE_HEAD_NECK,
    SITE_PROSTATE_UROLOGICAL,
    SITE_SKIN,
    SITE_HAEMATOLOGY,
    SITE_BRAIN_CNS,
    SITE_UNKNOWN,
)
from ..types import Signal, TimelineEvent


_FORM_TYPE_TO_SITE = {
    # Canonical 2ww_<site_key> form types built by the live-graph
    # normaliser. Keep in sync with site_keys.ALL_SITES.
    "2ww_breast": SITE_BREAST,
    "2ww_upper_gi": SITE_UPPER_GI,
    "2ww_lower_gi": SITE_LOWER_GI,
    "2ww_lung": SITE_LUNG,
    "2ww_gynae": SITE_GYNAE,
    "2ww_head_neck": SITE_HEAD_NECK,
    "2ww_prostate_urological": SITE_PROSTATE_UROLOGICAL,
    "2ww_skin": SITE_SKIN,
    "2ww_haematology": SITE_HAEMATOLOGY,
    "2ww_brain_cns": SITE_BRAIN_CNS,
    # Legacy aliases kept for back-compatibility with the pre-rebind
    # synthetic test fixtures and any cached referral form payloads.
    "breast_2ww": SITE_BREAST,
    "upper_gi_2ww": SITE_UPPER_GI,
    "lower_gi_2ww": SITE_LOWER_GI,
    "lung_2ww": SITE_LUNG,
    "2ww_prostate": SITE_PROSTATE_UROLOGICAL,
    "2ww_urology": SITE_PROSTATE_UROLOGICAL,
    "2ww_brain": SITE_BRAIN_CNS,
}


_REASON_TO_SITE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bbreast\b", re.I), SITE_BREAST),
    (re.compile(r"\b(oesophagus|gastric|stomach|upper gi|dysphagia)\b", re.I), SITE_UPPER_GI),
    (re.compile(r"\b(colorectal|colon|rectal|lower gi|pr bleed)\b", re.I), SITE_LOWER_GI),
    (re.compile(r"\b(lung|chest|haemoptysis)\b", re.I), SITE_LUNG),
    (re.compile(r"\b(ovarian|cervical|endometrial|gynae)\b", re.I), SITE_GYNAE),
    (re.compile(r"\b(head and neck|throat|laryng)\b", re.I), SITE_HEAD_NECK),
    (re.compile(r"\b(prostate|urology|urological|psa)\b", re.I), SITE_PROSTATE_UROLOGICAL),
    (re.compile(r"\b(melanoma|skin lesion)\b", re.I), SITE_SKIN),
    (re.compile(r"\b(leuk|lymph|myeloma)\b", re.I), SITE_HAEMATOLOGY),
    (re.compile(r"\b(brain|cns|glioma)\b", re.I), SITE_BRAIN_CNS),
]


def _site_from_form(form: dict | None) -> str:
    if not form:
        return SITE_UNKNOWN
    raw_type = (form.get("form_type") or "").strip().lower()
    if raw_type in _FORM_TYPE_TO_SITE:
        return _FORM_TYPE_TO_SITE[raw_type]
    reason = str(form.get("reason") or "")
    for pattern, site in _REASON_TO_SITE_PATTERNS:
        if pattern.search(reason):
            return site
    return SITE_UNKNOWN


def _intent_from_urgency(urgency: str | None) -> tuple[str, float]:
    norm = (urgency or "").strip().lower()
    if norm in {"2ww", "two_week_wait", "urgent_suspected_cancer", "fast_track"}:
        return "suspected", 0.85
    if norm in {"urgent"}:
        return "suspected", 0.65
    if norm in {"routine"}:
        return "unspecified", 0.40
    return "unspecified", 0.30


def extract_pathway_signals(events: Iterable[TimelineEvent]) -> list[Signal]:
    out: list[Signal] = []
    for event in events:
        form = event.referral_form
        if not form:
            continue
        site = _site_from_form(form)
        if site == SITE_UNKNOWN or site not in ALL_SITES:
            continue
        intent, confidence = _intent_from_urgency(form.get("urgency"))
        out.append(
            Signal(
                channel="pathway",
                encounter_id=event.encounter_id,
                site_key=site,
                role="referral",
                intent=intent,
                confidence=confidence,
                citation=(
                    f"Referral form {form.get('form_type') or 'unknown'} "
                    f"({form.get('urgency') or 'unknown urgency'})"
                ),
            )
        )
    return out
