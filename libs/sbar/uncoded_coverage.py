"""Uncoded-sentence coverage analyser with salvage policy (A3.4)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from libs.nlp.sentence_splitter import SentenceSplitter

_QUALIFIER_RE = re.compile(
    r"\b("
    r"for|since|over|past|last|duration|weeks?|months?|years?|days?|"
    r"progressive|worsening|persistent|recurrent|intermittent|"
    r"unexplained|recent|ongoing"
    r")\b",
    re.IGNORECASE,
)

_FILLER_RE = re.compile(
    r"^(dear colleague|yours sincerely|regards|re:|cc:|enc\.|"
    r"patient details|nhs number|date of birth|dob)[\s:,.-]*",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ChunkText:
    chunk_id: str
    text: str


@dataclass(frozen=True)
class CodeEvidenceSpan:
    chunk_id: str
    sentence_index: int | None
    evidence_start: int | None
    evidence_end: int | None


@dataclass(frozen=True)
class SalvageSentence:
    chunk_id: str
    sentence_index: int
    text: str
    reason: str


@dataclass
class CoverageReport:
    total_sentences: int = 0
    covered_sentences: int = 0
    uncovered_sentences: int = 0
    omitted_filler: int = 0
    salvage_sentences: list[SalvageSentence] = field(default_factory=list)
    omitted_uncoded: int = 0


def analyse_uncoded_coverage(
    chunks: list[ChunkText],
    spans: list[CodeEvidenceSpan],
    *,
    salvage_policy: dict[str, Any] | None = None,
) -> CoverageReport:
    """Identify uncovered sentences and apply the versioned salvage policy."""
    policy = salvage_policy or {}
    max_sentences = int(policy.get("maxSentences") or 50)
    include_qualifiers = bool(policy.get("includeQualifiers", True))

    splitter = SentenceSplitter()
    report = CoverageReport()
    salvaged = 0

    for chunk in chunks:
        text = str(chunk.text or "")
        if not text.strip():
            continue
        sentences = splitter.split(text)
        covered_indices = _covered_sentence_indices(chunk.chunk_id, sentences, spans)
        for idx, sentence in enumerate(sentences):
            report.total_sentences += 1
            if idx in covered_indices:
                report.covered_sentences += 1
                continue
            report.uncovered_sentences += 1
            sentence_text = str(sentence.text or "").strip()
            if not sentence_text:
                continue
            if _FILLER_RE.match(sentence_text):
                report.omitted_filler += 1
                continue
            if not include_qualifiers or not _QUALIFIER_RE.search(sentence_text):
                report.omitted_uncoded += 1
                continue
            if salvaged >= max_sentences:
                report.omitted_uncoded += 1
                continue
            report.salvage_sentences.append(
                SalvageSentence(
                    chunk_id=chunk.chunk_id,
                    sentence_index=idx,
                    text=sentence_text,
                    reason="uncoded_qualifier",
                )
            )
            salvaged += 1
    return report


def _covered_sentence_indices(
    chunk_id: str,
    sentences: list[Any],
    spans: list[CodeEvidenceSpan],
) -> set[int]:
    covered: set[int] = set()
    chunk_spans = [s for s in spans if s.chunk_id == chunk_id]
    for span in chunk_spans:
        if span.sentence_index is not None:
            covered.add(int(span.sentence_index))
            continue
        if span.evidence_start is None or span.evidence_end is None:
            continue
        start = int(span.evidence_start)
        end = int(span.evidence_end)
        for idx, sentence in enumerate(sentences):
            s_start = int(getattr(sentence, "start", 0) or 0)
            s_end = int(getattr(sentence, "end", s_start) or s_start)
            if start < s_end and end > s_start:
                covered.add(idx)
    return covered
