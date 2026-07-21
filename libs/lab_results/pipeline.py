"""Pipeline helpers for derived lab-result findings.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any

from libs.lab_results.classifier import LabConfigError, classify_lab_result

logger = logging.getLogger(__name__)


def observation_from_entity(entity: dict[str, Any]) -> dict[str, Any] | None:
    """Build a guideline observation row from one resolved observable entity."""
    if str(entity.get("label") or entity.get("semantic_tag") or "") not in {
        "observable_entity",
        "observable entity",
    }:
        return None
    concept_id = str(entity.get("concept_id") or entity.get("snomed_concept_id") or "")
    if not concept_id or entity.get("value") is None:
        return None
    try:
        value = float(entity.get("value"))
    except (TypeError, ValueError):
        return None
    observed_at = (
        entity.get("observed_at")
        or entity.get("date")
        or entity.get("encounter_date")
        or datetime.now(timezone.utc).isoformat()
    )
    return {
        "observable_id": concept_id,
        "value": value,
        "unit": str(entity.get("unit") or ""),
        "observed_at": str(observed_at),
    }


def observations_from_entities(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [observation_from_entity(entity) for entity in entities]
    return [row for row in rows if row is not None]


def enrich_lab_result_findings(
    entities: list[dict[str, Any]],
    *,
    patient_sex: str | None,
    patient_age: float | None,
) -> list[dict[str, Any]]:
    """Append configured abnormal-result finding entities after coding."""
    enriched = list(entities)
    for entity in entities:
        derived = _derived_finding(
            entity, patient_sex=patient_sex, patient_age=patient_age
        )
        if derived is not None:
            enriched.append(derived)
    return enriched


def _derived_finding(
    entity: dict[str, Any],
    *,
    patient_sex: str | None,
    patient_age: float | None,
) -> dict[str, Any] | None:
    observation = observation_from_entity(entity)
    if observation is None:
        return None
    try:
        result = classify_lab_result(
            observation["observable_id"],
            observation["value"],
            observation["unit"],
            patient_sex=patient_sex,
            patient_age=patient_age,
        )
    except LabConfigError as exc:
        logger.info("Lab result not classified for derived finding: %s", exc)
        return None
    if result.classification == "normal" or not result.interpretation_concept_id:
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
        "unit": result.canonical_unit,
        "reference_range": {
            "low": result.reference_range.low if result.reference_range else None,
            "high": result.reference_range.high if result.reference_range else None,
            "range_id": (
                result.reference_range.range_id if result.reference_range else None
            ),
        },
    }
