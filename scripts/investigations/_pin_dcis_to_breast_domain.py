"""Add DCIS (Ductal Carcinoma In Situ) concepts to the cancer_types mapping.

DCIS is classified in SNOMED under 'in situ neoplasm of breast', NOT under
'Malignant tumor of breast' (254837009). IS-A expansion from the malignant
parent misses DCIS. This script adds them directly to the mapping JSON and
reseeds the ValueSet in Neo4j so the anchor detector picks them up.

Run:
    python scripts/investigations/_pin_dcis_to_breast_domain.py
"""
from __future__ import annotations
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

_MAPPING_FILE = ROOT / "configs" / "snomed" / "snomed_ncda_cancer_types_mapping.json"

_DCIS_ENTRIES: dict = {
    "Ductal carcinoma in situ of breast (disorder)": {
        "concept_id": 399935008,
        "preferred_term": "Ductal carcinoma in situ of breast (disorder)",
        "semantic_tag": "Disease",
        "cancer_category": "breast",
        "score": 1.0,
        "llm_disambiguated": True,
        "ribbon_color": "#FF69B4",
        "ribbon_color_name": "Pink",
        "guideline_synonyms": [
            "DCIS",
            "Ductal carcinoma in situ",
            "Intraductal carcinoma in situ",
            "Intraductal carcinoma in situ of breast",
            "Carcinoma in situ of breast",
            "DCIS of breast",
            "DCIS left breast",
            "DCIS right breast",
            "In situ carcinoma of breast",
            "Ductal CIS breast",
            "Pre-invasive breast cancer",
            "Non-invasive breast cancer",
        ],
        "guideline_synonym_count": 12,
        "guideline_name": "Ductal carcinoma in situ of breast",
        "parent_concept_id": 254837009,
    },
    "Intraductal carcinoma in situ of breast (disorder)": {
        "concept_id": 447137006,
        "preferred_term": "Intraductal carcinoma in situ of breast (disorder)",
        "semantic_tag": "Disease",
        "cancer_category": "breast",
        "score": 1.0,
        "llm_disambiguated": True,
        "ribbon_color": "#FF69B4",
        "ribbon_color_name": "Pink",
        "guideline_synonyms": ["Intraductal DCIS", "DCIS intraductal"],
        "guideline_synonym_count": 2,
        "guideline_name": "Intraductal carcinoma in situ of breast",
        "parent_concept_id": 254837009,
    },
    "Carcinoma in situ of breast (disorder)": {
        "concept_id": 32102001,
        "preferred_term": "Carcinoma in situ of breast (disorder)",
        "semantic_tag": "Disease",
        "cancer_category": "breast",
        "score": 1.0,
        "llm_disambiguated": True,
        "ribbon_color": "#FF69B4",
        "ribbon_color_name": "Pink",
        "guideline_synonyms": ["CIS breast", "In situ breast carcinoma"],
        "guideline_synonym_count": 2,
        "guideline_name": "Carcinoma in situ of breast",
        "parent_concept_id": 254837009,
    },
    "Ductal carcinoma in situ of left breast (disorder)": {
        "concept_id": 716917000,
        "preferred_term": "Ductal carcinoma in situ of left breast (disorder)",
        "semantic_tag": "Disease",
        "cancer_category": "breast",
        "score": 1.0,
        "llm_disambiguated": True,
        "ribbon_color": "#FF69B4",
        "ribbon_color_name": "Pink",
        "guideline_synonyms": ["DCIS left breast", "Left DCIS"],
        "guideline_synonym_count": 2,
        "guideline_name": "Ductal carcinoma in situ of left breast",
        "parent_concept_id": 254837009,
    },
    "Ductal carcinoma in situ of right breast (disorder)": {
        "concept_id": 716918005,
        "preferred_term": "Ductal carcinoma in situ of right breast (disorder)",
        "semantic_tag": "Disease",
        "cancer_category": "breast",
        "score": 1.0,
        "llm_disambiguated": True,
        "ribbon_color": "#FF69B4",
        "ribbon_color_name": "Pink",
        "guideline_synonyms": ["DCIS right breast", "Right DCIS"],
        "guideline_synonym_count": 2,
        "guideline_name": "Ductal carcinoma in situ of right breast",
        "parent_concept_id": 254837009,
    },
}


def _update_json() -> None:
    data = json.loads(_MAPPING_FILE.read_text(encoding="utf-8"))
    mappings: dict = data["mappings"]

    added = 0
    for term, entry in _DCIS_ENTRIES.items():
        existing = {
            k: v for k, v in mappings.items()
            if v.get("concept_id") == entry["concept_id"]
        }
        if existing:
            print(f"  Already present: {term} ({entry['concept_id']})")
        else:
            mappings[term] = entry
            added += 1
            print(f"  Added: {term} ({entry['concept_id']})")

    if added:
        data["metadata"]["total_terms"] = len(mappings)
        _MAPPING_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"\nSaved {_MAPPING_FILE} (+{added} DCIS concepts)")
    else:
        print("\nNo changes needed.")


def _reseed_neo4j() -> None:
    """Push the updated ValueSet back into Neo4j so the registry picks it up."""
    print("\nRe-seeding cancer_types ValueSet in Neo4j...")
    from libs.neo4j_client.client import PatientGraphClient
    client = PatientGraphClient()

    data = json.loads(_MAPPING_FILE.read_text(encoding="utf-8"))
    mappings: dict = data["mappings"]

    # Upsert each concept into the ncda-cancer-types ValueSet
    _UPSERT_Q = """
    MERGE (c:Concept {conceptId: $concept_id})
    SET   c.name        = $name,
          c.semanticTag = $semantic_tag
    WITH c
    MATCH (vs:ValueSet {id: 'ncda-cancer-types'})
    MERGE (vs)-[rel:HAS_MEMBER]->(c)
    SET rel.milestone_type    = 'diagnosis',
        rel.cancer_category   = $cancer_category,
        rel.assertion_filter  = '["present"]'
    RETURN c.conceptId AS cid
    """
    upserted = 0
    for term, entry in mappings.items():
        try:
            rows = client.run(
                _UPSERT_Q,
                concept_id=entry["concept_id"],
                name=entry.get("preferred_term", term),
                semantic_tag=entry.get("semantic_tag", "Disease"),
                cancer_category=entry.get("cancer_category", "unknown"),
            )
            if rows:
                upserted += 1
        except Exception as exc:
            print(f"  WARNING: {entry['concept_id']} - {exc}")

    client.close()
    print(f"  Upserted {upserted} concepts into ncda-cancer-types ValueSet.")


def main() -> None:
    print("=== Pinning DCIS concepts to breast cancer domain ===\n")
    _update_json()
    _reseed_neo4j()
    print("\nDone.")


if __name__ == "__main__":
    main()
