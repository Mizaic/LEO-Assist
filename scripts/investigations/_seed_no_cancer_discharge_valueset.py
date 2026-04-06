"""Seed the no_cancer_discharge ValueSet into Neo4j for the cancer_audit domain.

The episode detector loads its milestone configuration from FHIR ValueSet nodes
stored in Neo4j, linked to an AuditDomain via HAS_SUBDOMAIN relationships.

This script upserts a new ValueSet (ncda-no-cancer-discharge) containing
SNOMED concept 395100000 (No evidence of cancer found) with milestone_type
'benign_closure', then attaches it to every AuditDomain node that has
episodeDetector=true (including cancer_audit).

When the anchor detector runs next time it will classify any DOCUMENTS
relationship to 395100000 as a benign_closure milestone and the episode
builder will mark those episodes as closed_benign rather than in_progress.

Run:
    python scripts/investigations/_seed_no_cancer_discharge_valueset.py

    # Verify only (no writes):
    python scripts/investigations/_seed_no_cancer_discharge_valueset.py --verify-only
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

# ---------------------------------------------------------------------------
# FHIR ValueSet JSON for the no_cancer_discharge domain
# The extension block follows the same pattern as other ncda-* ValueSets in KG.
# milestoneType: benign_closure -- marks 395100000 as a pathway-closure event.
# ---------------------------------------------------------------------------
_VS_ID = "ncda-no-cancer-discharge"

_VALUESET_RAW = {
    "resourceType": "ValueSet",
    "id": _VS_ID,
    "url": f"https://leo.ai/fhir/ValueSet/{_VS_ID}",
    "version": "1.0.0",
    "name": "NoCancerDischarge",
    "title": "No Cancer Discharge -- Benign Pathway Closure",
    "status": "active",
    "description": (
        "No evidence of cancer found -- explicit pathway-level discharge "
        "(benign biopsy, histopathology, clinic discharge letter). "
        "Closes an episode as benign without a cancer diagnosis."
    ),
    "extension": [
        {
            "url": "https://leo.ai/fhir/StructureDefinition/domain-config",
            "extension": [
                {"url": "milestoneType", "valueCode": "benign_closure"},
                {"url": "semanticTag", "valueString": "Clinical_finding"},
                {"url": "semanticTag", "valueString": "Situation"},
            ],
        }
    ],
    "compose": {
        "include": [
            {
                "system": "http://snomed.info/sct",
                "concept": [
                    {
                        "code": "395100000",
                        "display": "No evidence of cancer found (situation)",
                    }
                ],
            }
        ]
    },
}

# Cypher: upsert the ValueSet node and link it to all episode-detector domains
_UPSERT_VALUESET = """
MERGE (v:ValueSet {id: $vs_id})
SET v.rawJson = $raw_json,
    v.updatedAt = datetime()
RETURN v.id AS id
"""

_LINK_TO_EPISODE_DOMAINS = """
MATCH (d:AuditDomain)
WHERE coalesce(d.episodeDetector, false) = true
   OR d.id = 'cancer_audit'
MERGE (d)-[:HAS_SUBDOMAIN]->(v:ValueSet {id: $vs_id})
RETURN d.id AS domain_id
"""

_VERIFY_QUERY = """
MATCH (d:AuditDomain)-[:HAS_SUBDOMAIN]->(v:ValueSet {id: $vs_id})
RETURN d.id AS domain_id, v.id AS vs_id, v.rawJson AS raw_json
"""


def run_seed(kg: KnowledgeGraphClient) -> None:
    raw_json = json.dumps(_VALUESET_RAW)

    print(f"Upserting ValueSet node: {_VS_ID} ...")
    rows = kg.run(_UPSERT_VALUESET, vs_id=_VS_ID, raw_json=raw_json)
    for r in (rows or []):
        print(f"  Upserted: {r.get('id')}")

    print()
    print("Linking to episode-detector AuditDomain nodes ...")
    rows = kg.run(_LINK_TO_EPISODE_DOMAINS, vs_id=_VS_ID)
    for r in (rows or []):
        print(f"  Linked: {r.get('domain_id')} -> {_VS_ID}")

    print()
    print("Done.")


def run_verify(kg: KnowledgeGraphClient) -> bool:
    rows = kg.run(_VERIFY_QUERY, vs_id=_VS_ID) or []
    if not rows:
        print(f"  FAIL: No AuditDomain linked to {_VS_ID}")
        return False

    ok = True
    for r in rows:
        try:
            vs_json = json.loads(r.get("raw_json") or "{}")
            exts = vs_json.get("extension") or []
            milestone = None
            for ext in exts:
                for sub in ext.get("extension") or []:
                    if sub.get("url") == "milestoneType":
                        milestone = sub.get("valueCode")
            concepts = [
                c.get("code")
                for inc in (vs_json.get("compose") or {}).get("include") or []
                for c in inc.get("concept") or []
            ]
            domain_id = r.get("domain_id")
            has_concept = "395100000" in concepts
            has_milestone = milestone == "benign_closure"
            status = "PASS" if (has_concept and has_milestone) else "FAIL"
            print(
                f"  [{status}] domain={domain_id}  "
                f"concept=395100000:{has_concept}  "
                f"milestoneType={milestone}"
            )
            if status == "FAIL":
                ok = False
        except Exception as exc:
            print(f"  [FAIL] Error parsing ValueSet JSON: {exc}")
            ok = False

    return ok


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed no_cancer_discharge ValueSet into the Neo4j KG"
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify; do not write.",
    )
    args = parser.parse_args()

    kg = KnowledgeGraphClient()
    try:
        if not args.verify_only:
            run_seed(kg)
            print()
            print("Verifying ...")
            print()

        ok = run_verify(kg)
        if not ok:
            sys.exit(1)
        print()
        print("Verification passed.")
    finally:
        kg.close()


if __name__ == "__main__":
    main()
