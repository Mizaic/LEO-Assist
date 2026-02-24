"""Sentence splitting for V3 pipeline using spaCy/PyRuSH when available."""

from __future__ import annotations

import re
from dataclasses import dataclass


_FALLBACK_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")


@dataclass(frozen=True)
class SentenceChunk:
    sentence_id: str
    text: str
    start: int
    end: int


class SentenceSplitter:
    """Sentence splitter with best-effort PyRuSH support.

    Runtime behavior:
    - If spaCy + PyRuSH are available, they are used.
    - Else if spaCy is available, sentencizer is used.
    - Else fallback regex split is used.
    """

    def __init__(self) -> None:
        self._mode = "regex"
        self._nlp = None
        self._init_pipeline()

    def _init_pipeline(self) -> None:
        try:
            import spacy
        except Exception:  # pragma: no cover - runtime-dependent optional deps
            return

        # Try PyRuSH pipeline first.
        try:
            nlp = spacy.blank("en")
            import medspacy  # pylint: disable=import-outside-toplevel,unused-import
            import PyRuSH  # pylint: disable=import-outside-toplevel,unused-import

            if "sentencizer" in nlp.pipe_names:
                nlp.remove_pipe("sentencizer")
            nlp.add_pipe("sentencizer")
            self._nlp = nlp
            self._mode = "spacy_pyrush"
            return
        except Exception:  # pragma: no cover
            pass

        # Fallback to vanilla spaCy sentencizer.
        try:
            nlp = spacy.blank("en")
            if "sentencizer" not in nlp.pipe_names:
                nlp.add_pipe("sentencizer")
            self._nlp = nlp
            self._mode = "spacy_sentencizer"
        except Exception:  # pragma: no cover
            self._nlp = None
            self._mode = "regex"

    @property
    def mode(self) -> str:
        return self._mode

    def split(self, text: str) -> list[SentenceChunk]:
        if not text.strip():
            return []
        if self._nlp is not None:
            chunks = self._split_spacy(text)
            if chunks:
                return chunks
        return self._split_regex(text)

    def _split_spacy(self, text: str) -> list[SentenceChunk]:
        doc = self._nlp(text)
        chunks: list[SentenceChunk] = []
        sid = 0
        for sent in doc.sents:
            sent_text = sent.text.strip()
            if not sent_text:
                continue
            start = sent.start_char
            end = sent.end_char
            chunks.append(
                SentenceChunk(
                    sentence_id=f"s{sid}",
                    text=sent_text,
                    start=start,
                    end=end,
                )
            )
            sid += 1
        return chunks

    def _split_regex(self, text: str) -> list[SentenceChunk]:
        chunks: list[SentenceChunk] = []
        cursor = 0
        sid = 0
        for raw in _FALLBACK_SPLIT_RE.split(text):
            sent = raw.strip()
            if not sent:
                continue
            start = text.find(sent, cursor)
            if start < 0:
                start = cursor
            end = start + len(sent)
            cursor = end
            chunks.append(
                SentenceChunk(
                    sentence_id=f"s{sid}",
                    text=sent,
                    start=start,
                    end=end,
                )
            )
            sid += 1
        return chunks

