"""Quick spot-check on the formerly-unknown completed episodes."""

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


def main() -> None:
    client = PatientGraphClient()

    pids = [
        "9990002012",
        "9990002015",  # breast cancer via FP anchor
        "9990010034",
        "9990010042",  # haematological / haematuria
        "9990010069",
        "9990010031",  # bowel / carcinoid
    ]
    rows = client.run(
        "MATCH (ep:EpisodeOfCare) "
        "WHERE ep.patient_id IN $pids "
        "RETURN ep.patient_id AS pid, ep.referral_date AS ref, "
        "       ep.cancer_type AS ct, ep.status AS st, ep.hitl_flag AS hitl "
        "ORDER BY ep.patient_id, ep.referral_date",
        pids=pids,
    )
    print(
        f"{'Patient':<15} {'Ref Date':<12} {'Cancer Type':<22} {'Status':<12} {'HITL'}"
    )
    print("-" * 70)
    for r in rows:
        print(
            f"{r['pid']:<15} {str(r['ref']):<12} {str(r['ct']):<22} "
            f"{r['st']:<12} {r['hitl']}"
        )

    # Overall breakdown
    breakdown = client.run(
        "MATCH (ep:EpisodeOfCare) "
        "WHERE ep.status = 'completed' "
        "RETURN ep.cancer_type AS ct, count(*) AS n "
        "ORDER BY n DESC"
    )
    print()
    print("=== Completed episode cancer_type breakdown ===")
    for r in breakdown:
        print(f"  {str(r['ct']):<30} {r['n']}")

    client.close()


if __name__ == "__main__":
    main()
