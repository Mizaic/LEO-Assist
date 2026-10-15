"""Word fit between a lookup phrase and the wording a SNOMED concept matched on.

precision: share of the matched wording's words that the phrase also has.
           Below 1 means the code claims something the letter did not say.
recall:    share of the phrase's words the matched wording covers.

``covers`` is the attach rule for fulltext hits: precision 1, and every
phrase word the wording misses is a time / onset word, a number, or a
measurement unit.
``strip_qualifiers`` drops onset and duration wording so the clinical part
of a phrase can be looked up on its own.

The resolver and the offline simulation (``scripts/terminology_sim``) both
use this module, so they cannot drift. Risk R-76DCF7B7.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

STOP_WORDS = frozenset(
    "a an and at by for from in into of on or the to with without".split()
)
# Time and onset words: dropping them keeps the clinical meaning of a finding.
QUALIFIERS = frozenset(
    "new newly onset recent recently ongoing current currently since "
    "day days week weeks month months year years hour hours".split()
)
# Measurement units: a reading's value and unit do not change what was
# measured ("blood pressure 130/80 mmHg" -> Blood pressure).
UNITS = frozenset(
    "mmhg kpa kg g mg mcg ug ng ml l dl mmol umol nmol pmol iu "
    "mm cm m m2 bpm".split()
)
_TOKEN = re.compile(r"[a-z0-9]+")
_STRIP_PATTERNS = (
    re.compile(r"\bof (?:new|recent|sudden) onset\b", re.I),
    re.compile(r"\b(?:new|recent|recently)(?:[- ]onset)?\b", re.I),
    re.compile(r"\bnewly\b", re.I),
    re.compile(r"\bonset of\b", re.I),
    re.compile(
        r"\b(?:for|over|since)(?: (?:about|around|approximately|over|the last|"
        r"the past))? \d+ (?:day|week|month|year)s?\b",
        re.I,
    ),
)


@dataclass(frozen=True)
class WordFit:
    precision: float
    recall: float
    missing_are_qualifiers: bool


def strip_qualifiers(phrase: str) -> str:
    """Drop onset and duration wording, e.g. 'New-onset diarrhoea' -> 'diarrhoea'."""
    out = str(phrase or "")
    for pattern in _STRIP_PATTERNS:
        out = pattern.sub(" ", out)
    out = re.sub(r"\s*,\s*$|^\s*[,-]\s*", "", " ".join(out.split()))
    return out.strip(" ,-")


def tokens(text: str) -> frozenset[str]:
    out = set()
    for tok in _TOKEN.findall(str(text or "").lower()):
        if tok in STOP_WORDS:
            continue
        if len(tok) > 4 and tok.endswith("ies"):
            tok = tok[:-3] + "y"
        elif len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss"):
            tok = tok[:-1]
        out.add(tok)
    return frozenset(out)


def is_qualifier(tok: str, measured: bool = False) -> bool:
    """``measured``: the phrase holds a number, so unit words are units.

    Without a number "L" or "m" is more likely left or male than a unit.
    """
    if measured and tok in UNITS:
        return True
    return tok in QUALIFIERS or tok.isdigit() or tok + "s" in QUALIFIERS


def fit_tokens(phrase_tokens: frozenset[str], wording: str) -> WordFit:
    matched = tokens(wording)
    shared = phrase_tokens & matched
    missing = phrase_tokens - matched
    measured = any(t.isdigit() for t in phrase_tokens)
    return WordFit(
        precision=len(shared) / len(matched) if matched else 0.0,
        recall=len(shared) / len(phrase_tokens) if phrase_tokens else 0.0,
        missing_are_qualifiers=bool(shared)
        and all(is_qualifier(t, measured) for t in missing),
    )


def word_fit(phrase: str, wording: str) -> WordFit:
    return fit_tokens(tokens(phrase), wording)


def fit_passes(fit: WordFit) -> bool:
    return fit.precision >= 1.0 and (fit.recall >= 1.0 or fit.missing_are_qualifiers)


def covers(phrase: str, wording: str) -> bool:
    """True when ``wording`` may stand for ``phrase`` (the fulltext attach rule)."""
    return fit_passes(word_fit(phrase, wording))
