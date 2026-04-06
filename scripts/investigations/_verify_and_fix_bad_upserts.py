"""Fix wrong upserts from _upsert_correct_mappings_neo4j.py.

Some SNOMED concept IDs resolved to the wrong concept (UK edition IDs differ
from expected).  This script:
  1. Deletes the wrong MAPS_TO edges introduced by bad concept IDs.
  2. Searches the knowledge graph for correct IDs for the forms that were skipped.
  3. Upserts the correct mappings.
"""
from __future__ import annotations

import os
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets
load_keyvault_secrets()

from neo4j import GraphDatabase

kg_uri  = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI",      "bolt://localhost:7688")
kg_user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
kg_pass = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev")

# --------------------------------------------------------------------------
# Wrong concept IDs that resolved to incorrect concepts in this graph edition
# --------------------------------------------------------------------------
_WRONG_UPSERTS = [
    # (normalized, bad_concept_id, reason)
    ("left hemiplegia",            "193093009", "resolved to Bell's palsy"),
    ("paraparesis",                "26538006",  "resolved to lumbar disc degeneration"),
    ("flaccid hemiplegia",         "1734006",   "resolved to vertebral fracture with cord injury"),
    ("intermittent claudication",  "29819009",  "resolved to aortocoronary bypass"),
    ("intermittent claudication (finding)", "29819009", "resolved to aortocoronary bypass"),
    ("past ctd",                   "396230008", "resolved to dermatomyositis"),
]

_DELETE_SPECIFIC = """
MATCH (sf:SurfaceForm {normalized: $normalized})-[m:MAPS_TO]->(c:Concept {id: $concept_id})
DELETE m
RETURN count(m) AS deleted
"""

_UPSERT = """
MATCH (c:Concept {id: $concept_id})
WHERE c.active = true
MERGE (sf:SurfaceForm {normalized: $normalized})
ON CREATE SET sf.form = $form, sf.source = 'manual', sf.status = 'active',
              sf.created_at = datetime()
MERGE (sf)-[m:MAPS_TO]->(c)
ON CREATE SET m.created_at = datetime(), m.approved_at = datetime()
SET m.confidence = 1.0,
    m.provenance = 'audit-fix-wrong-gcl-situations-2026-04'
RETURN sf.normalized AS normalized, c.id AS concept_id, c.fsn AS concept_fsn
"""

# Fulltext search to find correct concept ID
_SEARCH_BY_TERM = """
CALL db.index.fulltext.queryNodes("term_fulltext", $q) YIELD node, score
MATCH (node)-[:DESCRIBES]->(c:Concept)
WHERE c.active = true
RETURN c.id AS concept_id, c.fsn AS fsn, c.semantic_tag AS tag, score
ORDER BY score DESC
LIMIT 5
"""

