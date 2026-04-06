"""Check the 8 'in remission' encounters to verify cancer context before pinning."""
import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets
load_keyvault_secrets()
from libs.neo4j_client.client import PatientGraphClient

INVENTORY = ROOT / "scripts" / "investigations" / "encounter_audit" / "no_cancer_phrase_inventory.jsonl"

with INVENTORY.open() as fh:
    rows = [json.loads(l) for l in fh]

remission_encs = [
    r["encounter_id"] for r in rows
    if "in remission" in r.get("matched_phrases", [])
    and not r.get("already_coded_395100000")
    and not r.get("excluded")
]

print(f"Encounters with 'in remission' (uncoded): {len(remission_encs)}")

client = PatientGraphClient()
with client.session() as s:
    for eid in remission_encs:
        rec = s.run(
            "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) WHERE toString(e.id) = $eid "
            "RETURN toString(p.id) AS pid, coalesce(e.text, e.note, e.description, '') AS text, "
            "coalesce(toString(e.date),'') AS date",
            eid=eid,
        ).single()
        if not rec:
            continue
        print()
        print(f"  enc={eid[:8]}...  pid={rec['pid']}  date={rec['date'][:10]}")
        print(f"  text: {rec['text'][:300].replace(chr(10), ' ')!r}")
client.close()
