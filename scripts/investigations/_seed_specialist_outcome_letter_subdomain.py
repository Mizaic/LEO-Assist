"""Seed specialist_outcome_letter ValueSet (ncda-specialist-outcome-letter).

Run:
    python scripts/investigations/_seed_specialist_outcome_letter_subdomain.py
    python scripts/investigations/_seed_specialist_outcome_letter_subdomain.py --verify-only
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

from libs.neo4j_client.client import KnowledgeGraphClient

_VS_ID = "ncda-specialist-outcome-letter"
_VS_NAME = "specialist_outcome_letter"
_MILESTONE_TYPE = "specialist_outcome_letter"

_VALUESET_RAW = {
    "resourceType": "ValueSet",
    "id": _VS_ID,
    "url": f"https://leo.ai/fhir/ValueSet/{_VS_ID}",
    "version": "1.0.0",
    "name": _VS_NAME,
    "title": "Specialist outcome letter",
    "status": "active",
    "description": (
        "Clinic letters and specialist correspondence (record artifacts) received "
        "at the practice after referral and specialist review."
    ),
    "milestoneType": _MILESTONE_TYPE,
    "semanticTags": ["record artifact"],
    "assertionFilter": [],
    "extension": [
        {
            "url": "https://leo.ai/fhir/StructureDefinition/domain-config",
            "extension": [
                {"url": "milestoneType", "valueCode": _MILESTONE_TYPE},
                {"url": "semanticTag", "valueString": "record artifact"},
            ],
        }
    ],
    "compose": {
        "include": [
            {
                "system": "http://snomed.info/sct",
                "concept": [
                    {
                        "code": "308470004",
                        "display": "Letter (record artifact)",
                    },
                    {
                        "code": "371530004",
                        "display": "Clinical letter (record artifact)",
                    },
                ],
            }
        ]
    },
}

_UPSERT_VALUESET = """
MERGE (v:ValueSet {id: $vs_id})
SET v.name           = $name,
    v.title          = $title,
    v.description    = $description,
    v.status         = 'active',
    v.resourceType   = 'ValueSet',
    v.milestoneType  = $milestone_type,
    v.semanticTags   = $semantic_tags,
    v.assertionFilter = [],
    v.rawJson        = $raw_json,
    v.updatedAt      = datetime()
RETURN v.id AS id
"""

_LINK_TO_EPISODE_DOMAINS = """
MATCH (d:AuditDomain)
WHERE coalesce(d.episodeDetector, false) = true
   OR d.id = 'cancer_audit'
WITH d
MATCH (v:ValueSet {id: $vs_id})
MERGE (d)-[:HAS_SUBDOMAIN]->(v)
RETURN d.id AS domain_id
"""

_VERIFY_QUERY = """
MATCH (d:AuditDomain)-[:HAS_SUBDOMAIN]->(v:ValueSet {id: $vs_id})
RETURN d.id AS domain_id, v.milestoneType AS milestone_flat, v.name AS name
"""


def run_seed(kg: KnowledgeGraphClient) -> None:
    raw_json = json.dumps(_VALUESET_RAW)
    print(f"Upserting ValueSet node: {_VS_ID} ...")
    for r in (
        kg.run(
            _UPSERT_VALUESET,
            vs_id=_VS_ID,
            name=_VS_NAME,
            title=_VALUESET_RAW["title"],
            description=_VALUESET_RAW["description"],
            milestone_type=_MILESTONE_TYPE,
            semantic_tags=_VALUESET_RAW["semanticTags"],
            raw_json=raw_json,
        )
        or []
    ):
        print(f"  Upserted: {r.get('id')}")

    print("Linking to cancer_audit / episode domains ...")
    for r in kg.run(_LINK_TO_EPISODE_DOMAINS, vs_id=_VS_ID) or []:
        print(f"  Linked: {r.get('domain_id')} -> {_VS_ID}")


def run_verify(kg: KnowledgeGraphClient) -> bool:
    rows = kg.run(_VERIFY_QUERY, vs_id=_VS_ID) or []
    if not rows:
        print(f"  FAIL: no domain linked to {_VS_ID}")
        return False
    ok = True
    for r in rows:
        if r.get("milestone_flat") != _MILESTONE_TYPE or r.get("name") != _VS_NAME:
            print(f"  FAIL: row {r}")
            ok = False
        else:
            print(f"  PASS: domain={r.get('domain_id')} name={r.get('name')!r}")
    return ok


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify-only", action="store_true")
    args = ap.parse_args()
    kg = KnowledgeGraphClient()
    try:
        if not args.verify_only:
            run_seed(kg)
            print()
        if not run_verify(kg):
            sys.exit(1)
        print("OK.")
    finally:
        kg.close()


if __name__ == "__main__":
    main()
