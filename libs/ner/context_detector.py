"""Lightweight clinical context detection for NER entity assertions.

Detects family history, negation, uncertainty, and historical context
from the encounter text surrounding each entity span. Inspired by
MedSpaCy ConText but purpose-built for UK primary care records without
the heavy dependency chain.

Each detector returns the assertion string to apply, or None if no
context trigger was found. Detectors are applied in priority order;
the first match wins.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ContextRule:
    pattern: re.Pattern[str]
    assertion: str
    direction: str  # "backward" = cue before entity, "forward" = cue after, "bidirectional"
    max_scope: int  # max chars the cue can reach


_FAMILY_RULES: list[ContextRule] = [
    ContextRule(re.compile(r"\bfamily\s+history\b", re.I), "family", "bidirectional", 120),
    ContextRule(re.compile(r"\bfh\s*(?:of|:|\b)", re.I), "family", "bidirectional", 80),
    ContextRule(re.compile(r"\bfhx\s*(?:of|:|\b)", re.I), "family", "bidirectional", 80),
    ContextRule(re.compile(r"\b(?:mother|father|mum|dad|sister|brother|sibling|son|daughter|"
                           r"parent|grandparent|grandmother|grandfather|aunt|uncle|"
                           r"maternal|paternal)\b", re.I), "family", "bidirectional", 60),
    ContextRule(re.compile(r"\bfamily\b", re.I), "family", "bidirectional", 40),
]

_NEGATION_RULES: list[ContextRule] = [
    # Scope 80 chars to cover GP list patterns: "no weight loss/ haematemesis/ jaundice/ fever/ malaena"
    ContextRule(re.compile(r"\b(?:no|denies|denied|nil|without|never|not|absence\s+of|"
                           r"no\s+evidence\s+of|ruled\s+out|excluded)\b", re.I), "absent", "forward", 80),
]

_HISTORICAL_RULES: list[ContextRule] = [
    ContextRule(re.compile(r"\b(?:history\s+of|h/o|hx\s+of|previous(?:ly)?|past|former)\b", re.I),
                "historical", "forward", 60),
]

_UNCERTAINTY_RULES: list[ContextRule] = [
    ContextRule(re.compile(r"\b(?:possible|probable|likely|suspect(?:ed)?|"
                           r"suggestive\s+of|query|differential|"
                           r"rule\s+out|r/o|consider)\b", re.I), "possible", "forward", 50),
    ContextRule(re.compile(r"\?\s*$"), "possible", "backward", 20),
]

_TERMINATOR_RE = re.compile(r"[.;:\n]")

_ALL_RULES = _FAMILY_RULES + _NEGATION_RULES + _HISTORICAL_RULES + _UNCERTAINTY_RULES


def _scope_text(
    encounter_text: str,
    entity_start: int,
    entity_end: int,
    direction: str,
    max_scope: int,
) -> str:
    """Return the text window to search for context cues.

    "backward" = text before the entity (cue precedes entity).
    "forward"  = also text before the entity (cue fires forward onto entity).
    "bidirectional" = text on both sides.
    """
    if direction in ("backward", "forward"):
        lo = max(0, entity_start - max_scope)
        window = encounter_text[lo:entity_start]
        term = _TERMINATOR_RE.search(window[::-1])
        if term:
            window = window[len(window) - term.start():]
        return window
    else:
        lo = max(0, entity_start - max_scope)
        hi = min(len(encounter_text), entity_end + max_scope)
        window = encounter_text[lo:hi]
        return window


def detect_assertion(
    encounter_text: str,
    entity_start: int,
    entity_end: int,
    *,
    rules: list[ContextRule] | None = None,
) -> str:
    """Return the detected assertion for an entity span.

    Priority: family > absent > historical > possible > present.
    """
    if rules is None:
        rules = _ALL_RULES

    detected: dict[str, bool] = {}

    for rule in rules:
        window = _scope_text(encounter_text, entity_start, entity_end, rule.direction, rule.max_scope)
        if rule.pattern.search(window):
            detected.setdefault(rule.assertion, True)

    if "family" in detected:
        return "family"
    if "absent" in detected:
        return "absent"
    if "historical" in detected:
        return "historical"
    if "possible" in detected:
        return "possible"
    return "present"


_SITUATION_NORMALIZATIONS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(?:2ww|two\s+week\s+wait)\s+referral\b", re.I), "fast track referral"),
    (re.compile(r"\b(?:on\s+)?waiting\s+list\s+(?:for|to)\b", re.I), "planned procedure"),
    (re.compile(r"\bbooked\s+(?:for|in)\b", re.I), "planned procedure"),
    (re.compile(r"\bscheduled\s+(?:for|to)\b", re.I), "planned procedure"),
    (re.compile(r"\bplanned\b", re.I), "planned procedure"),
    (re.compile(r"\bawaiting\b", re.I), "planned procedure"),
    (re.compile(r"\breferred\s+(?:for|to)\b", re.I), "referral to service"),
    (re.compile(r"\breferral\s+(?:for|to)\b", re.I), "referral to service"),
]


def normalize_situation_lookup(entity_text: str) -> str | None:
    """Return a SNOMED-friendly lookup term for freeform situation phrases.

    Returns None if no normalization pattern matches, meaning the original
    text should be used as-is for terminology lookup.
    """
    for pattern, canonical in _SITUATION_NORMALIZATIONS:
        if pattern.search(entity_text):
            return canonical
    return None


def apply_context_detection(
    encounter_text: str,
    entities: list[dict[str, Any]],
) -> None:
    """Set assertion on each entity dict based on context cues.

    Also normalizes lookup terms for situation entities whose freeform
    text won't match SNOMED terminology directly.

    Only overrides assertion if the entity doesn't already have a
    non-default assertion set (i.e., only fills in 'present' defaults).
    """
    for ent in entities:
        current = str(ent.get("assertion", "present") or "present").strip()
        if current != "present":
            continue
        start = int(ent.get("start", 0) or 0)
        end = int(ent.get("end", start) or start)
        assertion = detect_assertion(encounter_text, start, end)
        if assertion != "present":
            ent["assertion"] = assertion

    for ent in entities:
        label = str(ent.get("label", "") or "")
        if label != "situation":
            continue
        text = str(ent.get("text", "") or "")
        canonical = normalize_situation_lookup(text)
        if canonical:
            ent["normalized"] = canonical
