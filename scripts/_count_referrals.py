"""Quick count of patients with referrals by different methods."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "api"))

from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env")

from libs.neo4j_client.client import PatientGraphClient

client = PatientGraphClient()

r1 = client.run("MATCH (p:Patient) RETURN count(p) AS total")
print("Total patients:", [dict(r) for r in r1])

r2 = client.run(
    "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[d:DOCUMENTS]->(c) "
    "WHERE d.domain IN ['fast_track_referrals'] "
    "RETURN count(DISTINCT p) AS n"
)
print("Patients with DOCUMENTS fast_track_referrals:", [dict(r) for r in r2])

r3 = client.run(
    "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
    "WHERE e.text CONTAINS 'Fast track referral' "
    "   OR e.text CONTAINS 'fast track referral' "
    "RETURN count(DISTINCT p) AS n"
)
print("Patients with 'fast track referral' in encounter text:", [dict(r) for r in r3])

r4 = client.run(
    "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
    "WHERE e.text CONTAINS 'Seen in fast track' "
    "   OR e.text CONTAINS 'seen in fast track' "
    "RETURN count(DISTINCT p) AS n"
)
print("Patients with 'seen in fast track' in encounter text:", [dict(r) for r in r4])

r5 = client.run(
    "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
    "WHERE e.text CONTAINS '2WW' OR e.text CONTAINS '2ww' "
    "RETURN count(DISTINCT p) AS n"
)
print("Patients with '2WW' in encounter text:", [dict(r) for r in r5])

client.close()
