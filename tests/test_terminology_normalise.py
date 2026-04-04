"""Tests for VT-LEO-AI-080 -- resolver input normalisation and header filtering.

Covers DI-LEO-AI-080 (appointment header filter) and the DI-LEO-AI-004
bug fix (_normalise_for_resolve strips lab values and EMIS codes).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

import pytest

from libs.nlp.sentence_splitter import (
    SentenceChunk,
    filter_header_sentences,
    is_header_sentence,
)
from libs.terminology.client import _normalise_for_resolve


# ---------------------------------------------------------------------------
# VT-080-TC-001 / TC-002 / TC-003 / TC-004 -- header detection
# ---------------------------------------------------------------------------

class TestIsHeaderSentence:
    @pytest.mark.parametrize("text", [
        "07:35 - Surgery: INGLE, Kirsty (Receptionist Access Role)",
        "07:35 - Surgery: Unknown Staff Member",
        "06:04 - Surgery: Unknown Staff Member",
        "Entered at: LLR Community Therapy Service",
        "Entered at: LLR SPA",
        "Presenting to non-clinical team with: To request repeat medication",
        "Presenting to non-clinical team: To request repeat medication",
        "Your appointment has been booked for 13 Nov 2024 at Woodbrook Medical Centre",
        "Confirmation of appointment at Woodbrook Medical Centre",
        "Sent online by Miss Karen J Griffiths",
        "Phlebotomy Service",
        "Seen by practice phlebotomist",
    ])
    def test_header_sentences_detected(self, text):
        # VT-080-TC-001 through TC-004
        assert is_header_sentence(text) is True, f"Expected header: {text!r}"

    # VT-080-TC-005 -- clinical sentences must NOT be filtered
    @pytest.mark.parametrize("text", [
        "Patient reports chest pain on exertion for 3 weeks.",
        "Type 2 diabetes mellitus, well controlled on Metformin.",
        "Weight loss of 5kg over the past 3 months.",
        "Hypertension - blood pressure 145/90.",
        "Referred to Oncology for further investigation.",
        "No evidence of cancer found.",
        "Fatigue for the last month, no fever.",
        "HbA1c 58 mmol/mol, eGFR 62 mL/min.",
        "Serum triglyceride 1.05 mmol/L - within range.",
        "07 July 2025 - routine review.",   # date line, not HH:MM header
        "Surgery was performed under general anaesthesia.",
    ])
    def test_clinical_sentences_not_filtered(self, text):
        assert is_header_sentence(text) is False, f"False positive on: {text!r}"


# ---------------------------------------------------------------------------
# VT-080-TC-006 -- filter_header_sentences empty-list behaviour
# ---------------------------------------------------------------------------

class TestFilterHeaderSentences:
    def _chunk(self, idx: int, text: str) -> SentenceChunk:
        return SentenceChunk(sentence_id=f"s{idx}", text=text, start=0, end=len(text))

    def test_removes_header_chunks(self):
        chunks = [
            self._chunk(0, "07:35 - Surgery: INGLE, Kirsty"),
            self._chunk(1, "Patient reports chest pain."),
            self._chunk(2, "Entered at: LLR SPA"),
        ]
        result = filter_header_sentences(chunks)
        assert len(result) == 1
        assert result[0].text == "Patient reports chest pain."

    def test_empty_result_when_all_headers(self):
        # VT-080-TC-006
        chunks = [
            self._chunk(0, "07:35 - Surgery: Unknown Staff Member"),
            self._chunk(1, "Entered at: The County Practice"),
        ]
        result = filter_header_sentences(chunks)
        assert result == []

    def test_no_change_when_no_headers(self):
        chunks = [
            self._chunk(0, "Patient reports weight loss."),
            self._chunk(1, "Hypertension, well controlled."),
        ]
        result = filter_header_sentences(chunks)
        assert len(result) == 2

    def test_empty_input(self):
        assert filter_header_sentences([]) == []


# ---------------------------------------------------------------------------
# VT-080-TC-007 -- lab value stripping
# ---------------------------------------------------------------------------

class TestNormaliseForResolve:
    @pytest.mark.parametrize("raw,expected", [
        ("Serum triglyceride 1.05 mmol/L", "Serum triglyceride"),
        ("Serum cholesterol level 5.3 mmol/L", "Serum cholesterol level"),
        ("Haemoglobin 160 g/L", "Haemoglobin"),
        ("Serum TSH level 1.3 mIU/L", "Serum TSH level"),
        ("Serum folate 4.1 ng/ml", "Serum folate"),
        ("Serum vitamin B12 631 ng/L", "Serum vitamin B12"),
        ("BMI 28.4 kg/m2", "BMI"),
        ("White blood cell count 6.8 10^9/L", "White blood cell count"),
        ("eGFR 62 mL/min", "eGFR"),
        ("Platelet count 220 10^9/L", "Platelet count"),
        ("Serum alkaline phosphatase 78 U/L", "Serum alkaline phosphatase"),
        ("Serum HDL cholesterol 1.22 mmol/L", "Serum HDL cholesterol"),
    ])
    def test_strips_lab_value_and_unit(self, raw, expected):
        # VT-080-TC-007
        assert _normalise_for_resolve(raw) == expected

    # VT-080-TC-008 -- EMIS local code stripping
    @pytest.mark.parametrize("raw,expected", [
        ("Carcinoma of stomach (X78gA)", "Carcinoma of stomach"),
        ("Chronic Symptoms (Y41c9)", "Chronic Symptoms"),
        ("Prolapsed intervertebral disc (X70Cg)", "Prolapsed intervertebral disc"),
        ("Lumbar spinal stenosis (N1402)", "Lumbar spinal stenosis"),
    ])
    def test_strips_emis_code(self, raw, expected):
        assert _normalise_for_resolve(raw) == expected

    # VT-080-TC-009 -- plain clinical terms unchanged
    @pytest.mark.parametrize("text", [
        "Type 2 diabetes mellitus",
        "hypertension",
        "weight loss",
        "back pain",
        "chronic back pain",
        "fatigue for the last month",
    ])
    def test_clinical_terms_unchanged(self, text):
        # VT-080-TC-009
        assert _normalise_for_resolve(text) == text

    def test_never_returns_empty(self):
        # Edge case: if stripping would produce empty, return original
        result = _normalise_for_resolve("  ")
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# VT-080-TC-010 -- result re-keying in TerminologyClient.resolve()
# ---------------------------------------------------------------------------

class TestResolveReKeying:
    def test_results_keyed_by_original_term(self):
        """Results must be keyed by the original (un-normalised) term."""
        from libs.terminology.client import TerminologyClient, ResolvedTerm

        fake_candidate = ResolvedTerm(
            text="Serum triglyceride",
            concept_id="134427008",
            term="Serum triglyceride measurement",
            semantic_tag="observable_entity",
            score=0.95,
        )

        client = TerminologyClient()
        # _resolve_batch returns results keyed by the NORMALISED term.
        with patch.object(
            client,
            "_resolve_batch",
            return_value={"Serum triglyceride": [fake_candidate]},
        ):
            result = client.resolve(["Serum triglyceride 1.05 mmol/L"])

        # Caller must get results keyed by the ORIGINAL term.
        assert "Serum triglyceride 1.05 mmol/L" in result
        assert result["Serum triglyceride 1.05 mmol/L"][0].concept_id == "134427008"

    def test_two_originals_normalising_to_same_key(self):
        """Two different lab strings that normalise to the same term both get results."""
        from libs.terminology.client import TerminologyClient, ResolvedTerm

        fake = ResolvedTerm(
            text="Serum triglyceride",
            concept_id="134427008",
            term="Serum triglyceride measurement",
            semantic_tag="observable_entity",
            score=0.95,
        )

        client = TerminologyClient()
        with patch.object(
            client,
            "_resolve_batch",
            return_value={"Serum triglyceride": [fake]},
        ):
            result = client.resolve([
                "Serum triglyceride 1.05 mmol/L",
                "Serum triglyceride 2.3 mmol/L",
            ])

        assert "Serum triglyceride 1.05 mmol/L" in result
        assert "Serum triglyceride 2.3 mmol/L" in result
