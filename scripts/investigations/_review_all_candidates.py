"""Pull full encounter text for ALL uncoded T1/T2 candidates (excluding in-remission)."""

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

# All uncoded, non-excluded, non-remission encounters from the inventory
CANDIDATES = [
    ("4187508279", "8feea974-ab6a-4b12-a737-fda7e4b3afa8", "no malignancy"),
    ("4209455806", "15911be4-fc30-4de8-bb0c-8f54f3cb50f0", "no malignancy (OGD)"),
    ("4245896566", "1783873c-6be2-4682-874d-21f17d905e1f", "cancer excluded"),
    (
        "4802241127",
        "99da05a8-8cfa-40d6-b227-d58524ff1f95",
        "no evidence of metastatic disease",
    ),
    (
        "4842019832",
        "8fbb5daf-7bb7-411b-97f0-00c50b82ca1d",
        "no malignancy (colonoscopy)",
    ),
    ("4867552062", "b2b0ab38-76cb-4a04-9731-ab7d6920cea5", "no mets"),
    ("6142203497", "984b01e4-67b4-4b8f-93ce-282e0273df81", "no mets (hip pain)"),
    ("6261656266", "64a7bee5-de05-4e47-be76-b4cf318d4038", "no metastatic disease"),
    ("6507904570", "0f1d01ac-9f7c-40a1-aeec-b58ecdb2756e", "benign histology (T2)"),
    (
        "7324271383",
        "60d51cc3-2492-4e75-8a05-47577e14414c",
        "no metastatic disease (dermatology)",
    ),
]

client = PatientGraphClient()
with client.session() as s:
    for pid, eid, phrase_label in CANDIDATES:
        rec = s.run(
            "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
            "WHERE toString(e.id) = $eid "
            "RETURN coalesce(e.text, e.note, e.description, '') AS text, "
            "coalesce(toString(e.date), '') AS date",
            eid=eid,
        ).single()
        if not rec:
            print(f"\n[NOT FOUND] pid={pid} enc={eid[:8]}")
            continue
        print()
        print("=" * 70)
        print(f"  pid={pid}  enc={eid[:8]}  date={rec['date'][:10]}  [{phrase_label}]")
        print("=" * 70)
        print(rec["text"])
client.close()
