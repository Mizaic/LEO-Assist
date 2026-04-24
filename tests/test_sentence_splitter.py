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

    def test_single_newline_is_soft_wrap(self):
        """DI-D3391745 AC1: single \\n is a soft wrap, not a sentence break."""
        from libs.nlp.sentence_splitter import SentenceSplitter

        splitter = SentenceSplitter()
        text = "Line one\nLine two\nLine three"
        result = splitter.split(text)
        assert len(result) == 1
        assert result[0].text == text
        assert result[0].start == 0
        assert result[0].end == len(text)

    def test_blank_line_is_hard_break(self):
        """DI-D3391745 AC3: blank line separates narrative paragraphs."""
        from libs.nlp.sentence_splitter import SentenceSplitter

        splitter = SentenceSplitter()
        result = splitter.split("Para A.\n\nPara B.")
        assert len(result) == 2
        assert result[0].text == "Para A."
        assert result[1].text == "Para B."

    def test_lab_value_then_interpretation_on_next_line(self):
        """DI-D3391745 AC1: wrapped lab line + interpretation = 1 chunk."""
        from libs.nlp.sentence_splitter import SentenceSplitter

        splitter = SentenceSplitter()
        text = "PSA (XE25C) 12 ng/ml [0 - 6.5]\nOutside reference range"
        result = splitter.split(text)
        assert len(result) == 1
        assert result[0].text == text
        assert result[0].start == 0
        assert result[0].end == len(text)

    def test_lab_value_then_blank_then_interpretation(self):
        """DI-D3391745 AC2: blank line gap defers merge to Layer 3c."""
        from libs.nlp.sentence_splitter import SentenceSplitter

        splitter = SentenceSplitter()
        text = "PSA (XE25C) 12 ng/ml [0 - 6.5]\n\nOutside reference range"
        result = splitter.split(text)
        assert len(result) == 2
        assert result[0].text == "PSA (XE25C) 12 ng/ml [0 - 6.5]"
        assert result[1].text == "Outside reference range"

    def test_narrative_two_paragraphs_not_merged(self):
        """DI-D3391745 AC3: narrative paragraphs remain separate sentences."""
        from libs.nlp.sentence_splitter import SentenceSplitter

        splitter = SentenceSplitter()
        text = (
            "The patient reports fatigue and weight loss over six months.\n\n"
            "On examination there is mild tenderness over the right flank."
        )
        result = splitter.split(text)
        assert len(result) == 2
        assert result[0].text.startswith("The patient reports fatigue")
        assert result[1].text.startswith("On examination there is mild tenderness")

    def test_semicolon_eol_is_hard_break(self):
        """Lab-style semicolon + newline still segments cleanly."""
        from libs.nlp.sentence_splitter import SentenceSplitter

        splitter = SentenceSplitter()
        result = splitter.split("Test A 5 mmol/L;\nTest B 7 mmol/L")
        assert len(result) == 2
        assert result[0].text == "Test A 5 mmol/L;"
        assert result[1].text == "Test B 7 mmol/L"

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
        assert is_non_evidence_line(
            "An abnormal ABPI - ankle brachial pressure index could suggest significant arterial stenosis."
        )
        assert is_non_evidence_line(
            "A reduced ABPI - ankle brachial pressure index may indicate peripheral arterial disease."
        )
        assert is_non_evidence_line("Not on Thyroid Tx")
        assert is_non_evidence_line("No abnormality detected")
        assert is_non_evidence_line(
            "ALT level may be raised given the clinical picture."
        )
        assert is_non_evidence_line(
            "If symptoms worsen, AMY may rise above 500 U/L warranting further review."
        )
        assert is_non_evidence_line(
            "AST could be elevated, possibly around 90 U/L, given the clinical picture."
        )

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


class TestBuildContextWindow:
    """Tests for build_context_window -- short-sentence context enrichment."""

    def _chunks(self, texts: list[str]) -> list:
        from libs.nlp.sentence_splitter import SentenceChunk

        offset = 0
        result = []
        for i, t in enumerate(texts):
            result.append(SentenceChunk(sentence_id=f"s{i}", text=t, start=offset, end=offset + len(t)))
            offset += len(t) + 1
        return result

    def test_long_sentence_unchanged(self):
        from libs.nlp.sentence_splitter import build_context_window

        chunks = self._chunks(["No cough.", "Dyspnea on exertion for the past two weeks.", "Afebrile."])
        text, offset = build_context_window(chunks, 1, threshold=10)
        assert text == chunks[1].text
        assert offset == 0

    def test_short_sentence_middle_gets_neighbours(self):
        from libs.nlp.sentence_splitter import build_context_window

        chunks = self._chunks(["No cough.", "SOB", "O2 sats 96%."])
        text, offset = build_context_window(chunks, 1, threshold=50)
        assert "SOB" in text
        assert "No cough." in text
        assert "O2 sats 96%." in text
        # anchor_offset must point to "SOB" inside the context string
        assert text[offset:offset + len("SOB")] == "SOB"

    def test_short_sentence_at_start_only_appends(self):
        from libs.nlp.sentence_splitter import build_context_window

        chunks = self._chunks(["SOB", "No fever.", "Cough."])
        text, offset = build_context_window(chunks, 0, threshold=50)
        assert text.startswith("SOB")
        assert offset == 0
        assert "No fever." in text

    def test_short_sentence_at_end_only_prepends(self):
        from libs.nlp.sentence_splitter import build_context_window

        chunks = self._chunks(["Chest clear.", "No wheeze.", "SOB"])
        text, offset = build_context_window(chunks, 2, threshold=50)
        assert text.endswith("SOB")
        assert offset > 0
        assert text[offset:] == "SOB"

    def test_context_sents_limits_window(self):
        from libs.nlp.sentence_splitter import build_context_window

        chunks = self._chunks(["A.", "B.", "SOB", "D.", "E."])
        text, _ = build_context_window(chunks, 2, threshold=50, context_sents=1)
        assert "A." not in text
        assert "E." not in text
        assert "B." in text and "D." in text

    def test_anchor_offset_within_context(self):
        from libs.nlp.sentence_splitter import build_context_window

        chunks = self._chunks(["Prev sentence here.", "HTN", "Next one."])
        text, offset = build_context_window(chunks, 1, threshold=50)
        # The character at anchor_offset should be the start of the target
        assert text[offset : offset + len("HTN")] == "HTN"
