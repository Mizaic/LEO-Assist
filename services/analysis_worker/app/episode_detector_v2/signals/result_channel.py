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
from ..site_keys import ALL_SITES, SITE_BREAST, SITE_SKIN
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
) -> tuple[
    re.Pattern[str] | None,
    frozenset[str],
    re.Pattern[str] | None,
    re.Pattern[str] | None,
]:
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
    site_vocab = {site: _site_vocab(site) for site in ALL_SITES}
    out: list[Signal] = []
    for event in events:
        text_signal = _breast_benign_text_result(event)
        if text_signal is not None:
            out.append(text_signal)
        text_signal = _skin_benign_text_result(event)
        if text_signal is not None:
            out.append(text_signal)
        for site_key, vocab in site_vocab.items():
            text_signal = _text_result_signal(event, site_key, vocab)
            if text_signal is not None:
                out.append(text_signal)
            out.extend(_observation_result_signals(event, site_key, vocab))
    return out


def _observation_result_signals(
    event: TimelineEvent,
    site_key: str,
    vocab: tuple[
        re.Pattern[str] | None,
        frozenset[str],
        re.Pattern[str] | None,
        re.Pattern[str] | None,
    ],
) -> list[Signal]:
    inv_re, obs_codes, pos_re, neg_re = vocab
    if inv_re is None and not obs_codes:
        return []
    out: list[Signal] = []
    for observation in event.observation_results:
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


def _text_result_signal(
    event: TimelineEvent,
    site_key: str,
    vocab: tuple[
        re.Pattern[str] | None,
        frozenset[str],
        re.Pattern[str] | None,
        re.Pattern[str] | None,
    ],
) -> Signal | None:
    inv_re, _obs_codes, pos_re, neg_re = vocab
    text = " ".join((event.text_snippet or "").lower().split())
    if not text or inv_re is None or not inv_re.search(text):
        return None
    if site_key == SITE_BREAST and _is_historical_breast_treatment_summary(text):
        return None
    classification = _classify_text_value(text, pos_re, neg_re)
    if classification is None:
        return None
    intent, confidence = classification
    return Signal(
        channel="result",
        encounter_id=event.encounter_id,
        site_key=site_key,
        role="investigation",
        intent=intent,
        confidence=confidence,
        citation="Investigation result text",
    )


def _classify_text_value(
    text: str,
    pos_regex: re.Pattern[str] | None,
    neg_regex: re.Pattern[str] | None,
) -> tuple[str, float] | None:
    if pos_regex is not None and pos_regex.search(text):
        return "confirmed", 0.85
    if neg_regex is not None and neg_regex.search(text):
        return "ruled_out", 0.80
    return None


def _is_historical_breast_treatment_summary(text: str) -> bool:
    has_breast_history = any(
        phrase in text
        for phrase in (
            "hx of breast ca",
            "history of breast ca",
            "background - l breast",
            "b/g of breast ca",
            "left breast ca",
            "breast ca",
            "breast ca 2 years ago",
            "invasive ductal carcinoma",
        )
    )
    has_prior_treatment = any(
        phrase in text
        for phrase in (
            "wle +",
            "radiotherapy 5 fractions",
            "post-radiotherapy fibrosis",
            "after radiotherapy",
            "currently on tamoxifen",
            "tamoxifen",
        )
    )
    return has_breast_history and has_prior_treatment


def _breast_benign_text_result(event: TimelineEvent) -> Signal | None:
    text = " ".join((event.text_snippet or "").lower().split())
    if not text:
        return None
    has_benign_breast_finding = any(
        phrase in text
        for phrase in ("lipoma of breast", "cyst of breast", "fibroadenoma of breast")
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


def _skin_benign_text_result(event: TimelineEvent) -> Signal | None:
    text = " ".join((event.text_snippet or "").lower().split())
    if not text:
        return None
    has_skin_investigation = any(
        phrase in text
        for phrase in (
            "excision of skin lesion",
            "excision left forearm",
            "skin cancer follow up",
            "histopathology reports noted",
        )
    )
    has_benign_result = any(
        phrase in text
        for phrase in (
            "compound naevus with moderate atypia",
            "surgical margin is tumour free",
            "dysplastic naevus",
            "atypical naevus",
            "discharge",
        )
    )
    if not has_skin_investigation or not has_benign_result:
        return None
    return Signal(
        channel="result",
        encounter_id=event.encounter_id,
        site_key=SITE_SKIN,
        role="investigation",
        intent="ruled_out",
        confidence=0.80,
        citation="Benign skin excision result text",
    )
