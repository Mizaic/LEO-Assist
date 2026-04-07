"""Check whether the diagnosis domain uses flat concept IDs or IS_A hierarchy expansion,
and whether there is any LIMIT in the Cypher that fetches anchor concepts."""
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

from libs.neo4j_client.client import PatientGraphClient

# SNOMED code for "Malignant neoplastic disease (disorder)"
MALIGNANT_ROOT = "363346000"

_Q_VALUESETS = """
MATCH (v:ValueSet)
WHERE v.milestoneType = 'diagnosis'
RETURN v.name AS name, v.id AS id, v.title AS title
"""

_Q_CONCEPTS_IN_VS = """
MATCH (v:ValueSet {name: $vname})-[:CONTAINS]->(c)
RETURN count(DISTINCT c) AS cnt
"""

_Q_SAMPLE_CONCEPTS = """
MATCH (v:ValueSet {name: $vname})-[:CONTAINS]->(c)
RETURN c.code AS code, c.name AS name
LIMIT 10
"""

_Q_ISA_DESCENDANTS = """
MATCH (c)-[:IS_A*1..]->(root {code: $root_code})
RETURN count(DISTINCT c) AS descendants
"""

_Q_ISA_DIRECT = """
MATCH (c)-[:IS_A]->(root {code: $root_code})
RETURN count(DISTINCT c) AS direct
"""

_Q_TOTAL_CONCEPTS_IN_DIAGNOSIS_DOMAINS = """
MATCH (v:ValueSet)-[:CONTAINS]->(c)
WHERE v.milestoneType = 'diagnosis'
RETURN count(DISTINCT c) AS total
"""

_Q_MALIGNANT_IN_GRAPH_BY_NAME = """
MATCH (c)
WHERE (c:Concept OR c:SCTConcept OR c:SnomedConcept)
  AND toLower(c.name) CONTAINS 'malignant'
RETURN count(c) AS cnt
"""

_Q_CONCEPT_LABELS = """
MATCH (c)-[:IS_A]->(root)
WHERE root.code = '363346000'
RETURN labels(c) AS lbl, labels(root) AS root_lbl
LIMIT 1
"""

_Q_ANY_CONCEPT_LABELS = """
MATCH (v:ValueSet)-[:CONTAINS]->(c)
WHERE v.milestoneType = 'diagnosis'
RETURN labels(c) AS lbl
LIMIT 1
"""


def main() -> None:
    client = PatientGraphClient()
    try:
        with client.session() as s:
            print("=== Diagnosis ValueSets ===")
            vs_rows = s.run(_Q_VALUESETS).data()
            for r in vs_rows:
                cnt = s.run(_Q_CONCEPTS_IN_VS, vname=r["name"]).single()["cnt"]
                print(f"  {r['name']!r:40s}  concepts: {cnt}")
                sample = s.run(_Q_SAMPLE_CONCEPTS, vname=r["name"]).data()
                for sc in sample:
                    print(f"    code={sc['code']}  {sc['name']}")

            print()
            total = s.run(_Q_TOTAL_CONCEPTS_IN_DIAGNOSIS_DOMAINS).single()["total"]
            print(f"Total distinct concepts across all diagnosis ValueSets: {total}")

            print()
            print("=== IS_A hierarchy in graph ===")
            lbl_row = s.run(_Q_CONCEPT_LABELS).data()
            if lbl_row:
                print(f"  Labels on IS_A child: {lbl_row[0]['lbl']}, root: {lbl_row[0]['root_lbl']}")
                direct = s.run(_Q_ISA_DIRECT, root_code=MALIGNANT_ROOT).single()["direct"]
                print(f"  Direct IS_A children of {MALIGNANT_ROOT}: {direct}")
                print("  Counting all IS_A descendants (may take a moment)...")
                desc = s.run(_Q_ISA_DESCENDANTS, root_code=MALIGNANT_ROOT).single()["descendants"]
                print(f"  All IS_A descendants of {MALIGNANT_ROOT}: {desc}")
            else:
                print("  No IS_A relationships found from code 363346000 -- hierarchy may not be in graph")

            print()
            any_lbl = s.run(_Q_ANY_CONCEPT_LABELS).data()
            if any_lbl:
                print(f"  Labels on ValueSet concept nodes: {any_lbl[0]['lbl']}")

            print()
            print("=== Malignant concepts by name in graph ===")
            mal_cnt = s.run(_Q_MALIGNANT_IN_GRAPH_BY_NAME).single()["cnt"]
            print(f"  Nodes with 'malignant' in name: {mal_cnt}")

    finally:
        client.close()


if __name__ == "__main__":
    main()
