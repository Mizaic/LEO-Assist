"""Fulltext matches must cover the phrase; onset and duration words are stripped.

The fulltext branch runs an any-word search, so "New onset" used to come
back as "New relationship" at 0.92. Each fulltext candidate now carries the
wording it matched on, and only a wording that claims nothing the phrase
did not say may stand for it (``libs/terminology/word_fit.py``).

Risk R-76DCF7B7 (incorrect SNOMED code used as a confirmed clinical fact).
Phrases are SNOMED wordings or the de-identified hard cases, not patient text.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock

from services.terminology_api.app.queries import terminology as q
from services.terminology_api.app.services.coding_resolver import (
    CodingCandidate,
    CodingResolver,
)

ATTACH_GATE = 0.55
ABDOMINAL_PAIN = "21522001"
NEW_ONSET_ANGINA = "233821000"
CIBH = "88111009"
CONSTIPATION = "14760008"
BLEEDING = "131148009"
HEMORRHAGE = "50960005"
# Stand-in ids: these tests check wording, not the real SNOMED identifiers.
NEW_RELATIONSHIP = "fake-new-relationship"
GESTATION_3_MONTHS = "fake-gestation-3-months"
FOLLOW_UP_6_WEEKS = "fake-follow-up-6-weeks"
PAINFUL_RECTAL_BLEEDING = "fake-painful-rectal-bleeding"
ANGINA = "fake-angina"


def _exact_hit(cid, fsn, tag):
    return {
        "concept_id": cid,
        "fsn": fsn,
        "semantic_tag": tag,
        "read_codes": [],
        "score": 1.0,
        "surface_form_status": "",
        "match_source": "term",
        "acceptability_rank": 2,
    }


def _ft_row(cid, fsn, tag, matched, score, sf_status=""):
    return {
        "concept_id": cid,
        "fsn": fsn,
        "semantic_tag": tag,
        "read_codes": [],
        "score": score,
        "surface_form_status": sf_status,
        "matched": matched,
    }


def _session(ft_rows=(), exact_hits_by_norm=None):
    def _run(query, **kwargs):
        if "normalized_terms" in kwargs:
            return [
                {"input_term": n, "hits": (exact_hits_by_norm or {}).get(n, [])}
                for n in kwargs["normalized_terms"]
            ]
        if "normalized" in kwargs:
            return [
                dict(h)
                for h in (exact_hits_by_norm or {}).get(kwargs["normalized"], [])
            ]
        if "ft_query" in kwargs:
            return [dict(r) for r in ft_rows]
        return []

    session = MagicMock()
    session.run.side_effect = _run
    return session


def _resolve(phrase, session, tag=None):
    resolver = CodingResolver()
    resolver._surface_form_exact_ok = True
    resolver._surface_form_fulltext_ok = True
    resolver._cache = MagicMock(mget=lambda keys: {})
    return resolver.resolve_candidates(
        [phrase],
        neo4j_session=session,
        expected_tags={phrase: tag} if tag else None,
        enrich_lab_domain=False,
    )[phrase]


class TestMatchedWording:
    def test_fulltext_queries_return_the_matched_wording(self):
        assert q.BATCH_FULLTEXT_QUERY.count("AS matched") == 2
        assert "AS matched" in q.FULLTEXT_QUERY
        assert "AS matched" in q.FULLTEXT_SURFACE_FORM_QUERY

    def test_candidate_keeps_wording_of_its_best_scoring_row(self):
        rows = [
            _ft_row(
                ABDOMINAL_PAIN,
                "Abdominal pain (finding)",
                "finding",
                "Pain abdominal",
                2.0,
            ),
            _ft_row(
                ABDOMINAL_PAIN,
                "Abdominal pain (finding)",
                "finding",
                "Abdominal pain",
                3.0,
            ),
        ]
        out = _resolve("abdominal pain", _session(rows))
        assert out[0].snomed_concept_id == ABDOMINAL_PAIN
        assert out[0].matched_wording == "Abdominal pain"

    def test_old_cached_payload_without_new_fields_still_loads(self):
        c = CodingCandidate(
            snomed_concept_id=ABDOMINAL_PAIN,
            snomed_term="Abdominal pain (finding)",
            semantic_tag="finding",
            read_code=None,
            score=0.9,
            source="lexical",
        )
        assert c.matched_wording == ""
        assert c.lookup_variant == ""


def _codes_at_gate(out):
    return {c.snomed_concept_id for c in out if c.score >= ATTACH_GATE}


class TestWordGate:
    def test_new_onset_does_not_become_new_relationship(self):
        rows = [
            _ft_row(
                NEW_RELATIONSHIP,
                "New relationship (finding)",
                "finding",
                "New relationship",
                11.5,
            )
        ]
        assert _codes_at_gate(_resolve("New onset", _session(rows))) == set()

    def test_diarrhoea_for_3_months_does_not_become_gestation_period(self):
        rows = [
            _ft_row(
                GESTATION_3_MONTHS,
                "Gestation period, 3 months (observable entity)",
                "observable entity",
                "Gestation period, 3 months",
                9.0,
            )
        ]
        out = _resolve("diarrhoea for 3 months", _session(rows))
        assert GESTATION_3_MONTHS not in {c.snomed_concept_id for c in out}

    def test_abdominal_pain_for_6_weeks_does_not_become_follow_up(self):
        rows = [
            _ft_row(
                FOLLOW_UP_6_WEEKS,
                "Follow-up 6 weeks (finding)",
                "finding",
                "Follow-up 6 weeks",
                8.0,
            )
        ]
        out = _resolve("abdominal pain for 6 weeks", _session(rows))
        assert FOLLOW_UP_6_WEEKS not in {c.snomed_concept_id for c in out}

    def test_new_onset_rectal_bleeding_does_not_become_painful_rectal_bleeding(self):
        rows = [
            _ft_row(
                PAINFUL_RECTAL_BLEEDING,
                "Painful rectal bleeding (finding)",
                "finding",
                "Painful rectal bleeding",
                12.0,
            )
        ]
        out = _resolve("New onset rectal bleeding", _session(rows))
        assert PAINFUL_RECTAL_BLEEDING not in {c.snomed_concept_id for c in out}

    def test_wording_missing_only_qualifiers_survives(self):
        rows = [
            _ft_row(
                ABDOMINAL_PAIN,
                "Abdominal pain (finding)",
                "finding",
                "Abdominal pain",
                8.0,
            )
        ]
        out = _resolve("abdominal pain for 6 weeks", _session(rows))
        assert _codes_at_gate(out) == {ABDOMINAL_PAIN}
        assert out[0].matched_wording == "Abdominal pain"

    def test_covering_wording_wins_over_higher_scoring_non_covering_one(self):
        rows = [
            _ft_row(
                ABDOMINAL_PAIN,
                "Abdominal pain (finding)",
                "finding",
                "Abdominal pain",
                5.0,
            ),
            _ft_row(
                ABDOMINAL_PAIN,
                "Abdominal pain (finding)",
                "finding",
                "Abdominal pain severe",
                9.0,
            ),
        ]
        out = _resolve("abdominal pain", _session(rows))
        assert _codes_at_gate(out) == {ABDOMINAL_PAIN}
        assert out[0].matched_wording == "Abdominal pain"

    def test_fulltext_row_without_wording_is_not_attached(self):
        rows = [_ft_row(ABDOMINAL_PAIN, "Abdominal pain (finding)", "finding", "", 8.0)]
        assert _codes_at_gate(_resolve("abdominal pain", _session(rows))) == set()

    def test_exact_new_onset_angina_untouched(self):
        exact = {
            "new onset angina": [
                _exact_hit(NEW_ONSET_ANGINA, "New onset angina (disorder)", "disorder")
            ]
        }
        out = _resolve(
            "New onset angina", _session(exact_hits_by_norm=exact), tag="disorder"
        )
        assert out[0].snomed_concept_id == NEW_ONSET_ANGINA
        assert out[0].score == 1.0

    def test_single_term_path_applies_the_same_gate(self):
        rows = [
            _ft_row(
                NEW_RELATIONSHIP,
                "New relationship (finding)",
                "finding",
                "New relationship",
                11.5,
            )
        ]
        resolver = CodingResolver()
        resolver._surface_form_exact_ok = False
        resolver._surface_form_fulltext_ok = False
        out = resolver._resolve_single("New onset", _session(rows))
        assert _codes_at_gate(out) == set()

    def test_cache_keys_bumped_so_pre_gate_results_are_not_served(self):
        from libs.terminology import client
        from services.terminology_api.app.services.cache import TerminologyCache

        assert ":v4:" in TerminologyCache().generate_key("New onset", "finding", True)
        assert client._TERMINOLOGY_CACHE_PREFIX == "terminology:api:v4:"


class TestStripStep:
    def test_recent_onset_change_in_bowel_habit_found_by_stripping(self):
        exact = {
            "change in bowel habit": [
                _exact_hit(CIBH, "Change in bowel habit (finding)", "finding")
            ]
        }
        out = _resolve(
            "Recent-onset change in bowel habit",
            _session(exact_hits_by_norm=exact),
            tag="finding",
        )
        assert out[0].snomed_concept_id == CIBH
        assert out[0].score >= ATTACH_GATE
        assert out[0].lookup_variant == "stripped"
        assert out[0].matched_wording == "change in bowel habit"

    def test_new_onset_constipation_is_constipation_not_new_onset_angina(self):
        exact = {
            "constipation": [
                _exact_hit(CONSTIPATION, "Constipation (finding)", "finding")
            ]
        }
        rows = [
            _ft_row(
                NEW_ONSET_ANGINA,
                "New onset angina (disorder)",
                "disorder",
                "New onset angina",
                10.0,
            )
        ]
        out = _resolve("New-onset constipation", _session(rows, exact), tag="finding")
        assert _codes_at_gate(out) == {CONSTIPATION}
        assert out[0].lookup_variant == "stripped"

    def test_phrase_with_its_own_exact_hit_is_not_stripped(self):
        exact = {
            "new onset angina": [
                _exact_hit(NEW_ONSET_ANGINA, "New onset angina (disorder)", "disorder")
            ],
            "angina": [_exact_hit(ANGINA, "Angina (disorder)", "disorder")],
        }
        out = _resolve(
            "New onset angina", _session(exact_hits_by_norm=exact), tag="disorder"
        )
        assert [c.snomed_concept_id for c in out] == [NEW_ONSET_ANGINA]
        assert out[0].lookup_variant == ""

    def test_held_back_stripped_tie_is_not_won_back_by_fulltext(self):
        exact = {
            "bleeding": [
                {
                    **_exact_hit(
                        HEMORRHAGE,
                        "Hemorrhage (morphologic abnormality)",
                        "morphologic abnormality",
                    ),
                    "acceptability_rank": 1,
                },
                _exact_hit(BLEEDING, "Bleeding (finding)", "finding"),
            ]
        }
        rows = [
            _ft_row(
                HEMORRHAGE,
                "Hemorrhage (morphologic abnormality)",
                "morphologic abnormality",
                "Bleeding",
                8.0,
            )
        ]
        out = _resolve("recent onset bleeding", _session(rows, exact))
        assert _codes_at_gate(out) == set()
        assert {c.withheld_reason for c in out} == {"ambiguous_exact"}

    def test_single_term_path_strips_the_same_way(self):
        exact = {
            "constipation": [
                _exact_hit(CONSTIPATION, "Constipation (finding)", "finding")
            ]
        }
        resolver = CodingResolver()
        resolver._surface_form_exact_ok = False
        resolver._surface_form_fulltext_ok = False
        out = resolver._resolve_single(
            "New-onset constipation", _session(exact_hits_by_norm=exact), "finding"
        )
        assert _codes_at_gate(out) == {CONSTIPATION}
        assert out[0].lookup_variant == "stripped"


class TestRouterPassThrough:
    @staticmethod
    @contextmanager
    def _session_cm():
        yield MagicMock()

    def test_resolve_response_carries_wording_and_variant(self, monkeypatch):
        from services.terminology_api.app.routers import resolve as resolve_router

        cand = CodingCandidate(
            snomed_concept_id=ABDOMINAL_PAIN,
            snomed_term="Abdominal pain (finding)",
            semantic_tag="finding",
            read_code=None,
            score=1.0,
            source="lexical",
            had_exact_match=True,
            matched_wording="abdominal pain",
            lookup_variant="stripped",
        )
        monkeypatch.setattr(resolve_router._kg_client, "session", self._session_cm)
        monkeypatch.setattr(
            resolve_router._resolver,
            "resolve_candidates",
            lambda *a, **k: {"abdominal pain for 6 weeks": [cand]},
        )
        body = resolve_router.ResolveRequest(terms=["abdominal pain for 6 weeks"])
        got = resolve_router.resolve_terms(body).results["abdominal pain for 6 weeks"][
            0
        ]
        assert got.matched_wording == "abdominal pain"
        assert got.lookup_variant == "stripped"
