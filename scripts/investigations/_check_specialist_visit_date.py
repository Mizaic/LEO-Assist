"""Check specialist_visit_date on stale_post_specialist episodes.

Verifies:
  - How many have specialist_visit_date stored (vs NULL)
  - Distribution of visit dates
  - How many would NOT be stale if measured from visit date (< 90 days ago)
"""

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

_Q_SAMPLE = """
MATCH (ep:EpisodeOfCare)
WHERE ep.status = 'stale_post_specialist'
WITH ep,
     CASE WHEN ep.specialist_visit_date IS NOT NULL
          THEN duration.inDays(date(ep.specialist_visit_date), date()).days
          ELSE null
     END AS days_since_visit,
     duration.inDays(date(ep.referral_date), date()).days AS days_since_ref
RETURN
  ep.referral_date        AS ref_date,
  ep.specialist_visit_date AS visit_date,
  days_since_visit,
  days_since_ref
ORDER BY days_since_visit ASC
"""

_Q_SUMMARY = """
MATCH (ep:EpisodeOfCare)
WHERE ep.status = 'stale_post_specialist'
WITH ep,
     CASE WHEN ep.specialist_visit_date IS NOT NULL
          THEN duration.inDays(date(ep.specialist_visit_date), date()).days
          ELSE null
     END AS days_since_visit
RETURN
  count(*) AS total,
  count(ep.specialist_visit_date) AS with_visit_date,
  count(CASE WHEN days_since_visit IS NOT NULL AND days_since_visit <= 90 THEN 1 END) AS within_90d,
  min(ep.specialist_visit_date) AS earliest_visit,
  max(ep.specialist_visit_date) AS latest_visit
"""


def main() -> None:
    client = PatientGraphClient()
    try:
        with client.session() as s:
            summary = s.run(_Q_SUMMARY).single()
            print("=== stale_post_specialist summary ===")
            print(f"  Total episodes         : {summary['total']}")
            print(f"  With visit_date stored : {summary['with_visit_date']}")
            print(
                f"  Visit within 90 days   : {summary['within_90d']}  <- would NOT be stale under correct date-math"
            )
            print(f"  Earliest visit date    : {summary['earliest_visit']}")
            print(f"  Latest visit date      : {summary['latest_visit']}")
            print()
            rows = list(s.run(_Q_SAMPLE))
            print(
                f"{'ref_date':<14} {'visit_date':<14} {'days_visit':>10} {'days_ref':>10}"
            )
            for row in rows:
                print(
                    f"{str(row['ref_date'] or ''):<14} "
                    f"{str(row['visit_date'] or 'NULL'):<14} "
                    f"{str(row['days_since_visit'] or 'N/A'):>10} "
                    f"{str(row['days_since_ref'] or 'N/A'):>10}"
                )
    finally:
        client.close()


if __name__ == "__main__":
    main()
