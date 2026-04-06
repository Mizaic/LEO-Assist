"""Check IS_A expansion for the concepts added to the cancer_audit domain.

Verifies:
1. Whether the KG has IS_A relationships from the parent concepts.
2. How many descendants each parent has.
3. Whether those descendants match the hardcoded concept sets.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from libs.keyvault.loader import load_keyvault_secrets
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
load_keyvault_secrets()

from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient
from libs.domains.ncda_concept_sets import (
    CANCER_TYPE_IDS,
    FAST_TRACK_REFERRAL_IDS,
    SEEN_BY_SPECIALIST_IDS,
)

PARENT_CONCEPTS = {
    "referral":       199251000000107,  # Fast track cancer referral (procedure)
    "diagnosis":      363346000,        # Malignant neoplastic disease (disorder)
    "specialist":     382761000000101,  # Seen in fast track suspected cancer clinic (finding)
}

# -- 1. Check IS_A descendants in KG --
print("=" * 70)
print("KG IS_A DESCENDANTS (depth 1..5)")
print("=" * 70)

kg = KnowledgeGraphClient()

isa_q = (
    "MATCH (parent:Concept)-[:IS_A*1..5]->(child:Concept) "
    "WHERE parent.snomedId = $parent_id OR parent.conceptId = $parent_id "
    "RETURN child.snomedId AS id, child.conceptId AS id2, "
    "       child.preferredTerm AS term LIMIT 100"
)

# Also check what relationship names exist for IS_A
rel_q = (
    "MATCH ()-[r]->() "
    "WHERE type(r) IN ['IS_A','ISA','is_a','BROADER_THAN','HAS_PARENT'] "
    "RETURN type(r) AS rel, count(r) AS n LIMIT 10"
)
rel_rows = kg.run(rel_q)
print("IS_A-style relationships in KG:", rel_rows or "none found")

# Check concept node properties
prop_q = "MATCH (c:Concept) RETURN keys(c) AS props LIMIT 1"
prop_rows = kg.run(prop_q)
print("Concept node properties:", prop_rows[0]["props"] if prop_rows else "none")

# Try to find the parent concepts by snomedId or id property
for label, parent_id in PARENT_CONCEPTS.items():
    check_q = (
        "MATCH (c) WHERE c.snomedId = $id OR c.id = $id "
        "OR toString(c.conceptId) = $sid "
        "RETURN labels(c) AS lbl, c.preferredTerm AS term LIMIT 3"
    )
    rows = kg.run(check_q, id=parent_id, sid=str(parent_id))
    print(f"\n  {label} ({parent_id}): KG node -> {rows or 'NOT FOUND'}")

kg.close()

# -- 2. Check patient graph for IS_A / hierarchy relationships --
print("\n" + "=" * 70)
print("PATIENT GRAPH HIERARCHY CHECK")
print("=" * 70)

pg = PatientGraphClient()

# What relationship types connect concept nodes?
pg_rels = pg.run(
    "MATCH (a)-[r]->(b) WHERE b.conceptId IS NOT NULL AND a.conceptId IS NOT NULL "
    "RETURN type(r) AS rel, count(r) AS n ORDER BY n DESC LIMIT 10"
)
print("Patient graph concept relationships:", pg_rels)

# Do parent concepts have IS_A children in patient graph?
for label, parent_id in PARENT_CONCEPTS.items():
    isa_rows = pg.run(
        "MATCH (parent)-[:IS_A*1..5]->(child) "
        "WHERE parent.conceptId = $id OR parent.conceptId = $sid "
        "RETURN toString(child.conceptId) AS child_id LIMIT 100",
        id=parent_id,
        sid=str(parent_id),
    )
    child_ids = {int(r["child_id"]) for r in isa_rows if r["child_id"]}
    print(f"\n  {label} IS_A descendants in patient graph: {len(child_ids)}")

    if label == "referral" and child_ids:
        overlap = child_ids & FAST_TRACK_REFERRAL_IDS
        print(f"    Overlap with FAST_TRACK_REFERRAL_IDS: {len(overlap)}/{len(FAST_TRACK_REFERRAL_IDS)}")
    elif label == "diagnosis" and child_ids:
        overlap = child_ids & CANCER_TYPE_IDS
        print(f"    Overlap with CANCER_TYPE_IDS: {len(overlap)}/{len(CANCER_TYPE_IDS)}")
    elif label == "specialist" and child_ids:
        overlap = child_ids & SEEN_BY_SPECIALIST_IDS
        print(f"    Overlap with SEEN_BY_SPECIALIST_IDS: {len(overlap)}/{len(SEEN_BY_SPECIALIST_IDS)}")

# -- 3. Can we match patients via IS_A traversal? --
print("\n" + "=" * 70)
print("PATIENT MATCH VIA IS_A TRAVERSAL")
print("=" * 70)

for label, parent_id in PARENT_CONCEPTS.items():
    rows = pg.run(
        "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[:DOCUMENTS]->(child) "
        "WHERE (child)-[:IS_A*0..5]->(:Disease {conceptId: $sid}) "
        "   OR (child)-[:IS_A*0..5]->(:Procedure {conceptId: $sid}) "
        "   OR (child)-[:IS_A*0..5]->(:Clinical_finding {conceptId: $sid}) "
        "RETURN count(DISTINCT p) AS n",
        sid=str(parent_id),
    )
    n = rows[0]["n"] if rows else 0
    print(f"  {label} ({parent_id}): {n} patients via IS_A traversal")

pg.close()
