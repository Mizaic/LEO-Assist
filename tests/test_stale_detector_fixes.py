"""Verification tests for the stale-episode detector fixes.

Covers VT-LEO-AI-157 (DI-LEO-AI-159, DI-LEO-AI-160, R-LEO-AI-162,
R-LEO-AI-163).

Rules under test (the five fixes from the plan):

1. Same-day "diagnosis from problem-list" -- malignancy Read code in
   the post-referral window emits a confirmed diagnosis anchor with the
   correct cancer site.
2. Same-day "benign exclusion from problem-list" -- benign-explanation
   Read code or investigation phrase in the post-referral window emits a
   benign-closure anchor.
3. Letter-stub follow-up DQ alert -- ``dq_letter_stub_unfilled`` matches
   short routing-only stubs on stale episodes.
4. Site reconciliation -- explicit ``(XaMeC)`` style 2WW Read code wins
   over the surface-form heuristic.
5. Stricter stale criteria -- ``STALE_CLOSE_Q`` excludes episodes
   carrying a ``diagnosis_confirmed`` or ``benign_closure`` milestone.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from libs.domains.code_inventories import (
    BENIGN_EXPLANATION_READ_CODES,
    BENIGN_INVESTIGATION_PHRASES,
    BENIGN_PHRASE_REQUIRES_CANCER_CONTEXT,
    CANCER_FOLLOW_UP_PHRASES,
    CANCER_PATHWAY_CONTEXT_REGEX,
    CANCER_TREATMENT_PROCEDURE_CODES,
    FAST_TRACK_REFERRAL_READ_CODES,
    MALIGNANCY_READ_CODES,
    SPECIALIST_CLINIC_READ_CODES,
    extract_read_codes,
    find_benign_explanation_code,
    find_cancer_follow_up_phrase,
    find_cancer_treatment_procedure_code,
    find_fast_track_referral_site,
    find_malignancy_code,
    find_specialist_clinic_site,
    looks_like_letter_stub,
    match_benign_investigation_phrase,
    text_has_cancer_pathway_context,
)
from services.analysis_worker.app.analyzers.anchor_detector import (
    _classify_text_encounters,
)
from services.analysis_worker.app.analyzers.episode_builder._cypher import (
    STALE_CLOSE_Q,
)
from services.analysis_worker.app.analyzers.episode_builder._site_resolution import (
    _extract_condition_key_from_anchor,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _text_row(
    enc_id: str, date: str, text: str, content_type: str = "consultation"
) -> dict[str, Any]:
    return {
        "encounter_id": enc_id,
        "encounter_date": date,
        "coding_status": "uncoded",
        "content_type": content_type,
        "significance": "clinical",
        "domains": [],
        "purpose": [],
        "text": text,
    }


def _classify_one(text: str, enc_id: str = "E1", date: str = "2025-06-01"):
    """Run _classify_text_encounters on a single encounter and return buckets."""
    return _classify_text_encounters(
        text_rows=[_text_row(enc_id, date, text)],
        already_coded_ids=set(),
    )


# ---------------------------------------------------------------------------
# Inventory sanity checks
# ---------------------------------------------------------------------------


class TestCodeInventories:

    def test_extract_codes_picks_parenthesised_tokens(self):
        text = "Endometrioid carcinoma (BB5j2) with single renal cyst (PD10.)"
        assert extract_read_codes(text) == ["BB5j2", "PD10."]

    def test_find_malignancy_code_breast(self):
        hit = find_malignancy_code("Major: Malignant tumour of breast (X78WM)")
        assert hit == ("X78WM", "breast")

    def test_find_benign_explanation_code(self):
        text = "Major: Laryngopharyngeal reflux (XaK99) added to problem list"
        assert find_benign_explanation_code(text) == "XaK99"

    def test_find_fast_track_referral_site_breast(self):
        text = "Fast track referral for suspected breast cancer (XaMeC)"
        assert find_fast_track_referral_site(text) == ("XaMeC", "breast")

    def test_no_false_positive_on_unrelated_code(self):
        text = "Annual review (Xab12) discussed BP"
        assert find_malignancy_code(text) is None
        assert find_benign_explanation_code(text) is None
        assert find_fast_track_referral_site(text) is None

    def test_match_benign_investigation_phrase_mammogram_normal(self):
        label = match_benign_investigation_phrase(
            "Mammogram - normal, no further action required"
        )
        assert label == "mammogram normal"

    def test_match_benign_investigation_phrase_cancer_excluded(self):
        label = match_benign_investigation_phrase(
            "Letter from breast clinic: cancer excluded - discharge to GP"
        )
        assert label is not None and "cancer excluded" in label.lower()

    def test_inventories_are_non_empty(self):
        assert MALIGNANCY_READ_CODES
        assert BENIGN_EXPLANATION_READ_CODES
        assert FAST_TRACK_REFERRAL_READ_CODES
        assert BENIGN_INVESTIGATION_PHRASES
        assert all(isinstance(rx, re.Pattern) for rx, _ in BENIGN_INVESTIGATION_PHRASES)

    def test_looks_like_letter_stub_recognises_routing_only(self):
        assert looks_like_letter_stub("Breast Clinic to Old Surgery House")
        assert looks_like_letter_stub(
            "Urology to Greenfields Surgery", max_chars=200
        )

    def test_looks_like_letter_stub_rejects_full_letter(self):
        long_body = (
            "Breast Clinic to Old Surgery House. Patient seen today. "
            "Mammogram showed M2 normal appearance. No further action required. "
            "Discharged from clinic with reassurance."
        )
        assert not looks_like_letter_stub(long_body, max_chars=120)


# ---------------------------------------------------------------------------
# Anchor detector -- problem-list malignancy diagnosis (rule 1)
# ---------------------------------------------------------------------------


class TestAnchorMalignancyFromProblemList:

    def test_breast_x78wm_emits_diagnosis_with_site(self):
        text = "Major: Malignant tumour of breast (X78WM) confirmed"
        _, diagnoses, _, _, _, _, _, _ = _classify_one(text)
        assert len(diagnoses) == 1
        d = diagnoses[0]
        assert d["site_key"] == "breast"
        assert d.get("diagnosis_source") == "problem_list_code"
        assert d.get("diagnosis_code") == "X78WM"
        assert d["assertion"] == "present"

    def test_endometrial_bb5j2_emits_diagnosis(self):
        text = "Major: Endometrioid carcinoma (BB5j2) histology confirmed"
        _, diagnoses, _, _, _, _, _, _ = _classify_one(text)
        assert len(diagnoses) == 1
        assert diagnoses[0]["site_key"] == "endometrial"
        assert diagnoses[0]["diagnosis_code"] == "BB5j2"

    def test_endometrial_x78xo_emits_diagnosis(self):
        text = "Endometrial carcinoma (X78XO) reported on biopsy"
        _, diagnoses, _, _, _, _, _, _ = _classify_one(text)
        assert any(d["site_key"] == "endometrial" for d in diagnoses)

    def test_no_diagnosis_on_referral_encounter_with_malignancy_code(self):
        # Referral text overlaps cancer terms; rule should NOT emit a
        # diagnosis on the same encounter that is the referral itself.
        text = (
            "Fast track referral for suspected breast cancer (XaMeC). "
            "Considering malignant tumour of breast (X78WM)."
        )
        referrals, diagnoses, _, _, _, _, _, _ = _classify_one(text)
        assert referrals, "the encounter should still be a referral"
        # The referral guard removes diagnoses from this encounter
        for d in diagnoses:
            assert d["encounter_id"] != "E1"


# ---------------------------------------------------------------------------
# Anchor detector -- benign explanation from problem list (rule 2)
# ---------------------------------------------------------------------------


class TestAnchorBenignFromProblemList:

    def test_xak99_lpr_emits_benign_closure(self):
        text = "Letter from ENT clinic. Major: Laryngopharyngeal reflux (XaK99) added."
        _, _, _, _, benign, _, _, _ = _classify_one(text)
        assert len(benign) == 1
        b = benign[0]
        assert b.get("benign_source") == "problem_list_code"
        assert b.get("benign_code") == "XaK99"
        assert b.get("is_pathway_completion") is True

    def test_cancer_excluded_phrase_emits_benign_closure(self):
        text = "Breast clinic letter: cancer excluded - discharge to GP."
        _, _, _, _, benign, _, _, _ = _classify_one(text)
        assert len(benign) == 1
        assert benign[0].get("benign_source") == "investigation_phrase"

    def test_mammogram_m2_emits_benign_closure(self):
        text = "Mammogram - M2 (BIRADS benign), no further action."
        _, _, _, _, benign, _, _, _ = _classify_one(text)
        assert len(benign) == 1


# ---------------------------------------------------------------------------
# Anchor detector + site resolution -- explicit 2WW code (rule 4)
# ---------------------------------------------------------------------------


class TestSiteReconciliation:

    def test_explicit_xamec_overrides_surface_form_match(self):
        # Surface-form heuristic would say "lung clinic" => lung; the
        # XaMeC code must win and pin the site to breast.
        text = (
            "Fast track referral for suspected breast cancer (XaMeC). "
            "Note: previously seen in lung clinic for chronic cough."
        )
        referrals, _, _, _, _, _, _, _ = _classify_one(text)
        assert len(referrals) == 1
        r = referrals[0]
        assert r.get("site_source") == "explicit_2ww_code"
        assert r.get("site_key") == "breast"
        # And the resolver agrees
        assert _extract_condition_key_from_anchor(r) == "breast"

    def test_resolver_prefers_explicit_2ww_over_concept_id(self):
        anchor = {
            "site_source": "explicit_2ww_code",
            "site_key": "breast",
            # A coded SNOMED ID that would otherwise resolve to "lung"
            "concept_id": "276491000000101",
            "concept_name": "Fast track referral for suspected lung cancer",
        }
        assert _extract_condition_key_from_anchor(anchor) == "breast"

    def test_resolver_ignores_explicit_when_unknown_site(self):
        anchor = {
            "site_source": "explicit_2ww_code",
            "site_key": "",
            "concept_id": "276491000000101",
            "concept_name": "Fast track referral for suspected lung cancer",
        }
        assert _extract_condition_key_from_anchor(anchor) == "lung"


# ---------------------------------------------------------------------------
# Stricter stale criteria -- STALE_CLOSE_Q (rule 5)
# ---------------------------------------------------------------------------


class TestStaleCloseQuery:

    def test_query_contains_diagnosis_milestone_guard(self):
        assert "diagnosis_confirmed" in STALE_CLOSE_Q
        assert "has_dx" in STALE_CLOSE_Q
        assert "WHERE NOT (has_dx OR has_benign_or_treatment)" in STALE_CLOSE_Q

    def test_query_still_assigns_stale_post_specialist_status(self):
        # Original behaviour preserved.
        assert "stale_post_specialist" in STALE_CLOSE_Q
        assert "stale_no_diagnosis" in STALE_CLOSE_Q


# ---------------------------------------------------------------------------
# DQ tool -- dq_letter_stub_unfilled (rule 3)
# ---------------------------------------------------------------------------


class TestLetterStubDQ:

    def test_tool_registered_in_safety_pack(self):
        from services.neo4j_mcp.tools.query_pack_safety import TOOLS

        names = {t["name"] for t in TOOLS}
        assert "dq_letter_stub_unfilled" in names

    def test_tool_descriptor_has_expected_inputs(self):
        from services.neo4j_mcp.tools.query_pack_safety import TOOLS

        tool = next(t for t in TOOLS if t["name"] == "dq_letter_stub_unfilled")
        props = tool["inputSchema"]["properties"]
        assert {"days_threshold", "max_chars", "limit"} <= set(props)

    def test_tool_returns_summary_when_run(self, monkeypatch):
        # Patch run_patient to a synthetic stub-row list and confirm the
        # function returns the expected envelope shape.
        fake_rows = [
            {
                "patient_id": "1",
                "encounter_id": "E1",
                "encounter_date": "2024-01-01",
                "text_length": 50,
                "text_preview": "Breast Clinic to Old Surgery",
                "episode_id": "EP1",
                "cancer_type": "breast",
                "episode_status": "stale_post_specialist",
                "age_days": 360,
            }
        ]
        import services.neo4j_mcp.tools.query_pack_safety as qps

        monkeypatch.setattr(qps, "run_patient", lambda *a, **kw: fake_rows)
        out = qps.dq_letter_stub_unfilled(days_threshold=7)
        assert out["rows"] == fake_rows
        assert out["row_count"] == 1
        assert "letter stub" in out["summary"].lower()
        assert out["query_id"] == "dq_letter_stub_unfilled"


# ---------------------------------------------------------------------------
# Outcome-inference defence layer -- POST_CANCER / POST_BENIGN extension
# ---------------------------------------------------------------------------


class TestOutcomeInferenceDefence:

    def test_malignancy_codes_are_in_post_cancer(self):
        from libs.pipeline.outcome_inference import POST_CANCER

        # Lowercased because POST_CANCER patterns are matched against
        # text.lower(); ensure at least one curated code is present.
        joined = " ".join(p for p, _ in POST_CANCER)
        assert "x78wm" in joined.lower()

    def test_benign_codes_are_in_post_benign(self):
        from libs.pipeline.outcome_inference import POST_BENIGN

        joined = " ".join(p for p, _ in POST_BENIGN)
        assert "xak99" in joined.lower()

    def test_score_inference_recognises_problem_list_malignancy(self):
        from libs.pipeline.outcome_inference import (
            score_post_specialist_encounters,
        )

        rows = [
            {
                "date": "2024-03-01",
                "text": "Major: Malignant tumour of breast (X78WM)",
                "flags": "",
            }
        ]
        result = score_post_specialist_encounters(rows)
        assert result.inferred_outcome == "cancer"
        assert any("x78wm" in s.lower() for s in result.inference_signals)

    def test_score_inference_recognises_benign_phrase(self):
        from libs.pipeline.outcome_inference import (
            score_post_specialist_encounters,
        )

        rows = [
            {
                "date": "2024-03-01",
                "text": "Breast clinic letter: cancer excluded - discharge to GP",
                "flags": "",
            }
        ]
        result = score_post_specialist_encounters(rows)
        assert result.inferred_outcome == "benign"


# ---------------------------------------------------------------------------
# DI-LEO-AI-171: malignancy term + active-care code recognition
# DI-LEO-AI-172: adjuvant-therapy diagnosis inference
# DI-LEO-AI-173: site reconciliation in episode build
# ---------------------------------------------------------------------------


from libs.domains.code_inventories import (
    ACTIVE_CANCER_CARE_CODES,
    ADJUVANT_THERAPY_DRUG_PATTERNS,
    HISTORY_OF_CANCER_CODE_PREFIXES,
    MALIGNANCY_TERM_PATTERNS,
    adjuvant_therapy_is_newly_issued,
    find_active_cancer_care_code,
    find_adjuvant_therapy_drug,
    find_malignancy_term_in_problem_line,
    is_history_of_cancer_code,
    text_contains_history_of_cancer,
)


class TestMissedCancerInventories:
    """DI-LEO-AI-171: new inventories are non-empty and self-consistent."""

    def test_active_cancer_care_codes_non_empty(self):
        assert ACTIVE_CANCER_CARE_CODES
        # Every entry must be a non-empty string
        assert all(isinstance(c, str) and c for c in ACTIVE_CANCER_CARE_CODES)
        # The corpus-confirmed XaIph "Cancer confirmed" must be present
        assert "XaIph" in ACTIVE_CANCER_CARE_CODES

    def test_history_of_cancer_prefixes_non_empty(self):
        assert HISTORY_OF_CANCER_CODE_PREFIXES
        # ZV10 family is the canonical Read 'personal history' prefix
        assert "ZV10" in HISTORY_OF_CANCER_CODE_PREFIXES

    def test_malignancy_term_patterns_compile(self):
        assert MALIGNANCY_TERM_PATTERNS
        for rx, site in MALIGNANCY_TERM_PATTERNS:
            assert isinstance(rx, re.Pattern)
            assert isinstance(site, str) and site

    def test_adjuvant_drug_patterns_compile(self):
        assert ADJUVANT_THERAPY_DRUG_PATTERNS
        for rx, site, indication in ADJUVANT_THERAPY_DRUG_PATTERNS:
            assert isinstance(rx, re.Pattern)
            assert isinstance(site, str) and site
            assert isinstance(indication, str) and indication


class TestHistoryOfCancerGuard:
    """DI-LEO-AI-171: history-of-cancer codes must NOT fire diagnosis."""

    def test_zv10_prefix_recognised(self):
        assert is_history_of_cancer_code("ZV10.")
        assert is_history_of_cancer_code("ZV1011")

    def test_b934_recognised(self):
        # H/O malignant neoplasm of breast
        assert is_history_of_cancer_code("B934.")

    def test_unrelated_code_not_history(self):
        assert not is_history_of_cancer_code("X78WM")  # malignant breast (active)
        assert not is_history_of_cancer_code("")
        assert not is_history_of_cancer_code("XaMeC")  # 2WW referral

    def test_text_history_marker_blocks_diagnosis(self):
        text = "Major: H/O carcinoma of breast (B934.)"
        assert text_contains_history_of_cancer(text)
        # Even though carcinoma of breast is on the line, the H/O guard wins
        _, diagnoses, _, _, _, _, _, _ = _classify_one(text)
        assert diagnoses == []

    def test_personal_history_text_blocks_diagnosis(self):
        text = "Personal history of malignant neoplasm of prostate"
        assert text_contains_history_of_cancer(text)
        _, diagnoses, _, _, _, _, _, _ = _classify_one(text)
        assert diagnoses == []


class TestActiveCancerCareCode:
    """DI-LEO-AI-171: active-care codes fire diagnosis_confirmed."""

    def test_xaiph_cancer_confirmed_emits_diagnosis(self):
        text = "Cancer confirmed (XaIph) on MDT review"
        _, diagnoses, _, _, _, _, _, _ = _classify_one(text)
        assert len(diagnoses) == 1
        d = diagnoses[0]
        assert d.get("diagnosis_source") == "active_cancer_care_code"
        assert d.get("diagnosis_code") == "XaIph"
        assert d.get("hitl_required") is True

    def test_mdt_meeting_emits_diagnosis(self):
        text = "Discussed at multidisciplinary team meeting (XaN5C)"
        _, diagnoses, _, _, _, _, _, _ = _classify_one(text)
        assert len(diagnoses) == 1
        assert diagnoses[0].get("diagnosis_code") == "XaN5C"

    def test_active_care_blocked_by_history(self):
        text = "Cancer follow-up (ZV67E). H/O malignant neoplasm of breast (B934.)"
        # ZV67E is in active-care set, but the history marker should suppress it
        assert find_active_cancer_care_code(text) is None
        _, diagnoses, _, _, _, _, _, _ = _classify_one(text)
        assert diagnoses == []


class TestMalignancyTermProblemLine:
    """DI-LEO-AI-171: free-text malignancy on a problem-list line."""

    def test_carcinoma_of_prostate_problem_line(self):
        text = "Major: Carcinoma of prostate (Xxxxx) - awaiting MDT"
        hit = find_malignancy_term_in_problem_line(text)
        assert hit is not None
        term, site = hit
        assert "carcinoma of prostate" in term.lower()
        assert site == "prostate"

    def test_invasive_carcinoma_of_breast_problem_line(self):
        text = "Problem: Invasive carcinoma of breast - on tamoxifen"
        hit = find_malignancy_term_in_problem_line(text)
        assert hit is not None
        assert hit[1] == "breast"

    def test_term_in_free_prose_does_not_fire(self):
        # No problem-list prefix on the relevant line
        text = "Patient asked about carcinoma of prostate during consultation"
        assert find_malignancy_term_in_problem_line(text) is None

    def test_history_line_does_not_fire(self):
        text = "Major: H/O carcinoma of breast (B934.) reviewed today"
        assert find_malignancy_term_in_problem_line(text) is None

    def test_anchor_emits_diagnosis_with_term_site(self):
        # Use a less-common phrasing so the gold-mined cancer_site_terms
        # dictionary does not already pre-assign site_source from
        # match_cancer_site -- we want to see the malignancy_term path
        # claim site_source itself.
        text = "Major: Renal cell carcinoma documented today"
        _, diagnoses, _, _, _, _, _, _ = _classify_one(text)
        assert len(diagnoses) == 1
        d = diagnoses[0]
        assert d.get("site_key") == "renal"
        assert d.get("hitl_required") is True

    def test_anchor_with_term_in_problem_line_site_correct(self):
        # Even when the surface-form dictionary also matches, the
        # final site_key must be the term's site (or a compatible one).
        text = "Major: Carcinoma of prostate, on triptorelin"
        _, diagnoses, _, _, _, _, _, _ = _classify_one(text)
        assert len(diagnoses) == 1
        assert diagnoses[0].get("site_key") == "prostate"
        assert diagnoses[0].get("hitl_required") is True


class TestAdjuvantTherapyInference:
    """DI-LEO-AI-172: adjuvant-therapy diagnosis inference + guard."""

    def test_drug_alone_does_not_fire(self):
        # Routine repeat prescription with no issue marker and no
        # cancer co-text -- must NOT fire a diagnosis anchor.
        text = "Repeat prescription review: letrozole 2.5mg OD continues"
        _, diagnoses, _, _, _, _, _, _ = _classify_one(text)
        assert diagnoses == []

    def test_drug_with_newly_issued_marker_fires(self):
        text = "Newly issued: tamoxifen 20mg OD initiated today"
        _, diagnoses, _, _, _, _, _, _ = _classify_one(text)
        assert len(diagnoses) == 1
        d = diagnoses[0]
        assert d.get("diagnosis_source") == "adjuvant_therapy_drug"
        assert d.get("site_key") == "breast"
        assert d.get("hitl_required") is True

    def test_drug_with_active_care_code_fires(self):
        text = "Cancer review (XaIyc). On letrozole 2.5mg daily."
        _, diagnoses, _, _, _, _, _, _ = _classify_one(text)
        assert len(diagnoses) >= 1
        # Active care code beats the drug as the source
        sources = {d.get("diagnosis_source") for d in diagnoses}
        assert "active_cancer_care_code" in sources or "adjuvant_therapy_drug" in sources

    def test_drug_with_history_of_cancer_does_not_fire(self):
        text = (
            "H/O cancer of breast (B934.). Routine letrozole repeat continues."
        )
        _, diagnoses, _, _, _, _, _, _ = _classify_one(text)
        assert diagnoses == []

    def test_triptorelin_maps_to_prostate(self):
        hit = find_adjuvant_therapy_drug("Started on triptorelin (Decapeptyl) 11.25mg")
        assert hit is not None
        drug, site, _indication = hit
        assert site == "prostate"
        assert "triptorelin" in drug.lower()

    def test_newly_issued_marker_helper(self):
        assert adjuvant_therapy_is_newly_issued("Newly issued: anastrozole 1mg OD")
        assert adjuvant_therapy_is_newly_issued("Initiated on tamoxifen")
        assert not adjuvant_therapy_is_newly_issued("On long-term tamoxifen review")


class TestSiteReconciliationInBuilder:
    """DI-LEO-AI-173: episode builder picks the diagnosis-anchor's
    explicit site when it conflicts with the referral site, and flags
    the episode HITL."""

    def test_explicit_diagnosis_site_wins_over_referral_site(self):
        # Simulate the helper logic by exercising the resolver directly:
        # a diagnosis anchor with an explicit malignancy code site of
        # 'prostate' must override a referral surface-form match of
        # 'liver'.
        diag_anchor = {
            "site_source": "explicit_malignancy_code",
            "site_key": "prostate",
            "concept_id": 363346000,
            "concept_name": "Text: confirmed cancer diagnosis",
        }
        assert _extract_condition_key_from_anchor(diag_anchor) == "prostate"

    def test_malignancy_term_site_source_resolved(self):
        diag_anchor = {
            "site_source": "malignancy_term_problem_line",
            "site_key": "breast",
            "concept_id": 363346000,
            "concept_name": "Text: confirmed cancer diagnosis",
        }
        # The resolver short-circuit covers explicit_2ww_code and
        # explicit_malignancy_code; for malignancy_term_problem_line
        # it falls into the "explicit and not unknown" branch.
        assert _extract_condition_key_from_anchor(diag_anchor) == "breast"


class TestB5MappingBugFixed:
    """DI-LEO-AI-171: the B5... -> head_and_neck mapping was a bug; the
    only B5x prefix that should map is B57.. (brain)."""

    def test_b5_dots_not_in_inventory(self):
        assert "B5..." not in MALIGNANCY_READ_CODES

    def test_b57_brain_still_maps(self):
        assert MALIGNANCY_READ_CODES.get("B57..") == "brain"


class TestRegressionMissedCancers:
    """DI-LEO-AI-171 / DI-LEO-AI-172: regression fixtures from the 2025
    closed_benign audit. Each case represents one of the missed cancers
    we must now catch."""

    def test_prostate_x78y6_problem_line(self):
        # eps a6c093d2702d379f / e7c8b99ad0ae77ab
        text = "Major: Carcinoma of prostate (X78Y6)"
        _, diagnoses, _, _, _, _, _, _ = _classify_one(text)
        assert len(diagnoses) == 1
        assert diagnoses[0]["site_key"] == "prostate"

    def test_invasive_breast_ya0ln_problem_line(self):
        # eps 1ecfb55618c2a6d2
        text = "Major: Invasive carcinoma of breast (Ya0ln)"
        _, diagnoses, _, _, _, _, _, _ = _classify_one(text)
        assert len(diagnoses) == 1
        assert diagnoses[0]["site_key"] == "breast"

    def test_letrozole_newly_issued_after_breast_2ww(self):
        text = (
            "Initiated letrozole 2.5mg OD per oncology recommendation. "
            "First prescription issued today."
        )
        _, diagnoses, _, _, _, _, _, _ = _classify_one(text)
        assert len(diagnoses) == 1
        d = diagnoses[0]
        assert d["site_key"] == "breast"
        assert d.get("hitl_required") is True


class TestSilentBenignClosureProvenance:
    """DI-LEO-AI-171 (silent-closure provenance fix): every closed_benign
    episode must carry a benign_closure IS_PART_OF edge so the audit
    trail can distinguish 'no diagnosis recorded' from 'clinically
    resolved as not-cancer'."""

    def test_link_anchor_helper_returns_earliest_in_window(self):
        from datetime import date as _date

        from services.analysis_worker.app.analyzers.episode_builder._builder import (
            _benign_closure_link_anchors,
        )

        anchors = [
            {"encounter_id": "B", "encounter_date": "2025-03-15"},
            {"encounter_id": "A", "encounter_date": "2025-03-01"},
            {"encounter_id": "C", "encounter_date": "2025-04-20"},
        ]
        out = _benign_closure_link_anchors(
            anchors,
            benign_date=_date(2025, 4, 1),
            ref_date=_date(2025, 1, 1),
        )
        assert len(out) == 1
        assert out[0]["encounter_id"] == "A"

    def test_link_anchor_helper_empty_when_no_benign_date(self):
        from services.analysis_worker.app.analyzers.episode_builder._builder import (
            _benign_closure_link_anchors,
        )

        anchors = [{"encounter_id": "A", "encounter_date": "2025-03-01"}]
        assert _benign_closure_link_anchors(anchors, None, None) == []

    def test_link_anchor_helper_drops_anchors_outside_window(self):
        from datetime import date as _date

        from services.analysis_worker.app.analyzers.episode_builder._builder import (
            _benign_closure_link_anchors,
        )

        anchors = [
            {"encounter_id": "before-ref", "encounter_date": "2024-12-01"},
            {"encounter_id": "after-benign", "encounter_date": "2025-05-15"},
        ]
        out = _benign_closure_link_anchors(
            anchors,
            benign_date=_date(2025, 4, 1),
            ref_date=_date(2025, 1, 1),
        )
        assert out == []


