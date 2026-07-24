"""Stable ``recommendation_key`` assignment across NICE guideline re-ingests.

Atlas trace:
  DI: DI-42246DA7
  DO: DO-F8C56339
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")

``Recommendation.id`` is positional and version-scoped
(``{guideline}:v{N}:CH{idx}:SEC{idx}:R{idx}``, see ``nice_graph_upserter.py``)
-- every re-ingest mints a fresh id for every recommendation, even one whose
clinical text didn't change at all. Continuity today is attempted only via
the human-visible ``r.number`` string (e.g. ``"1.2.9"``), which is exactly
what NICE renumbers on a guideline update (confirmed against the NG12
April-update scenario).

This module mints a LEO-internal ``recommendation_key`` (UUID) once, at
first ingest, and resolves it across re-ingests:

1. **Exact ``number`` match** -- today's cheap path, works when nothing
   moved. Carries the old key forward, no ``renumbered_from``.
2. **Text-similarity fallback** -- only tried for a new recommendation
   whose number has no exact match at all, against old recommendations
   whose number has no *surviving* new recommendation either (a pure
   "orphaned old number" candidate pool, computed once other numbers are
   known -- see ``match_recommendation_keys``). A candidate must clear an
   absolute similarity floor **and** beat the second-best candidate by a
   margin before it wins -- the same two-threshold shape as
   ``libs/coding_engine/tier_classifier.py`` (floor) and
   ``libs/episode_learning/champion_challenger.py``'s ``beats()`` (margin
   over the runner-up). A true split (one recommendation becoming two,
   each ~50% similar to the original) fails the margin check by
   construction, which is correct -- neither side should silently win.
3. **Floor cleared, margin not** -- genuinely ambiguous: a plausible move
   exists but isn't confident. Mints a fresh key (today's safe default,
   same as "no candidate at all") but surfaces the top candidate via
   ``ambiguous_candidate_number`` / ``ambiguous_score`` so a caller (the
   ``GuidelineChangesDrawer`` diff, per the ``nice-renumber-ambiguous-
   prompt`` todo) can prompt an explicit admin yes/no instead of silently
   picking a winner.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

# Mirrors recommendationTextMatch.ts's STOPWORDS -- same rule, ported here,
# so "with" / "or" / "any" never drive a similarity score on their own.
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "of",
        "with",
        "and",
        "or",
        "in",
        "to",
        "for",
        "is",
        "are",
        "any",
        "following",
        "these",
        "that",
    }
)

_WORD_RE = re.compile(r"[A-Za-z0-9']+")

# Absolute floor a candidate must clear to be considered plausible at all
# (tier_classifier.py's threshold-plus-floor shape).
SIMILARITY_FLOOR = 0.55

# How far a candidate must beat the runner-up to be trusted as *the* match,
# not just *a* match (champion_challenger.py's beats() margin-over-
# competitor shape). A genuine split (one rec becoming two, each ~50%
# similar) fails this by construction -- neither side wins outright.
SIMILARITY_MARGIN = 0.15


@dataclass(frozen=True)
class OldRecommendation:
    """One recommendation from the previous ingest version, as fed to the
    matcher -- not a live Neo4j record."""

    number: str
    text: str
    recommendation_key: str


@dataclass(frozen=True)
class NewRecommendation:
    """One recommendation from the current ingest, as fed to the matcher.

    ``ref`` is the caller's own identifier (e.g. the version-scoped
    ``rec_id``) used purely to key the returned results dict -- it plays
    no part in matching itself.
    """

    ref: str
    number: str
    text: str


@dataclass(frozen=True)
class RecommendationKeyMatch:
    """Resolved identity for one new recommendation."""

    recommendation_key: str
    renumbered_from: str | None = None
    ambiguous_candidate_number: str | None = None
    ambiguous_score: float | None = None


def _tokenize(text: str) -> set[str]:
    return {
        w.lower() for w in _WORD_RE.findall(text or "") if w.lower() not in _STOPWORDS
    }


def text_similarity(a: str, b: str) -> float:
    """Jaccard-style token-overlap similarity between two whole recommendation
    texts, in ``[0, 1]``. ``0.0`` when either side has no non-stopword
    tokens at all.
    """
    tokens_a, tokens_b = _tokenize(a), _tokenize(b)
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


def _rank_candidates(
    candidates: list[OldRecommendation], text: str
) -> list[tuple[float, OldRecommendation]]:
    return sorted(
        ((text_similarity(text, c.text), c) for c in candidates),
        key=lambda pair: pair[0],
        reverse=True,
    )


def _match_by_similarity(
    new_rec: NewRecommendation,
    orphaned: list[OldRecommendation],
    claimed_numbers: set[str],
) -> RecommendationKeyMatch:
    """Text-similarity fallback for one new recommendation with no exact
    number match. Mutates ``claimed_numbers`` on a confident match so a
    later new recommendation in the same ingest can't also claim it.
    """
    candidates = [o for o in orphaned if o.number not in claimed_numbers]
    ranked = _rank_candidates(candidates, new_rec.text)
    if not ranked:
        return RecommendationKeyMatch(recommendation_key=str(uuid.uuid4()))

    best_score, best_old = ranked[0]
    second_score = ranked[1][0] if len(ranked) > 1 else 0.0
    if best_score < SIMILARITY_FLOOR:
        return RecommendationKeyMatch(recommendation_key=str(uuid.uuid4()))

    if (best_score - second_score) >= SIMILARITY_MARGIN:
        claimed_numbers.add(best_old.number)
        return RecommendationKeyMatch(
            recommendation_key=best_old.recommendation_key,
            renumbered_from=best_old.number,
        )

    # Clears the floor but not the margin: a plausible move exists but
    # isn't confident enough to carry forward silently.
    return RecommendationKeyMatch(
        recommendation_key=str(uuid.uuid4()),
        ambiguous_candidate_number=best_old.number,
        ambiguous_score=best_score,
    )


def match_recommendation_keys(
    new_recs: list[NewRecommendation],
    old_recs: list[OldRecommendation],
) -> dict[str, RecommendationKeyMatch]:
    """Resolve a stable ``recommendation_key`` for every recommendation in
    ``new_recs``.

    Two passes, computed against the *complete* set of new numbers so
    matching order never matters:

    1. Exact ``number`` match against ``old_recs``.
    2. Text-similarity fallback, but only against old recommendations whose
       number has no surviving new recommendation at all (``orphaned``) --
       an old recommendation that legitimately kept its number is never a
       fallback candidate for a *different* new recommendation.

    ``old_recs`` empty (first-ever ingest) mints a fresh key for every new
    recommendation, no fallback attempted.

    Returns a dict keyed by each ``NewRecommendation.ref``.
    """
    by_number = {o.number: o for o in old_recs}
    new_numbers = {n.number for n in new_recs}
    orphaned = [o for o in old_recs if o.number not in new_numbers]

    claimed_numbers: set[str] = set()
    results: dict[str, RecommendationKeyMatch] = {}
    for new_rec in new_recs:
        exact = by_number.get(new_rec.number)
        if exact is not None:
            results[new_rec.ref] = RecommendationKeyMatch(
                recommendation_key=exact.recommendation_key
            )
            continue
        results[new_rec.ref] = _match_by_similarity(new_rec, orphaned, claimed_numbers)
    return results
