"""Audit EpisodeOfCare node quality:
- Patients with multiple episodes (check distinctness)
- Episodes with no end_date
- Episodes that are still 'in_progress' with referral_date > 1 year ago (stale)
"""

from __future__ import annotations
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

from libs.neo4j_client.client import PatientGraphClient

_Q_ALL = """
MATCH (ep:EpisodeOfCare)
WHERE ep.patient_id IS NOT NULL
RETURN
    ep.patient_id       AS patient_id,
    ep.episode_id       AS episode_id,
    ep.condition_type   AS condition_type,
    ep.referral_date    AS referral_date,
    ep.end_date         AS end_date,
    ep.status           AS status,
    ep.specialist_seen  AS specialist_seen,
    ep.domain_id        AS domain_id
ORDER BY ep.patient_id, ep.referral_date
"""

STALE_THRESHOLD_DAYS = 365


def _parse_date(val) -> date | None:
    if val is None:
        return None
    if hasattr(val, "year"):
        return date(val.year, val.month, val.day)
    try:
        return datetime.strptime(str(val)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def main() -> None:
    client = PatientGraphClient()
    today = date.today()

    with client.session() as s:
        rows = list(s.run(_Q_ALL))

    client.close()

    print(f"Total EpisodeOfCare nodes with patient_id: {len(rows)}")
    print()

    # Group by patient
    by_patient: dict[str, list[dict]] = {}
    for r in rows:
        pid = str(r["patient_id"])
        by_patient.setdefault(pid, []).append(dict(r))

    # --- Patients with multiple episodes ---
    multi = {pid: eps for pid, eps in by_patient.items() if len(eps) > 1}
    print(f"Patients with multiple episodes : {len(multi)}")
    for pid, eps in sorted(multi.items()):
        print(f"  {pid}  ({len(eps)} episodes)")
        for ep in eps:
            print(
                f"    cond={ep['condition_type']:<20}  rd={ep['referral_date']}  "
                f"status={ep['status']}  spec={ep['specialist_seen']}"
            )

    # --- No end_date ---
    no_end = [r for r in rows if r["end_date"] is None]
    print()
    print(f"Episodes with no end_date       : {len(no_end)}")

    # --- Stale: in_progress and referral_date >= 1 year ago ---
    stale = []
    for r in rows:
        if str(r.get("status") or "") != "in_progress":
            continue
        rd = _parse_date(r["referral_date"])
        if rd and (today - rd).days >= STALE_THRESHOLD_DAYS:
            stale.append(r)

    print(f"Stale episodes (in_progress, referral >= 1yr ago): {len(stale)}")
    for r in stale:
        print(
            f"  pid={r['patient_id']}  cond={r['condition_type']:<20}  "
            f"rd={r['referral_date']}  age={(today - _parse_date(r['referral_date'])).days}d"
        )

    # --- Summary by status ---
    print()
    status_counts: dict[str, int] = {}
    for r in rows:
        s = str(r.get("status") or "None")
        status_counts[s] = status_counts.get(s, 0) + 1
    print("Episodes by status:")
    for s, n in sorted(status_counts.items(), key=lambda x: -x[1]):
        print(f"  {s:<20} : {n}")

    # --- Duplicate episode_id check ---
    ep_ids = [str(r["episode_id"]) for r in rows]
    dupes = len(ep_ids) - len(set(ep_ids))
    print()
    print(f"Duplicate episode_id values     : {dupes}")


if __name__ == "__main__":
    main()
