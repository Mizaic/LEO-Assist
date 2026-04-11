from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from libs.keyvault.loader import load_keyvault_secrets
from libs.neo4j_client.client import PatientGraphClient

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
load_keyvault_secrets()


def main() -> None:
    c = PatientGraphClient()
    try:
        summary = (
            c.run(
                "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
                "WHERE ep.referral_date IS NOT NULL "
                "  AND NOT ep.status IN ['merged', 'closed_phantom', 'closed_related'] "
                "  AND EXISTS { "
                "    MATCH (:Encounter)-[r:IS_PART_OF]->(ep) "
                "    WHERE r.milestone_type = 'referral' "
                "  } "
                "RETURN ep.status AS status, count(ep) AS n "
                "ORDER BY n DESC"
            )
            or []
        )
        print("Summary status counts (dashboard episode_summary basis):")
        for r in summary:
            print(f"  {r['status']}: {r['n']}")

        diagnosed = (
            c.run(
                "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
                "WHERE ep.status = 'completed' "
                "  AND ep.referral_date IS NOT NULL "
                "  AND coalesce(ep.letter_inferred_benign, false) = false "
                "  AND EXISTS { "
                "    MATCH (:Encounter)-[r:IS_PART_OF]->(ep) "
                "    WHERE r.milestone_type = 'referral' "
                "  } "
                "RETURN ep.cancer_type AS cancer_type, count(ep) AS n "
                "ORDER BY n DESC"
            )
            or []
        )
        print("\nDiagnosed counts (dashboard episode_diagnosed basis):")
        for r in diagnosed:
            print(f"  {r['cancer_type']}: {r['n']}")

        unknown = (
            c.run(
                "MATCH (ep:EpisodeOfCare) "
                "WHERE ep.status = 'completed' "
                "  AND ep.referral_date IS NOT NULL "
                "  AND coalesce(ep.letter_inferred_benign, false) = false "
                "  AND ep.cancer_type = 'unknown' "
                "OPTIONAL MATCH (e:Encounter)-[r:IS_PART_OF]->(ep) "
                "  WHERE r.milestone_type = 'referral' "
                "WITH ep, count(r) AS referral_links "
                "RETURN "
                "  coalesce(ep.referral_route, '(null)') AS route, "
                "  coalesce(ep.referral_site, '(null)') AS site, "
                "  referral_links, "
                "  count(*) AS n "
                "ORDER BY n DESC"
            )
            or []
        )
        print("\nUnknown completed breakdown:")
        for r in unknown:
            print(
                f"  route={r['route']!r} site={r['site']!r} "
                f"referral_links={r['referral_links']} n={r['n']}"
            )
    finally:
        c.close()


if __name__ == "__main__":
    main()
