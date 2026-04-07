"""
Check exactly why STALE-NODIAG episodes with cancer codes are not being detected.
Tests:
  1. Are the specific concept IDs (SCC, BCC, melanoma) in IS_A depth<=5 of 363346000?
  2. Does the assertion filter in the registry exclude 'possible'?
  3. What does the registry actually have in its cancer_types bucket?
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

# Specific concept IDs from the STALE encounters
SKIN_CONCEPT_IDS = {
    "254651007": "Squamous cell carcinoma of skin",
    "254701007": "Basal cell carcinoma of skin",
    "93655004":  "Malignant melanoma of skin",
    "302837001": "Lentigo maligna melanoma",
}

_Q_IS_DESCENDANT = """
MATCH (root:Concept {id: '363346000'})<-[:IS_A*1..5]-(d:Concept {id: $cid})
RETURN d.id AS cid, d.fsn AS fsn, d.active AS active
"""

_Q_IS_DESCENDANT_DEEPER = """
MATCH path = (root:Concept {id: '363346000'})<-[:IS_A*]-(d:Concept {id: $cid})
RETURN d.id AS cid, d.fsn AS fsn, length(path) AS depth
LIMIT 1
"""

_Q_VS_CONCEPT_IDS = """
MATCH (vs:ValueSet)
WHERE vs.name IN ['cancer_types', 'cancer_audit'] OR vs.milestoneType = 'diagnosis'
RETURN vs.name AS name, vs.milestoneType AS mt, size(vs.conceptIds) AS n_ids,
       vs.conceptIds[0..5] AS sample_ids
"""

_Q_REGISTRY_HAS_SCC = """
MATCH (vs:ValueSet)
WHERE vs.milestoneType = 'diagnosis'
  AND $cid IN vs.conceptIds
RETURN vs.name AS vs_name
"""

_Q_ASSERTION_FILTER = """
MATCH (vs:ValueSet)
WHERE vs.milestoneType = 'diagnosis'
RETURN vs.name AS name, vs.assertionFilter AS assertion_filter
"""


def main():
    kg = KnowledgeGraphClient()
    pg = PatientGraphClient()
    try:
        print("=== 1. Are specific skin cancer concept IDs in IS_A depth<=5? ===")
        for cid, label in SKIN_CONCEPT_IDS.items():
            with kg.session() as s:
                r = s.run(_Q_IS_DESCENDANT, cid=cid).single()
            if r:
                print(f"  YES depth<=5: {cid} ({label})")
            else:
                with kg.session() as s:
                    r2 = s.run(_Q_IS_DESCENDANT_DEEPER, cid=cid).single()
                if r2:
                    print(f"  MISS - depth={r2['depth']}: {cid} ({label}) -- TOO DEEP for anchor engine")
                else:
                    print(f"  NOT IN HIERARCHY at any depth: {cid} ({label})")

        print()
        print("=== 2. ValueSet nodes with milestoneType=diagnosis ===")
        with pg.session() as s:
            rows = s.run(_Q_VS_CONCEPT_IDS).data()
        for r in rows:
            print(f"  {r['name']} | mt={r['mt']} | n_ids={r['n_ids']} | sample={r['sample_ids']}")

        print()
        print("=== 3. Is SCC of skin (254651007) in any diagnosis ValueSet? ===")
        for cid, label in SKIN_CONCEPT_IDS.items():
            with pg.session() as s:
                rows = s.run(_Q_REGISTRY_HAS_SCC, cid=cid).data()
            if rows:
                print(f"  FOUND in ValueSet: {cid} ({label}) -> {[r['vs_name'] for r in rows]}")
            else:
                print(f"  NOT IN ANY ValueSet: {cid} ({label})")

        print()
        print("=== 4. Assertion filters on diagnosis ValueSets ===")
        with pg.session() as s:
            rows = s.run(_Q_ASSERTION_FILTER).data()
        for r in rows:
            print(f"  {r['name']} | assertion_filter={r['assertion_filter']}")

        print()
        print("=== 5. What assertions are on cancer diagnoses in completed vs stale? ===")
        _Q_DIAG_ASSERTIONS = """
        MATCH (ep:EpisodeOfCare)<-[:IS_PART_OF]-(enc:Encounter)-[r:DOCUMENTS]->(c)
        WHERE ep.status IN ['completed', 'stale_no_diagnosis']
        RETURN ep.status AS status,
               coalesce(r.assertion, 'present') AS assertion,
               count(*) AS cnt
        ORDER BY status, cnt DESC
        """
        # This needs IS_PART_OF to exist - skip if not
        # Instead, check assertions on encounters for stale patients
        _Q_STALE_ASSERTIONS = """
        MATCH (p:Patient)-[:HAS_ENCOUNTER]->(enc:Encounter)-[r:DOCUMENTS]->(c)
        WHERE toString(p.id) IN $pids
          AND c.conceptId IN [254651007, 254701007, 93655004, 302837001]
        RETURN toString(p.id) AS pid, enc.date AS date,
               c.conceptId AS cid, c.name AS name,
               coalesce(r.assertion, 'present') AS assertion,
               r.source AS source
        ORDER BY enc.date
        """
        stale_pids = [4203796334, 4921442355, 4940120139, 6261656266]
        with pg.session() as s:
            rows = s.run(_Q_STALE_ASSERTIONS, pids=stale_pids).data()
        for r in rows:
            print(f"  pid={r['pid']} {r['date']} | cid={r['cid']} | assertion={r['assertion']} | {r['name']}")

    finally:
        kg.close()
        pg.close()


if __name__ == "__main__":
    main()
