"""Pure ranking helpers for few-shot example selection.

Kept free of embedding and I/O concerns so the selection policy can be
unit tested without loading a sentence-transformer model.

Atlas trace:
  DO: DO-83EBEE2C
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-83EBEE2C")
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

Scored = tuple[int, float]


def rank_by_score(indices: Sequence[int], scores: np.ndarray) -> list[Scored]:
    """Pair pool indices with their scores, best first.

    Ties break on the pool index so the order is reproducible across
    runs -- an audit requirement, since the selected example ids are
    recorded against every extraction.
    """
    paired = [(int(idx), float(scores[pos])) for pos, idx in enumerate(indices)]
    paired.sort(key=lambda item: (-item[1], item[0]))
    return paired


def apply_similarity_floor(ranked: Sequence[Scored], floor: float) -> list[Scored]:
    """Drop candidates scoring below ``floor``.

    Returning fewer examples is deliberate: a weak exemplar actively
    misleads extraction rather than being neutral.
    """
    if floor <= 0.0:
        return list(ranked)
    return [(idx, score) for idx, score in ranked if score >= floor]


def mmr_select(
    ranked: Sequence[Scored],
    vectors: np.ndarray | None,
    k: int,
    diversity_lambda: float,
) -> list[int]:
    """Pick ``k`` indices by maximal marginal relevance.

    ``diversity_lambda`` of 1.0 is pure relevance, which short-circuits
    to a plain top-k slice. ``vectors`` must be indexable by pool index
    and hold L2-normalised rows so a dot product is the cosine.
    """
    if k <= 0 or not ranked:
        return []
    if diversity_lambda >= 1.0 or vectors is None or len(ranked) == 1:
        return [idx for idx, _ in ranked[:k]]

    remaining = list(ranked)
    selected: list[int] = []
    while remaining and len(selected) < k:
        best_pos = 0
        best_score = None
        for pos, (idx, relevance) in enumerate(remaining):
            penalty = _max_similarity(vectors, idx, selected)
            score = diversity_lambda * relevance - (1.0 - diversity_lambda) * penalty
            if best_score is None or score > best_score:
                best_score = score
                best_pos = pos
        selected.append(remaining.pop(best_pos)[0])
    return selected


def _max_similarity(vectors: np.ndarray, index: int, selected: Sequence[int]) -> float:
    """Return the highest cosine between ``index`` and anything selected."""
    if not selected:
        return 0.0
    return float(max(float(vectors[index] @ vectors[other]) for other in selected))


def order_for_prompt(examples: Sequence[dict], ascending: bool) -> list[dict]:
    """Order ranked examples for rendering into a prompt.

    Ascending relevance puts the strongest example immediately before
    the query so its pattern is freshest when the model starts
    generating.
    """
    ordered = list(examples)
    if ascending:
        ordered.reverse()
    return ordered
