"""Break down EpisodeOfCare nodes still in_progress (run ad-hoc)."""

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

Q_SPEC = """
MATCH (ep:EpisodeOfCare)
WHERE ep.status = 'in_progress'
RETURN ep.specialist_seen AS spec, count(*) AS n
"""

Q_AGE = """
MATCH (ep:EpisodeOfCare)
WHERE ep.status = 'in_progress' AND ep.referral_date IS NOT NULL
WITH ep, date(ep.referral_date) AS rd
WITH duration.inDays(rd, date()).days AS age_days
RETURN
  sum(CASE WHEN age_days <= 365 THEN 1 ELSE 0 END) AS referral_within_1yr,
  sum(CASE WHEN age_days > 365 AND age_days <= 730 THEN 1 ELSE 0 END) AS year1_to_2,
  sum(CASE WHEN age_days > 730 THEN 1 ELSE 0 END) AS over_2yr,
  count(*) AS total
"""

Q_DOMAIN = """
MATCH (ep:EpisodeOfCare)
WHERE ep.status = 'in_progress'
RETURN coalesce(ep.domain_id, '') AS domain_id, count(*) AS n
ORDER BY n DESC
"""


def main() -> None:
    client = PatientGraphClient()
    try:
        with client.session() as s:
            print("in_progress by specialist_seen flag:")
            for r in s.run(Q_SPEC):
                print(f"  specialist_seen={r['spec']!r}  count={r['n']}")
            print()
            print("in_progress by age of referral_date (vs today):")
            for r in s.run(Q_AGE):
                print(f"  {dict(r)}")
            print()
            print("in_progress by domain_id:")
            for r in s.run(Q_DOMAIN):
                print(f"  domain={r['domain_id']!r}  count={r['n']}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
