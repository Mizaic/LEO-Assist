"""Seed lab result metadata into the Knowledge Graph.

The seed is guarded: if any LabResultConfig nodes already exist the
script skips all writes to avoid overwriting user-managed knowledge.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import sys
import uuid
from typing import Any

from dotenv import load_dotenv

_REPO_ROOT_EARLY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT_EARLY))
load_dotenv(_REPO_ROOT_EARLY / "secrets" / ".env.secrets")
load_dotenv(_REPO_ROOT_EARLY / "secrets" / ".env.config", override=True)

from libs.cypher.lab_result_config_queries import (  # noqa: E402
    GET_LAB_RESULT_CONFIG,
    UPSERT_INTERPRETATION,
    UPSERT_LAB_RESULT_CONFIG,
    UPSERT_REFERENCE_RANGE,
    UPSERT_UNIT_CONVERSION,
)
from libs.lab_results.concept_aliases import (  # noqa: E402
    LAB_CONFIG_CONCEPT_ALIASES,
)
from libs.neo4j_client.client import KnowledgeGraphClient  # noqa: E402
from libs.units.observable_units import OBSERVABLE_UNIT_REGISTRY  # noqa: E402

logger = logging.getLogger(__name__)
_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_RANGES = _REPO_ROOT / "configs/reference_ranges/nhs_haematology_defaults.json"
_DEFAULT_INTERPRETS_AS = (
    _REPO_ROOT / "configs/reference_ranges/lab_interprets_as_defaults.json"
)

_ALIAS_DISPLAY_NAMES = {
    "1107511000000100": "Mass concentration of haemoglobin in blood",
    "271026005": "Haemoglobin",
    "997491000000108": "Serum amylase level",
}


def _range_id(entry: dict[str, Any]) -> str:
    key = "|".join(
        str(entry.get(part) if entry.get(part) is not None else "")
        for part in ("concept_id", "unit", "sex", "age_min", "age_max")
    )
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"lab-result-range:{key}"))


def _seed_registry_specs(client: KnowledgeGraphClient, updated_by: str) -> int:
    created = 0
    for concept_id, spec in OBSERVABLE_UNIT_REGISTRY.items():
        client.run(
            UPSERT_LAB_RESULT_CONFIG,
            concept_id=concept_id,
            display_name=spec.display_name,
            canonical_unit=spec.canonical_unit,
            source="observable_units_registry_migration",
            updated_by=updated_by,
        )
        for unit, conv in spec.aliases.items():
            client.run(
                UPSERT_UNIT_CONVERSION,
                concept_id=concept_id,
                unit=unit,
                factor=conv.factor,
                offset=conv.offset,
                updated_by=updated_by,
            )
        for band in spec.reference_ranges:
            entry = {
                "concept_id": concept_id,
                "unit": band.unit,
                "sex": band.sex or "all",
                "age_min": band.age_min_years,
                "age_max": band.age_max_years,
            }
            client.run(
                UPSERT_REFERENCE_RANGE,
                range_id=_range_id(entry),
                concept_id=concept_id,
                sex=entry["sex"],
                age_min=entry["age_min"],
                age_max=entry["age_max"],
                low=band.lower,
                high=band.upper,
                critical_low=None,
                critical_high=None,
                source=band.source,
                updated_by=updated_by,
            )
        created += 1
    return created


def _seed_default_ranges(client: KnowledgeGraphClient, updated_by: str) -> int:
    ranges = json.loads(_DEFAULT_RANGES.read_text(encoding="utf-8"))
    count = 0
    for entry in ranges:
        concept_id = str(entry.get("concept_id") or "")
        if not concept_id:
            continue
        client.run(
            UPSERT_LAB_RESULT_CONFIG,
            concept_id=concept_id,
            display_name=entry.get("preferred_term") or concept_id,
            canonical_unit=entry.get("unit") or "",
            source=entry.get("source") or "nhs_haematology_defaults_v1",
            updated_by=updated_by,
        )
        client.run(
            UPSERT_REFERENCE_RANGE,
            range_id=_range_id(entry),
            concept_id=concept_id,
            sex=entry.get("sex") or "all",
            age_min=entry.get("age_min"),
            age_max=entry.get("age_max"),
            low=entry.get("low"),
            high=entry.get("high"),
            critical_low=entry.get("critical_low"),
            critical_high=entry.get("critical_high"),
            source=entry.get("source") or "nhs_haematology_defaults_v1",
            updated_by=updated_by,
        )
        count += 1
    return count


def _clone_config_to_alias(
    client: KnowledgeGraphClient,
    *,
    source_id: str,
    alias_id: str,
    updated_by: str,
) -> bool:
    rows = client.run(GET_LAB_RESULT_CONFIG, concept_id=source_id)
    if not rows:
        logger.warning(
            "[LabResultConfigSeed] Cannot alias %s; source %s missing",
            alias_id,
            source_id,
        )
        return False
    source = rows[0]
    client.run(
        UPSERT_LAB_RESULT_CONFIG,
        concept_id=alias_id,
        display_name=_ALIAS_DISPLAY_NAMES.get(alias_id)
        or source.get("display_name")
        or alias_id,
        canonical_unit=source.get("canonical_unit") or "",
        source=f"uk_observable_alias:alias_of:{source_id}",
        updated_by=updated_by,
    )
    for conv in source.get("conversions") or []:
        unit = str((conv or {}).get("unit") or "").strip()
        if not unit:
            continue
        client.run(
            UPSERT_UNIT_CONVERSION,
            concept_id=alias_id,
            unit=unit,
            factor=float(conv.get("factor") if conv.get("factor") is not None else 1.0),
            offset=float(conv.get("offset") or 0.0),
            updated_by=updated_by,
        )
    for band in source.get("ranges") or []:
        if not band or not band.get("range_id"):
            continue
        client.run(
            UPSERT_REFERENCE_RANGE,
            range_id=f"{band['range_id']}:{alias_id}",
            concept_id=alias_id,
            sex=band.get("sex") or "all",
            age_min=band.get("age_min"),
            age_max=band.get("age_max"),
            low=band.get("low"),
            high=band.get("high"),
            critical_low=band.get("critical_low"),
            critical_high=band.get("critical_high"),
            source=band.get("source") or "uk_observable_alias",
            updated_by=updated_by,
        )
    for interp in source.get("interpretations") or []:
        finding_id = str((interp or {}).get("concept_id") or "").strip()
        classification = str((interp or {}).get("classification") or "").strip()
        if not finding_id or not classification:
            continue
        client.run(
            UPSERT_INTERPRETATION,
            concept_id=alias_id,
            finding_concept_id=finding_id,
            classification=classification,
            updated_by=updated_by,
        )
    return True


def ensure_uk_observable_aliases(
    client: KnowledgeGraphClient,
    *,
    updated_by: str = "system_seed",
) -> int:
    """Clone missing UK extraction IDs from their canonical LabResultConfig."""
    created = 0
    for alias_id, source_id in LAB_CONFIG_CONCEPT_ALIASES.items():
        existing = client.run(
            "MATCH (cfg:LabResultConfig {conceptId: $cid}) " "RETURN count(cfg) AS cnt",
            cid=alias_id,
        )
        if existing and int(existing[0]["cnt"]) > 0:
            continue
        if _clone_config_to_alias(
            client,
            source_id=source_id,
            alias_id=alias_id,
            updated_by=updated_by,
        ):
            created += 1
            logger.info("[LabResultConfigSeed] Cloned %s from %s", alias_id, source_id)
    return created


def ensure_lab_interpretations(
    client: KnowledgeGraphClient,
    *,
    updated_by: str = "system_seed",
) -> int:
    """Upsert INTERPRETS_AS edges from terminology-verified defaults."""
    payload = json.loads(_DEFAULT_INTERPRETS_AS.read_text(encoding="utf-8"))
    written = 0
    for group in payload.get("mappings") or []:
        interpretations = group.get("interpretations") or {}
        for concept_id in group.get("concept_ids") or []:
            cfg_rows = client.run(
                "MATCH (cfg:LabResultConfig {conceptId: $cid}) "
                "RETURN count(cfg) AS cnt",
                cid=str(concept_id),
            )
            if not cfg_rows or int(cfg_rows[0]["cnt"]) == 0:
                logger.warning(
                    "[LabResultConfigSeed] Skip interpretations; no config %s",
                    concept_id,
                )
                continue
            for classification, info in interpretations.items():
                finding_id = str((info or {}).get("concept_id") or "").strip()
                band = str(classification or "").strip().lower()
                if not finding_id or not band:
                    continue
                rows = client.run(
                    UPSERT_INTERPRETATION,
                    concept_id=str(concept_id),
                    finding_concept_id=finding_id,
                    classification=band,
                    updated_by=updated_by,
                )
                if rows:
                    written += 1
    logger.info("[LabResultConfigSeed] Upserted %d INTERPRETS_AS edges", written)
    return written


def seed_if_missing(
    client: KnowledgeGraphClient,
    *,
    updated_by: str = "system_seed",
) -> int:
    rows = client.run("MATCH (cfg:LabResultConfig) RETURN count(cfg) AS cnt")
    existing = int(rows[0]["cnt"]) if rows else 0
    seeded = 0
    if existing > 0:
        logger.info("[LabResultConfigSeed] Skipping; %d configs exist", existing)
    else:
        specs = _seed_registry_specs(client, updated_by)
        ranges = _seed_default_ranges(client, updated_by)
        logger.info(
            "[LabResultConfigSeed] Seeded %d registry specs and %d ranges",
            specs,
            ranges,
        )
        seeded = specs + ranges
    aliased = ensure_uk_observable_aliases(client, updated_by=updated_by)
    interpreted = ensure_lab_interpretations(client, updated_by=updated_by)
    return seeded + aliased + interpreted


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    client = KnowledgeGraphClient()
    try:
        seed_if_missing(client)
    finally:
        client.close()


if __name__ == "__main__":
    main()
