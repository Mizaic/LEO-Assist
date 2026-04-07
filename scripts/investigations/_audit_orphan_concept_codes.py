"""Audit orphaned/retired SNOMED codes in patient encounter data.

For each suspect code:
  - Count encounters using it
  - Show which patients are affected
  - Find the active SNOMED replacement in the Concept hierarchy
  - Show whether the replacement IS_A descendant of 363346000
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

CANCER_ROOT = "363346000"

# All concept IDs that appear in patient encounters but are not covered
# by the IS_A expansion of the cancer root
SUSPECT_IDS = [
    ("269457002", "Malignant neoplasm of esophagus NOS"),
    ("255080008", "Carcinoma of stomach"),
]

_Q_ENCOUNTERS_WITH_CODE = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[:DOCUMENTS]->(c)
WHERE toString(c.conceptId) = $cid
RETURN
  toString(p.id)   AS patient_id,
  toString(e.id)   AS encounter_id,
  toString(e.date) AS enc_date,
  c.name           AS concept_name,
  labels(c)        AS node_labels
ORDER BY enc_date
"""

_Q_CONCEPT_NODE = """
MATCH (c:Concept {id: $cid})
RETURN c.id AS id, c.active AS active, c.fsn AS fsn, c.semantic_tag AS tag
"""

_Q_IS_IN_CANCER_HIERARCHY = """
MATCH (c:Concept {id: $cid})-[:IS_A*1..10]->(root:Concept {id: $root})
RETURN count(*) > 0 AS is_descendant
"""

_Q_ACTIVE_CONCEPTS_WITH_SIMILAR_NAME = """
MATCH (c:Concept)
WHERE c.active = true
  AND toLower(c.fsn) CONTAINS $keyword
OPTIONAL MATCH (c)-[:IS_A*1..5]->(root:Concept {id: $root})
RETURN c.id AS id, c.fsn AS fsn, c.semantic_tag AS tag,
       (root IS NOT NULL) AS in_cancer_root
ORDER BY in_cancer_root DESC, c.fsn
LIMIT 8
"""


def main() -> None:
    kg = KnowledgeGraphClient()
    pg = PatientGraphClient()
    try:
        for cid, label in SUSPECT_IDS:
            print(f"{'='*70}")
            print(f"Code: {cid}  ({label})")

            # 1. Does the Concept node exist?
            concept_rows = kg.run(_Q_CONCEPT_NODE, cid=cid)
            if concept_rows:
                c = concept_rows[0]
                print(f"  :Concept node: active={c['active']}  fsn={c['fsn']}")
            else:
                print(f"  :Concept node: NOT FOUND")

            # 2. Is it in the cancer IS_A hierarchy?
            hier = kg.run(_Q_IS_IN_CANCER_HIERARCHY, cid=cid, root=CANCER_ROOT)
            in_hier = hier[0]['is_descendant'] if hier else False
            print(f"  IS_A descendant of {CANCER_ROOT}: {in_hier}")

            # 3. Encounters in patient data
            with pg.session() as s:
                enc_rows = s.run(_Q_ENCOUNTERS_WITH_CODE, cid=cid).data()
            print(f"  Patient encounters using this code: {len(enc_rows)}")
            for r in enc_rows:
                print(f"    patient={r['patient_id']}  enc={r['encounter_id']}  date={r['enc_date']}  labels={r['node_labels']}")

            # 4. Suggest active replacement
            keyword = label.lower().split("of")[-1].strip().split()[0]  # e.g. 'esophagus', 'stomach'
            print(f"  Active SNOMED concepts containing '{keyword}':")
            active = kg.run(
                _Q_ACTIVE_CONCEPTS_WITH_SIMILAR_NAME,
                keyword=keyword,
                root=CANCER_ROOT,
            )
            for a in active or []:
                flag = " <-- IN CANCER ROOT" if a['in_cancer_root'] else ""
                print(f"    {a['id']}  {a['tag']:<15} {a['fsn']}{flag}")

            print()

    finally:
        kg.close()
        pg.close()


if __name__ == "__main__":
    main()