# --------------------------------------------------------------------------
# Correct mappings to find and upsert
# (form, search_query, expected_tag)
# --------------------------------------------------------------------------
_TO_FIND_AND_UPSERT = [
    # Forms where the original concept was not found in graph
    ("Paraplegia",           "paraplegia disorder",       "disorder"),
    ("Paraplegic",           "paraplegia disorder",       "disorder"),
    ("Quadriplegia",         "tetraplegia disorder",      "disorder"),
    ("Quadriplegic",         "tetraplegia disorder",      "disorder"),
    ("Tetraplegic",          "tetraplegia disorder",      "disorder"),
    ("Monoplegia",           "monoplegia disorder",       "disorder"),
    ("Monoplegic",           "monoplegia disorder",       "disorder"),
    ("Monoparesis",          "monoparesis finding",       "finding"),
    ("Diplegia",             "diplegia disorder",         "disorder"),
    ("Diplegic",             "diplegia disorder",         "disorder"),
    ("Spastic diplegia",     "spastic diplegia",          "disorder"),
    ("Spastic hemiplegia",   "spastic hemiplegia",        "disorder"),
    ("LMN paralysis",        "lower motor neuron disorder",  "disorder"),
    ("UMN weakness",         "upper motor neuron disorder",  "disorder"),
    ("Lower motor neuron lesion", "lower motor neuron disorder", "disorder"),
    ("Upper motor neuron lesion", "upper motor neuron disorder", "disorder"),
    ("Paralysis of legs",    "paraplegia disorder",       "disorder"),
    ("Paralysed legs",       "paraplegia disorder",       "disorder"),
    ("Lower limb paralysis", "paraplegia disorder",       "disorder"),
    ("B/L lower limb paralysis", "paraplegia disorder",   "disorder"),
    ("Paralyzed from waist down", "paraplegia disorder",  "disorder"),
    ("Paralysis of all four limbs", "tetraplegia disorder","disorder"),
    ("Single limb paralysis","monoplegia disorder",       "disorder"),
    ("Unilateral paralysis", "monoplegia disorder",       "disorder"),
    # Left hemiplegia correction (Bell's palsy was wrong)
    ("Left hemiplegia",      "left hemiplegia disorder",  "disorder"),
    # PMR
    ("PMR",                        "polymyalgia rheumatica", "disorder"),
    ("Polymyalgia rheumatica",     "polymyalgia rheumatica", "disorder"),
    ("Polymyalgia rheumatica (disorder)", "polymyalgia rheumatica", "disorder"),
    # Emphysema
    ("Emphysema",            "emphysema disorder",        "disorder"),
    ("Pulmonary emphysema",  "emphysema disorder",        "disorder"),
    ("Pulmonary emphysema (disorder)", "emphysema disorder", "disorder"),
    # Intermittent claudication
    ("Intermittent claudication", "intermittent claudication", "finding"),
    ("Intermittent claudication (finding)", "intermittent claudication", "finding"),
    # Past CTD - history of connective tissue disease situation is actually correct
    # for "Past CTD" - leave it unmapped, falls back to search which will return CTD disorder
]


def _norm(text: str) -> str:
    low = text.lower().strip()
    nfkd = unicodedata.normalize("NFKD", low)
    return " ".join(nfkd.encode("ascii", "ignore").decode("ascii").split())


def main() -> None:
    print(f"Connecting: {kg_uri}")
    driver = GraphDatabase.driver(kg_uri, auth=(kg_user, kg_pass))

    with driver.session() as s:
        # Step 1: Delete wrong upserts
        print("\n1. DELETING WRONG UPSERTS")
        for normalized, cid, reason in _WRONG_UPSERTS:
            r = s.run(_DELETE_SPECIFIC, normalized=normalized, concept_id=cid).data()
            deleted = r[0]["deleted"] if r else 0
            print(f"  {normalized!r} -> {cid}: deleted={deleted} ({reason})")

        # Step 2: Find correct concept IDs and upsert
        print("\n2. FINDING AND UPSERTING CORRECT CONCEPTS")
        _seen_cid: dict[str, str] = {}  # search_q -> concept_id cache

        for form, search_q, expected_tag in _TO_FIND_AND_UPSERT:
            normalized = _norm(form)

            # Try cache first
            if search_q in _seen_cid:
                cid = _seen_cid[search_q]
            else:
                results = s.run(_SEARCH_BY_TERM, q=search_q).data()
                # Pick highest-scored result with matching tag
                match = next(
                    (r for r in results if r.get("tag", "") == expected_tag),
                    results[0] if results else None,
                )
                if not match:
                    print(f"  SKIP {form!r} -- no search results for {search_q!r}")
                    continue
                cid = match["concept_id"]
                fsn = match["fsn"]
                _seen_cid[search_q] = cid
                print(f"  Found: {search_q!r} -> {cid} | {fsn}")

            # Upsert
            r = s.run(_UPSERT, normalized=normalized, form=form, concept_id=cid).data()
            if r:
                print(f"  OK  {form!r} -> {r[0]['concept_id']} | {r[0]['concept_fsn']}")
            else:
                print(f"  SKIP {form!r} -> {cid} (concept not in graph)")

    driver.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
