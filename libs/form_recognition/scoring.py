"""Score one document against one taught form.

Four numbers, all from 0 to 1:

- recall: the weighted share of the form's anchors found in the document
  (rapidfuzz partial alignment, or an exact phrase for short anchors);
- precision: the share of the document's section headings and tick-box
  options that the form explains (1.0 when the document has none);
- order: how closely the found sections follow the taught order
  (difflib SequenceMatcher);
- option_coverage: the share of the form's taught options found, so a
  same-trust form that shares the headings but not the criteria fails.

Atlas trace: DI-E21DF9EF -> DO-E458EEC5.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from rapidfuzz import fuzz, process

from libs.form_recognition.anchors import CompiledSchema
from libs.form_recognition.normalise import normalise_text, segments
from libs.form_recognition.settings import (
    FUZZY_CUTOFF,
    SHORT_ALT_MAX_CHARS,
    SHORT_ALT_MAX_WORDS,
)


def is_short(text: str) -> bool:
    """Short phrases need an exact match; one letter changes their meaning."""
    return len(text.split()) <= SHORT_ALT_MAX_WORDS or len(text) < SHORT_ALT_MAX_CHARS


def _contains(haystack: str, needle: str) -> bool:
    return f" {needle} " in f" {haystack} "


class DocumentView:
    """A document normalised once, with a cache of anchor positions."""

    def __init__(self, text: str) -> None:
        self.norm = normalise_text(text)
        self._padded = f" {self.norm} "
        clinical = [s.words for s in segments(text) if s.is_clinical_structure()]
        self.clinical = tuple(dict.fromkeys(clinical))
        self._positions: dict[str, int | None] = {}

    def find(self, alt: str) -> int | None:
        """Return where *alt* sits in the document, or None if absent."""
        if alt not in self._positions:
            self._positions[alt] = self._locate(alt)
        return self._positions[alt]

    def _locate(self, alt: str) -> int | None:
        if is_short(alt):
            index = self._padded.find(f" {alt} ")
            return index if index >= 0 else None
        hit = fuzz.partial_ratio_alignment(alt, self.norm, score_cutoff=FUZZY_CUTOFF)
        return None if hit is None else hit.dest_start


@dataclass(frozen=True)
class Score:
    """How well one taught form explains one document."""

    fingerprint: str
    form_name: str
    recall: float
    precision: float
    order: float
    option_coverage: float
    matched: tuple[str, ...]
    missing: tuple[str, ...]
    unexplained: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "fingerprint": self.fingerprint,
            "form_name": self.form_name,
            "recall": round(self.recall, 3),
            "precision": round(self.precision, 3),
            "order": round(self.order, 3),
            "option_coverage": round(self.option_coverage, 3),
            "matched_count": len(self.matched),
            "missing_count": len(self.missing),
            "matched": list(self.matched),
            "missing": list(self.missing),
            "unexplained": list(self.unexplained),
        }


def _explains(segment: str, short_alts: list[str], long_alts: list[str]) -> bool:
    if any(_contains(segment, alt) for alt in short_alts):
        return True
    if is_short(segment):
        return any(_contains(alt, segment) for alt in long_alts)
    best = process.extractOne(
        segment, long_alts, scorer=fuzz.partial_ratio, score_cutoff=FUZZY_CUTOFF
    )
    return best is not None


def _unexplained(view: DocumentView, compiled: CompiledSchema) -> tuple[str, ...]:
    alts = [alt for anchor in compiled.anchors for alt in anchor.alternatives]
    short_alts = [alt for alt in alts if is_short(alt)]
    long_alts = [alt for alt in alts if not is_short(alt)]
    return tuple(
        seg for seg in view.clinical if not _explains(seg, short_alts, long_alts)
    )


def _order(found_sections: list[tuple[int, int]]) -> float:
    if len(found_sections) < 2:
        return 1.0
    taught = sorted(order for _, order in found_sections)
    seen = [order for _, order in sorted(found_sections)]
    return SequenceMatcher(None, taught, seen, autojunk=False).ratio()


def _coverage(found: dict[str, bool], compiled: CompiledSchema) -> float:
    items = [found[a.key] for a in compiled.anchors if a.kind == "item"]
    return sum(items) / len(items) if items else 1.0


def score_schema(view: DocumentView, compiled: CompiledSchema) -> Score:
    """Score *view* against one compiled taught form."""
    found: dict[str, bool] = {}
    sections: list[tuple[int, int]] = []
    for anchor in compiled.anchors:
        positions = [p for p in map(view.find, anchor.alternatives) if p is not None]
        found[anchor.key] = bool(positions)
        if positions and anchor.kind == "section":
            sections.append((min(positions), anchor.order))
    total = sum(anchor.weight for anchor in compiled.anchors)
    hit_weight = sum(a.weight for a in compiled.anchors if found[a.key])
    unexplained = _unexplained(view, compiled)
    explained = len(view.clinical) - len(unexplained)
    return Score(
        fingerprint=compiled.fingerprint,
        form_name=compiled.schema.form_name,
        recall=hit_weight / total if total else 0.0,
        precision=explained / len(view.clinical) if view.clinical else 1.0,
        order=_order(sections),
        option_coverage=_coverage(found, compiled),
        matched=tuple(a.label for a in compiled.anchors if found[a.key]),
        missing=tuple(a.label for a in compiled.anchors if not found[a.key]),
        unexplained=unexplained,
    )
