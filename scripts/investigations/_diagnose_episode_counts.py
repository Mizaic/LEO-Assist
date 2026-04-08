"""Diagnose why episode count exceeds expected patient count for a date range."""
from __future__ import annotations
import sys
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets
load_keyvault_secrets()

from libs.neo4j_client.client import PatientGraphClient

DATE_FROM = "2025-01-01"
DATE_TO   = "2025-12-31"

client = PatientGraphClient()
try:
    rows = client.run(
        "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
        "WHERE ep.referral_date >= $df AND ep.referral_date <= $dt "
        "RETURN toString(p.id) AS pid, ep.cancer_type AS ctype, "
        "       ep.status AS status, toString(ep.referral_date) AS rdate "
        "ORDER BY pid, rdate",
        df=DATE_FROM, dt=DATE_TO,
    )

    unique_patients = len({r["pid"] for r in rows})
    eps_per_patient = Counter()
    for r in rows:
        eps_per_patient[r["pid"]] += 1

    counts = Counter(eps_per_patient.values())
    multi = [(pid, n) for pid, n in eps_per_patient.items() if n > 1]

    print(f"Total episodes in {DATE_FROM} to {DATE_TO}: {len(rows)}")
    print(f"Unique patients                           : {unique_patients}")
    print()
    print("Episodes per patient distribution:")
    for n in sorted(counts):
        print(f"  {n} episode(s): {counts[n]} patients")
    print()
    if multi:
        print(f"Patients with 2+ episodes in range ({len(multi)}):")
        for pid, n in sorted(multi, key=lambda x: -x[1])[:20]:
            patient_rows = [r for r in rows if r["pid"] == pid]
            for r in patient_rows:
                print(f"  pid={pid}  ctype={r['ctype']:25s}  status={r['status']:25s}  rdate={r['rdate']}")
            print()
    else:
        print("No patients have more than 1 episode in the range.")
finally:
    client.close()
