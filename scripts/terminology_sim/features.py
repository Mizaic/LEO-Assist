"""Word-coverage features between a phrase and the wording a concept matched on.

The word lists, tokeniser and strip patterns live in
``libs/terminology/word_fit.py`` so the simulation scores the same rule the
resolver runs. This module adds the per-hit view the strategies need.
"""

from __future__ import annotations

from dataclasses import dataclass

from libs.terminology.word_fit import fit_tokens, tokens
from libs.terminology.word_fit import is_qualifier, strip_qualifiers  # noqa: F401
from scripts.terminology_sim.pool import Hit, Pool


@dataclass(frozen=True)
class Fit:
    precision: float
    recall: float
    missing_are_qualifiers: bool
    matched: str
    bm25: float


def fit(phrase_tokens: frozenset[str], hit: Hit) -> Fit:
    wf = fit_tokens(phrase_tokens, hit.matched)
    return Fit(
        precision=wf.precision,
        recall=wf.recall,
        missing_are_qualifiers=wf.missing_are_qualifiers,
        matched=hit.matched,
        bm25=hit.score,
    )


def best_fits(pool: Pool) -> dict[str, Fit]:
    """Best-fitting matched wording per concept across all fulltext hits."""
    phrase_tokens = tokens(pool.case.phrase)
    best: dict[str, Fit] = {}
    for hit in pool.fulltext:
        f = fit(phrase_tokens, hit)
        old = best.get(hit.concept_id)
        if old is None or (f.precision, f.recall, f.bm25) > (
            old.precision,
            old.recall,
            old.bm25,
        ):
            best[hit.concept_id] = f
    return best
