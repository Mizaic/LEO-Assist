"""Canonical sentence splitter for clinical text.

Atlas trace:
  DO: DO-1D5031E0
  Also implements: DO-27B414B3, DO-8620A68B
  DI: DI-12015DBC, DI-5A802C83, DI-702F4583, DI-DA7584D8
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-1D5031E0")

Provides a lightweight sentence splitter that handles clinical text.
Can optionally use MedSpaCy's PyRuSH for more accurate splits.
All pipeline code should import from here — do NOT duplicate.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


def _suppress_pyrush_debug_noise() -> None:
    """Mute PyRuSH debug spam unless explicitly enabled.

    PyRuSH emits verbose token-by-token debug logs via both stdlib logging and
    loguru in some runtime paths. Those logs can dominate validation output and
    slow local runs. Set PYRUSH_DEBUG_LOGS=1 to keep full debug output.
    """
    if os.getenv("PYRUSH_DEBUG_LOGS", "").strip().lower() in {"1", "true", "yes"}:
        return

    logging.getLogger("PyRuSH").setLevel(logging.WARNING)
    try:
        from loguru import logger as _loguru_logger

        _loguru_logger.disable("PyRuSH")
        _loguru_logger.disable("PyRuSH.PyRuSHSentencizer")
    except Exception:
        # loguru is optional in some environments
        pass

# ---------------------------------------------------------------------------
# Administrative header detection
# EMIS encounter exports prepend administrative metadata lines that must not
# be treated as clinical text by extractors. Patterns are conservative --
# when in doubt the sentence is preserved (err on the side of keeping content).
# ---------------------------------------------------------------------------

_HEADER_RE = re.compile(
    r"^("
    r"\d{2}:\d{2}"  # HH:MM timestamp
    r"|Entered\s+at\s*:"  # EMIS entry location
    r"|Presenting\s+to\s+non[- ]clinical"  # Reception note
    r"|Your\s+appointment\s+has\s+been\s+booked"
    r"|Confirmation\s+of\s+appointment"
    r"|Sent\s+online\s+by"  # Online consultation header
    r"|Phlebotomy\s+Service\s*$"  # Phlebotomy service line
    r"|Seen\s+by\s+practice\s+phlebotomist"
    r")",
    re.IGNORECASE,
)


def is_header_sentence(text: str) -> bool:
    """Return True if the sentence is an administrative appointment header.

    Conservative: only returns True when the pattern is unambiguous.
    """
    return bool(_HEADER_RE.match(text.strip()))


# Clinical milestone phrases that must never be stripped, even if a future
# header pattern accidentally matches them. Both specialist visit and referral
# milestones are critical to the cancer episode detector.
_FAST_TRACK_MILESTONE_RE = re.compile(
    r"seen\s+in\s+fast\s+track|fast\s+track\s+referral\s+for\s+suspected|fast\s+track\s+cancer\s+referral",
    re.IGNORECASE,
)

_NON_EVIDENCE_PATTERNS = [
    re.compile(r"^[A-Z][A-Za-z0-9\s\-/]{0,40}:\s+[A-Z0-9]{6,}$"),
    re.compile(
        r"^\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml)\b.*\b(?:tablet|capsule|inhaler|cream|patch)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"^[A-Z][A-Za-z0-9\s\-/]+\s+\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml)\b.*\b(?:tablet|capsule|inhaler|cream|patch)\b",
        re.IGNORECASE,
    ),
    re.compile(r"^(Discussed|Advised|Counselled)\b", re.IGNORECASE),
    re.compile(r"^Clinical\s+note\s+indicates\b", re.IGNORECASE),
    re.compile(
        r"^An?\s+abnormal\s+ABPI\b.*\bcould\s+suggest\s+significant\s+arterial\s+stenosis\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"^A?\s*reduced\s+ABPI\b.*\bmay\s+indicate\s+peripheral\s+arterial\s+disease\b",
        re.IGNORECASE,
    ),
    re.compile(r"^Not\s+on\s+Thyroid\s+Tx\b", re.IGNORECASE),
    re.compile(r"^No\s+abnormality\s+detected\b", re.IGNORECASE),
    re.compile(
        r"^ALT\s+level\s+may\s+be\s+raised\s+given\s+the\s+clinical\s+picture\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"^If\s+symptoms\s+worsen\b.*\bAMY\b.*\bmay\s+rise\s+above\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"^AST\b.*\bcould\s+be\s+elevated\b.*\bpossibly\b.*\bgiven\s+the\s+clinical\s+picture\b",
        re.IGNORECASE,
    ),
    re.compile(r"^(Vision\s+forward|EMIS|QOF)\b", re.IGNORECASE),
]

_REFERRAL_PROCEDURE_RE = re.compile(
    r"(?:\bfast\s*track\b|\b2ww\b|\btwo\s*week\s*wait\b|\burgent\b)?\s*"
    r"(?:\breferral\b|\breferred?\s+to\b)",
    re.IGNORECASE,
)


def filter_header_sentences(chunks: list["SentenceChunk"]) -> list["SentenceChunk"]:
    """Remove administrative header sentences from a sentence chunk list.

    Returns an empty list (not an exception) if all sentences are headers.
    Allowlist: chunks containing cancer pathway milestone phrases are always
    preserved regardless of surrounding header context.
    """
    return [
        c
        for c in chunks
        if not is_header_sentence(c.text) or _FAST_TRACK_MILESTONE_RE.search(c.text)
    ]


def is_non_evidence_line(text: str) -> bool:
    """Return True when a sentence looks like non-clinical template noise."""
    stripped = text.strip()
    if not stripped:
        return True
    if _FAST_TRACK_MILESTONE_RE.search(stripped):
        return False
    return any(pattern.match(stripped) for pattern in _NON_EVIDENCE_PATTERNS)


def is_referral_procedure_phrase(text: str) -> bool:
    """Return True when text describes a referral procedure phrase."""
    stripped = text.strip()
    if not stripped:
        return False
    return bool(_REFERRAL_PROCEDURE_RE.search(stripped))


SHORT_SENTENCE_THRESHOLD: int = 50
"""Sentences shorter than this (chars, stripped) are considered context-starved.

