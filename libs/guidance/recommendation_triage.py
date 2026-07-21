"""Cheap triage of guideline recommendations before expensive rule extraction.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")
"""

from __future__ import annotations

import re
from typing import Literal

TriageBucket = Literal["full_rule", "trigger_plus_narrative", "no_rule"]

_REFERRAL_RE = re.compile(
    r"\b("
    r"refer|referral|urgent(?:ly)?|same[- ]day|2[- ]?ww|two[- ]week|"
    r"investigate|offer\s+(?:a\s+)?(?:test|scan|imaging|blood)|"
    r"consider\s+(?:a\s+)?(?:referral|CT|MRI|ultrasound|colonoscopy)|"
    r"arrange|admit|hospital"
    r")\b",
    re.IGNORECASE,
)

_ADVICE_ACTION_RE = re.compile(
    r"\b("
    r"advise|advice|discuss|information|inform|explain|counsel|"
    r"encourage|support|educat|lifestyle|diet|skin\s+care|moisturis|"
    r"make-up|makeup|sunscreen|syndet|cleanser|picking|scratching"
    r")\b",
    re.IGNORECASE,
)

_INFO_ONLY_RE = re.compile(
    r"\b("
    r"give\s+people\s+.*\s+information|"
    r"include\s+parents\s+and\s+carers|"
    r"topics\s+to\s+cover|"
    r"there\s+is\s+not\s+enough\s+evidence|"
    r"for\s+general\s+advice"
    r")\b",
    re.IGNORECASE,
)

_CLINICAL_TRIGGER_RE = re.compile(
    r"\b("
    r"people\s+with|person\s+with|patients?\s+with|"
    r"diagnos|symptom|sign|lesion|severity|moderate|severe|"
    r"fulminans|suspected|confirmed|aged|years"
    r")\b",
    re.IGNORECASE,
)


def triage_recommendation(verbatim: str) -> TriageBucket:
    """Classify a recommendation for rule-generation cost control.

    - full_rule: referral / investigation / treatment IF-THEN
    - trigger_plus_narrative: clinical population + advice-style action
    - no_rule: information / education with no patient-level action
    """
    text = (verbatim or "").strip()
    if not text:
        return "no_rule"

    has_referral = bool(_REFERRAL_RE.search(text))
    has_advice = bool(_ADVICE_ACTION_RE.search(text))
    info_only = bool(_INFO_ONLY_RE.search(text))
    has_trigger = bool(_CLINICAL_TRIGGER_RE.search(text))

    if info_only and not has_referral:
        return "no_rule"
    if has_referral:
        return "full_rule"
    if has_trigger and has_advice:
        return "trigger_plus_narrative"
    if has_advice and not has_trigger:
        return "no_rule"
    if has_trigger:
        return "trigger_plus_narrative"
    return "no_rule"


def default_selected_for_triage(bucket: TriageBucket) -> bool:
    """Whether the recommendation picker should pre-select this bucket."""
    return bucket in ("full_rule", "trigger_plus_narrative")
