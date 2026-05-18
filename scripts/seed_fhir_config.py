"""Seed FHIR Device and ValueSet resources into the Knowledge Graph.

Creates the baseline agent configuration (Device) and clinical domain
definitions (ValueSet) that the episode engine relies on.

Usage:
    python scripts/seed_fhir_config.py

Only seeds when no Device or ValueSet resources exist; skips if any are
already present to avoid overwriting user-modified config.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from libs.neo4j_client.client import KnowledgeGraphClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ── Device resources (agent configuration) ───────────────────────────────

DEVICE_RESOURCES = [
    {
        "id": "device-episode-builder",
        "resourceType": "Device",
        "typeCode": "episode-builder",
        "typeDisplay": "Episode Builder Agent",
        "status": "active",
        "version": "2.0.0",
        "agentDescription": "Creates and classifies cancer episodes from referral, diagnosis, and treatment anchors.",
        "maxEpisodes": 10,
        "preReferralDays": 30,
        "postReferralDays": 180,
        "preReferralLimit": 5,
        "consolidationWindowDays": 30,
    },
    {
        "id": "device-anchor-detector",
        "resourceType": "Device",
        "typeCode": "anchor-detector",
        "typeDisplay": "Anchor Detector Agent",
        "status": "active",
        "version": "1.0.0",
        "agentDescription": "Detects referral, diagnosis, and treatment anchors from patient encounters.",
        "expandMonths": 3,
    },
    {
        "id": "device-quality-checker",
        "resourceType": "Device",
        "typeCode": "quality-checker",
        "typeDisplay": "Quality Checker Agent",
        "status": "active",
        "version": "1.0.0",
        "agentDescription": "Checks coded encounters for quality issues and safety-net signals.",
    },
    {
        "id": "device-safety-net-detector",
        "resourceType": "Device",
        "typeCode": "safety-net-detector",
        "typeDisplay": "SafetyNet Detector Agent",
        "status": "active",
        "version": "1.0.0",
        "agentDescription": "Detects clinical safety signals in patient pathways.",
    },
]


# ── ValueSet resources (domain definitions) ──────────────────────────────


def _make_valueset(
    domain_name: str,
    description: str,
    milestone_type: str | None = None,
    time_window_months: int | None = None,
    semantic_tags: list[str] | None = None,
) -> dict:
    return {
        "id": f"ncda-{domain_name.replace('_', '-')}",
        "resourceType": "ValueSet",
        "status": "active",
        "name": domain_name,
        "title": description,
        "description": description,
        "milestoneType": milestone_type,
        "timeWindowMonths": time_window_months,
        "semanticTags": semantic_tags or [],
    }


VALUESET_RESOURCES = [
    _make_valueset(
        "cancer_types",
        "Cancer type diagnosis concepts",
        milestone_type="diagnosis",
        semantic_tags=["disorder"],
    ),
    _make_valueset(
        "fast_track_referrals",
        "Fast-track (2WW) referral procedures",
        milestone_type="referral",
        semantic_tags=["procedure"],
    ),
    _make_valueset(
        "treatment",
        "Cancer treatment procedures",
        milestone_type="treatment",
        semantic_tags=["procedure"],
    ),
    _make_valueset(
        "symptoms",
        "Presenting symptoms",
        time_window_months=12,
        semantic_tags=["finding", "situation"],
    ),
    _make_valueset(
        "comorbidities", "Comorbid conditions", semantic_tags=["finding", "disorder"]
    ),
    _make_valueset(
        "physical_signs", "Physical examination findings", semantic_tags=["finding"]
    ),
    _make_valueset(
        "investigations", "Primary care investigations", semantic_tags=["procedure"]
    ),
    _make_valueset(
        "lifestyle_factors",
        "Lifestyle and risk factors",
        semantic_tags=["finding", "situation"],
    ),
    _make_valueset(
        "family_history", "Family history of cancer", semantic_tags=["situation"]
    ),
    _make_valueset(
        "cancer_risk_factors", "Cancer risk factors", semantic_tags=["finding"]
    ),
    _make_valueset(
        "place_of_presentation",
        "Place of first presentation",
        semantic_tags=["environment"],
    ),
    _make_valueset(
        "seen_by_specialist",
        "Seen by specialist encounters",
        milestone_type="specialist_visit",
        semantic_tags=["procedure"],
    ),
    _make_valueset(
        "referral_outcomes", "Referral outcome codes", semantic_tags=["situation"]
    ),
    _make_valueset("screening", "Cancer screening", semantic_tags=["procedure"]),
    _make_valueset(
        "observable_entities",
        "Observable entity measurements",
        semantic_tags=["observable entity"],
    ),
    _make_valueset(
        "ethnicity",
        "NCDA ethnicity (SNOMED CT UK census-aligned)",
        semantic_tags=["Clinical finding", "Ethnic group"],
    ),
    _make_valueset(
        "housebound_status", "Housebound status", semantic_tags=["situation"]
    ),
    _make_valueset(
        "living_arrangement", "Living arrangement", semantic_tags=["situation"]
    ),
    _make_valueset(
        "communication_difficulty",
        "Communication difficulties",
        semantic_tags=["finding"],
    ),
    _make_valueset(
        "english_language_competency",
        "English language competency",
        semantic_tags=["finding"],
    ),
    _make_valueset(
        "performance_status", "WHO performance status", semantic_tags=["finding"]
    ),
    _make_valueset(
        "temporal_analysis", "Temporal analysis concepts", semantic_tags=["situation"]
    ),
]


# ── Seeding logic ────────────────────────────────────────────────────────

_SKIP_KEYS = {"id", "resourceType"}


def _seed_node(client: KnowledgeGraphClient, resource: dict) -> None:
    """MERGE a resource node with all scalar/array values as flat properties."""
    label = resource["resourceType"]
    rid = resource["id"]

    set_clauses = []
    params: dict = {"rid": rid}
    for key, val in resource.items():
        if key in _SKIP_KEYS or val is None:
            continue
        if isinstance(val, (str, int, float, bool)):
            set_clauses.append(f"r.{key} = ${key}")
            params[key] = val
        elif isinstance(val, list) and all(isinstance(v, str) for v in val):
            set_clauses.append(f"r.{key} = ${key}")
            params[key] = val
        else:
            set_clauses.append(f"r.{key} = ${key}")
            params[key] = json.dumps(val)

    set_expr = ", ".join(set_clauses)
    client.run(
        f"MERGE (r:{label} {{id: $rid}}) SET {set_expr}",
        **params,
    )


def main() -> None:
    client = KnowledgeGraphClient()

    existing_devices = client.run(
        "MATCH (r:Device) WHERE r.id IN $ids RETURN count(r) AS cnt",
        ids=[d["id"] for d in DEVICE_RESOURCES],
    )
    cnt = existing_devices[0]["cnt"] if existing_devices else 0
    if cnt > 0:
        logger.info("Skipped — %d Device resource(s) already present.", cnt)
        client.close()
        return

    existing_valuesets = client.run(
        "MATCH (r:ValueSet) WHERE r.id IN $ids RETURN count(r) AS cnt",
        ids=[vs["id"] for vs in VALUESET_RESOURCES],
    )
    cnt_vs = existing_valuesets[0]["cnt"] if existing_valuesets else 0
    if cnt_vs > 0:
        logger.info("Skipped — %d ValueSet resource(s) already present.", cnt_vs)
        client.close()
        return

    logger.info("Seeding %d Device resources...", len(DEVICE_RESOURCES))
    for device in DEVICE_RESOURCES:
        _seed_node(client, device)
        logger.info("  Seeded Device: %s", device["id"])

    logger.info("Seeding %d ValueSet resources...", len(VALUESET_RESOURCES))
    for vs in VALUESET_RESOURCES:
        _seed_node(client, vs)
        logger.info("  Seeded ValueSet: %s", vs["id"])

    logger.info(
        "Done. Seeded %d resources total.",
        len(DEVICE_RESOURCES) + len(VALUESET_RESOURCES),
    )
    client.close()


if __name__ == "__main__":
    main()
