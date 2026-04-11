"""Show patients with more than one episode and their status breakdown."""

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

_Q_MULTI = """
MATCH (ep:EpisodeOfCare)
WITH ep.patient_id AS pid, count(*) AS ep_count
WHERE ep_count > 1
RETURN pid, ep_count
ORDER BY ep_count DESC
"""

_Q_DETAIL = """
MATCH (ep:EpisodeOfCare)
WHERE ep.patient_id = $pid
RETURN
  ep.episode_id        AS episode_id,
  ep.condition_type    AS site,
  ep.status            AS status,
  ep.referral_date     AS ref_date,
  ep.specialist_visit_date AS visit_date,
  ep.specialist_seen   AS spec_seen,
  ep.hitl_flag         AS hitl
ORDER BY ep.referral_date
"""

STATUS_SYMBOL = {
    "completed": "OK ",
    "stale_post_specialist": "SPS",
    "stale_no_diagnosis": "SND",
    "in_progress": "IP ",
    "closed_related": "CR ",
    "closed_benign": "CB ",
    "closed_phantom": "CPH",
}


def main() -> None:
    client = PatientGraphClient()
    try:
        with client.session() as s:
            multi = s.run(_Q_MULTI).data()
            print(f"Patients with >1 episode: {len(multi)}")
            print()

            status_tally: dict[str, int] = {}
            for row in multi:
                pid = row["pid"]
                ep_count = row["ep_count"]
                eps = s.run(_Q_DETAIL, pid=pid).data()

                statuses = [e["status"] for e in eps]
                for st in statuses:
                    status_tally[st] = status_tally.get(st, 0) + 1

                sym_line = "  ".join(STATUS_SYMBOL.get(e["status"], "???") for e in eps)
                print(f"Patient {pid}  ({ep_count} episodes)  [{sym_line}]")
                for ep in eps:
                    hitl = " HITL" if ep["hitl"] else ""
                    print(
                        f"    {STATUS_SYMBOL.get(ep['status'], '???')}  "
                        f"{ep['site']:<20}  "
                        f"ref={ep['ref_date'] or 'N/A'}  "
                        f"visit={ep['visit_date'] or 'N/A'}  "
                        f"{ep['status']}{hitl}"
                    )
                print()

            print("=== Status totals across multi-episode patients ===")
            for st, n in sorted(status_tally.items(), key=lambda x: -x[1]):
                print(f"  {n:4d}  {st}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