# ---------------------------------------------------------------------------
# DI-LEO-AI-175: skin / melanoma inventory completeness
# ---------------------------------------------------------------------------


class TestSkinMelanomaInventory:
    """DI-LEO-AI-175: skin/melanoma vocabulary that was missing in the
    2026-04-17 audit of patient 4921442355 (Lentigo maligna melanoma)."""

    def test_xamea_in_fast_track(self):
        assert FAST_TRACK_REFERRAL_READ_CODES.get("XaMeA") == "melanoma"

    def test_xapyd_in_specialist_clinic(self):
        assert SPECIALIST_CLINIC_READ_CODES.get("XaPyd") == "melanoma"

    def test_xa99y_lentigo_maligna_in_malignancy(self):
        hit = find_malignancy_code("Major: Lentigo maligna melanoma (Xa99Y)")
        assert hit == ("Xa99Y", "melanoma")

    def test_b3230_cheek_melanoma_in_malignancy(self):
        hit = find_malignancy_code(
            "Diagnosis: Malignant melanoma of cheek (B3230)"
        )
        assert hit == ("B3230", "melanoma")

    def test_b32_parent_in_malignancy(self):
        hit = find_malignancy_code(
            "Problem: Malignant melanoma of skin (B32..)"
        )
        assert hit == ("B32..", "melanoma")

    def test_b32_family_full_coverage(self):
        # Every B32.. family code must map to melanoma.
        b32_codes = [c for c in MALIGNANCY_READ_CODES if c.startswith("B32")]
        assert len(b32_codes) >= 20  # parent + sub-prefixes + leaves
        assert all(MALIGNANCY_READ_CODES[c] == "melanoma" for c in b32_codes)

    def test_lentigo_maligna_term_on_problem_line(self):
        from libs.domains.code_inventories import (
            find_malignancy_term_in_problem_line,
        )

        hit = find_malignancy_term_in_problem_line(
            "Major: Lentigo maligna melanoma - excised by plastics April 2025"
        )
        assert hit is not None
        assert hit[1] == "melanoma"

    def test_other_melanoma_subtypes_recognised(self):
        from libs.domains.code_inventories import (
            find_malignancy_term_in_problem_line,
        )

        for line in (
            "Major: Superficial spreading melanoma",
            "Problem: Nodular melanoma",
            "Active Problem: Acral lentiginous melanoma",
            "Major: Desmoplastic melanoma",
        ):
            hit = find_malignancy_term_in_problem_line(line)
            assert hit is not None, line
            assert hit[1] == "melanoma", line

    def test_treatment_procedure_codes_set_contents(self):
        assert "7G055" in CANCER_TREATMENT_PROCEDURE_CODES
        assert "X90PX" in CANCER_TREATMENT_PROCEDURE_CODES

    def test_find_cancer_treatment_procedure_code(self):
        assert find_cancer_treatment_procedure_code(
            "Wide excision of skin lesion (7G055) - right cheek lentigo maligna"
        ) == "7G055"
        assert find_cancer_treatment_procedure_code("Routine review") is None

    def test_treatment_anchor_fires_on_7G055(self):
        # _RE_TREATMENT does NOT match "Wide excision of skin lesion"
        # without the "lesion" word being part of "excision of lesion".
        # The procedure-code path must still fire.
        text = "Wide excision of skin lesion (7G055) - right cheek"
        _, _, treatments, _, _, _, _, _ = _classify_one(text)
        assert len(treatments) == 1
        assert treatments[0].get("treatment_source") == "procedure_code"
        assert treatments[0].get("treatment_code") == "7G055"

    def test_xapyd_emits_first_seen_with_site_key(self):
        text = "Seen in fast track suspected skin cancer clinic (XaPyd)"
        _, _, _, _, _, _, _, first_seens = _classify_one(text)
        assert len(first_seens) == 1
        fs = first_seens[0]
        assert fs.get("first_seen_source") == "specialist_clinic_code"
        assert fs.get("first_seen_code") == "XaPyd"
        assert fs.get("site_key") == "melanoma"

    def test_find_specialist_clinic_site_helper(self):
        hit = find_specialist_clinic_site(
            "Letter from suspected skin cancer clinic (XaPyd)"
        )
        assert hit == ("XaPyd", "melanoma")


