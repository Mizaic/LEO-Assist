"""Tied exact matches: kind, then parent, then preferred wording, else hold back.

When one phrase exactly matches the wording of more than one SNOMED concept,
the resolver must not attach whichever row came first. It settles the tie in
this order:

1. Kind: the hint's tag, then the hint's group. A hint that matches none
   of the tied kinds narrows nothing ("Serum triglyceride levels" as an
   observable is not handed to the finding).
2. Parent: the most general concept that SNOMED itself words this way
   ("Cystocele" -> Prolapse of urinary bladder). A concept that arrives only
   through a SurfaceForm cannot win as the parent ("Depressive disorder").
3. Preferred wording: the one concept whose matched description is
   "preferred". Only when a hint was given.
4. Otherwise every tied candidate is capped below the attach gate. With no
   hint, only the parent step may settle a tie ("Urticaria" is held back).

Risk R-76DCF7B7 (incorrect SNOMED code used as a confirmed clinical fact).
Phrases are SNOMED wordings, not patient text.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from services.terminology_api.app.services.coding_resolver import CodingResolver

ATTACH_GATE = 0.55

URTICARIA_DISORDER = "126485001"
URTICARIA_MORPHOLOGY = "64305001"
FEMALE_CYSTOCELE = "252005008"
BLADDER_PROLAPSE = "1371404005"
FREE_THYROXINE_LEVEL = "1030801000000101"
SERUM_FREE_T4_LEVEL = "1016971000000106"
DEPRESSIVE_DISORDER = "35489007"
MENTAL_DISORDER = "74732009"
UREA_SUBSTANCE = "387092000"
UREA_PRODUCT = "777896000"
UREA_MEASUREMENT = "105010007"
BODY_WEIGHT = "27113001"
WEIGHING_PATIENT = "39857003"
COUGH = "49727002"
TRIGLYCERIDE_FINDING = "365796000"
TRIGLYCERIDE_MEASUREMENT = "271245006"


def _exact(cid, fsn, tag, *, term=True, rank=2, ancestors=()):
    return {
        "concept_id": cid,
        "fsn": fsn,
        "semantic_tag": tag,
        "read_codes": [],
        "lexical_raw": 1.0 if term else 1.2,
        "vector_raw": 0.0,
        "had_exact_match": True,
        "surface_form_status": "" if term else "approved",
        "term_exact": term,
        "acceptability_rank": rank if term else 0,
        "ancestor_ids": set(ancestors),
    }


def _rank(*rows, expected_tag=None):
    merged = {r["concept_id"]: r for r in rows}
    out = CodingResolver()._fuse_and_rank(merged, expected_tag=expected_tag)
    return {c.snomed_concept_id: c for c in out}


def _urticaria():
    return (
        _exact(URTICARIA_DISORDER, "Urticaria (disorder)", "disorder"),
        _exact(
            URTICARIA_MORPHOLOGY,
            "Urticaria (morphologic abnormality)",
            "morphologic_abnormality",
        ),
    )


def _cystocele():
    return (
        _exact(
            FEMALE_CYSTOCELE,
            "Female cystocele (disorder)",
            "disorder",
            rank=2,
            ancestors={BLADDER_PROLAPSE},
        ),
        _exact(
            BLADDER_PROLAPSE,
            "Prolapse of urinary bladder (disorder)",
            "disorder",
            rank=1,
        ),
    )


class TestKind:
    def test_urticaria_situation_hint_picks_disorder_not_morphology(self):
        got = _rank(*_urticaria(), expected_tag="situation")
        assert got[URTICARIA_DISORDER].score >= ATTACH_GATE
        assert got[URTICARIA_MORPHOLOGY].score < ATTACH_GATE
        assert got[URTICARIA_MORPHOLOGY].withheld_reason == "ambiguous_exact"
        assert got[URTICARIA_DISORDER].withheld_reason == ""

    def test_urticaria_no_hint_is_held_back_not_guessed_clinical(self):
        got = _rank(*_urticaria())
        assert all(c.score < ATTACH_GATE for c in got.values())
        assert {c.withheld_reason for c in got.values()} == {"ambiguous_exact"}

    def test_no_hint_preferred_wording_does_not_settle_tie(self):
        got = _rank(
            _exact(BODY_WEIGHT, "Body weight (observable entity)", "observable entity"),
            _exact(
                WEIGHING_PATIENT, "Weighing patient (procedure)", "procedure", rank=1
            ),
        )
        assert all(c.score < ATTACH_GATE for c in got.values())
        assert {c.withheld_reason for c in got.values()} == {"ambiguous_exact"}

    def test_weight_observable_hint_picks_body_weight_not_procedure(self):
        got = _rank(
            _exact(
                BODY_WEIGHT,
                "Body weight (observable entity)",
                "observable entity",
                rank=1,
            ),
            _exact(
                WEIGHING_PATIENT,
                "Weighing patient (procedure)",
                "procedure",
                term=False,
            ),
            expected_tag="observable entity",
        )
        assert got[BODY_WEIGHT].score >= ATTACH_GATE
        assert got[WEIGHING_PATIENT].score < ATTACH_GATE

    def test_hint_matching_no_tied_kind_does_not_fall_back_to_clinical(self):
        got = _rank(
            _exact(
                TRIGLYCERIDE_FINDING,
                "Finding of serum triglyceride levels (finding)",
                "finding",
                rank=1,
            ),
            _exact(
                TRIGLYCERIDE_MEASUREMENT,
                "Measurement of serum triglyceride level (procedure)",
                "procedure",
                rank=1,
            ),
            expected_tag="observable entity",
        )
        assert all(c.score < ATTACH_GATE for c in got.values())
        assert {c.withheld_reason for c in got.values()} == {"ambiguous_exact"}


class TestParent:
    def test_cystocele_picks_parent_prolapse_of_urinary_bladder(self):
        got = _rank(*_cystocele(), expected_tag="disorder")
        assert got[BLADDER_PROLAPSE].score >= ATTACH_GATE
        assert got[FEMALE_CYSTOCELE].score < ATTACH_GATE

    def test_free_t4_picks_free_thyroxine_level_over_surface_form_child(self):
        got = _rank(
            _exact(
                FREE_THYROXINE_LEVEL,
                "Free thyroxine level (observable entity)",
                "observable entity",
                rank=1,
            ),
            _exact(
                SERUM_FREE_T4_LEVEL,
                "Serum free T4 level (observable entity)",
                "observable entity",
                term=False,
                ancestors={FREE_THYROXINE_LEVEL},
            ),
            expected_tag="observable entity",
        )
        assert got[FREE_THYROXINE_LEVEL].score >= ATTACH_GATE
        assert got[SERUM_FREE_T4_LEVEL].score < ATTACH_GATE

    def test_surface_form_only_parent_cannot_win(self):
        got = _rank(
            _exact(
                DEPRESSIVE_DISORDER,
                "Depressive disorder (disorder)",
                "disorder",
                rank=2,
                ancestors={MENTAL_DISORDER},
            ),
            _exact(
                MENTAL_DISORDER, "Mental disorder (disorder)", "disorder", term=False
            ),
            expected_tag="disorder",
        )
        assert got[MENTAL_DISORDER].score < ATTACH_GATE
        assert got[DEPRESSIVE_DISORDER].score >= ATTACH_GATE


class TestHoldBack:
    def test_urea_substance_product_procedure_all_held_back(self):
        got = _rank(
            _exact(UREA_SUBSTANCE, "Urea (substance)", "substance"),
            _exact(UREA_PRODUCT, "Urea (product)", "product"),
            _exact(
                UREA_MEASUREMENT,
                "Urea measurement (procedure)",
                "procedure",
                term=False,
            ),
            expected_tag="observable entity",
        )
        assert all(c.score < ATTACH_GATE for c in got.values())
        assert {c.withheld_reason for c in got.values()} == {"ambiguous_exact"}

    def test_single_exact_concept_untouched(self):
        got = _rank(_exact(COUGH, "Cough (finding)", "finding"), expected_tag="finding")
        assert got[COUGH].score == 1.0
        assert got[COUGH].withheld_reason == ""


def _session(exact_hits, ancestry_rows=None, ancestry_error=False):
    def _run(query, **kwargs):
        if "normalized_terms" in kwargs:
            return [
                {"input_term": n, "hits": exact_hits}
                for n in kwargs["normalized_terms"]
            ]
        if "groups" in kwargs:
            if ancestry_error:
                raise RuntimeError("simulated ancestry failure")
            return ancestry_rows or []
        return []

    session = MagicMock()
    session.run.side_effect = _run
    return session


def _cystocele_hits():
    return [
        {
            "concept_id": FEMALE_CYSTOCELE,
            "fsn": "Female cystocele (disorder)",
            "semantic_tag": "disorder",
            "read_codes": [],
            "score": 1.0,
            "surface_form_status": "",
            "match_source": "term",
            "acceptability_rank": 2,
        },
        {
            "concept_id": BLADDER_PROLAPSE,
            "fsn": "Prolapse of urinary bladder (disorder)",
            "semantic_tag": "disorder",
            "read_codes": [],
            "score": 1.0,
            "surface_form_status": "",
            "match_source": "term",
            "acceptability_rank": 1,
        },
    ]


class TestResolverWiring:
    def test_batch_path_reads_ancestry_and_picks_parent(self):
        resolver = CodingResolver()
        resolver._surface_form_exact_ok = True
        resolver._cache = MagicMock(mget=lambda keys: {})
        ancestry = [
            {
                "key": "Cystocele",
                "child_id": FEMALE_CYSTOCELE,
                "parent_id": BLADDER_PROLAPSE,
            }
        ]
        out = resolver.resolve_candidates(
            ["Cystocele"],
            neo4j_session=_session(_cystocele_hits(), ancestry),
            expected_tags={"Cystocele": "disorder"},
            enrich_lab_domain=False,
        )["Cystocele"]
        assert out[0].snomed_concept_id == BLADDER_PROLAPSE
        assert out[0].score >= ATTACH_GATE
        assert out[1].score < ATTACH_GATE

    def test_ancestry_failure_holds_back_instead_of_guessing(self):
        resolver = CodingResolver()
        resolver._surface_form_exact_ok = True
        resolver._cache = MagicMock(mget=lambda keys: {})
        out = resolver.resolve_candidates(
            ["Cystocele"],
            neo4j_session=_session(_cystocele_hits(), ancestry_error=True),
            expected_tags={"Cystocele": "disorder"},
            enrich_lab_domain=False,
        )["Cystocele"]
        assert all(c.score < ATTACH_GATE for c in out)
        assert {c.withheld_reason for c in out} == {"tiebreak_unavailable"}

    def test_exact_query_returns_acceptability_and_match_source(self):
        from services.terminology_api.app.queries import terminology as q

        for query in (q.BATCH_EXACT_QUERY, q.EXACT_QUERY):
            assert "acceptability_rank" in query
            assert "match_source" in query
        assert "match_source" in q.EXACT_SURFACE_FORM_QUERY

    def test_cache_key_bumped_so_pre_tiebreak_results_are_not_served(self):
        from services.terminology_api.app.services.cache import TerminologyCache

        key = TerminologyCache().generate_key("Cystocele", "disorder", True)
        assert ":v4:" in key
