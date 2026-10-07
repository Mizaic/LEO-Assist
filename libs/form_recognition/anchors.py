"""Anchors: the headings and options a taught form says it contains.

Each section gives one anchor (its label and start pattern) and each item
gives one anchor (its pattern and entity text). An item whose pattern is
too short to search for ("B1.") gives no anchor: its entity text is a
coded meaning, not words printed on the form. An anchor is found when
any of its alternative texts is in the document. Anchors shared by many
taught forms, such as "Patient Details", weigh less than anchors unique
to one form (inverse document frequency across the taught forms).

Atlas trace: DI-E21DF9EF -> DO-E458EEC5.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Iterable, Literal

from libs.form_recognition.normalise import normalise_text
from libs.form_recognition.settings import ITEM_WEIGHT, SECTION_WEIGHT
from libs.pipeline.form_schema_normalizer import FormSchema

AnchorKind = Literal["section", "item"]

_REGEX_SYNTAX_RE = re.compile(r"\(\?[a-zA-Z]+\)|\\[sSbBdDwW][*+?]?|\\\||[\^$]")
_ESCAPE_RE = re.compile(r"\\(.)")
_MIN_ALT_CHARS = 4
_MIN_WORD_CHARS = 3


@dataclass(frozen=True)
class Anchor:
    """One heading or option of a taught form."""

    key: str
    kind: AnchorKind
    label: str
    alternatives: tuple[str, ...]
    order: int
    weight: float = 1.0


@dataclass(frozen=True)
class CompiledSchema:
    """A taught form reduced to weighted anchors."""

    schema: FormSchema
    anchors: tuple[Anchor, ...]

    @property
    def fingerprint(self) -> str:
        return self.schema.fingerprint


def pattern_text(pattern: str) -> str:
    """Strip regex syntax from a taught pattern, leaving its words."""
    text = _REGEX_SYNTAX_RE.sub(" ", pattern or "")
    text = _ESCAPE_RE.sub(r"\1", text)
    return re.sub(r"[()\[\]{}|*+?.]", " ", text)


def _usable(norm: str) -> bool:
    if len(norm) < _MIN_ALT_CHARS:
        return False
    return any(len(word) >= _MIN_WORD_CHARS for word in norm.split())


def _alternatives(texts: Iterable[str]) -> tuple[str, ...]:
    seen: list[str] = []
    for text in texts:
        norm = normalise_text(text)
        if _usable(norm) and norm not in seen:
            seen.append(norm)
    return tuple(seen)


def _raw_anchors(schema: FormSchema) -> list[Anchor]:
    anchors: list[Anchor] = []
    for order, section in enumerate(schema.sections):
        alts = _alternatives([section.label, pattern_text(section.start_pattern)])
        if alts:
            key = section.section_id
            anchors.append(Anchor(key, "section", section.label, alts, order))
        for index, item in enumerate(section.items):
            if not _alternatives([pattern_text(item.pattern)]):
                continue
            alts = _alternatives([pattern_text(item.pattern), item.entity_text])
            if alts:
                key = f"{section.section_id}/{index}"
                anchors.append(Anchor(key, "item", item.entity_text, alts, order))
    return _dedupe(anchors)


def _dedupe(anchors: list[Anchor]) -> list[Anchor]:
    kept: list[Anchor] = []
    seen: set[str] = set()
    for anchor in anchors:
        if seen.intersection(anchor.alternatives):
            continue
        seen.update(anchor.alternatives)
        kept.append(anchor)
    return kept


def _weighted(anchor: Anchor, df: int, total: int) -> Anchor:
    kind_weight = SECTION_WEIGHT if anchor.kind == "section" else ITEM_WEIGHT
    weight = kind_weight * math.log(1.0 + total / max(df, 1))
    return Anchor(
        anchor.key,
        anchor.kind,
        anchor.label,
        anchor.alternatives,
        anchor.order,
        weight,
    )


def compile_schemas(schemas: Iterable[FormSchema]) -> list[CompiledSchema]:
    """Turn taught forms into weighted anchors; raises on a malformed form."""
    raw = [(schema, _raw_anchors(schema)) for schema in schemas]
    alt_sets = [
        {a for anchor in anchors for a in anchor.alternatives} for _, anchors in raw
    ]
    total = len(raw)
    compiled: list[CompiledSchema] = []
    for schema, anchors in raw:
        weighted = tuple(
            _weighted(
                anchor,
                sum(1 for alts in alt_sets if alts.intersection(anchor.alternatives)),
                total,
            )
            for anchor in anchors
        )
        compiled.append(CompiledSchema(schema, weighted))
    return compiled
