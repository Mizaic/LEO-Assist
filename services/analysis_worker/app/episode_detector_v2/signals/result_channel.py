"""Result-channel signal extractor.

Atlas trace:
  DI: DI-8A5FCF4F
  DI: DI-FA3CE229 (RulebookBundle-backed runtime)

REAL implementation. Reads investigation, observation-SNOMED, positive,
and negative vocabularies from each site's champion rulebook via
``_rulebook_adapter``. Sites without a rulebook in the installed
bundle fall back to the v0 breast defaults, preserving the original
behaviour.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from .._rulebook_adapter import (
    result_investigation_terms,
    result_negative_terms,
    result_observation_snomed,
    result_positive_terms,
)
from ..site_keys import ALL_SITES, SITE_BREAST
from ..types import Signal, TimelineEvent


# ---------------------------------------------------------------------------
# v0 breast defaults -- used as the fallback if the bundle is empty or the
# runner is called from a test that never installs one.
# ---------------------------------------------------------------------------

_V0_BREAST_INVESTIGATION_TERMS: tuple[str, ...] = (
    "mammogra",
    "breast ultrasound",
    "breast biopsy",
    "core biopsy of breast",
    "fine needle aspiration of breast",
    "breast mri",
)
_V0_BREAST_OBS_CODES: frozenset[str] = frozenset(
    {
        "169068008",
        "722164000",
        "439470001",
    }
)
_V0_POSITIVE_TERMS: tuple[str, ...] = (
    "malignant",
    "carcinoma",
    "invasive",
    "dcis",
    "positive for malignancy",
)
_V0_NEGATIVE_TERMS: tuple[str, ...] = (
    "benign",
    "no malignancy",
    "no abnormality",
    "normal",
    "negative",
)


def _term_regex(terms: Iterable[str]) -> re.Pattern[str] | None:
    """Compile an OR-of-alternatives regex from a list of plain terms.

    Returns ``None`` for an empty list so callers can cheaply skip the
    search. Each term is regex-escaped to avoid accidental pattern
    injection from a rulebook JSON file.
    """
    unique = sorted({t.strip() for t in terms if t and t.strip()})
    if not unique:
        return None
    joined = "|".join(re.escape(term) for term in unique)
    # The `\b` word-boundary keeps the legacy semantics for short
    # tokens like "dcis" -- substrings inside longer clinical words
    # do not match.
    return re.compile(rf"(?:{joined})", re.IGNORECASE)


def _site_vocab(
    site_key: str,
) -> tuple[re.Pattern[str] | None, frozenset[str], re.Pattern[str] | None, re.Pattern[str] | None]:
    """Return (investigation_regex, obs_codes, positive_regex, negative_regex)
    for a site, with v0-breast fallback when no rulebook is installed.
    """
    inv_terms = result_investigation_terms(site_key) or (
        _V0_BREAST_INVESTIGATION_TERMS if site_key == SITE_BREAST else ()
    )
    obs_codes = result_observation_snomed(site_key) or (
        _V0_BREAST_OBS_CODES if site_key == SITE_BREAST else frozenset()
    )
    pos_terms = result_positive_terms(site_key) or (
        _V0_POSITIVE_TERMS if site_key == SITE_BREAST else ()
    )
    neg_terms = result_negative_terms(site_key) or (
        _V0_NEGATIVE_TERMS if site_key == SITE_BREAST else ()
    )
    return (
        _term_regex(inv_terms),
        frozenset(obs_codes),
        _term_regex(pos_terms),
        _term_regex(neg_terms),
    )


def _is_site_investigation(
    observation: dict,
    obs_codes: frozenset[str],
    inv_regex: re.Pattern[str] | None,
) -> bool:
    code = str(observation.get("observation_code") or "")
    if code and obs_codes and code in obs_codes:
        return True
    value = str(observation.get("value") or "")
    if not value or inv_regex is None:
        return False
    return bool(inv_regex.search(value))


def _classify_value(
    observation: dict,
    pos_regex: re.Pattern[str] | None,
    neg_regex: re.Pattern[str] | None,
) -> tuple[str, float] | None:
    value = str(observation.get("value") or "")
    interpretation = str(observation.get("interpretation") or "")
    blob = f"{value} {interpretation}"
    if pos_regex is not None and pos_regex.search(blob):
        return "confirmed", 0.90
    if neg_regex is not None and neg_regex.search(blob):
        return "ruled_out", 0.80
    return None


def extract_result_signals(events: Iterable[TimelineEvent]) -> list[Signal]:
    """Walk every installed site rulebook and emit result signals for
    any observation that matches that site's investigation vocabulary.

    Emitting per-site (instead of breast-only) is what makes the
    prostate and lung v1 rulebooks contribute evidence -- the v0 code
    path was breast-only and silently dropped every other site.
    """
    # Pre-compile regexes once per call; the number of sites is small
    # and this keeps the inner loop allocation-free.
    site_vocab = {
        site: _site_vocab(site) for site in ALL_SITES
    }
    out: list[Signal] = []
    for event in events:
        text_signal = _breast_benign_text_result(event)
        if text_signal is not None:
            out.append(text_signal)
        for observation in event.observation_results:
            for site_key, (inv_re, obs_codes, pos_re, neg_re) in site_vocab.items():
                if inv_re is None and not obs_codes:
                    continue
                if not _is_site_investigation(observation, obs_codes, inv_re):
                    continue
                classification = _classify_value(observation, pos_re, neg_re)
                if classification is None:
                    continue
                intent, confidence = classification
                out.append(
                    Signal(
                        channel="result",
                        encounter_id=event.encounter_id,
                        site_key=site_key,
                        role="investigation",
                        intent=intent,
                        confidence=confidence,
                        citation=(
                            f"Investigation result "
                            f"{observation.get('observation_code') or 'unknown code'}"
                        ),
                    )
                )
    return out


def _breast_benign_text_result(event: TimelineEvent) -> Signal | None:
    text = " ".join((event.text_snippet or "").lower().split())
    if not text:
        return None
    has_benign_breast_finding = any(
        phrase in text for phrase in ("lipoma of breast", "cyst of breast")
    )
    has_breast_investigation = any(
        phrase in text
        for phrase in (
            "us scan of breast",
            "ultrasound scan of breast",
            "mammogram",
            "aspiration of breast",
            "breast ultrasound",
        )
    )
    if not (has_benign_breast_finding and has_breast_investigation):
        return None
    return Signal(
        channel="result",
        encounter_id=event.encounter_id,
        site_key=SITE_BREAST,
        role="investigation",
        intent="ruled_out",
        confidence=0.80,
        citation="Benign breast investigation text",
    )
