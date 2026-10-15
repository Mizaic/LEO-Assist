"""Candidate fixes for the lookup ranking, as pure functions over a pool.

Every strategy returns the concept production would attach (after the
attach gate, blocklist and type-family filter) or None. Exact matches are
never changed: the fixes only act on keyword (fulltext) matches. Tied exact
matches are settled by production's own rule inside ``baseline_rank``.

Building blocks:
  gate_*    keep a fulltext candidate attachable only if its wording fits.
  soft_*    scale a fulltext candidate's confidence by its word coverage.
  exact     attach exact matches only (withhold every fulltext match).
  tag       when a type is given, drop candidates of another type.
  strip     also look up the phrase without onset/duration wording, and
            prefer an exact match on that.
  production  the resolver's own word gate and strip step (what runs now).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Callable, Optional

from scripts.terminology_sim.features import Fit, best_fits
from scripts.terminology_sim.pool import Pool, attach, baseline_rank, production_rank
from services.terminology_api.app.services.coding_resolver import CodingCandidate

Ranked = list[CodingCandidate]
Ranker = Callable[[Pool, Optional[str]], Ranked]
Strategy = Callable[[Pool, Optional[str], Optional[Pool]], Optional[str]]
_BELOW_GATE = 0.5


def _norm_tag(tag: str | None) -> str:
    return str(tag or "").strip().lower().replace(" ", "_").replace("-", "_")


_CACHE: dict[tuple[int, str], tuple[Ranked, dict[str, Fit]]] = {}


def _base(pool: Pool, tag: str | None) -> tuple[Ranked, dict[str, Fit]]:
    key = (id(pool), tag or "")
    if key not in _CACHE:
        _CACHE[key] = (baseline_rank(pool, tag), best_fits(pool))
    return _CACHE[key]


def clear_cache() -> None:
    _CACHE.clear()


def _cached_baseline(pool: Pool, tag: str | None) -> Ranked:
    return _base(pool, tag)[0]


def _rescore(pool: Pool, tag: str | None, factor: Callable[[Fit], float]) -> Ranked:
    ranked, fits = _base(pool, tag)
    out = []
    for cand in ranked:
        f = fits.get(str(cand.snomed_concept_id))
        if cand.had_exact_match or f is None:
            out.append(cand)
            continue
        out.append(replace(cand, score=cand.score * factor(f)))
    return sorted(out, key=lambda c: c.score, reverse=True)


def _gate(pred: Callable[[Fit], bool]) -> Ranker:
    def rank(pool: Pool, tag: str | None) -> Ranked:
        return _rescore(pool, tag, lambda f: 1.0 if pred(f) else 0.0)

    return rank


def _soft(a: float, b: float) -> Ranker:
    def rank(pool: Pool, tag: str | None) -> Ranked:
        return _rescore(pool, tag, lambda f: (f.precision**a) * (f.recall**b))

    return rank


def _exact_only(pool: Pool, tag: str | None) -> Ranked:
    return [c for c in _cached_baseline(pool, tag) if c.had_exact_match]


RANKERS: dict[str, Ranker] = {
    "baseline": _cached_baseline,
    "exact": _exact_only,
    "gate_prec": _gate(lambda f: f.precision >= 1.0),
    "gate_prec_r50": _gate(lambda f: f.precision >= 1.0 and f.recall >= 0.5),
    "gate_prec_r67": _gate(lambda f: f.precision >= 1.0 and f.recall >= 0.67),
    "gate_prec_qual": _gate(
        lambda f: f.precision >= 1.0 and (f.recall >= 1.0 or f.missing_are_qualifiers)
    ),
    "gate_full": _gate(lambda f: f.precision >= 1.0 and f.recall >= 1.0),
    "soft_p2r1": _soft(2.0, 1.0),
    "soft_p3r1": _soft(3.0, 1.0),
    "soft_p2r05": _soft(2.0, 0.5),
}


def _tag_filter(ranked: Ranked, tag: str | None) -> Ranked:
    want = _norm_tag(tag)
    if not want:
        return ranked
    return [c for c in ranked if _norm_tag(c.semantic_tag) == want]


def make(ranker: str, *, tag_strict: bool = False, strip: bool = False) -> Strategy:
    rank = RANKERS[ranker]

    def finish(pool: Pool, tag: str | None, ranked: Ranked) -> str | None:
        if tag_strict:
            ranked = _tag_filter(ranked, tag)
        return attach(pool.case.phrase, tag, ranked)

    def run(pool: Pool, tag: str | None, stripped: Pool | None) -> str | None:
        if strip and not pool.exact and stripped is not None and stripped.exact:
            got = finish(stripped, tag, _cached_baseline(stripped, tag))
            if got:
                return got
        return finish(pool, tag, rank(pool, tag))

    return run


def production(pool: Pool, tag: str | None, stripped: Pool | None) -> str | None:
    return attach(pool.case.phrase, tag, production_rank(pool, tag, stripped))


def all_strategies() -> dict[str, Strategy]:
    out: dict[str, Strategy] = {"production": production}
    for name in RANKERS:
        for strip in (False, True):
            for tag_strict in (False, True):
                label = (
                    name + ("+strip" if strip else "") + ("+tag" if tag_strict else "")
                )
                out[label] = make(name, tag_strict=tag_strict, strip=strip)
    return out
