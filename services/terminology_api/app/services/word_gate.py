"""Fulltext candidates must cover the phrase they stand for.

The fulltext branch is an any-word search, so a hit can share one word
with the phrase and still score high ("New onset" -> New relationship).
Each fulltext row carries the description wording it matched on. A
fulltext-only candidate is kept only when one of its wordings claims
nothing the phrase did not say, and the phrase words it misses are only
time / onset words or numbers (``libs.terminology.word_fit.covers``).
Exact candidates are never changed here.

A candidate with no wording at all is dropped: without the wording the
gate cannot check it, so it must not be attached.

When a phrase has no exact match, the phrase without its onset and duration
words ("New-onset constipation" -> "constipation") is looked up on the exact
branch too. Its exact hits join the phrase's own candidates, marked
``lookup_variant="stripped"``, so they take part in the tie-break like any
exact hit: a tie that is held back cannot be won back by a fulltext hit on
one of the same concepts. The fact text is not changed, so ConText still
sees "new onset" / "for 3 months".

Risk R-76DCF7B7 (incorrect SNOMED code used as a confirmed clinical fact).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from libs.terminology.surface_normalize import normalize_surface
from libs.terminology.word_fit import (
    fit_passes,
    fit_tokens,
    strip_qualifiers,
    tokens,
)

Merged = dict[str, Any]


def keep_wording(candidate: Merged, rec: Mapping[str, Any], score: float) -> None:
    """Record the wording one fulltext row matched on, with its score."""
    wording = str(rec.get("matched") or "").strip()
    if wording:
        candidate.setdefault("wordings", []).append((wording, score))


def apply_word_gate(merged: dict[str, Merged], phrase: str) -> None:
    """Drop fulltext-only candidates none of whose wordings cover ``phrase``."""
    phrase_tokens = tokens(phrase)
    for cid in list(merged):
        candidate = merged[cid]
        if candidate.get("had_exact_match"):
            continue
        covering = [
            w
            for w in candidate.get("wordings") or []
            if fit_passes(fit_tokens(phrase_tokens, w[0]))
        ]
        if covering:
            candidate["wordings"] = covering
        else:
            del merged[cid]


def stripped_text(phrase: str) -> str:
    """The phrase without onset / duration words, or "" when that changes nothing."""
    out = strip_qualifiers(phrase)
    if not out or normalize_surface(out) == normalize_surface(phrase):
        return ""
    return out


def merge_stripped_exact(
    merged: dict[str, Merged], stripped: Mapping[str, Merged], text: str
) -> None:
    """Add the exact hits of the stripped phrase ``text`` to the phrase's candidates."""
    for cid, hit in stripped.items():
        if not hit.get("had_exact_match"):
            continue
        joined = dict(hit, lookup_variant="stripped", exact_wording=text)
        old = merged.get(cid)
        if old is not None:
            joined["lexical_raw"] = max(old["lexical_raw"], hit["lexical_raw"])
            joined["wordings"] = list(old.get("wordings") or [])
        merged[cid] = joined


def best_wording(candidate: Merged) -> str:
    """The wording the candidate matched on: the stripped phrase for a stripped
    exact hit, else its best-scoring fulltext wording ("" if none)."""
    if candidate.get("exact_wording"):
        return str(candidate["exact_wording"])
    wordings = candidate.get("wordings") or []
    if not wordings:
        return ""
    return max(wordings, key=lambda w: w[1])[0]
