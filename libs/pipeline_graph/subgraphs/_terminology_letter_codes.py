"""Terminology-step rules for facts whose code comes from the letter itself.

A taught test row carries the code its form teacher chose, and a
lab-derived finding carries the code the lab config gives its reading.
Neither needed a lookup, so a looked-up copy of the same code must not
replace them, and a failed lab lookup must not pass as "no finding".

Atlas trace:
  DO: DO-572A5C05 (terminology subgraph), DO-AA3B7FCC (lab findings)
  DI: DI-5C9CA57B, DI-9456E5BE, DI-B7A69F26 (fail-closed boundary)
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from libs.lab_results.classifier import LabConfigUnavailable
from libs.lab_results.pipeline import enrich_lab_result_findings
from libs.pipeline.form_checkbox_seed import is_taught_checkbox
from libs.pipeline.form_schema_seeding import carries_taught_test_row_code

logger = logging.getLogger(__name__)


def dedup_by_concept_id(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove duplicate resolved entities that share a concept_id and assertion.

    Multi-classification produces distinct (surface_form, entity_type) pairs
    that should resolve to different concepts.  Any that collide -- same
    concept_id returned for different entity types -- are deduplicated by
    keeping the highest-scoring candidate so the graph MERGE produces one
    :DOCUMENTS link rather than a phantom duplicate. A fact whose code
    came from the letter beats a looked-up copy whatever its score.

    The graph keys :DOCUMENTS on code and assertion, so copies that differ
    in assertion are both kept: an absent copy must never erase a present
    finding, and the conflict stays visible to the reviewer.

    Unresolved entities (terminology_unresolved=True or no concept_id) are
    always kept regardless.
    """
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    kept: list[dict[str, Any]] = []
    for ent in entities:
        if is_taught_checkbox(ent):
            kept.append(ent)
            continue
        concept_id = str(ent.get("concept_id") or "").strip()
        if not concept_id or ent.get("terminology_unresolved"):
            kept.append(ent)
            continue
        key = (concept_id, _persisted_assertion(ent))
        existing = seen.get(key)
        if existing is None:
            seen[key] = ent
            kept.append(ent)
        elif _wins_same_code(ent, existing):
            kept.remove(existing)
            seen[key] = ent
            kept.append(ent)
    return kept


def _persisted_assertion(entity: dict[str, Any]) -> str:
    """The assertion persist writes: a missing one is stored as present."""
    return str(entity.get("assertion") or "present").strip().lower()


def _code_from_the_letter(entity: dict[str, Any]) -> bool:
    """A taught test row or a lab-derived finding: its code needed no lookup."""
    return carries_taught_test_row_code(entity) or bool(
        entity.get("lab_result_derived")
    )


def _wins_same_code(entity: dict[str, Any], existing: dict[str, Any]) -> bool:
    """Keep the copy that carries the letter's own code and reading.

    A taught row or a derived finding holds the value and comparator; a
    looked-up copy of the same code may not, and its score only says how
    well the lookup went.
    """
    own, theirs = _code_from_the_letter(entity), _code_from_the_letter(existing)
    if own != theirs:
        return own
    return float(entity.get("score") or 0) > float(existing.get("score") or 0)


def drop_copies_of_taught_rows(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop looked-up facts that repeat a taught test row's code.

    Runs before the lab step, so a copy whose reading lost its comparator
    ("200" for "> 200") cannot make a finding of its own. Taught ticks
    are left alone, as in :func:`dedup_by_concept_id`.
    """
    taught = {
        str(e.get("concept_id")).strip()
        for e in entities
        if carries_taught_test_row_code(e)
    }
    if not taught:
        return entities
    return [
        e
        for e in entities
        if carries_taught_test_row_code(e)
        or is_taught_checkbox(e)
        or str(e.get("concept_id") or "").strip() not in taught
    ]


def with_lab_findings(
    entities: list[dict[str, Any]],
    state: Mapping[str, Any],
    warnings: list[str],
) -> tuple[list[dict[str, Any]], bool]:
    """Add lab-derived findings; return the facts and whether the run degrades.

    If the lab settings cannot be loaded, no result was checked against its
    range, so the run goes to a person (fail-closed-boundary.mdc rule 1).
    """
    kept = drop_copies_of_taught_rows(entities)
    try:
        enriched = enrich_lab_result_findings(
            kept,
            patient_sex=state.get("patient_sex"),
            patient_age=state.get("patient_age"),
            org_id=state.get("org_id"),
        )
    except LabConfigUnavailable as exc:
        logger.error("Lab result findings skipped: %s", exc)
        warnings.append(
            "lab_result_lookup_failed: we could not load the lab result "
            "settings, so no test result was checked against its normal "
            "range. Someone needs to check this referral."
        )
        return kept, True
    return enriched, False


__all__ = [
    "dedup_by_concept_id",
    "drop_copies_of_taught_rows",
    "with_lab_findings",
]
