"""Shared lab result classifier backed by Knowledge Graph metadata.

Atlas trace:
  UN: UN-1DCDA92F
  DI: DI-6BA67DFF
  DO: DO-F34C6679
  Risk: R-77E35839
  VT: VT-6A6C90E0
  UN: UN-15EEDC06
  DI: DI-6EFB48AB
  DO: DO-669C4B13
  Risk: R-B8C4F461
  VT: VT-F4377BA4
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import math
from typing import Any

from libs.cypher.lab_result_config_queries import GET_LAB_RESULT_CONFIG
from libs.lab_results.concept_aliases import resolve_lab_config_concept_id
from libs.lab_results.range_select import LabReferenceRange, select_reference_range
from libs.neo4j_client.client import KnowledgeGraphClient

logger = logging.getLogger(__name__)


class LabConfigError(RuntimeError):
    """Raised when a lab result cannot be classified safely."""


@dataclass(frozen=True)
class UnitConversion:
    unit: str
    factor: float
    offset: float = 0.0


@dataclass(frozen=True)
class LabConfig:
    concept_id: str
    display_name: str
    canonical_unit: str
    conversions: dict[str, UnitConversion]
    reference_ranges: tuple[LabReferenceRange, ...]
    interpretations: dict[str, dict[str, str]]
    source: str = "manual"


@dataclass(frozen=True)
class LabClassification:
    concept_id: str
    display_name: str
    classification: str
    canonical_value: float
    canonical_unit: str
    reference_range: LabReferenceRange | None
    interpretation_concept_id: str | None
    interpretation_term: str | None


_CONFIG_CACHE: dict[tuple[str, str], LabConfig | None] = {}


def get_lab_config(
    concept_id: str,
    *,
    session: Any | None = None,
    use_cache: bool = True,
    org_id: str | None = None,
) -> LabConfig | None:
    """Load one observable's lab metadata from the Knowledge Graph."""
    requested = str(concept_id or "").strip()
    if not requested:
        return None
    org = str(org_id or "").strip()
    key = resolve_lab_config_concept_id(requested)
    cache_key = (requested, org)
    if use_cache and session is None and cache_key in _CONFIG_CACHE:
        return _CONFIG_CACHE[cache_key]
    row = _fetch_config_row(key, session=session, org_id=org)
    if row is None and key != requested:
        row = _fetch_config_row(requested, session=session, org_id=org)
    config = _row_to_config(row) if row else None
    if use_cache and session is None:
        _CONFIG_CACHE[cache_key] = config
        if key != requested:
            _CONFIG_CACHE[(key, org)] = config
    return config


def has_lab_config(
    concept_id: str,
    *,
    session: Any | None = None,
    org_id: str | None = None,
) -> bool:
    return get_lab_config(concept_id, session=session, org_id=org_id) is not None


def classify_lab_result(
    concept_id: str,
    value: float,
    unit: str | None,
    *,
    patient_sex: str | None,
    patient_age: float | None,
    session: Any | None = None,
    org_id: str | None = None,
) -> LabClassification:
    """Convert and classify one lab result against governed metadata."""
    config = get_lab_config(concept_id, session=session, org_id=org_id)
    if config is None:
        raise LabConfigError(f"No lab result config for observable {concept_id}.")
    canonical = convert_value(config, value, unit)
    band = select_reference_range(
        config.reference_ranges,
        sex=patient_sex,
        age_years=patient_age,
        org_id=org_id,
    )
    if band is None:
        raise LabConfigError(f"No reference range for observable {concept_id}.")
    classification = classify_against_range(canonical, band)
    interpretation = _select_interpretation(config, classification)
    return LabClassification(
        concept_id=config.concept_id,
        display_name=config.display_name,
        classification=classification,
        canonical_value=canonical,
        canonical_unit=config.canonical_unit,
        reference_range=band,
        interpretation_concept_id=interpretation.get("concept_id"),
        interpretation_term=interpretation.get("term"),
    )


def convert_value(config: LabConfig, value: float, unit: str | None) -> float:
    """Convert *value* into the config's canonical unit."""
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise LabConfigError(f"Lab result value {value!r} is not numeric.") from exc
    if not math.isfinite(numeric):
        raise LabConfigError(f"Lab result value {value!r} is not finite.")
    source_unit = str(unit or config.canonical_unit).strip()
    if source_unit == config.canonical_unit:
        return numeric
    conversion = _lookup_conversion(config.conversions, source_unit)
    if conversion is None:
        raise LabConfigError(
            f"No conversion from {source_unit!r} to {config.canonical_unit!r} "
            f"for observable {config.concept_id}."
        )
    return numeric * conversion.factor + conversion.offset


