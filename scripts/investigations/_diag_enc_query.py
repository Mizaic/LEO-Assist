"""Diagnose why the encounter query returns no results."""

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

SAMPLE_PID = "9990010021"
SAMPLE_DATE = "2025-03-12"

client = PatientGraphClient()

r = client.run("MATCH (p:Patient) RETURN count(p) AS n")
print("Patient nodes:", r[0]["n"])

r2 = client.run("MATCH (e:Encounter) RETURN count(e) AS n")
print("Encounter nodes:", r2[0]["n"])

r3 = client.run("MATCH (p:Patient) RETURN p.id LIMIT 3")
for row in r3:
    print("  p.id sample:", repr(row["p.id"]), type(row["p.id"]).__name__)

# Check if any encounters link to this patient
r4 = client.run(
    "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
    "WHERE toString(p.id) = $pid "
    "RETURN e.date, e.id LIMIT 3",
    pid=SAMPLE_PID,
)
print(f"\nEncounters for {SAMPLE_PID} (any date):")
for row in r4:
    print("  date:", repr(row["e.date"]), "  id:", repr(row["e.id"]))

if not r4:
    print("  (none found via HAS_ENCOUNTER)")

# Try matching the EpisodeOfCare patient_id directly
r5 = client.run(
    "MATCH (ep:EpisodeOfCare {patient_id: $pid}) "
    "RETURN ep.referral_date, ep.cancer_type LIMIT 3",
    pid=SAMPLE_PID,
)
print(f"\nEpisodeOfCare nodes for {SAMPLE_PID}:")
for row in r5:
    print(
        "  ref_date:", repr(row["ep.referral_date"]), "  site:", row["ep.cancer_type"]
    )

# Try querying encounters by patient_id on Encounter (some schemas store pid on encounter)
r6 = client.run(
    "MATCH (e:Encounter) WHERE e.patient_id = $pid OR toString(e.patient_id) = $pid "
    "RETURN e.date, e.id LIMIT 3",
    pid=SAMPLE_PID,
)
print(f"\nEncounters with patient_id on node for {SAMPLE_PID}:")
for row in r6:
    print("  date:", repr(row["e.date"]), "  id:", repr(row["e.id"]))

# Check the anchor_detector's approach
r7 = client.run(
    "MATCH (p:Patient {id: $pid})-[:HAS_ENCOUNTER]->(e:Encounter) "
    "RETURN count(e) AS n",
    pid=int(SAMPLE_PID),
)
print(f"\nEncounters (int patient id) for {SAMPLE_PID}:", r7[0]["n"] if r7 else "error")

# Date type check
r8 = client.run("MATCH (e:Encounter) RETURN e.date LIMIT 1")
if r8:
    d = r8[0]["e.date"]
    print("\nSample e.date:", repr(d), type(d).__name__)

client.close()