Both the inference service and the training candidate creation path use this
constant to decide when to widen the context window to include neighbouring
sentences, giving the transformer enough surrounding text to build useful
embeddings for very short clinical abbreviations (e.g. "SOB", "HTN").
Override via NER_SHORT_CONTEXT_THRESHOLD env-var at runtime.
"""


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


# DI-D3391745 (DO-1DB93C8E): only treat blank lines, sentence-terminating
# punctuation, and end-of-line semicolons as hard sentence boundaries.
# Single newlines are soft wraps (EHR line wrapping) and stay inside one
# SentenceChunk so downstream NER/post-processing can recognise lab
# observable + interpretation phrases that span line breaks.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n{2,}|(?<=;)[ \t]*\n")
_SOFT_WRAP_GAP_RE = re.compile(r"^[ \t]*\n[ \t]*$")
_SENTENCE_TERMINATOR_TAIL_RE = re.compile(r"""[.!?][\"')\]]?\s*$""")


def _rejoin_soft_wraps(
    text: str, chunks: list["SentenceChunk"]
) -> list["SentenceChunk"]:
    """Merge adjacent chunks separated only by a single newline (soft wrap).

    PyRuSH treats every newline as a hard sentence boundary, but EHR exports
    routinely wrap long lines (e.g. lab result lines) on single newlines. A
    chunk pair is merged when:
      - the gap between them contains exactly one '\\n' (no blank line), and
      - the leading chunk does not end with sentence-terminating punctuation.
    Blank-line separated paragraphs and full sentences are left untouched.
    """
    if len(chunks) <= 1:
        return chunks
    merged: list["SentenceChunk"] = []
    current = chunks[0]
    for nxt in chunks[1:]:
        gap = text[current.end : nxt.start]
        is_soft_wrap = (
            _SOFT_WRAP_GAP_RE.fullmatch(gap) is not None
            and _SENTENCE_TERMINATOR_TAIL_RE.search(current.text) is None
        )
        if is_soft_wrap:
            merged_text = text[current.start : nxt.end].strip()
            current = SentenceChunk(
                sentence_id=current.sentence_id,
                text=merged_text,
                start=current.start,
                end=nxt.end,
            )
        else:
            merged.append(current)
            current = nxt
    merged.append(current)
    return merged


def build_context_window(
    chunks: list[SentenceChunk],
    index: int,
    *,
    threshold: int = SHORT_SENTENCE_THRESHOLD,
    context_sents: int = 2,
) -> tuple[str, int]:
    """Return a context-enriched string for a potentially short sentence.

    When ``chunks[index].text`` is shorter than *threshold* characters, the
    function attaches up to *context_sents* neighbouring sentences on each
    side so the transformer has sufficient surrounding text.

    Returns ``(context_text, anchor_offset)`` where *anchor_offset* is the
    character position of the target sentence within *context_text*.  When no
    expansion is needed, *anchor_offset* is 0 and *context_text* equals the
    original sentence text.

    Each neighbour is deidentified separately before joining so that the
    per-piece offsets remain stable and predictable (deidentification can
    change string lengths).  Callers that need entity positions relative to the
    original encounter text should subtract *anchor_offset* from model-reported
    char positions after filtering to ``[anchor_offset, anchor_offset +
    len(target_text)]``.
    """
    target = chunks[index]
    if len(target.text.strip()) >= threshold:
        return target.text, 0

    parts: list[str] = []

    for j in range(max(0, index - context_sents), index):
        prev = chunks[j].text.strip()
        if prev:
            parts.append(prev)

    anchor_offset = sum(len(p) + 1 for p in parts)  # +1 per joining space
    parts.append(target.text.strip())

    for j in range(index + 1, min(len(chunks), index + context_sents + 1)):
        nxt = chunks[j].text.strip()
        if nxt:
            parts.append(nxt)

    return " ".join(parts), anchor_offset


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
            _suppress_pyrush_debug_noise()
            import spacy

            nlp = spacy.blank("en")
            from medspacy.sentence_splitting import PyRuSHSentencizer  # noqa: F401

            nlp.add_pipe("medspacy_pyrush")
            return nlp
        except Exception:
            logger.debug(
                "PyRuSH sentence splitter unavailable -- falling back to regex",
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
            return _rejoin_soft_wraps(text, chunks)
        return self._split_regex(text)

    def _split_pyrush(self, text: str) -> list[SentenceChunk]:
        doc = self._pyrush(text)
        chunks: list[SentenceChunk] = []
        for idx, sent in enumerate(doc.sents):
            t = sent.text.strip()
            if t:
                chunks.append(
                    SentenceChunk(
                        sentence_id=f"s{idx}",
                        text=t,
                        start=sent.start_char,
                        end=sent.end_char,
                    )
                )
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
            chunks.append(
                SentenceChunk(
                    sentence_id=f"s{idx}",
                    text=stripped,
                    start=start,
                    end=end,
                )
            )
            offset = end
        return chunks