# ---------------------------------------------------------------------------
# DI-LEO-AI-177: cancer follow-up template recogniser
# ---------------------------------------------------------------------------


class TestCancerFollowUpTemplate:
    """DI-LEO-AI-177: Skin/Breast/Prostate/etc. Cancer Follow Up template
    names emit diagnosis_confirmed anchors with cancer_follow_up_template
    provenance, gated by the history-of-cancer guard."""

    def test_helper_recognises_skin_template(self):
        hit = find_cancer_follow_up_phrase(
            "Template: Skin Cancer Follow Up - 6 month surveillance"
        )
        assert hit is not None
        assert hit[1] == "melanoma"

    def test_helper_recognises_breast_template(self):
        hit = find_cancer_follow_up_phrase(
            "Breast Cancer Follow Up clinic - 12 month review"
        )
        assert hit is not None
        assert hit[1] == "breast"

    def test_helper_recognises_generic_clinic(self):
        hit = find_cancer_follow_up_phrase("Cancer follow up clinic")
        assert hit is not None
        assert hit[1] == "non_site_specific"

    def test_helper_returns_none_without_cancer_word(self):
        assert find_cancer_follow_up_phrase("Routine follow up appointment") is None

    def test_detector_emits_diagnosis_with_template_provenance(self):
        text = (
            "Skin Cancer Follow Up: lesion on back 4x4mm seb k. "
            "No local recurrence."
        )
        _, diagnoses, _, _, _, _, _, _ = _classify_one(text)
        assert len(diagnoses) == 1
        d = diagnoses[0]
        assert d.get("diagnosis_source") == "cancer_follow_up_template"
        assert d.get("hitl_required") is True
        assert d.get("site_key") == "melanoma"

    def test_history_of_cancer_guard_wins(self):
        text = (
            "Major: H/O cancer of breast (B934.). "
            "Skin Cancer Follow Up template attached."
        )
        _, diagnoses, _, _, _, _, _, _ = _classify_one(text)
        assert diagnoses == []

    def test_phrases_compile_with_site_keys(self):
        import re as _re

        for rx, site in CANCER_FOLLOW_UP_PHRASES:
            assert isinstance(rx, _re.Pattern)
            assert isinstance(site, str) and site


