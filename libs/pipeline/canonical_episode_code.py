"""Canonical episode-level SNOMED code derivation.

Atlas trace:
  DI: DI-885930F8 (Each EpisodeOfCare gets a canonical episode-level code)

Given the per-encounter coded entities for an EpisodeOfCare, derive a
single canonical code that represents the episode as a whole. The rule
is:

1. Among ``confirmed`` codes for the episode's site, pick the most
   specific (longest concept_id; ties broken by highest count then by
   earliest first-occurrence date).
2. If no confirmed codes exist, pick the highest-confidence
   ``suspected`` code on the same site.
3. If neither, the episode has no canonical code yet.

The output is structured so the persistence layer can write it to the
``EpisodeCanonicalCode`` graph node with full provenance:

    (concept_id, display_name, intent, modifiers[], confidence,
     derivation_trace[])
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from libs.pipeline_graph.subgraphs.coding_qa import CodedEntityRecord


@dataclass(frozen=True)
class CanonicalEpisodeCode:
    concept_id: str
    display_name: str
    intent: str  # confirmed | suspected
    modifiers: tuple[str, ...] = ()
    confidence: float = 0.0
    derivation_trace: tuple[str, ...] = ()


@dataclass
class _Score:
    concept_id: str
    display_name: str
    intent: str
    count: int = 0
    first_seen: date | None = None
    confidence_sum: float = 0.0
    encounter_ids: list[str] = field(default_factory=list)


def _aggregate(records: list[CodedEntityRecord]) -> dict[str, _Score]:
    by_concept: dict[str, _Score] = {}
    for rec in records:
        score = by_concept.setdefault(
            rec.concept_id,
            _Score(
                concept_id=rec.concept_id,
                display_name=rec.display_name or rec.concept_id,
                intent=rec.intent,
            ),
        )
        score.count += 1
        score.confidence_sum += 1.0 if rec.intent == "confirmed" else 0.6
        score.encounter_ids.append(rec.encounter_id)
        if score.first_seen is None or rec.occurred_on < score.first_seen:
            score.first_seen = rec.occurred_on
    return by_concept


def _pick_best(
    candidates: list[_Score],
) -> _Score | None:
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda s: (
            -len(s.concept_id),
            -s.count,
            s.first_seen or date.max,
        ),
    )[0]


def derive_canonical_code(
    records: list[CodedEntityRecord],
    *,
    suspected_site: str,
) -> CanonicalEpisodeCode | None:
    """Return the canonical episode code, or None if it cannot be derived."""
    if not records:
        return None

    on_site = [r for r in records if r.site_key == suspected_site]
    if not on_site:
        return None

    confirmed = [r for r in on_site if r.intent == "confirmed"]
    suspected = [r for r in on_site if r.intent == "suspected"]

    pool = confirmed if confirmed else suspected
    if not pool:
        return None

    aggregated = _aggregate(pool)
    best = _pick_best(list(aggregated.values()))
    if best is None:
        return None

    intent = "confirmed" if confirmed else "suspected"
    confidence = (
        best.confidence_sum / max(1, best.count)
    )
    most_common = Counter(r.role for r in pool).most_common(1)
    modifiers = tuple(sorted({m for m in (most_common[0][0],) if m}))
    trace = tuple(
        f"{eid}::{best.concept_id}" for eid in best.encounter_ids
    )

    return CanonicalEpisodeCode(
        concept_id=best.concept_id,
        display_name=best.display_name,
        intent=intent,
        modifiers=modifiers,
        confidence=round(confidence, 3),
        derivation_trace=trace,
    )
