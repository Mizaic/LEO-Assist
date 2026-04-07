"""Check why specific cancer concepts miss IS_A expansion, and probe related endpoint utility."""
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

from libs.neo4j_client.client import KnowledgeGraphClient

# Concepts present in patient encounters but missing from IS_A expansion of 363346000
MISSING_CANCER_IDS = [
    "269457002",  # Malignant neoplasm of esophagus NOS
    "255080008",  # Carcinoma of stomach
    "189336000",  # Carcinoma in situ of breast
]

CANCER_ROOT = "363346000"

_Q_CONCEPT_EXISTS = """
MATCH (c:Concept {id: $cid})
RETURN c.id AS id, c.active AS active, c.fsn AS fsn, c.semantic_tag AS tag
"""

_Q_ISA_ANCESTORS = """
MATCH (c:Concept {id: $cid})-[:IS_A*1..10]->(anc:Concept)
WHERE anc.active = true
RETURN anc.id AS ancestor_id, anc.fsn AS ancestor_fsn
ORDER BY anc.id
LIMIT 30
"""

_Q_ISA_ANCESTORS_INACTIVE = """
MATCH (c:Concept {id: $cid})-[:IS_A*1..10]->(anc:Concept)
RETURN anc.id AS ancestor_id, anc.fsn AS ancestor_fsn, anc.active AS active
ORDER BY anc.id
LIMIT 30
"""

_Q_DEPTH_TO_ROOT = """
MATCH path = shortestPath(
  (c:Concept {id: $cid})-[:IS_A*]->(root:Concept {id: $root})
)
RETURN length(path) AS depth
"""

# For the related endpoint use case:
# Check which encounter procedures have HAS_ASSOCIATED_FINDING -> cancer concept
_Q_PROCEDURE_TO_CANCER = """
MATCH (proc:Concept)-[:HAS_ASSOCIATED_FINDING]->(finding:Concept)
WHERE proc.active = true AND finding.active = true
OPTIONAL MATCH (finding)-[:IS_A*1..5]->(cancer_root:Concept {id: '363346000'})
WITH proc, finding, cancer_root
WHERE cancer_root IS NOT NULL
RETURN proc.id AS proc_id, proc.fsn AS proc_fsn,
       finding.id AS finding_id, finding.fsn AS finding_fsn
LIMIT 20
"""

# Stale episodes: which post-referral procedures are linked via HAS_ASSOCIATED_FINDING to cancer?
_Q_ENCOUNTER_PROCS_WITH_CANCER_FINDING = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[:DOCUMENTS]->(doc)
WHERE doc.semanticTag = 'Procedure'
MATCH (c:Concept {id: toString(doc.conceptId)})-[:HAS_ASSOCIATED_FINDING]->(f:Concept)
WHERE f.active = true
OPTIONAL MATCH (f)-[:IS_A*1..5]->(root:Concept {id: '363346000'})
WITH doc, c, f, root, count(e) AS enc_count
WHERE root IS NOT NULL
RETURN c.id AS proc_concept_id, c.fsn AS proc_name,
       f.id AS finding_id, f.fsn AS finding_name,
       enc_count
ORDER BY enc_count DESC
LIMIT 20
"""


def main() -> None:
    kg = KnowledgeGraphClient()
    try:
        print("=== Missing cancer concepts: do they exist in Concept hierarchy? ===")
        for cid in MISSING_CANCER_IDS:
            rows = kg.run(_Q_CONCEPT_EXISTS, cid=cid)
            if not rows:
                print(f"  {cid}: NOT FOUND as :Concept node (only exists as Disease/Clinical_finding)")
            else:
                r = rows[0]
                print(f"  {cid}: FOUND -- active={r['active']} tag={r['tag']}  fsn={r['fsn']}")

            # Try to find path to cancer root
            depth_rows = kg.run(_Q_DEPTH_TO_ROOT, cid=cid, root=CANCER_ROOT)
            if depth_rows:
                print(f"    IS_A depth to {CANCER_ROOT}: {depth_rows[0]['depth']} hops")
            else:
                anc_rows = kg.run(_Q_ISA_ANCESTORS_INACTIVE, cid=cid)
                if anc_rows:
                    print(f"    Ancestors found ({len(anc_rows)}), but root {CANCER_ROOT} not reachable")
                    for a in anc_rows[:5]:
                        print(f"      {a['ancestor_id']} (active={a['active']}) {str(a['ancestor_fsn'])[:60]}")
                else:
                    print(f"    No IS_A ancestors found at all")
            print()

        print("=== HAS_ASSOCIATED_FINDING: procedures -> cancer findings ===")
        proc_rows = kg.run(_Q_PROCEDURE_TO_CANCER)
        if not proc_rows:
            print("  No HAS_ASSOCIATED_FINDING relationships from procedures to cancer concepts found")
        else:
            for r in proc_rows:
                print(f"  {r['proc_id']} {str(r['proc_fsn'])[:50]:50s} -> {r['finding_id']} {str(r['finding_fsn'])[:50]}")

        print()
        print("=== Encounter procedures in patient data that link via HAS_ASSOCIATED_FINDING to cancer ===")
        enc_rows = kg.run(_Q_ENCOUNTER_PROCS_WITH_CANCER_FINDING)
        if not enc_rows:
            print("  None found -- HAS_ASSOCIATED_FINDING data may not be loaded")
        else:
            for r in enc_rows:
                print(f"  {r['enc_count']:>4}x {str(r['proc_name'])[:55]:55s} -> {str(r['finding_name'])[:50]}")

    finally:
        kg.close()


if __name__ == "__main__":
    main()
