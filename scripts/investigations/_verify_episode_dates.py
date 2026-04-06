"""Verify EpisodeOfCare nodes now have referral_date set for previously-missing patients."""
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

PREVIOUSLY_NO_DATE = [
    "4246627143", "4822890058", "4983118659", "6517334858",
    "7313758405", "7319972905", "7321643565", "7322946243",
]

Q = """
MATCH (ep:EpisodeOfCare {patient_id: $pid})
RETURN ep.referral_date AS rd, ep.condition_type AS ct,
       ep.specialist_seen AS spec, ep.status AS status
ORDER BY ep.referral_date
LIMIT 5
"""

client = PatientGraphClient()
with client.session() as s:
    for pid in PREVIOUSLY_NO_DATE:
        rows = list(s.run(Q, pid=pid))
        if not rows:
            print(f"{pid}  NO EPISODE FOUND")
        else:
            for row in rows:
                print(
                    f"{pid}  rd={row['rd']}  cond={row['ct']}"
                    f"  spec={row['spec']}  status={row['status']}"
                )
client.close()
