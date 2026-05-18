"""Seed the NCDA ethnicity ValueSet into the Knowledge Graph and link cancer_audit.

Loads ``configs/snomed/snomed_ncda_ethnicity_mapping.json``, builds a FHIR-style
ValueSet (compose.include + benchmark_key designations), upserts ``ValueSet``
node ``ncda-ethnicity``, and MERGEs ``(:AuditDomain {id:'cancer_audit'})-[:HAS_SUBDOMAIN]->(v)``.

Run:
    python scripts/ncda/seed_ncda_ethnicity_valueset.py
    python scripts/ncda/seed_ncda_ethnicity_valueset.py --verify-only

Requires Knowledge Graph Neo4j credentials (same as analytics_api domains router).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "analytics_api"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets  # noqa: E402

load_keyvault_secrets()

from app.routers.domains import _upsert_valueset_flat  # noqa: E402
from libs.neo4j_client.client import KnowledgeGraphClient  # noqa: E402

VS_ID = "ncda-ethnicity"
VS_NAME = "ethnicity"
MAPPING_PATH = ROOT / "configs" / "snomed" / "snomed_ncda_ethnicity_mapping.json"
SNOMED_SYSTEM = "http://snomed.info/sct"


def _load_mapping() -> Dict[str, Any]:
    return json.loads(MAPPING_PATH.read_text(encoding="utf-8"))


def _build_concepts(mapping: Dict[str, Any]) -> List[Dict[str, Any]]:
    concepts: List[Dict[str, Any]] = []
    for key, value in (mapping.get("mappings") or {}).items():
        cid = value.get("concept_id")
        display = value.get("preferred_term") or key.replace("_", " ")
        if not cid:
            continue
        designations: List[Dict[str, Any]] = []
        for syn in value.get("guideline_synonyms") or []:
            if syn:
                designations.append({"use": {"code": "synonym"}, "value": str(syn)})
        designations.append({"use": {"code": "benchmark_key"}, "value": key})
        concepts.append(
            {"code": str(cid), "display": str(display), "designation": designations}
        )
    return concepts


def _build_valueset(mapping: Dict[str, Any]) -> Dict[str, Any]:
    concepts = _build_concepts(mapping)
    return {
        "resourceType": "ValueSet",
        "id": VS_ID,
        "url": f"https://leo.ai/fhir/ValueSet/{VS_ID}",
        "version": "1.0.0",
        "name": VS_NAME,
        "title": "NCDA ethnicity",
        "status": "active",
        "description": (
            "National Cancer Diagnosis Audit ethnicity categories mapped to SNOMED CT "
            "UK concepts (England & Wales census-aligned findings)."
        ),
        "semanticTags": ["Clinical_finding", "Ethnic_group"],
        "assertionFilter": [],
        "extension": [
            {
                "url": "https://leo.ai/fhir/StructureDefinition/domain-config",
                "extension": [
                    {"url": "semanticTag", "valueString": "Clinical_finding"},
                    {"url": "semanticTag", "valueString": "Ethnic_group"},
                ],
            }
        ],
        "compose": {"include": [{"system": SNOMED_SYSTEM, "concept": concepts}]},
    }


def _link_to_cancer_audit(kg: KnowledgeGraphClient) -> None:
    kg.run(
        "MATCH (d:AuditDomain {id: 'cancer_audit'}), (v:ValueSet {id: $vs_id}) "
        "MERGE (d)-[:HAS_SUBDOMAIN]->(v)",
        vs_id=VS_ID,
    )


def _verify(kg: KnowledgeGraphClient) -> bool:
    rows = kg.run(
        "MATCH (d:AuditDomain {id: 'cancer_audit'})-[:HAS_SUBDOMAIN]->(v:ValueSet {id: $id}) "
        "RETURN v.rawJson AS raw, v.name AS name",
        id=VS_ID,
    )
    if not rows:
        print("FAIL: ethnicity ValueSet is not linked to cancer_audit.")
        return False

    raw = rows[0].get("raw") or "{}"
    vs = json.loads(raw) if isinstance(raw, str) else raw
    concept_count = sum(
        len(include.get("concept") or [])
        for include in (vs.get("compose") or {}).get("include") or []
    )
    print(
        "PASS:"
        f" linked=true, name={rows[0].get('name')!r},"
        f" concept_count={concept_count}"
    )
    return rows[0].get("name") == VS_NAME and concept_count >= 21


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()

    mapping = _load_mapping()
    valueset = _build_valueset(mapping)

    kg = KnowledgeGraphClient()
    try:
        if not args.verify_only:
            _upsert_valueset_flat(VS_ID, valueset)
            _link_to_cancer_audit(kg)
            print(f"Upserted {VS_ID} and linked to cancer_audit.")
        ok = _verify(kg)
        if not ok:
            sys.exit(1)
    finally:
        kg.close()


if __name__ == "__main__":
    main()
