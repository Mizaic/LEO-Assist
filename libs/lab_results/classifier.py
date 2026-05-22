"""Shared lab result classifier backed by Knowledge Graph metadata.

Atlas trace:
  UN: UN-1DCDA92F
  DI: DI-6BA67DFF
  DO: DO-F34C6679
  Risk: R-77E35839
  VT: VT-6A6C90E0
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import math
from typing import Any, Iterable

from libs.cypher.lab_result_config_queries import GET_LAB_RESULT_CONFIG
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
class LabReferenceRange:
    range_id: str
    low: float | None
    high: float | None
    critical_low: float | None
    critical_high: float | None
    source: str
    sex: str | None = None
    age_min: float | None = None
    age_max: float | None = None


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


_CONFIG_CACHE: dict[str, LabConfig | None] = {}


def get_lab_config(
    concept_id: str,
    *,
    session: Any | None = None,
    use_cache: bool = True,
) -> LabConfig | None:
    """Load one observable's lab metadata from the Knowledge Graph."""
    key = str(concept_id or "").strip()
    if not key:
        return None
    if use_cache and session is None and key in _CONFIG_CACHE:
        return _CONFIG_CACHE[key]
    row = _fetch_config_row(key, session=session)
    config = _row_to_config(row) if row else None
    if use_cache and session is None:
        _CONFIG_CACHE[key] = config
    return config


def has_lab_config(concept_id: str, *, session: Any | None = None) -> bool:
    return get_lab_config(concept_id, session=session) is not None


def classify_lab_result(
    concept_id: str,
    value: float,
    unit: str | None,
    *,
    patient_sex: str | None,
    patient_age: float | None,
    session: Any | None = None,
) -> LabClassification:
    """Convert and classify one lab result against governed metadata."""
    config = get_lab_config(concept_id, session=session)
    if config is None:
        raise LabConfigError(f"No lab result config for observable {concept_id}.")
    canonical = convert_value(config, value, unit)
    band = select_reference_range(
        config.reference_ranges,
        sex=patient_sex,
        age_years=patient_age,
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


def select_reference_range(
    ranges: Iterable[LabReferenceRange],
    *,
    sex: str | None,
    age_years: float | None,
) -> LabReferenceRange | None:
    """Return the tightest demographic range matching the patient."""
    sex_norm = str(sex or "").strip().lower() or None
    candidates: list[tuple[int, LabReferenceRange]] = []
    for band in ranges:
        if not _band_matches(band, sex=sex_norm, age_years=age_years):
            continue
        candidates.append((_band_specificity(band), band))
    if not candidates:
        return None
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    return candidates[0][1]


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


def _fetch_config_row(concept_id: str, *, session: Any | None) -> dict[str, Any] | None:
    if session is not None:
        rows = list(session.run(GET_LAB_RESULT_CONFIG, concept_id=concept_id) or [])
        return dict(rows[0]) if rows else None
    try:
        client = KnowledgeGraphClient()
        with client.session() as s:
            row = s.run(GET_LAB_RESULT_CONFIG, concept_id=concept_id).single()
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


def _band_matches(
    band: LabReferenceRange,
    *,
    sex: str | None,
    age_years: float | None,
) -> bool:
    band_sex = _norm_optional(band.sex)
    if band_sex and band_sex != "all" and band_sex != sex:
        return False
    if band.age_min is not None and (age_years is None or age_years < band.age_min):
        return False
    if band.age_max is not None and (age_years is None or age_years > band.age_max):
        return False
    return True


def _band_specificity(band: LabReferenceRange) -> int:
    score = 0
    if _norm_optional(band.sex) not in {None, "all"}:
        score += 2
    if band.age_min is not None:
        score += 1
    if band.age_max is not None:
        score += 1
    return score


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _norm_optional(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    return text or None
