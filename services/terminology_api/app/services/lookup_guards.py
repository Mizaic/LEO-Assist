"""Settle tied exact matches before any SNOMED code can be attached.

One phrase can exactly match the wording of several concepts ("Cystocele"
is a synonym of Female cystocele and of Prolapse of urinary bladder). The
exact branch scores them all 1.0, so the first row used to win. This module
settles the tie, in this order:

1. Kind -- the hint's tag, then the hint's tag group. A hint that matches
   none of the tied kinds narrows nothing.
2. Parent -- the most general tied concept that SNOMED itself words this way
   (a Term description, not only a SurfaceForm).
3. Preferred wording -- the one concept whose matched description is
   "preferred". Only when a hint was given.
4. Otherwise nobody wins: every tied candidate is capped at HOLD_BACK_SCORE,
   below the 0.55 attach gate, so a person codes the fact. With no hint,
   only the parent step may settle a tie.

If the parent lookup fails and the kind cannot choose, the tie is held back
with TIEBREAK_UNAVAILABLE rather than guessed (fail-closed-boundary.mdc).

Atlas trace: risk R-76DCF7B7 (incorrect SNOMED code used as a confirmed
clinical fact); exact-match tag rule DI-940E8B7D.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from services.terminology_api.app.queries.terminology import (
    EXACT_TIE_ANCESTRY_QUERY,
)

logger = logging.getLogger(__name__)

HOLD_BACK_SCORE = 0.5
AMBIGUOUS_EXACT = "ambiguous_exact"
TIEBREAK_UNAVAILABLE = "tiebreak_unavailable"
_PREFERRED_RANK = 2

Merged = dict[str, dict[str, Any]]
Scored = list[tuple[float, dict[str, Any]]]


def normalise_semantic_tag(tag: str | None) -> str:
    if not tag:
        return ""
    return str(tag).strip().lower().replace("_", " ")


def annotate_ancestry(merged_by_key: Mapping[str, Merged], session) -> None:
    """Record, on each tied exact candidate, which tied concepts are its ancestors.

    One round trip for every phrase that has more than one exact concept.
    On failure the tied candidates are flagged ``ancestry_failed``.
    """
    groups = []
    for key, merged in merged_by_key.items():
        ids = [cid for cid, c in merged.items() if c.get("had_exact_match")]
        if len(ids) > 1:
            groups.append({"key": key, "ids": ids})
    if not groups:
        return
    try:
        rows = list(session.run(EXACT_TIE_ANCESTRY_QUERY, groups=groups))
    except Exception:
        logger.warning(
            "[resolver] tie ancestry lookup failed; holding back %d tied phrase(s)",
            len(groups),
            exc_info=True,
        )
        for g in groups:
            for cid in g["ids"]:
                merged_by_key[g["key"]][cid]["ancestry_failed"] = True
        return
    for row in rows:
        child = merged_by_key.get(row.get("key"), {}).get(str(row.get("child_id")))
        if child is not None and row.get("parent_id"):
            child.setdefault("ancestor_ids", set()).add(str(row["parent_id"]))


def settle_exact_ties(
    scored: Scored, *, expected_tag: str, tag_groups: Mapping[str, str]
) -> list[tuple[float, dict[str, Any], str]]:
    """Return ``(score, candidate, withheld_reason)`` with ties settled or held back."""
    contenders = [
        c for conf, c in scored if c.get("had_exact_match") and conf > HOLD_BACK_SCORE
    ]
    if len(contenders) < 2:
        return [(conf, c, "") for conf, c in scored]
    winner, reason = _pick_winner(contenders, expected_tag, tag_groups)
    settled = []
    for conf, c in scored:
        if c is winner or conf <= HOLD_BACK_SCORE:
            settled.append((conf, c, ""))
        else:
            settled.append((HOLD_BACK_SCORE, c, reason))
    return settled


def _pick_winner(
    contenders: list[dict[str, Any]],
    expected_tag: str,
    tag_groups: Mapping[str, str],
) -> tuple[dict[str, Any] | None, str]:
    pool = _by_kind(contenders, expected_tag, tag_groups)
    if len(pool) == 1:
        return pool[0], AMBIGUOUS_EXACT
    if any(c.get("ancestry_failed") for c in pool):
        return None, TIEBREAK_UNAVAILABLE
    winner = _by_parent(pool)
    if winner is None and expected_tag:
        winner = _by_preferred(pool)
    return winner, AMBIGUOUS_EXACT


def _by_kind(
    contenders: list[dict[str, Any]],
    expected_tag: str,
    tag_groups: Mapping[str, str],
) -> list[dict[str, Any]]:
    def group(c: dict[str, Any]) -> str:
        return tag_groups.get(normalise_semantic_tag(c.get("semantic_tag")), "")

    if not expected_tag:
        return contenders
    same_tag = [
        c
        for c in contenders
        if normalise_semantic_tag(c.get("semantic_tag")) == expected_tag
    ]
    if same_tag:
        return same_tag
    expected_group = tag_groups.get(expected_tag, "")
    same_group = [
        c for c in contenders if expected_group and group(c) == expected_group
    ]
    return same_group or contenders


def _by_parent(pool: list[dict[str, Any]]) -> dict[str, Any] | None:
    for c in pool:
        if not c.get("term_exact"):
            continue
        others = [o for o in pool if o is not c]
        if all(c["concept_id"] in (o.get("ancestor_ids") or ()) for o in others):
            return c
    return None


def _by_preferred(pool: list[dict[str, Any]]) -> dict[str, Any] | None:
    preferred = [
        c
        for c in pool
        if c.get("term_exact")
        and int(c.get("acceptability_rank") or 0) >= _PREFERRED_RANK
    ]
    return preferred[0] if len(preferred) == 1 else None
