"""Simulation parity: tied exact matches settle the way production settles them.

The simulation replays production ranking on saved candidate pools. For tied
exact matches, production uses kind, then parent, then preferred wording,
else holds back (services/terminology_api/app/services/lookup_guards.py). A
pool must therefore carry each Term match's acceptability and which tied
concepts are ancestors of the others, or the simulation scores a different
rule from the one that runs.

Risk R-76DCF7B7. Phrases are SNOMED wordings, not patient text.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from scripts.terminology_sim.pool import Case, Hit, Pool
from scripts.terminology_sim.snapshot import snapshot
from scripts.terminology_sim.strategies import clear_cache, make

FEMALE_CYSTOCELE = "252005008"
BLADDER_PROLAPSE = "1371404005"
DEPRESSIVE_DISORDER = "35489007"
DEPRESSION_OTHER = "370143000"


def _hit(cid, fsn, rank, index="term_exact"):
    return Hit(cid, fsn, "disorder", "Cystocele", 1.0, index, acceptability_rank=rank)


def _cystocele_pool() -> Pool:
    return Pool(
        case=Case(case_id="t-cystocele", phrase="Cystocele", tag="disorder"),
        exact=[
            _hit(FEMALE_CYSTOCELE, "Female cystocele (disorder)", 2),
            _hit(BLADDER_PROLAPSE, "Prolapse of urinary bladder (disorder)", 1),
        ],
        exact_ancestors={FEMALE_CYSTOCELE: [BLADDER_PROLAPSE]},
    )


def test_baseline_picks_parent_like_production():
    clear_cache()
    got = make("baseline")(_cystocele_pool(), "disorder", None)
    assert got == BLADDER_PROLAPSE


def test_baseline_picks_the_one_preferred_wording_like_production():
    clear_cache()
    pool = Pool(
        case=Case(case_id="t-depression", phrase="Depression", tag="disorder"),
        exact=[
            _hit(DEPRESSIVE_DISORDER, "Depressive disorder (disorder)", 2),
            _hit(DEPRESSION_OTHER, "Major depressive disorder (disorder)", 1),
        ],
    )
    assert make("baseline")(pool, "disorder", None) == DEPRESSIVE_DISORDER


def _session(ancestry_error=False):
    exact_rows = [
        {
            "id": FEMALE_CYSTOCELE,
            "fsn": "Female cystocele (disorder)",
            "tag": "disorder",
            "matched": "Cystocele",
            "index": "term_exact",
            "acceptability_rank": 2,
        },
        {
            "id": BLADDER_PROLAPSE,
            "fsn": "Prolapse of urinary bladder (disorder)",
            "tag": "disorder",
            "matched": "Cystocele",
            "index": "term_exact",
            "acceptability_rank": 1,
        },
    ]

    def _run(query, **kwargs):
        if "norms" in kwargs:
            return [{"norm": n, "hits": exact_rows} for n in kwargs["norms"]]
        if "groups" in kwargs:
            if ancestry_error:
                raise RuntimeError("simulated ancestry failure")
            return [
                {
                    "key": g["key"],
                    "child_id": FEMALE_CYSTOCELE,
                    "parent_id": BLADDER_PROLAPSE,
                }
                for g in kwargs["groups"]
            ]
        return []

    session = MagicMock()
    session.run.side_effect = _run
    return session


def test_snapshot_records_acceptability_and_tied_ancestors():
    case = Case(case_id="t-cystocele", phrase="Cystocele", tag="disorder")
    pool = snapshot([case], _session())[0]
    ranks = {h.concept_id: h.acceptability_rank for h in pool.exact}
    assert ranks == {FEMALE_CYSTOCELE: 2, BLADDER_PROLAPSE: 1}
    assert pool.exact_ancestors == {FEMALE_CYSTOCELE: [BLADDER_PROLAPSE]}


def test_snapshot_fails_loudly_when_ancestry_cannot_be_read():
    case = Case(case_id="t-cystocele", phrase="Cystocele", tag="disorder")
    with pytest.raises(RuntimeError):
        snapshot([case], _session(ancestry_error=True))
