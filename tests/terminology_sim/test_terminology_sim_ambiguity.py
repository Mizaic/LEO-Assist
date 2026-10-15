"""Simulation: withhold an exact match that names more than one concept.

A short lab word such as "Ferritin" matches the substance and the lab level
word for word. Without a concept type, and with no parent or single
preferred wording to settle it, the lookup cannot tell which one the letter
meant, so the code is withheld. With a type, the one exact match of that
type is attached. The simulation gets this from production's own tie rule.
"""

from scripts.terminology_sim.pool import Case, Hit, Pool
from scripts.terminology_sim.strategies import clear_cache, make


def _ferritin_pool() -> Pool:
    return Pool(
        case=Case(case_id="t-ferritin", phrase="Ferritin", tag=""),
        exact=[
            Hit(
                "489004",
                "Ferritin (substance)",
                "substance",
                "Ferritin",
                1.0,
                "term_exact",
            ),
            Hit(
                "993381000000106",
                "Serum ferritin level (observable entity)",
                "observable entity",
                "Ferritin",
                1.2,
                "sf_exact",
            ),
        ],
        fulltext=[],
    )


def test_ambiguous_exact_match_without_type_is_withheld():
    clear_cache()
    strategy = make("gate_prec_qual")
    assert strategy(_ferritin_pool(), None, None) is None


def test_ambiguous_exact_match_with_type_attaches_that_type():
    clear_cache()
    strategy = make("gate_prec_qual")
    got = strategy(_ferritin_pool(), "observable entity", None)
    assert got == "993381000000106"


def test_single_exact_match_without_type_still_attaches():
    clear_cache()
    pool = _ferritin_pool()
    pool = Pool(case=pool.case, exact=pool.exact[:1], fulltext=[])
    strategy = make("gate_prec_qual")
    assert strategy(pool, None, None) == "489004"
