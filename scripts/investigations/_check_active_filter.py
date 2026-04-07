"""Confirm whether retired codes appear in patient records and whether active replacements cover them."""
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

CANCER_ROOT = "363346000"

_Q_ACTIVE_VS_INACTIVE = """
MATCH (ancestor:Concept {id: $root})<-[:IS_A*1..10]-(d:Concept)
RETURN
  sum(CASE WHEN d.active = true  THEN 1 ELSE 0 END) AS active_count,
  sum(CASE WHEN d.active = false THEN 1 ELSE 0 END) AS inactive_count
"""

_Q_INACTIVE_IN_PATIENT_DATA = """
MATCH (ancestor:Concept {id: $root})<-[:IS_A*1..10]-(d:Concept)
WHERE d.active = false
WITH collect(d.id) AS inactive_ids
MATCH (enc:Encounter)-[:DOCUMENTS]->(c)
WHERE toString(c.conceptId) IN inactive_ids
RETURN DISTINCT c.conceptId AS conceptId, c.name AS name, count(enc) AS enc_count
ORDER BY enc_count DESC
"""

_Q_ACTIVE_REPLACEMENTS = """
// For each inactive concept that appears in patient data,
// find what SNOMED says the replacement is (via SAME_AS or active ancestor)
MATCH (ancestor:Concept {id: $root})<-[:IS_A*1..10]-(retired:Concept)
WHERE retired.active = false
WITH collect(retired.id) AS retired_ids
MATCH (enc:Encounter)-[:DOCUMENTS]->(c)
WHERE toString(c.conceptId) IN retired_ids
WITH DISTINCT c.conceptId AS dead_cid, c.name AS dead_name
MATCH (dead:Concept {id: toString(dead_cid)})
OPTIONAL MATCH (dead)<-[:IS_A]-(child:Concept)
OPTIONAL MATCH (dead)-[:IS_A]->(parent:Concept)
RETURN dead_cid, dead_name, dead.active AS active,
       collect(DISTINCT parent.id)[0] AS parent_id,
       collect(DISTINCT parent.fsn)[0] AS parent_fsn,
       collect(DISTINCT parent.active)[0] AS parent_active
"""

_Q_UI_VARIANT_COUNT = """
// Count how many descendants the UI would show at each depth
MATCH (ancestor:Concept {id: $root})<-[:IS_A*1..{depth}]-(d:Concept)
WHERE d.active = true
RETURN count(DISTINCT d) AS count
"""

def main() -> None:
    kg = KnowledgeGraphClient()
    pg = PatientGraphClient()
    try:
        print("=== Active vs inactive descendants of 363346000 (unlimited depth) ===")
        r = kg.run(_Q_ACTIVE_VS_INACTIVE, root=CANCER_ROOT)
        if r:
            print(f"  Active descendants  : {r[0]['active_count']}")
            print(f"  Inactive descendants: {r[0]['inactive_count']}")

        print()
        print("=== Depth-by-depth active descendant counts ===")
        for depth in [1, 2, 3, 5, 7, 10]:
            q = f"""
            MATCH (ancestor:Concept {{id: '{CANCER_ROOT}'}})<-[:IS_A*1..{depth}]-(d:Concept)
            WHERE d.active = true
            RETURN count(DISTINCT d) AS cnt
            """
            r2 = kg.run(q)
            cnt = r2[0]['cnt'] if r2 else 0
            print(f"  depth <= {depth:>2}: {cnt:>6} active concepts")

        print()
        print("=== Inactive cancer concepts actually in patient encounter records ===")
        rows = kg.run(_Q_INACTIVE_IN_PATIENT_DATA, root=CANCER_ROOT)
        if not rows:
            print("  None -- all encounter cancer concepts are active SNOMED codes")
        else:
            for r in rows:
                print(f"  conceptId={r['conceptId']:>15}  enc_count={r['enc_count']:>4}  {r['name']}")

        print()
        print("=== For each retired code in patient data: what is its active parent? ===")
        rows2 = kg.run(_Q_ACTIVE_REPLACEMENTS, root=CANCER_ROOT)
        for r in rows2:
            print(f"  RETIRED {r['dead_cid']} '{r['dead_name']}'")
            print(f"    -> parent {r['parent_id']} (active={r['parent_active']}) '{r['parent_fsn']}'")

    finally:
        kg.close()
        pg.close()


if __name__ == "__main__":
    main()
