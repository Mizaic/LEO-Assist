"""Pipeline helpers for derived lab-result findings.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")
"""

from __future__ import annotations

import logging
import re
from typing import Any

from libs.lab_results.classifier import LabConfigError, classify_lab_result
from libs.pipeline.form_schema_seeding import is_taught_test_row

logger = logging.getLogger(__name__)

_OBSERVABLE_KINDS = frozenset({"observable_entity", "observable entity"})
_COMPARATOR_VALUE_RE = re.compile(r"([<>])\s*(\d+(?:\.\d+)?)")

# A reading such as "> 200" only bounds the true value, so it supports a
# finding only when every value past the bound would be classed the same.
_CLASSES_SURE_PAST_BOUND = {
    ">": frozenset({"high", "critically_high"}),
    "<": frozenset({"low", "critically_low"}),
}


def _entity_kind(entity: dict[str, Any]) -> str:
    # A taught test row's label is the printed row text, not an entity type.
    if is_taught_test_row(entity):
        return str(entity.get("semantic_tag") or "")
    return str(entity.get("label") or entity.get("semantic_tag") or "")


def _parse_reading(raw: Any) -> tuple[str, float] | None:
    """Return ``(comparator, value)``; the comparator is "" for a plain number."""
    try:
        return "", float(raw)
    except (TypeError, ValueError):
        pass
    match = _COMPARATOR_VALUE_RE.fullmatch(str(raw or "").strip())
    if match is None:
        return None
    return match.group(1), float(match.group(2))


def _lab_reading(entity: dict[str, Any]) -> dict[str, Any] | None:
    """Return the coded reading of an observable fact, or None."""
    if _entity_kind(entity) not in _OBSERVABLE_KINDS:
        return None
    concept_id = str(entity.get("concept_id") or entity.get("snomed_concept_id") or "")
    if not concept_id:
        return None
    reading = _parse_reading(entity.get("value"))
    if reading is None:
        return None
    comparator, value = reading
    return {
        "observable_id": concept_id,
        "comparator": comparator,
        "value": value,
        "unit": str(entity.get("unit") or ""),
    }


def observation_from_entity(entity: dict[str, Any]) -> dict[str, Any] | None:
    """Build a guideline observation row from one resolved observable entity.

    A reading with a comparator is left out: guideline rules compare exact
    values, and "> 200" is not the value 200.
    """
    reading = _lab_reading(entity)
    if reading is None or reading["comparator"]:
        return None
    observed_at = (
        entity.get("observed_at") or entity.get("date") or entity.get("encounter_date")
    )
    row = {
        "observable_id": reading["observable_id"],
        "value": reading["value"],
        "unit": reading["unit"],
    }
    if observed_at:
        row["observed_at"] = str(observed_at)
    return row


def observations_from_entities(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [observation_from_entity(entity) for entity in entities]
    return [row for row in rows if row is not None]


def enrich_lab_result_findings(
    entities: list[dict[str, Any]],
    *,
    patient_sex: str | None,
    patient_age: float | None,
    org_id: str | None = None,
) -> list[dict[str, Any]]:
    """Append configured abnormal-result finding entities after coding."""
    enriched = list(entities)
    for entity in entities:
        derived = _derived_finding(
            entity,
            patient_sex=patient_sex,
            patient_age=patient_age,
            org_id=org_id,
        )
        if derived is not None:
            enriched.append(derived)
    return enriched


def _derived_finding(
    entity: dict[str, Any],
    *,
    patient_sex: str | None,
    patient_age: float | None,
    org_id: str | None = None,
) -> dict[str, Any] | None:
    observation = _lab_reading(entity)
    if observation is None:
        return None
    try:
        result = classify_lab_result(
            observation["observable_id"],
            observation["value"],
            observation["unit"],
            patient_sex=patient_sex,
            patient_age=patient_age,
            org_id=org_id,
        )
    except LabConfigError as exc:
        logger.info("Lab result not classified for derived finding: %s", exc)
        return None
    if not result.interpretation_concept_id:
        return None
    comparator = observation["comparator"]
    if comparator and result.classification not in _CLASSES_SURE_PAST_BOUND.get(
        comparator, frozenset()
    ):
        return None
    text = (
        result.interpretation_term or f"{result.display_name} {result.classification}"
    )
    return {
        "text": text,
        "label": "finding",
        "semantic_tag": "finding",
        "concept_id": result.interpretation_concept_id,
        "term": result.interpretation_term or text,
        "score": 1.0,
        "assertion": "present",
        "lab_result_derived": True,
        "source_observable_id": observation["observable_id"],
        "source_observable_text": entity.get("text") or entity.get("term") or "",
        "classification": result.classification,
        "value": result.canonical_value,
        "value_comparator": comparator or None,
        "unit": result.canonical_unit,
        "reference_range": {
            "low": result.reference_range.low if result.reference_range else None,
            "high": result.reference_range.high if result.reference_range else None,
            "range_id": (
                result.reference_range.range_id if result.reference_range else None
            ),
            "org_id": (result.reference_range.org_id if result.reference_range else ""),
        },
    }
