"""Sentence splitting for V3 pipeline using spaCy/PyRuSH when available."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_FALLBACK_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")


def deduplicate_lines(text: str) -> str:
    """Remove duplicate lines from encounter text.

    GP encounter records often contain a structured consultation section followed
    by a coded summary that repeats the same lines verbatim.  This keeps only
    the first occurrence of each unique line (compared case-insensitively after
    stripping whitespace), preserving order and blank lines.
    """
    seen: set[str] = set()
    out: list[str] = []
    for line in text.split("\n"):
        key = line.strip().lower()
        if not key or key not in seen:
            out.append(line)
            if key:
                seen.add(key)
    return "\n".join(out)


@dataclass(frozen=True)
class SentenceChunk:
    sentence_id: str
    text: str
    start: int
    end: int


class SentenceSplitter:
    """Sentence splitter with best-effort PyRuSH support.

    Runtime behavior:
    - If spaCy + PyRuSH are available, ``medspacy_pyrush`` is used.
    - Else if spaCy is available, sentencizer is used.
    - Else fallback regex split is used.
    """

    def __init__(self) -> None:
        self._mode = "regex"
        self._nlp = None
        self._init_pipeline()
        logger.info("SentenceSplitter initialised: mode=%s", self._mode)

    def _init_pipeline(self) -> None:
        try:
            import spacy
        except Exception:  # pragma: no cover - runtime-dependent optional deps
            return

        # Try PyRuSH pipeline first (registered as "medspacy_pyrush").
        try:
            from PyRuSH import PyRuSHSentencizer  # noqa: F401  # pylint: disable=import-outside-toplevel,unused-import

            nlp = spacy.blank("en")
            nlp.add_pipe("medspacy_pyrush")
            self._nlp = nlp
            self._mode = "pyrush"
            return
        except Exception:  # pragma: no cover
            logger.debug("PyRuSH unavailable, trying spaCy sentencizer", exc_info=True)

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

