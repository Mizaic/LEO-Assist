"""Pull full encounter text for the four candidates under review."""

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

CANDIDATES = {
    "6142203497 - no mets (minor injuries, hip pain)": "984b01e4-67b4-4b8f-93ce-282e0273df81",
}

client = PatientGraphClient()
with client.session() as s:
    for label, eid in CANDIDATES.items():
        rec = s.run(
            "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
            "WHERE toString(e.id) = $eid "
            "RETURN toString(p.id) AS pid, "
            "coalesce(e.text, e.note, e.description, '') AS text, "
            "coalesce(toString(e.date), '') AS date",
            eid=eid,
        ).single()
        print(f"\n{'='*70}")
        print(f"  {label}")
        print(f"  pid={rec['pid']}  date={rec['date'][:10]}")
        print(f"{'='*70}")
        print(rec["text"])
client.close()
