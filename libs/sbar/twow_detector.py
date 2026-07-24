"""Adjudicated 2WW / Faster Diagnosis mention detector (B3.2).

Atlas trace:
  DO: DO-79266FAB
  DI: DI-C31E59C4
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-79266FAB")
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

DETECTOR_VERSION = "1.0"

_ACTIVE_PATTERNS = (
    re.compile(r"\b2ww\b", re.IGNORECASE),
    re.compile(r"\btwo[\s-]?week[\s-]?wait\b", re.IGNORECASE),
    re.compile(r"\bfaster[\s-]?diagnosis\b", re.IGNORECASE),
    re.compile(r"\bfast[\s-]?track\b.*\bcancer\b", re.IGNORECASE),
)

_NEGATION_PREFIX = re.compile(
    r"\b("
    r"no|not|never|without|denies|denied|rule out|r/o|exclude|excluded|"
    r"cancelled|canceled|declined|rejected|discharged from|removed from|"
    r"does not meet|did not meet|not eligible|no longer"
    r")\b[\s,:-]{0,12}$",
    re.IGNORECASE,
)

_HISTORICAL_PREFIX = re.compile(
    r"\b("
    r"previous|prior|past|history of|hx of|was|had|earlier|formerly|"
    r"last year|in \d{4}|referred by me on"
    r")\b[\s,:-]{0,12}$",
    re.IGNORECASE,
)

_TEMPLATE_TITLE_PREFIX = re.compile(
    r"^(?:"
    r"2ww|two week wait|fast track|faster diagnosis|"
    r"prism 2ww|questionnaire|template|form title"
    r")[\s:.-]*$",
    re.IGNORECASE,
)

_CLINICAL_VERB_RE = re.compile(
    r"\b(plan|refer|request|sent|booked|await|seen|discuss|agreed)\b",
    re.IGNORECASE,
)


def _is_template_title_line(text: str) -> bool:
    stripped = str(text or "").strip()
    if not stripped or len(stripped) > 60 or stripped.endswith("."):
        return False
    if _TEMPLATE_TITLE_PREFIX.match(stripped):
        return True
    if not _first_active_match(stripped):
        return False
    return _CLINICAL_VERB_RE.search(stripped) is None


class TwowMentionClass(str, Enum):
    active_claim = "active_claim"
    negated = "negated"
    historical = "historical"
    template_title = "template_title"
    none = "none"


@dataclass(frozen=True)
class TwowMention:
    classification: TwowMentionClass
    matched_text: str
    line: str
    detector_version: str = DETECTOR_VERSION


def classify_twow_mention(line: str) -> TwowMention:
    """Classify one line of clinical text for 2WW pathway claims."""
    text = str(line or "").strip()
    if not text:
        return TwowMention(
            classification=TwowMentionClass.none,
            matched_text="",
            line=text,
        )
    if _is_template_title_line(text):
        return TwowMention(
            classification=TwowMentionClass.template_title,
            matched_text=text[:80],
            line=text,
        )
    matched = _first_active_match(text)
    if not matched:
        return TwowMention(
            classification=TwowMentionClass.none,
            matched_text="",
            line=text,
        )
    prefix = text[: matched.start()].strip()
    if prefix and _NEGATION_PREFIX.search(prefix):
        return TwowMention(
            classification=TwowMentionClass.negated,
            matched_text=matched.group(0),
            line=text,
        )
    if prefix and _HISTORICAL_PREFIX.search(prefix):
        return TwowMention(
            classification=TwowMentionClass.historical,
            matched_text=matched.group(0),
            line=text,
        )
    return TwowMention(
        classification=TwowMentionClass.active_claim,
        matched_text=matched.group(0),
        line=text,
    )


def detect_active_twow_mentions(text: str) -> list[TwowMention]:
    """Return active 2WW claims found in multi-line text."""
    hits: list[TwowMention] = []
    for line in str(text or "").splitlines():
        mention = classify_twow_mention(line)
        if mention.classification is TwowMentionClass.active_claim:
            hits.append(mention)
    return hits


def _first_active_match(text: str) -> re.Match[str] | None:
    for pattern in _ACTIVE_PATTERNS:
        match = pattern.search(text)
        if match:
            return match
    return None