# ---------------------------------------------------------------------------
# DI-LEO-AI-178: benign-investigation phrase scope guard (day-17 closure bug)
# ---------------------------------------------------------------------------


# The exact CKD encounter text from patient 4921442355 / 2024-11-18 that
# triggered the silent benign closure of the parallel skin-cancer
# episode. This is the regression fixture for R-LEO-AI-173.
_HAROLD_CKD_TEXT = """\
15:55 - Surgery: HORNE, Jonathan (Dr) (Clinical Practitioner Access Role)
Problem: Chronic kidney disease stage 3 (XaLHI)
History: F2F review. Seen with son, Ian.

Review re bloods.
Mild persistent hyperkalaemia (5.6)
eGFR stable at 42.
Urine ACR 28.
Nephrectomy in 1970s. Unsure indication. Tells me it "never worked".
Examination: 134 / 80mmHg
Diagnosis: Mild hyperkalaemia secondary to CKD and ACEI.
Plan: Reduce lisinopril to 10mg OD.
Repeat bloods in 1 month with home BP readings. If BP in normal range \
and potassium normalised then no further action. \
If persists or BP uncontrolled then review again.
Review if new concerns.
"""


class TestBenignPhraseScopeGuard:
    """DI-LEO-AI-178: BENIGN_PHRASE_REQUIRES_CANCER_CONTEXT gates the
    broad phrases ('no further action', 'discharged from clinic',
    'discharged from care') so they only fire benign_closure when the
    encounter has cancer-pathway context."""

    def test_gated_set_contains_broad_phrases(self):
        assert "no further action" in BENIGN_PHRASE_REQUIRES_CANCER_CONTEXT
        assert "discharged from care" in BENIGN_PHRASE_REQUIRES_CANCER_CONTEXT
        assert (
            "discharged from clinic" in BENIGN_PHRASE_REQUIRES_CANCER_CONTEXT
        )

    def test_cancer_pathway_regex_matches_common_tokens(self):
        for phrase in (
            "cancer review",
            "2WW skin clinic",
            "fast track referral",
            "oncology surveillance",
            "malignant melanoma",
            "lymphoma follow-up",
        ):
            assert CANCER_PATHWAY_CONTEXT_REGEX.search(phrase), phrase

    def test_text_has_cancer_pathway_context_helper(self):
        assert text_has_cancer_pathway_context("Letter from oncology clinic")
        assert text_has_cancer_pathway_context("MDT review for melanoma")
        assert not text_has_cancer_pathway_context("CKD review and BP titration")

    def test_harold_ckd_encounter_does_not_emit_benign_closure(self):
        # THE regression fixture - this is the exact bug.
        _, _, _, _, benigns, _, _, _ = _classify_one(
            _HAROLD_CKD_TEXT, enc_id="3e80acf0", date="2024-11-18"
        )
        assert benigns == [], (
            "Day-17 closure bug regression: CKD encounter must not "
            "produce a benign_closure anchor."
        )

    def test_tier1_phrase_no_evidence_of_malignancy_still_fires(self):
        text = "Mole biopsy: no evidence of malignancy."
        _, _, _, _, benigns, _, _, _ = _classify_one(text)
        assert len(benigns) >= 1

    def test_tier1_psa_no_further_action_still_fires(self):
        # The PSA-specific phrase is tier-1 (already cancer-scoped)
        # so it fires without needing the gate. Note the PSA regex
        # uses [^.\n] so the surrounding text must not contain a
        # full stop between "antigen" and "normal".
        text = (
            "Prostate-specific antigen result normal, no further action."
        )
        _, _, _, _, benigns, _, _, _ = _classify_one(text)
        assert len(benigns) >= 1

    def test_gated_phrase_with_cancer_context_fires(self):
        # Cancer-pathway token ("oncology") is enough to satisfy the
        # gate; using oncology rather than 2WW so the encounter does
        # not also classify as a referral.
        text = (
            "Letter from oncology clinic: lesion benign, "
            "discharged from clinic."
        )
        _, _, _, _, benigns, _, _, _ = _classify_one(text)
        assert len(benigns) == 1
        b = benigns[0]
        assert b.get("benign_phrase") == "discharged from clinic"

    def test_gated_phrase_alone_does_not_fire(self):
        # No cancer context, no Read code, just the phrase.
        text = (
            "Mental health follow-up. Patient discharged from clinic. "
            "Continue current medication."
        )
        _, _, _, _, benigns, _, _, _ = _classify_one(text)
        assert benigns == []

    def test_benign_read_code_path_unaffected_by_gate(self):
        # Read-code hit is unconditional - the gate only governs
        # broad phrase hits. Use a benign-explanation Read code in
        # an encounter without any 2WW/fast-track tokens to avoid
        # the existing referral-encounter guard.
        text = "Problem: Laryngopharyngeal reflux (XaK99) - reviewed."
        _, _, _, _, benigns, _, _, _ = _classify_one(text)
        assert len(benigns) == 1
        assert benigns[0].get("benign_source") == "problem_list_code"

    def test_no_further_action_with_cancer_word_fires(self):
        # Cancer word in same encounter satisfies the gate.
        text = (
            "MDT review of melanoma case: low-risk, no further action."
        )
        _, _, _, _, benigns, _, _, _ = _classify_one(text)
        assert len(benigns) == 1

    def test_gold_mined_renal_term_alone_does_not_satisfy_gate(self):
        # match_cancer_site gold-mined dictionary contains "chronic
        # kidney disease stage 3" under the renal site. The gate
        # MUST NOT trust this loose signal -- otherwise R-LEO-AI-173
        # (day-17 closure bug) re-opens.
        text = (
            "Problem: Chronic kidney disease stage 3 (XaLHI). "
            "Repeat bloods in 1 month. If stable, no further action."
        )
        _, _, _, _, benigns, _, _, _ = _classify_one(text)
        assert benigns == [], (
            "Gold-mined renal term must not satisfy the cancer-context "
            "gate; only strict cancer-pathway tokens or benign Read codes "
            "should."
        )


