"""Seed NHS default reference ranges into the Patient Graph.

Usage:
    python scripts/seed_reference_ranges.py
"""

from __future__ import annotations

import json
import logging
import sys
import uuid
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from libs.cypher.reference_range_queries import UPSERT_REFERENCE_RANGE
from libs.neo4j_client.client import PatientGraphClient

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_PATH = _REPO_ROOT / "configs" / "reference_ranges" / "nhs_haematology_defaults.json"


def _build_range_id(entry: dict[str, Any]) -> str:
    key = "|".join(
        [
            str(entry.get("concept_id") or ""),
            str(entry.get("unit") or ""),
            str(entry.get("sex") or ""),
            str(entry.get("age_min") if entry.get("age_min") is not None else ""),
            str(entry.get("age_max") if entry.get("age_max") is not None else ""),
            str(entry.get("org_id") or ""),
        ]
    )
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"reference-range:{key}"))


def seed_if_missing(client: PatientGraphClient, *, updated_by: str = "system_seed") -> int:
    rows = client.run("MATCH (r:ReferenceRange) RETURN count(r) AS cnt")
    existing = int(rows[0]["cnt"]) if rows else 0
    if existing > 0:
        logger.info("[ReferenceRangeSeed] Skipping seed; %d ReferenceRange nodes already exist", existing)
        return 0

    payload = json.loads(_DEFAULT_PATH.read_text(encoding="utf-8"))
    created = 0
    for entry in payload:
        client.run(
            UPSERT_REFERENCE_RANGE,
            range_id=_build_range_id(entry),
            concept_id=str(entry.get("concept_id") or ""),
            preferred_term=entry.get("preferred_term") or "",
            unit=entry.get("unit"),
            sex=entry.get("sex"),
            age_min=entry.get("age_min"),
            age_max=entry.get("age_max"),
            low=entry.get("low"),
            high=entry.get("high"),
            critical_low=entry.get("critical_low"),
            critical_high=entry.get("critical_high"),
            source=entry.get("source") or "nhs_haematology_defaults_v1",
            org_id=entry.get("org_id"),
            updated_by=updated_by,
        )
        created += 1
    logger.info("[ReferenceRangeSeed] Seeded %d reference ranges", created)
    return created


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    client = PatientGraphClient()
    try:
        seed_if_missing(client)
    finally:
        client.close()


if __name__ == "__main__":
    main()
