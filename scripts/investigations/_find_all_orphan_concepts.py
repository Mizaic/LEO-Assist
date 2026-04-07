"""Find orphaned concept codes used in patient encounters.

Strategy (fast): start from the small set of encounter-documented concept IDs,
look up their :Concept node, then check if that node has any IS_A relationships.
Much faster than scanning all :Concept nodes.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets
load_keyvault_secrets()

from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient

# Step 1: get all distinct concept IDs appearing in patient encounter documents
_Q_DISTINCT_ENCOUNTER_CONCEPTS = """
MATCH (e:Encounter)-[:DOCUMENTS]->(c)
WHERE c.conceptId IS NOT NULL
  AND NOT 'Concept' IN labels(c)
RETURN DISTINCT
  toString(c.conceptId)   AS cid,
  c.name                  AS name,
  c.semanticTag           AS tag,
  count(e)                AS enc_count
ORDER BY enc_count DESC
"""

# Step 2: for a batch of IDs, check IS_A status in the Concept hierarchy
_Q_CHECK_CONCEPT_ISA = """
UNWIND $cids AS cid
OPTIONAL MATCH (c:Concept {id: cid})
OPTIONAL MATCH (c)-[:IS_A]->(parent:Concept)
OPTIONAL MATCH (child:Concept)-[:IS_A]->(c)
RETURN
  cid,
  c IS NOT NULL            AS concept_exists,
  c.active                 AS active,
  c.fsn                    AS fsn,
  c.semantic_tag           AS concept_tag,
  parent IS NOT NULL       AS has_isa_parent,
  child  IS NOT NULL       AS has_isa_child
"""

CANCER_ROOT = "363346000"

# Step 3: for confirmed orphans, check if ancestor is reachable via any path
_Q_REACHABLE_FROM_ROOT = """
MATCH (root:Concept {id: $root})<-[:IS_A*1..10]-(c:Concept {id: $cid})
RETURN count(c) > 0 AS reachable
"""


def main() -> None:
    kg = KnowledgeGraphClient()
    pg = PatientGraphClient()
    try:
        print("Step 1: collecting distinct concept IDs from patient encounters...")
        with pg.session() as s:
            enc_rows = s.run(_Q_DISTINCT_ENCOUNTER_CONCEPTS).data() or []
        print(f"  Distinct concept IDs in encounter data: {len(enc_rows)}")

        all_cids = [r["cid"] for r in enc_rows]
        enc_by_cid = {r["cid"]: r for r in enc_rows}

        print("Step 2: checking IS_A status for each concept in hierarchy...")
        results = []
        batch_size = 200
        for i in range(0, len(all_cids), batch_size):
            batch = all_cids[i : i + batch_size]
            rows = kg.run(_Q_CHECK_CONCEPT_ISA, cids=batch) or []
            results.extend(rows)

        # Classify
        no_concept_node = []   # no :Concept node at all
        orphan_in_graph = []   # :Concept node exists but no IS_A
        connected = []         # :Concept node with IS_A

        for r in results:
            cid = r["cid"]
            if not r["concept_exists"]:
                no_concept_node.append(cid)
            elif not r["has_isa_parent"] and not r["has_isa_child"]:
                orphan_in_graph.append(r)
            else:
                connected.append(cid)

        print(f"\n  :Concept node found + connected via IS_A : {len(connected)}")
        print(f"  No :Concept node at all                 : {len(no_concept_node)}")
        print(f"  :Concept node exists but IS_A ORPHAN    : {len(orphan_in_graph)}")

        if orphan_in_graph:
            print()
            print("=== IS_A orphans in patient encounter data ===")
            print(f"  {'concept_id':<18} {'active':<7} {'enc_count':>9}  {'tag':<20}  fsn")
            print("  " + "-" * 100)
            for r in sorted(orphan_in_graph, key=lambda x: -enc_by_cid.get(x["cid"], {}).get("enc_count", 0)):
                cid = r["cid"]
                enc_count = enc_by_cid.get(cid, {}).get("enc_count", 0)
                active = str(r.get("active") or "?")
                tag = str(r.get("concept_tag") or enc_by_cid.get(cid, {}).get("tag") or "")[:20]
                fsn = str(r.get("fsn") or enc_by_cid.get(cid, {}).get("name") or "")[:65]
                print(f"  {cid:<18} {active:<7} {enc_count:>9}  {tag:<20}  {fsn}")

        if no_concept_node:
            print()
            print(f"=== Concepts in encounters with NO :Concept node in hierarchy ({len(no_concept_node)}) ===")
            print("  (These can't be IS_A expanded at all -- encounter-only codes)")
            top = sorted(no_concept_node, key=lambda c: -enc_by_cid.get(c, {}).get("enc_count", 0))[:20]
            for cid in top:
                enc = enc_by_cid.get(cid, {})
                print(f"  {cid:<18}  enc_count={enc.get('enc_count',0):>5}  {str(enc.get('name',''))[:65]}")

    finally:
        kg.close()
        pg.close()


if __name__ == "__main__":
    main()
