"""Tests for libs/nlp/sentence_splitter.py (canonical) and its re-export."""

from __future__ import annotations

import pytest


class TestDeduplicate:

    def test_removes_consecutive_duplicates(self):
        from libs.nlp.sentence_splitter import deduplicate_lines

        text = "Line one\nLine one\nLine two\nLine two\nLine three"
        result = deduplicate_lines(text)
        assert result == "Line one\nLine two\nLine three"

    def test_preserves_non_consecutive(self):
        from libs.nlp.sentence_splitter import deduplicate_lines

        text = "A\nB\nA\nB"
        result = deduplicate_lines(text)
        assert result == "A\nB\nA\nB"

    def test_empty_text(self):
        from libs.nlp.sentence_splitter import deduplicate_lines

        assert deduplicate_lines("") == ""


class TestSentenceChunk:

    def test_frozen_dataclass(self):
        from libs.nlp.sentence_splitter import SentenceChunk

        chunk = SentenceChunk(sentence_id="s0", text="Hello.", start=0, end=6)
        assert chunk.sentence_id == "s0"
        assert chunk.text == "Hello."
        with pytest.raises(AttributeError):
            chunk.text = "other"


class TestSentenceSplitter:

    def test_split_empty_text(self):
        from libs.nlp.sentence_splitter import SentenceSplitter

        splitter = SentenceSplitter()
        assert splitter.split("") == []
        assert splitter.split("   ") == []

    def test_split_single_sentence(self):
        from libs.nlp.sentence_splitter import SentenceSplitter

        splitter = SentenceSplitter()
        result = splitter.split("Patient presents with cough.")
        assert len(result) >= 1
        assert result[0].text == "Patient presents with cough."
        assert result[0].sentence_id.startswith("s")

    def test_split_multiple_sentences(self):
        from libs.nlp.sentence_splitter import SentenceSplitter

        splitter = SentenceSplitter()
        result = splitter.split("First sentence. Second sentence. Third sentence.")
        assert len(result) == 3
        assert result[0].text == "First sentence."
        assert result[1].text == "Second sentence."
        assert result[2].text == "Third sentence."

    def test_split_newline_separated(self):
        from libs.nlp.sentence_splitter import SentenceSplitter

        splitter = SentenceSplitter()
        result = splitter.split("Line one\nLine two\nLine three")
        assert len(result) == 3

    def test_split_preserves_offsets(self):
        from libs.nlp.sentence_splitter import SentenceSplitter

        splitter = SentenceSplitter()
        text = "Abc. Def."
        result = splitter.split(text)
        assert len(result) == 2
        assert text[result[0].start : result[0].end] == result[0].text
        assert text[result[1].start : result[1].end] == result[1].text

    def test_regex_mode_by_default(self):
        from libs.nlp.sentence_splitter import SentenceSplitter

        splitter = SentenceSplitter()
        assert splitter.mode in ("regex", "pyrush")


class TestAssertionInference:

    def test_negated(self):
        from libs.nlp.assertion_inference import infer_assertion

        assert infer_assertion("no evidence of cancer") == "absent"
        assert infer_assertion("ruled out malignancy") == "absent"

    def test_family(self):
        from libs.nlp.assertion_inference import infer_assertion

        assert infer_assertion("family history of breast cancer") == "family"

    def test_historical(self):
        from libs.nlp.assertion_inference import infer_assertion

        assert infer_assertion("history of diabetes") == "historical"
        assert infer_assertion("Previous MI in 2019") == "historical"

    def test_present(self):
        from libs.nlp.assertion_inference import infer_assertion

        assert infer_assertion("Patient presents with chest pain") == "present"

    def test_record_disambiguation(self):
        from libs.nlp.assertion_inference import infer_assertion

        record = {"disambiguation": "historical"}
        assert infer_assertion("active disease", record=record) == "historical"


class TestNonEvidenceFilter:

    def test_non_evidence_patterns(self):
        from libs.nlp.sentence_splitter import is_non_evidence_line

        assert is_non_evidence_line("Discussed smoking cessation leaflet")
        assert is_non_evidence_line("EMIS template completed")
        assert is_non_evidence_line("Salbutamol 100 mcg/dose inhaler")

    def test_fast_track_phrase_is_not_filtered(self):
        from libs.nlp.sentence_splitter import is_non_evidence_line

        assert not is_non_evidence_line(
            "fast track referral for suspected bowel cancer arranged"
        )


class TestReferralProcedurePhrase:

    def test_detects_referral_phrase(self):
        from libs.nlp.sentence_splitter import is_referral_procedure_phrase

        assert is_referral_procedure_phrase(
            "Fast track referral for suspected breast cancer"
        )

    def test_ignores_non_referral_phrase(self):
        from libs.nlp.sentence_splitter import is_referral_procedure_phrase

        assert not is_referral_procedure_phrase("Possible breast cancer")
