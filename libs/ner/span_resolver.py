"""Resolve absolute character spans for LLM-extracted clinical entities.

Atlas trace:
  DO: DO-CBDF8FBC
  DI: DI-A0C90595
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-CBDF8FBC")

The LLM extractor returns entity ``text`` verbatim from the source sentence but
does not return character offsets. Downstream post-processing (scope guard,
ConText, observable/value-unit linking, trend split) reads ``start``/``end``
offsets to compute sentence windows -- if they are missing or wrong every
window-based guard degrades.

``SpanResolver`` walks the extracted terms in order and produces absolute
offsets into the encounter text, preferring a match inside the term's tagged
sentence and falling back to an encounter-wide search that advances a cursor
to keep repeated mentions distinct.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Protocol


@dataclass
class _ResolvedSentence:
    sentence_id: str
    text: str
    start: int


class _SentenceLike(Protocol):
    sentence_id: str
    text: str
    start: int


def _index_sentences(
    sentences: Iterable[_SentenceLike],
) -> dict[str, _ResolvedSentence]:
    out: dict[str, _ResolvedSentence] = {}
    for sentence in sentences:
        sid = str(getattr(sentence, "sentence_id", "") or "")
        if not sid:
            continue
        out[sid] = _ResolvedSentence(
            sentence_id=sid,
            text=str(getattr(sentence, "text", "") or ""),
            start=int(getattr(sentence, "start", 0) or 0),
        )
    return out


@dataclass
class SpanResolver:
    """Resolve absolute encounter offsets for ordered LLM-extracted terms.

    Keeps per-sentence and encounter-wide cursors so that repeated mentions
    (e.g. the same abbreviation appearing twice in a sentence) do not collapse
    onto the same offset.
    """

    encounter_text: str
    _encounter_text_lower: str = field(init=False, repr=False)
    _sentences: dict[str, _ResolvedSentence] = field(default_factory=dict, init=False)
    _sentence_cursors: dict[str, int] = field(default_factory=dict, init=False)
    _encounter_cursor: int = field(default=0, init=False)

    def __init__(
        self,
        encounter_text: str,
        sentences: Iterable[_SentenceLike] | None = None,
    ) -> None:
        self.encounter_text = encounter_text or ""
        self._encounter_text_lower = self.encounter_text.lower()
        self._sentences = _index_sentences(sentences or [])
        self._sentence_cursors = {}
        self._encounter_cursor = 0

    def resolve(
        self, term_text: str, sentence_id: str | None = None
    ) -> tuple[int, int]:
        """Return absolute ``(start, end)`` offsets for ``term_text``.

        Falls back to ``(0, max(len(term_text), 1))`` only when no match is
        found anywhere in the encounter; this preserves backward-compatible
        behaviour for malformed extractor output while ensuring correct output
        in the common case.
        """
        term = (term_text or "").strip()
        fallback_len = max(len(term), 1)
        if not term:
            return 0, fallback_len

        sid = str(sentence_id or "")
        sentence = self._sentences.get(sid) if sid else None
        if sentence is not None:
            abs_span = self._match_in_sentence(sentence, term)
            if abs_span is not None:
                return abs_span
            return sentence.start, sentence.start + fallback_len

        encounter_span = self._match_in_encounter(term)
        if encounter_span is not None:
            return encounter_span
        return 0, fallback_len

    def _match_in_sentence(
        self, sentence: _ResolvedSentence, term: str
    ) -> tuple[int, int] | None:
        lower_sentence = sentence.text.lower()
        lower_term = term.lower()
        cursor = self._sentence_cursors.get(sentence.sentence_id, 0)
        idx = lower_sentence.find(lower_term, cursor)
        if idx < 0:
            idx = lower_sentence.find(lower_term)
        if idx < 0:
            return None
        self._sentence_cursors[sentence.sentence_id] = idx + len(term)
        abs_start = sentence.start + idx
        return abs_start, abs_start + len(term)

    def _match_in_encounter(self, term: str) -> tuple[int, int] | None:
        lower_term = term.lower()
        idx = self._encounter_text_lower.find(lower_term, self._encounter_cursor)
        if idx < 0:
            idx = self._encounter_text_lower.find(lower_term)
        if idx < 0:
            return None
        self._encounter_cursor = idx + len(term)
        return idx, idx + len(term)
