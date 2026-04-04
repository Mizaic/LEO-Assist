"""Canonical sentence splitter for clinical text.

Provides a lightweight sentence splitter that handles clinical text.
Can optionally use MedSpaCy's PyRuSH for more accurate splits.
All pipeline code should import from here — do NOT duplicate.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Administrative header detection
# EMIS encounter exports prepend administrative metadata lines that must not
# be treated as clinical text by extractors. Patterns are conservative --
# when in doubt the sentence is preserved (err on the side of keeping content).
# ---------------------------------------------------------------------------

_HEADER_RE = re.compile(
    r"^("
    r"\d{2}:\d{2}"                              # HH:MM timestamp
    r"|Entered\s+at\s*:"                        # EMIS entry location
    r"|Presenting\s+to\s+non[- ]clinical"       # Reception note
    r"|Your\s+appointment\s+has\s+been\s+booked"
    r"|Confirmation\s+of\s+appointment"
    r"|Sent\s+online\s+by"                      # Online consultation header
    r"|Phlebotomy\s+Service\s*$"                # Phlebotomy service line
    r"|Seen\s+by\s+practice\s+phlebotomist"
    r")",
    re.IGNORECASE,
)


def is_header_sentence(text: str) -> bool:
    """Return True if the sentence is an administrative appointment header.

    Conservative: only returns True when the pattern is unambiguous.
    """
    return bool(_HEADER_RE.match(text.strip()))


def filter_header_sentences(chunks: list["SentenceChunk"]) -> list["SentenceChunk"]:
    """Remove administrative header sentences from a sentence chunk list.

    Returns an empty list (not an exception) if all sentences are headers.
    """
    return [c for c in chunks if not is_header_sentence(c.text)]


@dataclass(frozen=True)
class SentenceChunk:
    sentence_id: str
    text: str
    start: int
    end: int


def deduplicate_lines(text: str) -> str:
    """Remove consecutive duplicate lines (common in EHR exports)."""
    lines = text.split("\n")
    deduped: list[str] = []
    for line in lines:
        stripped = line.strip()
        if deduped and deduped[-1].strip() == stripped:
            continue
        deduped.append(line)
    return "\n".join(deduped)


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


class SentenceSplitter:
    """Split clinical text into sentence chunks.

    Uses PyRuSH (MedSpaCy) when available, falling back to regex.
    """

    def __init__(self) -> None:
        self._pyrush = self._try_load_pyrush()
        self.mode = "pyrush" if self._pyrush else "regex"

    @staticmethod
    def _try_load_pyrush():
        try:
            import spacy
            nlp = spacy.blank("en")
            from medspacy.sentence_splitting import PyRuSHSentencizer  # noqa: F401
            nlp.add_pipe("medspacy_pyrush")
            return nlp
        except Exception:
            logger.debug(
                "PyRuSH sentence splitter unavailable — falling back to regex",
                exc_info=True,
            )
            return None

    def split(self, text: str) -> list[SentenceChunk]:
        if not text.strip():
            return []
        if self._pyrush:
            chunks = self._split_pyrush(text)
            if len(chunks) <= 1 and _SENTENCE_SPLIT.search(text):
                return self._split_regex(text)
            return chunks
        return self._split_regex(text)

    def _split_pyrush(self, text: str) -> list[SentenceChunk]:
        doc = self._pyrush(text)
        chunks: list[SentenceChunk] = []
        for idx, sent in enumerate(doc.sents):
            t = sent.text.strip()
            if t:
                chunks.append(SentenceChunk(
                    sentence_id=f"s{idx}",
                    text=t,
                    start=sent.start_char,
                    end=sent.end_char,
                ))
        return chunks

    def _split_regex(self, text: str) -> list[SentenceChunk]:
        parts = _SENTENCE_SPLIT.split(text)
        chunks: list[SentenceChunk] = []
        offset = 0
        for idx, part in enumerate(parts):
            stripped = part.strip()
            if not stripped:
                offset += len(part) + 1
                continue
            start = text.find(stripped, offset)
            if start < 0:
                start = offset
            end = start + len(stripped)
            chunks.append(SentenceChunk(
                sentence_id=f"s{idx}",
                text=stripped,
                start=start,
                end=end,
            ))
            offset = end
        return chunks
