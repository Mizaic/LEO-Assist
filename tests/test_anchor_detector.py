"""Tests for services/analysis-worker/app/analyzers/anchor_detector.py.

VT-LEO-AI-084 -- TC-001, TC-002, TC-003 (assertion filter behaviour).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Shared fixture: mock DomainRegistry backed by synthetic concept sets
# ---------------------------------------------------------------------------

_REFERRAL_ID = 276281000000104
_DIAGNOSIS_ID = 363367000
_TREATMENT_ID = 421606006
_SPECIALIST_ID = 3457005

_CONCEPT_MAP = {
    "fast_track_referrals": [_REFERRAL_ID, 276431000000102, 363358000],
    "cancer_types": [_DIAGNOSIS_ID, 363358000],
    "treatments": [_TREATMENT_ID],
    "specialist_visits": [_SPECIALIST_ID],
}


def _fresh_configs():
    """Return a dict of fresh MagicMock domain configs (no shared state between tests)."""
    return {
        "fast_track_referrals": MagicMock(
            milestone_type="referral", assertion_filter=[]
        ),
        "cancer_types": MagicMock(milestone_type="diagnosis", assertion_filter=[]),
        "treatments": MagicMock(milestone_type="treatment_start", assertion_filter=[]),
        "specialist_visits": MagicMock(
            milestone_type="specialist_visit", assertion_filter=[]
        ),
    }


@pytest.fixture
def mock_registry():
    reg = MagicMock()
    reg.get_milestone_domains.return_value = _fresh_configs()
    reg.get_concept_ids.side_effect = lambda name: _CONCEPT_MAP.get(name, [])
    return reg


def _make_row(
    encounter_id, encounter_date, concept_id, concept_name, assertion="present"
):
    return {
        "encounter_id": encounter_id,
        "encounter_date": encounter_date,
        "concept_id": concept_id,
        "concept_name": concept_name,
        "semantic_tag": "procedure",
        "source": "documents",
        "confidence": 0.95,
        "evidence": concept_name,
        "assertion": assertion,
    }


# ---------------------------------------------------------------------------
# AnchorResult unit tests
# ---------------------------------------------------------------------------


class TestAnchorResult:

    def test_has_referral_empty(self):
        from services.analysis_worker.app.analyzers.anchor_detector import AnchorResult

        result = AnchorResult(patient_id="P1")
        assert not result.has_referral

    def test_has_referral_with_data(self):
        from services.analysis_worker.app.analyzers.anchor_detector import AnchorResult

        result = AnchorResult(patient_id="P1", referral_anchors=[{"x": 1}])
        assert result.has_referral


# ---------------------------------------------------------------------------
# _classify_anchor_rows unit tests
# ---------------------------------------------------------------------------


class TestClassifyAnchorRows:

    def test_empty_rows_returns_empty_buckets(self, mock_registry):
        from services.analysis_worker.app.analyzers.anchor_detector import (
            _build_buckets,
            _classify_anchor_rows,
        )

        buckets, _ = _build_buckets(mock_registry)
        refs, diags, treats, specs, benign, letters, first_pres, _first_seens = _classify_anchor_rows(
            [], buckets
        )
        assert (
            refs == []
            and diags == []
            and treats == []
            and specs == []
            and benign == []
            and letters == []
            and first_pres == []
        )

    def test_routes_referral_correctly(self, mock_registry):
        from services.analysis_worker.app.analyzers.anchor_detector import (
            _build_buckets,
            _classify_anchor_rows,
        )

        buckets, _ = _build_buckets(mock_registry)
        row = _make_row("E1", "2024-03-15", _REFERRAL_ID, "Fast track referral")
        refs, diags, treats, specs, benign, letters, first_pres, _first_seens = _classify_anchor_rows(
            [row], buckets
        )
        assert len(refs) == 1
        assert (
            diags == []
            and treats == []
            and specs == []
            and letters == []
            and first_pres == []
        )

    def test_routes_diagnosis_correctly(self, mock_registry):
        from services.analysis_worker.app.analyzers.anchor_detector import (
            _build_buckets,
            _classify_anchor_rows,
        )

        buckets, _ = _build_buckets(mock_registry)
        row = _make_row("E2", "2024-05-10", _DIAGNOSIS_ID, "Malignant tumour")
        refs, diags, treats, specs, benign, letters, first_pres, _first_seens = _classify_anchor_rows(
            [row], buckets
        )
        assert len(diags) == 1
        assert refs == [] and letters == [] and first_pres == []

    # VT-084-TC-001: assertion filter excludes non-matching assertion
    def test_assertion_filter_excludes_non_matching(self, mock_registry):
        from services.analysis_worker.app.analyzers.anchor_detector import (
            _build_buckets,
            _classify_anchor_rows,
        )

        # Set cancer_types to only accept "hypothetical"
        mock_registry.get_milestone_domains.return_value[
            "cancer_types"
        ].assertion_filter = ["hypothetical"]
        buckets, _ = _build_buckets(mock_registry)
        row = _make_row(
            "E3", "2024-05-10", _DIAGNOSIS_ID, "Malignant tumour", assertion="present"
        )
        refs, diags, treats, specs, benign, letters, first_pres, _first_seens = _classify_anchor_rows(
            [row], buckets
        )
        # present != hypothetical => excluded
        assert diags == [] and letters == [] and first_pres == []

    # VT-084-TC-002: assertion filter accepts matching assertion
    def test_assertion_filter_accepts_matching(self, mock_registry):
        from services.analysis_worker.app.analyzers.anchor_detector import (
            _build_buckets,
            _classify_anchor_rows,
        )

        mock_registry.get_milestone_domains.return_value[
            "cancer_types"
        ].assertion_filter = ["hypothetical"]
        buckets, _ = _build_buckets(mock_registry)
        row = _make_row(
            "E4",
            "2024-05-10",
            _DIAGNOSIS_ID,
            "Malignant tumour",
            assertion="hypothetical",
        )
        refs, diags, treats, specs, benign, letters, first_pres, _first_seens = _classify_anchor_rows(
            [row], buckets
        )
        assert len(diags) == 1 and letters == [] and first_pres == []

    # VT-084-TC-003: empty assertion_filter accepts all assertions
    def test_empty_assertion_filter_accepts_all(self, mock_registry):
        from services.analysis_worker.app.analyzers.anchor_detector import (
            _build_buckets,
            _classify_anchor_rows,
        )

        buckets, _ = _build_buckets(mock_registry)  # all filters are empty
        rows = [
            _make_row(
                "E5",
                "2024-05-10",
                _DIAGNOSIS_ID,
                "Malignant tumour",
                assertion="present",
            ),
            _make_row(
                "E6",
                "2024-06-10",
                _DIAGNOSIS_ID,
                "Malignant tumour",
                assertion="historical",
            ),
            _make_row(
                "E7",
                "2024-07-10",
                _DIAGNOSIS_ID,
                "Malignant tumour",
                assertion="hypothetical",
            ),
        ]
        refs, diags, treats, specs, benign, letters, first_pres, _first_seens = _classify_anchor_rows(
            rows, buckets
        )
        assert len(diags) == 3 and letters == [] and first_pres == []

    def test_two_diagnosis_domains_both_classified(self, mock_registry):
        """_build_buckets must merge concept IDs across domains sharing milestone_type.

        Regression: previously the second domain overwrote the first, silently
        dropping one set of diagnosis concepts.
        """
        from services.analysis_worker.app.analyzers.anchor_detector import (
            _build_buckets,
            _classify_anchor_rows,
        )

        _BENIGN_ID = 395100000
        mock_registry.get_milestone_domains.return_value["no_cancer_discharge"] = (
            MagicMock(milestone_type="diagnosis", assertion_filter=[])
        )
        mock_registry.get_concept_ids.side_effect = lambda name: (
            _CONCEPT_MAP.get(name, [])
            if name != "no_cancer_discharge"
            else [_BENIGN_ID]
        )
        buckets, pathway_ids = _build_buckets(mock_registry)

        cancer_row = _make_row("E8", "2024-05-10", _DIAGNOSIS_ID, "Malignant tumour")
        benign_row = _make_row(
            "E9", "2024-06-01", _BENIGN_ID, "No evidence of cancer found"
        )
        refs, diags, treats, specs, benign, letters, first_pres, _first_seens = _classify_anchor_rows(
            [cancer_row, benign_row], buckets, pathway_ids
        )

        assert (
            len(diags) == 2
        ), "Both cancer and benign concepts must reach diagnosis_anchors"
        tagged = [d for d in diags if d.get("is_pathway_completion")]
        untagged = [d for d in diags if not d.get("is_pathway_completion")]
        assert len(tagged) == 1
        assert len(untagged) == 1
        assert _BENIGN_ID in pathway_ids
        assert _DIAGNOSIS_ID not in pathway_ids
        assert letters == [] and first_pres == []

    # VT-LEO-AI-087: specialist outcome letter bucket
    def test_routes_specialist_letter_concept(self, mock_registry):
        from services.analysis_worker.app.analyzers.anchor_detector import (
            _build_buckets,
            _classify_anchor_rows,
        )

        _LETTER = 308470004
        cfg = dict(_fresh_configs())
        cfg["specialist_outcome_letter"] = MagicMock(
            milestone_type="specialist_outcome_letter",
            assertion_filter=[],
        )
        mock_registry.get_milestone_domains.return_value = cfg

        def _concept_ids(name):
            if name == "specialist_outcome_letter":
                return [_LETTER]
            return _CONCEPT_MAP.get(name, [])

        mock_registry.get_concept_ids.side_effect = _concept_ids
        buckets, _ = _build_buckets(mock_registry)
        row = _make_row("EL1", "2024-08-30", _LETTER, "Letter (record artifact)")
        refs, diags, treats, specs, benign, letters, first_pres, _first_seens = _classify_anchor_rows(
            [row], buckets
        )
        assert len(letters) == 1
        assert letters[0]["encounter_id"] == "EL1"

    def test_classify_text_clinic_letter_transfer(self):
        from services.analysis_worker.app.analyzers.anchor_detector import (
            _classify_text_encounters,
        )

        rows = [
            {
                "encounter_id": "DOC1",
                "encounter_date": "2024-08-30",
                "content_type": "document_transfer",
                "purpose": ["clinic_letter"],
                "text": "Dermatology to Woodbrook Medical Centre",
            }
        ]
        r, d, t, s, b, letters, first_pres, _first_seens = _classify_text_encounters(rows, set())
        assert len(letters) == 1
        assert letters[0]["concept_id"] == 308470004
        assert first_pres == []


class TestReferralRejectionAndResubmission:
    """DI-LEO-AI-182 -- detect referral rejection / marked-in-error /
    resubmission audit events as referral anchors with a dedicated
    subtype, so DQ tooling can surface workflow delays.

    Pattern level: applies to ANY 2WW pathway where the secondary-care
    provider rejects the referral (most often "no recent CXR / no
    recent imaging") and the GP must resubmit. These tests describe
    the textual pattern, NOT a specific patient.
    """

    def _classify(self, text: str, encounter_id: str = "E1"):
        from services.analysis_worker.app.analyzers.anchor_detector import (
            _classify_text_encounters,
        )

        rows = [
            {
                "encounter_id": encounter_id,
                "encounter_date": "2024-04-10",
                "content_type": "clinical",
                "text": text,
            }
        ]
        return _classify_text_encounters(rows, set())

    def test_choose_and_book_rejected_emits_referral_rejected_subtype(self):
        text = (
            "Choose and book referral rejected by service provider: referral "
            "rejected as no recent chest xray. Task to clinician to request CXR."
        )
        refs, _d, _t, _s, _b, _l, _fp, _fs = self._classify(text)
        assert len(refs) == 1
        assert refs[0]["referral_subtype"] == "rejected"

    def test_referral_marked_in_error_emits_rejected_subtype(self):
        text = (
            "Hospital Fast track referral for suspected breast cancer "
            "Marked in Error: Amended data\n"
            "e-Referral Service Referral Marked in Error: Amended data"
        )
        refs, _d, _t, _s, _b, _l, _fp, _fs = self._classify(text)
        assert len(refs) == 1
        assert refs[0]["referral_subtype"] == "rejected"

    def test_referral_resubmitted_emits_resubmitted_subtype(self):
        text = (
            "Fast track referral for suspected lung cancer (XaMeH) - "
            "amended referral sent following provider rejection."
        )
        refs, _d, _t, _s, _b, _l, _fp, _fs = self._classify(text)
        assert len(refs) == 1
        assert refs[0]["referral_subtype"] == "resubmitted"

    def test_rejection_does_not_emit_diagnosis_or_benign(self):
        text = (
            "Choose and book referral rejected by service provider for "
            "fast track referral for suspected colorectal cancer."
        )
        refs, diags, _t, _s, benigns, _l, _fp, _fs = self._classify(text)
        assert len(refs) == 1
        assert refs[0]["referral_subtype"] == "rejected"
        assert diags == []
        assert benigns == []

    def test_normal_2ww_referral_still_emits_text_generic(self):
        """Regression: vanilla 2WW referrals must still be detected as
        plain text_generic referrals, not get re-bucketed by the new
        rejection patterns."""
        text = "Fast track referral for suspected breast cancer (XaMeC)"
        refs, _d, _t, _s, _b, _l, _fp, _fs = self._classify(text)
        assert len(refs) == 1
        assert refs[0]["referral_subtype"] == "text_generic"

    def test_prism_referral_still_emits_prism_subtype(self):
        """Regression: PRISM proforma referrals must still take primacy
        over generic referral text."""
        text = (
            "PRISM 2WW Lung -  questionnaire started - "
            "(finalised: 09 Apr 2024 15:56)"
        )
        refs, _d, _t, _s, _b, _l, _fp, _fs = self._classify(text)
        assert len(refs) == 1
        assert refs[0]["referral_subtype"] == "prism"

    def test_rejection_keyword_alone_no_referral_context_does_not_match(self):
        """Guard: 'rejected' on its own (e.g. organ transplant rejection)
        must not match the referral-rejection pattern."""
        text = "Patient discussed: no signs of transplant rejection."
        refs, _d, _t, _s, _b, _l, _fp, _fs = self._classify(text)
        assert refs == []

    def test_resubmitted_keyword_alone_does_not_match_without_referral(self):
        """Guard: 'resubmitted' on its own (e.g. lab sample resubmitted)
        must not produce a referral anchor."""
        text = "Sample was resubmitted to the lab for re-analysis."
        refs, _d, _t, _s, _b, _l, _fp, _fs = self._classify(text)
        assert refs == []

    def test_marked_in_error_unrelated_event_does_not_match(self):
        """Guard: 'Marked in Error' on a non-referral entity (e.g. a lab
        value or diagnosis line) must not be classified as a referral
        rejection."""
        text = "Blood pressure 140/90 - Marked in Error: Amended data"
        refs, _d, _t, _s, _b, _l, _fp, _fs = self._classify(text)
        assert refs == []


# ---------------------------------------------------------------------------
# detect_anchors integration tests
# ---------------------------------------------------------------------------


class TestDetectAnchors:

    def test_no_encounters(self, mock_registry):
        from services.analysis_worker.app.analyzers.anchor_detector import (
            detect_anchors,
        )

        mock_client = MagicMock()
        mock_client.run.return_value = []

        result = detect_anchors(
            "P1", "2024-01-01", "2024-12-31", mock_client, mock_registry
        )
        assert result.patient_id == "P1"
        assert result.referral_anchors == []
        assert result.diagnosis_anchors == []

    def test_detects_referral_from_documents(self, mock_registry):
        from services.analysis_worker.app.analyzers.anchor_detector import (
            detect_anchors,
        )

        mock_client = MagicMock()
        mock_client.run.return_value = [
            _make_row(
                "E1",
                "2024-03-15",
                _REFERRAL_ID,
                "Fast track referral for suspected breast cancer",
            ),
        ]

        result = detect_anchors(
            "P1", "2024-01-01", "2024-12-31", mock_client, mock_registry
        )
        assert len(result.referral_anchors) == 1
        assert "breast" in result.referral_anchors[0]["concept_name"].lower()

    def test_detects_diagnosis_from_documents(self, mock_registry):
        from services.analysis_worker.app.analyzers.anchor_detector import (
            detect_anchors,
        )

        mock_client = MagicMock()
        mock_client.run.return_value = [
            _make_row("E2", "2024-05-10", _DIAGNOSIS_ID, "Malignant tumour of colon"),
        ]

        result = detect_anchors(
            "P1", "2024-01-01", "2024-12-31", mock_client, mock_registry
        )
        assert len(result.diagnosis_anchors) == 1
        assert "malignant" in result.diagnosis_anchors[0]["concept_name"].lower()

    def test_expand_window_sets_dates(self, mock_registry):
        from services.analysis_worker.app.analyzers.anchor_detector import (
            detect_anchors,
        )

        mock_client = MagicMock()
        mock_client.run.return_value = [
            _make_row(
                "E1",
                "2024-06-15",
                276431000000102,
                "Fast track referral for suspected lung cancer",
            ),
        ]

        result = detect_anchors(
            "P1", "2024-01-01", "2024-12-31", mock_client, mock_registry
        )
        assert result.earliest_date == "2024-06-15"
        assert result.expanded_start is not None
        assert result.expanded_start < "2024-06-15"

    # VT-084-TC-001 end-to-end: assertion filter blocks present concept from hypothetical-only bucket
    def test_assertion_filter_excludes_present_for_hypothetical_only(
        self, mock_registry
    ):
        from services.analysis_worker.app.analyzers.anchor_detector import (
            detect_anchors,
        )

        mock_registry.get_milestone_domains.return_value[
            "cancer_types"
        ].assertion_filter = ["hypothetical"]
        mock_client = MagicMock()
        mock_client.run.return_value = [
            _make_row(
                "E3",
                "2024-05-10",
                _DIAGNOSIS_ID,
                "Malignant tumour",
                assertion="present",
            ),
        ]
        result = detect_anchors(
            "P1", "2024-01-01", "2024-12-31", mock_client, mock_registry
        )
        assert result.diagnosis_anchors == []

    def test_construct_match_creates_referral_anchor(self, mock_registry):
        from libs.domain_config.registry import NCDAConstruct, NCDAConstructRole
        from services.analysis_worker.app.analyzers.anchor_detector import (
            detect_anchors,
        )

        mock_registry.get_milestone_domains.return_value = {
            "fast_track_referrals": MagicMock(
                milestone_type="referral",
                assertion_filter=[],
                constructs=[
                    NCDAConstruct(
                        construct_id="cg_pruritus_bleed",
                        display_name="Pruritus with bleeding referral signal",
                        logic="ALL",
                        roles=[
                            NCDAConstructRole(role="condition", concept_ids=[111], required=True),
                            NCDAConstructRole(role="qualifier", concept_ids=[222], required=True),
                        ],
                    )
                ],
            )
        }
        mock_registry.get_concept_ids.side_effect = lambda name: []

        mock_client = MagicMock()
        mock_client.run.side_effect = [
            [
                _make_row("E10", "2024-05-11", 111, "Pruritus of penis"),
                _make_row("E10", "2024-05-11", 222, "Mild bleeding"),
            ],
            [],
        ]

        result = detect_anchors(
            "P1", "2024-01-01", "2024-12-31", mock_client, mock_registry
        )
        assert len(result.referral_anchors) == 1
        assert result.referral_anchors[0].get("source") == "construct_match"
        assert (
            result.referral_anchors[0].get("construct_id")
            == "cg_pruritus_bleed"
        )