# ---------------------------------------------------------------------------
# Regression: patient 4921442355 (Mr Harold Allwyn, Lentigo maligna melanoma)
# ---------------------------------------------------------------------------


class TestRegressionHaroldAllwyn:
    """End-to-end-ish regression for the 2026-04-17 audit case. We
    cannot reach into the full episode builder here without a Neo4j
    fixture, but we CAN verify that each post-referral encounter the
    detector sees yields the right anchors."""

    def test_referral_encounter_recognised_as_melanoma(self):
        text = (
            "Fast track referral for suspected skin cancer (XaMeA) "
            "- (Added from Questionnaire)"
        )
        referrals, _, _, _, _, _, _, _ = _classify_one(text)
        assert len(referrals) == 1
        assert referrals[0].get("site_key") == "melanoma"
        assert referrals[0].get("site_source") == "explicit_2ww_code"

    def test_specialist_clinic_encounter_emits_first_seen(self):
        text = (
            "Seen in fast track suspected skin cancer clinic (XaPyd). "
            "Approx 3 mm oval shaped lesion to right side cheek."
        )
        _, _, _, _, _, _, _, first_seens = _classify_one(text)
        assert len(first_seens) == 1
        assert first_seens[0].get("site_key") == "melanoma"

    def test_lentigo_maligna_problem_line_emits_diagnosis(self):
        text = (
            "Major: Lentigo maligna melanoma (Xa99Y) - excised April 2025"
        )
        _, diagnoses, _, _, _, _, _, _ = _classify_one(text)
        assert len(diagnoses) == 1
        d = diagnoses[0]
        assert d.get("site_key") == "melanoma"
        # Read-code hit takes precedence over the term hit.
        assert d.get("diagnosis_source") == "problem_list_code"
        assert d.get("diagnosis_code") == "Xa99Y"

    def test_wide_excision_emits_treatment(self):
        text = (
            "Operation note: Wide excision of skin lesion (7G055) - "
            "right cheek lentigo maligna, clear margins."
        )
        _, _, treatments, _, _, _, _, _ = _classify_one(text)
        assert len(treatments) >= 1

    def test_skin_cancer_follow_up_template_emits_diagnosis(self):
        # Compressed UHL Dermatology surveillance template snippet.
        text = (
            "Skin Cancer Follow Up: lesion on back 4x4 mm inflamed seb k. "
            "Clinical management plan: fu 6 months as per surveillance, "
            "safety netting."
        )
        _, diagnoses, _, _, _, _, _, _ = _classify_one(text)
        assert len(diagnoses) == 1
        assert diagnoses[0].get("site_key") == "melanoma"
        assert diagnoses[0].get("diagnosis_source") == "cancer_follow_up_template"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
