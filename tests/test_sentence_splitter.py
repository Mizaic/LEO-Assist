"""Tests for services/coding-worker/app/pipeline/sentence_splitter.py."""

from __future__ import annotations

import pytest


class TestDeduplicate:

    def test_removes_consecutive_duplicates(self):
        from services.coding_worker.app.pipeline.sentence_splitter import deduplicate_lines

        text = "Line one\nLine one\nLine two\nLine two\nLine three"
        result = deduplicate_lines(text)
        assert result == "Line one\nLine two\nLine three"

    def test_preserves_non_consecutive(self):
        from services.coding_worker.app.pipeline.sentence_splitter import deduplicate_lines

        text = "A\nB\nA\nB"
        result = deduplicate_lines(text)
        assert result == "A\nB\nA\nB"

    def test_empty_text(self):
        from services.coding_worker.app.pipeline.sentence_splitter import deduplicate_lines
        assert deduplicate_lines("") == ""


class TestSentenceChunk:

    def test_frozen_dataclass(self):
        from services.coding_worker.app.pipeline.sentence_splitter import SentenceChunk

        chunk = SentenceChunk(sentence_id="s0", text="Hello.", start=0, end=6)
        assert chunk.sentence_id == "s0"
        assert chunk.text == "Hello."
        with pytest.raises(AttributeError):
            chunk.text = "other"


class TestSentenceSplitter:

    def test_split_empty_text(self):
        from services.coding_worker.app.pipeline.sentence_splitter import SentenceSplitter

        splitter = SentenceSplitter()
        assert splitter.split("") == []
        assert splitter.split("   ") == []

    def test_split_single_sentence(self):
        from services.coding_worker.app.pipeline.sentence_splitter import SentenceSplitter

        splitter = SentenceSplitter()
        result = splitter.split("Patient presents with cough.")
        assert len(result) >= 1
        assert result[0].text == "Patient presents with cough."
        assert result[0].sentence_id.startswith("s")

    def test_split_multiple_sentences(self):
        from services.coding_worker.app.pipeline.sentence_splitter import SentenceSplitter

        splitter = SentenceSplitter()
        result = splitter.split("First sentence. Second sentence. Third sentence.")
        assert len(result) == 3
        assert result[0].text == "First sentence."
        assert result[1].text == "Second sentence."
        assert result[2].text == "Third sentence."

    def test_split_newline_separated(self):
        from services.coding_worker.app.pipeline.sentence_splitter import SentenceSplitter

        splitter = SentenceSplitter()
        result = splitter.split("Line one\nLine two\nLine three")
        assert len(result) == 3

    def test_split_preserves_offsets(self):
        from services.coding_worker.app.pipeline.sentence_splitter import SentenceSplitter

        splitter = SentenceSplitter()
        text = "Abc. Def."
        result = splitter.split(text)
        assert len(result) == 2
        assert text[result[0].start:result[0].end] == result[0].text
        assert text[result[1].start:result[1].end] == result[1].text

    def test_regex_mode_by_default(self):
        from services.coding_worker.app.pipeline.sentence_splitter import SentenceSplitter

        splitter = SentenceSplitter()
        assert splitter.mode in ("regex", "pyrush")
