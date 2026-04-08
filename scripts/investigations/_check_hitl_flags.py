"""Check why HITL flag is False on unknown completed episodes."""
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

    rows = client.run(
        "MATCH (ep:EpisodeOfCare) "
        "WHERE ep.status = 'completed' AND ep.cancer_type = 'unknown' "
        "RETURN ep.episode_id AS eid, "
        "       ep.hitl_flag AS hitl, "
        "       ep.auto_closed AS ac, "
        "       ep.referral_date AS ref_date, "
        "       ep.patient_id AS pid "
        "LIMIT 5"
    )
    print(f"Sample unknown completed episodes:")
    for r in rows:
        print(f"  pid={r['pid']} hitl={r['hitl']} (type={type(r['hitl']).__name__}) "
              f"auto_closed={r['ac']} ref={r['ref_date']}")

    # Now manually patch hitl_flag=True for all unknown completed episodes
    print()
    print("Patching hitl_flag=True for all unknown completed episodes...")
    patch = client.run(
        "MATCH (ep:EpisodeOfCare) "
        "WHERE ep.status = 'completed' AND ep.cancer_type = 'unknown' "
        "SET ep.hitl_flag = true, "
        "    ep.hitl_reason = 'Completed via non-referral pathway. Cancer type could not be "
        "determined from coded diagnoses alone. Review records to confirm cancer site "
        "(possible emergency/incidental/non-GP-led diagnosis).' "
        "RETURN count(ep) AS updated"
    )
    print(f"  Episodes patched: {patch[0]['updated']}")
    client.close()


if __name__ == "__main__":
    main()
