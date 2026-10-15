"""Simulation parity: the "production" strategy runs the resolver's own gate and strip.

Production now drops fulltext hits whose wording does not cover the phrase,
and adds the exact hits of the phrase without onset / duration words to the
phrase's candidates (services/terminology_api/app/services/word_gate.py).
The simulation must score that same code, not a copy of it.

Risk R-76DCF7B7. Phrases are SNOMED wordings or de-identified hard cases.
"""

from __future__ import annotations

from scripts.terminology_sim.pool import Case, Hit, Pool
from scripts.terminology_sim.strategies import all_strategies

CONSTIPATION = "14760008"
NEW_ONSET_ANGINA = "233821000"
BLEEDING = "131148009"
HEMORRHAGE = "50960005"


def _production():
    return all_strategies()["production"]


def test_production_drops_fulltext_that_does_not_cover_the_phrase():
    pool = Pool(
        case=Case(case_id="t-onset", phrase="New-onset constipation", tag="finding"),
        fulltext=[
            Hit(
                NEW_ONSET_ANGINA,
                "New onset angina (disorder)",
                "disorder",
                "New onset angina",
                10.0,
                "term",
            )
        ],
    )
    stripped = Pool(
        case=Case(case_id="t-onset|strip", phrase="constipation", tag="finding"),
        exact=[
            Hit(
                CONSTIPATION,
                "Constipation (finding)",
                "finding",
                "Constipation",
                1.0,
                "term_exact",
                acceptability_rank=2,
            )
        ],
    )
    assert _production()(pool, "finding", stripped) == CONSTIPATION
    assert _production()(pool, "finding", None) is None


def test_production_holds_back_a_stripped_tie_a_fulltext_hit_would_win():
    pool = Pool(
        case=Case(case_id="t-bleed", phrase="recent onset bleeding", tag="finding"),
        fulltext=[
            Hit(
                HEMORRHAGE,
                "Hemorrhage (morphologic abnormality)",
                "morphologic abnormality",
                "Bleeding",
                8.0,
                "term",
            )
        ],
    )
    stripped = Pool(
        case=Case(case_id="t-bleed|strip", phrase="bleeding", tag="finding"),
        exact=[
            Hit(
                HEMORRHAGE,
                "Hemorrhage (morphologic abnormality)",
                "morphologic abnormality",
                "Bleeding",
                1.0,
                "term_exact",
                acceptability_rank=1,
            ),
            Hit(
                BLEEDING,
                "Bleeding (finding)",
                "finding",
                "Bleeding",
                1.0,
                "term_exact",
                acceptability_rank=2,
            ),
        ],
    )
    assert _production()(pool, None, stripped) is None
