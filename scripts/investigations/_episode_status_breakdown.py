"""Show full episode status, auto-close, and HITL breakdown."""

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


def main() -> None:
    from libs.neo4j_client.client import PatientGraphClient

    client = PatientGraphClient()

    print("=== Episode status breakdown ===")
    rows = client.run("""
        MATCH (ep:EpisodeOfCare)
        RETURN ep.status AS status,
               coalesce(ep.auto_closed, false) AS auto_closed,
               count(*) AS n
        ORDER BY n DESC
    """) or []
    total = sum(r["n"] for r in rows)
    for r in rows:
        ac = "auto-closed" if r.get("auto_closed") else "normal    "
        print(f"  {str(r['status']):35}  {ac}  n={r['n']}")
    print(f"  TOTAL: {total}")

    print("\n=== HITL-flagged episodes by reason ===")
    rows2 = client.run("""
        MATCH (ep:EpisodeOfCare)
        WHERE ep.hitl_flag = true
        RETURN ep.status AS status,
               coalesce(ep.auto_close_reason, 'n/a') AS reason,
               count(*) AS n
        ORDER BY n DESC
    """) or []
    hitl_total = sum(r["n"] for r in rows2)
    for r in rows2:
        print(f"  status={str(r['status']):30}  reason={r.get('reason')}  n={r['n']}")
    print(f"  HITL total: {hitl_total}")

    print("\n=== Still in_progress (13 remaining) ===")
    rows3 = client.run("""
        MATCH (ep:EpisodeOfCare)
        WHERE ep.status = 'in_progress'
        RETURN ep.patient_id AS pid,
               ep.cancer_type AS site,
               ep.referral_date AS ref_date,
               ep.specialist_seen AS spec_seen
        ORDER BY ep.patient_id
    """) or []
    for r in rows3:
        print(
            f"  pid={r['pid']}  site={r['site']}  ref={r['ref_date']}  spec={r.get('spec_seen')}"
        )

    client.close()


if __name__ == "__main__":
    main()