def classify_against_range(value: float, band: LabReferenceRange) -> str:
    """Classify a canonical value against one reference band."""
    if band.critical_low is not None and value < band.critical_low:
        return "critically_low"
    if band.critical_high is not None and value > band.critical_high:
        return "critically_high"
    if band.low is not None and value < band.low:
        return "low"
    if band.high is not None and value > band.high:
        return "high"
    return "normal"


def _fetch_config_row(
    concept_id: str,
    *,
    session: Any | None,
    org_id: str = "",
) -> dict[str, Any] | None:
    params = {
        "concept_id": concept_id,
        "include_all": False,
        "org_id": org_id,
    }
    if session is not None:
        rows = list(session.run(GET_LAB_RESULT_CONFIG, **params) or [])
        return dict(rows[0]) if rows else None
    try:
        client = KnowledgeGraphClient()
        with client.session() as s:
            row = s.run(GET_LAB_RESULT_CONFIG, **params).single()
            return dict(row) if row else None
    except Exception as exc:
        logger.warning("Lab result config lookup failed for %s: %s", concept_id, exc)
        return None
    finally:
        if "client" in locals():
            client.close()


def _row_to_config(row: dict[str, Any]) -> LabConfig:
    canonical_unit = str(row.get("canonical_unit") or "").strip()
    concept_id = str(row.get("concept_id") or "").strip()
    conversions = {
        conv.unit: conv
        for conv in (_parse_conversion(item) for item in row.get("conversions") or [])
        if conv is not None
    }
    ranges = tuple(
        band
        for band in (_parse_range(item) for item in row.get("ranges") or [])
        if band is not None
    )
    return LabConfig(
        concept_id=concept_id,
        display_name=str(row.get("display_name") or concept_id),
        canonical_unit=canonical_unit,
        conversions=conversions,
        reference_ranges=ranges,
        interpretations=_parse_interpretations(row.get("interpretations") or []),
        source=str(row.get("source") or "manual"),
    )


def _parse_conversion(raw: dict[str, Any]) -> UnitConversion | None:
    unit = str((raw or {}).get("unit") or "").strip()
    if not unit:
        return None
    return UnitConversion(
        unit=unit,
        factor=float(raw.get("factor") if raw.get("factor") is not None else 1.0),
        offset=float(raw.get("offset") or 0.0),
    )


def _parse_range(raw: dict[str, Any]) -> LabReferenceRange | None:
    if not raw or not raw.get("range_id"):
        return None
    return LabReferenceRange(
        range_id=str(raw.get("range_id")),
        sex=_norm_optional(raw.get("sex")),
        age_min=_float_or_none(raw.get("age_min")),
        age_max=_float_or_none(raw.get("age_max")),
        low=_float_or_none(raw.get("low")),
        high=_float_or_none(raw.get("high")),
        critical_low=_float_or_none(raw.get("critical_low")),
        critical_high=_float_or_none(raw.get("critical_high")),
        source=str(raw.get("source") or "manual"),
        org_id=str(raw.get("org_id") or "").strip(),
    )


def _parse_interpretations(
    raw_items: list[dict[str, Any]],
) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for raw in raw_items:
        key = str((raw or {}).get("classification") or "").strip().lower()
        concept_id = str((raw or {}).get("concept_id") or "").strip()
        if not key or not concept_id:
            continue
        out[key] = {"concept_id": concept_id, "term": str(raw.get("term") or "")}
    return out


def _select_interpretation(config: LabConfig, classification: str) -> dict[str, str]:
    mappings = config.interpretations
    for key in _classification_keys(classification):
        if key in mappings:
            return mappings[key]
    return {}


def _classification_keys(classification: str) -> tuple[str, ...]:
    if classification == "critically_high":
        return ("critically_high", "high", "out_of_range")
    if classification == "critically_low":
        return ("critically_low", "low", "out_of_range")
    if classification in {"high", "low"}:
        return (classification, "out_of_range")
    return ("normal",)


def _lookup_conversion(
    conversions: dict[str, UnitConversion],
    unit: str,
) -> UnitConversion | None:
    if unit in conversions:
        return conversions[unit]
    unit_norm = unit.lower()
    for candidate, conversion in conversions.items():
        if candidate.lower() == unit_norm:
            return conversion
    return None


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _norm_optional(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    return text or None
