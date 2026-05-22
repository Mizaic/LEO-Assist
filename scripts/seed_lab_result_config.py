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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from libs.cypher.lab_result_config_queries import (  # noqa: E402
    UPSERT_LAB_RESULT_CONFIG,
    UPSERT_REFERENCE_RANGE,
    UPSERT_UNIT_CONVERSION,
)
from libs.neo4j_client.client import KnowledgeGraphClient  # noqa: E402
from libs.units.observable_units import OBSERVABLE_UNIT_REGISTRY  # noqa: E402

logger = logging.getLogger(__name__)
_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_RANGES = _REPO_ROOT / "configs/reference_ranges/nhs_haematology_defaults.json"


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


def seed_if_missing(
    client: KnowledgeGraphClient,
    *,
    updated_by: str = "system_seed",
) -> int:
    rows = client.run("MATCH (cfg:LabResultConfig) RETURN count(cfg) AS cnt")
    existing = int(rows[0]["cnt"]) if rows else 0
    if existing > 0:
        logger.info("[LabResultConfigSeed] Skipping; %d configs exist", existing)
        return 0
    specs = _seed_registry_specs(client, updated_by)
    ranges = _seed_default_ranges(client, updated_by)
    logger.info(
        "[LabResultConfigSeed] Seeded %d registry specs and %d ranges",
        specs,
        ranges,
    )
    return specs + ranges


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    client = KnowledgeGraphClient()
    try:
        seed_if_missing(client)
    finally:
        client.close()


if __name__ == "__main__":
    main()
