"""Check HITL status of unknown completed episodes, and look up carcinoid syndrome."""
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


def main() -> None:
    client = PatientGraphClient()
    kg = KnowledgeGraphClient()

    rows = client.run(
        "MATCH (ep:EpisodeOfCare) "
        "WHERE ep.status = 'completed' AND ep.cancer_type = 'unknown' "
        "RETURN ep.patient_id AS pid, "
        "       ep.hitl_flag AS hitl, "
        "       ep.hitl_reason AS reason, "
        "       ep.referral_date AS ref_date "
        "ORDER BY ep.patient_id"
    )
    print(f"Unknown completed episodes: {len(rows)}")
    hitl_count = sum(1 for r in rows if r.get("hitl"))
    print(f"With hitl_flag=True: {hitl_count}")
    print()
    for r in rows:
        print(f"  Patient {r['pid']}  ref={r['ref_date']}  hitl={r['hitl']}")
        if r.get("reason"):
            print(f"    reason: {str(r['reason'])[:90]}")

    # Check if carcinoid syndrome and other suspects are IS_A descendants
    # of any cancer type base concept in the KG
    print()
    print("=== Checking if suspect concepts are IS_A cancer descendants ===")
    SUSPECTS = ["35868009", "10743008", "78873005"]
    for suspect in SUSPECTS:
        isa_rows = kg.run(
            "MATCH (anc:Concept)<-[:IS_A*1..8]-(d:Concept {id: $cid}) "
            "RETURN anc.id AS anc_id, anc.preferredTerm AS anc_term "
            "LIMIT 5",
            cid=suspect,
        )
        concept_rows = kg.run(
            "MATCH (c:Concept {id: $cid}) "
            "RETURN c.id AS cid, c.preferredTerm AS term, c.semanticTag AS tag",
            cid=suspect,
        )
        if concept_rows:
            cr = concept_rows[0]
            print(f"  {suspect}: {cr.get('term')} [{cr.get('tag')}]")
        else:
            print(f"  {suspect}: NOT in KG Concept nodes")
        for row in isa_rows[:3]:
            print(f"    ancestor: {row['anc_id']} - {row['anc_term']}")

    client.close()
    kg.close()


if __name__ == "__main__":
    main()
