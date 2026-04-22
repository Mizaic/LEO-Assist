"""Cross-encounter QA for episode-aware coding.

Atlas trace:
  DI: DI-E8FE404D
  Mitigates: R-D4BE025E (narrative incoherence in coding)

Inspects every coded entity inside an episode bundle and emits
``EpisodeCodingQAFlag`` items for:

- **Trajectory inversion**: a "confirmed" code earlier in the episode
  followed by a "suspected" code on the same site without a documented
  re-presentation.
- **Code contradiction**: two codes inside the same episode that map to
  conflicting clinical states (e.g. DCIS + benign breast disease) where
  no rule-out is recorded.
- **Site mismatch**: a coded entity for a site that disagrees with the
  episode's ``suspected_site``.

The module is intentionally pure: callers (langgraph subgraph or
pipeline_worker) hand it a `CodedEntityRecord` list and the episode
metadata; it returns a list of `CodingQAFlag` dataclasses. Persistence
is handled separately (see ``libs/cypher/episode_coding_queries.py``).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Sequence

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CodedEntityRecord:
    """One coded entity from one encounter in an episode bundle."""

    encounter_id: str
    occurred_on: date
    concept_id: str
    display_name: str
    site_key: str  # canonical site or "unknown"
    intent: str  # confirmed | suspected | ruled_out | unspecified
    role: str = ""  # diagnosis | investigation | treatment | outcome


@dataclass(frozen=True)
class EpisodeMeta:
    """Episode envelope for QA."""

    episode_id: str
    suspected_site: str
    intent: str  # confirmed | suspected | ruled_out


@dataclass(frozen=True)
class CodingQAFlag:
    """One issue surfaced by cross-encounter QA."""

    code: str  # "trajectory_inversion" | "code_contradiction" | "site_mismatch"
    severity: str  # "low" | "medium" | "high"
    summary: str
    encounter_ids: tuple[str, ...]
    citation: str = ""


# Pairs of (concept_a, concept_b) that should never co-exist in one
# episode without an intervening rule_out. The set is intentionally
# small; v2 minor releases can grow it from labelled corrections.
_CONTRADICTORY_PAIRS: dict[frozenset[str], str] = {
    # DCIS vs benign breast disease
    frozenset({"109888004", "266569009"}): "dcis_vs_benign_breast",
    # Malignant neoplasm of breast vs benign breast disease
    frozenset({"254837009", "266569009"}): "malignant_vs_benign_breast",
}


def _detect_trajectory_inversions(
    records: Sequence[CodedEntityRecord],
) -> list[CodingQAFlag]:
    """Confirmed -> suspected on the same site without re-presentation."""
    by_site: dict[str, list[CodedEntityRecord]] = defaultdict(list)
    for rec in records:
        if rec.site_key:
            by_site[rec.site_key].append(rec)
    flags: list[CodingQAFlag] = []
    for site_key, items in by_site.items():
        ordered = sorted(items, key=lambda r: (r.occurred_on, r.encounter_id))
        seen_confirmed = False
        confirmed_at: tuple[date, str] | None = None
        for rec in ordered:
            if rec.intent == "confirmed":
                seen_confirmed = True
                confirmed_at = (rec.occurred_on, rec.encounter_id)
            elif rec.intent == "suspected" and seen_confirmed:
                if confirmed_at is not None and rec.occurred_on >= confirmed_at[0]:
                    flags.append(
                        CodingQAFlag(
                            code="trajectory_inversion",
                            severity="medium",
                            summary=(
                                f"{site_key}: 'suspected' coding on "
                                f"{rec.occurred_on.isoformat()} after "
                                f"'confirmed' on "
                                f"{confirmed_at[0].isoformat()} without "
                                f"a documented re-presentation."
                            ),
                            encounter_ids=(confirmed_at[1], rec.encounter_id),
                            citation=f"site={site_key} concept={rec.concept_id}",
                        )
                    )
    return flags


def _detect_code_contradictions(
    records: Sequence[CodedEntityRecord],
) -> list[CodingQAFlag]:
    """Two codes that map to a contradictory pair without a rule_out."""
    concepts_present = {rec.concept_id for rec in records if rec.intent != "ruled_out"}
    flags: list[CodingQAFlag] = []
    for pair, label in _CONTRADICTORY_PAIRS.items():
        if pair.issubset(concepts_present):
            ruled_out = any(
                rec.intent == "ruled_out" and rec.concept_id in pair for rec in records
            )
            if ruled_out:
                continue
            encounter_ids = tuple(
                rec.encounter_id for rec in records if rec.concept_id in pair
            )
            flags.append(
                CodingQAFlag(
                    code="code_contradiction",
                    severity="high",
                    summary=(
                        f"Episode contains contradictory codes ({label}); "
                        "no rule-out recorded."
                    ),
                    encounter_ids=tuple(sorted(set(encounter_ids))),
                    citation=";".join(sorted(pair)),
                )
            )
    return flags


def _detect_site_mismatches(
    records: Sequence[CodedEntityRecord],
    *,
    expected_site: str,
) -> list[CodingQAFlag]:
    if not expected_site:
        return []
    flags: list[CodingQAFlag] = []
    for rec in records:
        if rec.site_key and rec.site_key != "unknown" and rec.site_key != expected_site:
            flags.append(
                CodingQAFlag(
                    code="site_mismatch",
                    severity="medium",
                    summary=(
                        f"Coded entity site '{rec.site_key}' does not match "
                        f"episode suspected_site '{expected_site}'."
                    ),
                    encounter_ids=(rec.encounter_id,),
                    citation=f"concept={rec.concept_id}",
                )
            )
    return flags


def run_cross_encounter_qa(
    records: Iterable[CodedEntityRecord],
    *,
    episode: EpisodeMeta,
) -> list[CodingQAFlag]:
    """Top-level entry: returns all QA flags for the episode bundle."""
    record_list = list(records)
    if not record_list:
        return []
    flags: list[CodingQAFlag] = []
    flags.extend(_detect_trajectory_inversions(record_list))
    flags.extend(_detect_code_contradictions(record_list))
    flags.extend(
        _detect_site_mismatches(record_list, expected_site=episode.suspected_site)
    )
    return flags
