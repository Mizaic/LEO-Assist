"""Candidate pools for the lookup simulation, and today's ranking as a baseline.

A pool is everything the knowledge graph returned for one phrase: exact
hits and keyword (fulltext) hits, each with the wording that matched. The
baseline replays scoring from before the word gate by calling the
resolver's own ``_fuse_and_rank``; ``production_rank`` adds the resolver's
own word gate and strip step, so both are the real code, not a copy.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from libs.pipeline.coding_candidate_gate import filter_coding_candidates
from libs.pipeline_graph.subgraphs.terminology import (
    _DEFAULT_MIN_SCORE,
    _is_blocked_mapping,
)
from libs.terminology.surface_normalize import normalize_surface
from services.terminology_api.app.services.coding_resolver import (
    CodingCandidate,
    CodingResolver,
    _push,
)
from services.terminology_api.app.services.word_gate import (
    apply_word_gate,
    merge_stripped_exact,
)

ATTACH_GATE = _DEFAULT_MIN_SCORE
SF_SCORE_FACTOR = 1.2


@dataclass(frozen=True)
class Hit:
    """One concept returned by one retrieval branch for one phrase."""

    concept_id: str
    fsn: str
    semantic_tag: str
    matched: str
    score: float
    index: str
    variant: str = ""
    acceptability_rank: int = 0


@dataclass
class Case:
    """A phrase to look up and what a correct answer is."""

    case_id: str
    phrase: str
    tag: str
    expected: list[str] = field(default_factory=list)
    expect_no_code: bool = False
    source: str = ""


@dataclass
class Pool:
    """``exact_ancestors`` maps a tied exact concept to the tied concepts above it."""

    case: Case
    exact: list[Hit] = field(default_factory=list)
    fulltext: list[Hit] = field(default_factory=list)
    exact_ancestors: dict[str, list[str]] = field(default_factory=dict)

    def hidden(self, phrase: str | None = None) -> "Pool":
        """The same pool as if no surface form for ``phrase`` had been made.

        SNOMED's own descriptions stay: the question is whether the lookup
        would be right without the person-made mapping.
        """
        norm = normalize_surface(phrase or self.case.phrase)

        def keep(hit: Hit) -> bool:
            if hit.index not in ("sf", "sf_exact"):
                return True
            return normalize_surface(hit.matched) != norm

        return Pool(
            case=self.case,
            exact=[h for h in self.exact if keep(h)],
            fulltext=[h for h in self.fulltext if keep(h)],
            exact_ancestors=self.exact_ancestors,
        )


def _hit_rec(hit: Hit) -> dict[str, Any]:
    is_sf = hit.index in ("sf", "sf_exact")
    score = 1.2 if hit.index == "sf_exact" else 1.0
    if hit.index in ("term", "sf"):
        score = hit.score * (SF_SCORE_FACTOR if is_sf else 1.0)
    rec = {
        "concept_id": hit.concept_id,
        "fsn": hit.fsn,
        "semantic_tag": hit.semantic_tag,
        "read_codes": [],
        "score": score,
        "surface_form_status": "approved" if is_sf else "",
        "matched": hit.matched,
    }
    if hit.index == "term_exact":
        rec["match_source"] = "term"
        rec["acceptability_rank"] = hit.acceptability_rank
    elif hit.index == "sf_exact":
        rec["match_source"] = "surface_form"
    return rec


def merged_for(pool: Pool) -> dict[str, dict[str, Any]]:
    """Rebuild the resolver's per-concept accumulator from a pool."""
    merged: dict[str, dict[str, Any]] = {}
    if pool.exact:
        for hit in pool.exact:
            _push(merged, _hit_rec(hit), "lexical_exact")
        for cid, ancestors in pool.exact_ancestors.items():
            if cid in merged:
                merged[cid]["ancestor_ids"] = set(ancestors)
        return merged
    for hit in pool.fulltext:
        _push(merged, _hit_rec(hit), "lexical")
    return merged


def baseline_rank(pool: Pool, tag: str | None) -> list[CodingCandidate]:
    """Ranking before the word gate and strip step (exact short-circuits fulltext)."""
    resolver = CodingResolver.__new__(CodingResolver)
    return resolver._fuse_and_rank(merged_for(pool), expected_tag=tag or None)


def production_rank(
    pool: Pool, tag: str | None, stripped: Pool | None
) -> list[CodingCandidate]:
    """Today's resolver: exact, else the stripped phrase's exact hits plus the
    fulltext hits that cover the phrase, ranked by ``_fuse_and_rank``."""
    merged = merged_for(pool)
    if not pool.exact and stripped is not None and stripped.exact:
        merge_stripped_exact(merged, merged_for(stripped), stripped.case.phrase)
    apply_word_gate(merged, pool.case.phrase)
    resolver = CodingResolver.__new__(CodingResolver)
    return resolver._fuse_and_rank(merged, expected_tag=tag or None)


def attach(
    phrase: str, tag: str | None, ranked: Iterable[CodingCandidate]
) -> str | None:
    """The concept production would attach: gate, blocklist, type family."""
    entity = {"text": phrase, "semantic_tag": tag or ""}
    shortlist = filter_coding_candidates(
        entity,
        [
            {
                "concept_id": c.snomed_concept_id,
                "term": c.snomed_term,
                "semantic_tag": c.semantic_tag,
                "score": c.score,
                "had_exact_match": c.had_exact_match,
            }
            for c in ranked
        ],
        is_blocked=_is_blocked_mapping,
        min_score=ATTACH_GATE,
    )
    return str(shortlist[0]["concept_id"]) if shortlist else None


def save_pools(path: Path, pools: list[Pool]) -> None:
    rows = [asdict(p) for p in pools]
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump(rows, handle)


def _pool_from_row(row: dict[str, Any]) -> Pool:
    return Pool(
        case=Case(**row["case"]),
        exact=[Hit(**h) for h in row.get("exact") or []],
        fulltext=[Hit(**h) for h in row.get("fulltext") or []],
        exact_ancestors=row.get("exact_ancestors") or {},
    )


def load_pools(path: Path) -> list[Pool]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        return [_pool_from_row(row) for row in json.load(handle)]
