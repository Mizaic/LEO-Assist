"""One-off: count canonical confirmed cancers for 2024/2025 after rebuild."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=True)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=True)

from libs.analytics.cohorts import confirmed_cancer_where  # noqa: E402
from libs.neo4j_client.client import PatientGraphClient  # noqa: E402

CLAUSE = confirmed_cancer_where("ep")

QUERY_BY_YEAR = f"""
MATCH (p:Patient)-[:HAS_EPISODE]->(ep:EpisodeOfCare)
WHERE {CLAUSE}
WITH ep, coalesce(ep.diagnosis_date, ep.referral_date, ep.start_date) AS d
WITH ep, d, CASE WHEN d IS NULL THEN 0 ELSE date(d).year END AS yr
RETURN yr AS year, count(DISTINCT ep) AS confirmed_cancer_episodes
ORDER BY year
"""

QUERY_LIST_2025 = f"""
MATCH (p:Patient)-[:HAS_EPISODE]->(ep:EpisodeOfCare)
WHERE {CLAUSE}
WITH ep, p, coalesce(ep.diagnosis_date, ep.referral_date, ep.start_date) AS d
WITH ep, p, CASE WHEN d IS NULL THEN 0 ELSE date(d).year END AS yr
WHERE yr = 2025
RETURN ep.id AS episode_id,
       p.id AS patient_id,
       ep.cancer_type AS cancer_type,
       ep.status AS status,
       ep.hitl_flag AS hitl,
       coalesce(ep.diagnosis_source, '') AS diag_source
ORDER BY ep.diagnosis_date
"""


def main() -> None:
    client = PatientGraphClient()
    try:
        print("=" * 70)
        print("Canonical confirmed cancers (post-rebuild) by year")
        print("=" * 70)
        rows = client.run(QUERY_BY_YEAR) or []
        for r in rows:
            print(f"  {r.get('year')}: {r.get('confirmed_cancer_episodes')}")

        print()
        print("=" * 70)
        print("2025 confirmed cancer episodes (detail)")
        print("=" * 70)
        details = client.run(QUERY_LIST_2025) or []
        print(f"  total: {len(details)}")
        for r in details:
            print(
                f"  {r.get('episode_id')[:16]:16s}  "
                f"pat={r.get('patient_id')}  "
                f"site={r.get('cancer_type'):20s}  "
                f"status={r.get('status'):16s}  "
                f"hitl={r.get('hitl')}  "
                f"src={r.get('diag_source')}"
            )
    finally:
        client.close()


if __name__ == "__main__":
    main()
