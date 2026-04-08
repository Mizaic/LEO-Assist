"""Count valid (non-merged, non-phantom) episodes for 2025."""
from __future__ import annotations
import sys
from pathlib import Path

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
DATE_TO = "2025-12-31"

client = PatientGraphClient()
try:
    r = client.run(
        "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
        "WHERE ep.referral_date >= $df AND ep.referral_date <= $dt "
        "AND NOT ep.status IN ['merged', 'closed_phantom'] "
        "RETURN count(ep) AS total, count(DISTINCT p) AS patients",
        df=DATE_FROM, dt=DATE_TO,
    )
    print(f"Valid episodes (excl merged+phantom) : {r[0]['total']}")
    print(f"Unique patients                       : {r[0]['patients']}")

    by_status = client.run(
        "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
        "WHERE ep.referral_date >= $df AND ep.referral_date <= $dt "
        "RETURN ep.status AS status, count(ep) AS n ORDER BY n DESC",
        df=DATE_FROM, dt=DATE_TO,
    )
    print("\nAll episode statuses in range:")
    for row in by_status:
        marker = " <-- excluded" if row["status"] in ("merged", "closed_phantom") else ""
        print(f"  {row['status']:30s}  {row['n']:>5}{marker}")
finally:
    client.close()
