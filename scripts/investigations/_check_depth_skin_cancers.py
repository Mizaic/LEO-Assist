"""
Check IS_A depth for specific skin cancer concepts that are appearing as STALE-NODIAG.
Also check what assertion/source these encounters have.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

from libs.neo4j_client.client import PatientGraphClient, KnowledgeGraphClient

# skin cancers that are appearing as STALE-NODIAG but with cancer codes on referral date
_SUSPECTED_MISSING = [
    ("Squamous cell carcinoma of skin", None),
    ("Malignant melanoma of skin", None),
    ("Basal cell carcinoma", None),
]

# depth check from cancer root
_Q_DEPTH = """
MATCH path = (root:Concept {id: '363346000'})<-[:IS_A*1..10]-(d:Concept)
WHERE d.active = true AND toLower(d.fsn) CONTAINS $keyword
RETURN d.id AS cid, d.fsn AS fsn, length(path) AS depth
ORDER BY depth
LIMIT 5
"""

# find what concept IDs these patients actually have
_Q_ENC_DETAIL = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(enc:Encounter)-[r:DOCUMENTS]->(c)
WHERE toString(p.id) IN $pids
  AND (toLower(c.name) CONTAINS 'squamous' OR toLower(c.name) CONTAINS 'melanoma'
    OR toLower(c.name) CONTAINS 'basal cell')
RETURN DISTINCT toString(p.id) AS pid, enc.date AS date, c.name AS name,
       c.conceptId AS concept_id, c.semanticTag AS tag,
       r.assertion AS assertion, r.source AS source
ORDER BY enc.date
"""

# check if those concept IDs exist in cancer_types ValueSet expand
_Q_IN_VALUESET = """
MATCH (vs:ValueSet {name: 'cancer_types'})
WITH vs, vs.conceptIds AS ids
UNWIND ids AS id
RETURN id
LIMIT 1
"""

# check the full expand from anchor.py to see if SCC of skin is captured
_Q_ISA_CHECK = """
MATCH (root:Concept {id: '363346000'})<-[:IS_A*1..5]-(d:Concept)
WHERE d.active = true
  AND (toLower(d.fsn) CONTAINS 'squamous cell carcinoma of skin'
    OR toLower(d.fsn) CONTAINS 'malignant melanoma'
    OR toLower(d.fsn) CONTAINS 'basal cell carcinoma of skin')
RETURN d.id AS cid, d.fsn AS fsn
"""

_STALE_NODIAG_SKIN_PIDS = ["9990002010", "9990003002", "9990002011", "9990002012"]


def main():
    kg = KnowledgeGraphClient()
    pg = PatientGraphClient()
    try:
        print("=== IS_A depth check (depth 1..10 from 363346000) ===")
        for label, _ in _SUSPECTED_MISSING:
            keyword = label.lower().split(" ")[0]  # first word
            with kg.session() as s:
                rows = s.run(_Q_DEPTH, keyword=keyword).data()
            if rows:
                for r in rows[:3]:
                    print(
                        f"  '{label}' -> depth={r['depth']}  id={r['cid']}  {r['fsn']}"
                    )
            else:
                print(f"  '{label}' -> NOT FOUND at any depth from 363346000")

        print()
        print("=== IS_A check at depth <=5 (anchor engine depth) ===")
        with kg.session() as s:
            rows = s.run(_Q_ISA_CHECK).data()
        if rows:
            for r in rows:
                print(f"  FOUND at depth<=5: {r['cid']}  {r['fsn']}")
        else:
            print(
                "  NONE of these concepts are within depth 5 of 363346000 -- BUG CONFIRMED"
            )

        print()
        print("=== Encounter detail for STALE-NODIAG skin patients ===")
        with pg.session() as s:
            rows = s.run(_Q_ENC_DETAIL, pids=_STALE_NODIAG_SKIN_PIDS).data()
        if rows:
            for r in rows:
                print(f"  pid={r['pid']} date={r['date']} concept_id={r['concept_id']}")
                print(f"    name={r['name']}")
                print(f"    assertion={r['assertion']} source={r['source']}")
        else:
            print("  No encounters found for these patients with skin cancer concepts")

    finally:
        kg.close()
        pg.close()


if __name__ == "__main__":
    main()
