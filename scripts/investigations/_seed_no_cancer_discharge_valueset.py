"""Seed the no_cancer_discharge ValueSet into Neo4j for the cancer_audit domain.

The episode detector loads its milestone configuration from FHIR ValueSet nodes
stored in Neo4j, linked to an AuditDomain via HAS_SUBDOMAIN relationships.

This script upserts the ValueSet (ncda-no-cancer-discharge) with
milestone_type 'diagnosis' so that "No evidence of cancer found" concepts
close an episode as completed -- the same as a cancer diagnosis.  Whether the
completed episode represents cancer or a benign outcome is determined by
reading the SNOMED concept code linked as the diagnosis.

All flat node properties (name, milestoneType, etc.) are written alongside
rawJson so the UI domain config pages can read them without parsing JSON.

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
# snake_case name -- must match _valueset_id_to_subdomain(_VS_ID) so that
# the UI round-trips correctly: name -> URL path -> ValueSet id lookup.
_VS_NAME = "no_cancer_discharge"
_MILESTONE_TYPE = "diagnosis"

_VALUESET_RAW = {
    "resourceType": "ValueSet",
    "id": _VS_ID,
    "url": f"https://leo.ai/fhir/ValueSet/{_VS_ID}",
    "version": "1.0.0",
    "name": _VS_NAME,
    "title": "No Cancer Discharge",
    "status": "active",
    "description": (
        "No evidence of cancer found -- explicit pathway-level discharge "
        "(benign biopsy, histopathology, clinic discharge letter). "
        "Milestone type 'diagnosis' so the episode closes as completed; "
        "cancer vs benign is determined by the SNOMED code of the linked concept."
    ),
    "milestoneType": _MILESTONE_TYPE,
    "semanticTags": ["Clinical_finding", "Situation"],
    "assertionFilter": [],
    "extension": [
        {
            "url": "https://leo.ai/fhir/StructureDefinition/domain-config",
            "extension": [
                {"url": "milestoneType", "valueCode": _MILESTONE_TYPE},
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

# Cypher: upsert the ValueSet node with all flat properties + rawJson.
# Flat properties are read directly by the domain listing UI (no JSON parsing).
# rawJson is read by the anchor detector registry loader (FHIR extension path).
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
MERGE (d)-[:HAS_SUBDOMAIN]->(v:ValueSet {id: $vs_id})
RETURN d.id AS domain_id
"""

_VERIFY_QUERY = """
MATCH (d:AuditDomain)-[:HAS_SUBDOMAIN]->(v:ValueSet {id: $vs_id})
RETURN d.id AS domain_id, v.id AS vs_id,
       v.name AS name, v.milestoneType AS milestone_flat,
       v.rawJson AS raw_json
"""


def run_seed(kg: KnowledgeGraphClient) -> None:
    raw_json = json.dumps(_VALUESET_RAW)

    print(f"Upserting ValueSet node: {_VS_ID} ...")
    rows = kg.run(
        _UPSERT_VALUESET,
        vs_id=_VS_ID,
        name=_VS_NAME,
        title=_VALUESET_RAW["title"],
        description=_VALUESET_RAW["description"],
        milestone_type=_MILESTONE_TYPE,
        semantic_tags=_VALUESET_RAW["semanticTags"],
        raw_json=raw_json,
    )
    for r in rows or []:
        print(f"  Upserted: {r.get('id')}")

    print()
    print("Linking to episode-detector AuditDomain nodes ...")
    rows = kg.run(_LINK_TO_EPISODE_DOMAINS, vs_id=_VS_ID)
    for r in rows or []:
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
            concepts = [
                c.get("code")
                for inc in (vs_json.get("compose") or {}).get("include") or []
                for c in inc.get("concept") or []
            ]
            domain_id = r.get("domain_id")
            has_concept = "395100000" in concepts
            flat_milestone = r.get("milestone_flat")
            flat_name = r.get("name")
            has_milestone = flat_milestone == _MILESTONE_TYPE
            has_name = flat_name == _VS_NAME
            status = "PASS" if (has_concept and has_milestone and has_name) else "FAIL"
            print(
                f"  [{status}] domain={domain_id}  "
                f"name={flat_name!r}  "
                f"milestoneType={flat_milestone!r}  "
                f"concept_395100000={has_concept}"
            )
            if not has_milestone:
                print(f"    PROBLEM: milestoneType should be {_MILESTONE_TYPE!r}")
            if not has_name:
                print(f"    PROBLEM: name should be {_VS_NAME!r}")
            if not has_concept:
                print("    PROBLEM: concept 395100000 missing from compose")
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
