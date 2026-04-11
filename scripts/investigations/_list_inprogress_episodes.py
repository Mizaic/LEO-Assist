"""List all in_progress EpisodeOfCare nodes with referral date, specialist
flag, cancer type, and whether the same patient has any completed/closed
episodes alongside.

Run:
    python scripts/investigations/_list_inprogress_episodes.py
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

_Q_OPEN = """
MATCH (ep:EpisodeOfCare)
WHERE ep.status = 'in_progress'
RETURN
    ep.patient_id     AS pid,
    ep.cancer_type    AS site,
    ep.referral_date  AS ref_date,
    ep.specialist_seen AS spec_seen,
    ep.episode_id     AS ep_id
ORDER BY ep.patient_id, ep.referral_date
"""

_Q_ALL = """
MATCH (ep:EpisodeOfCare)
WHERE ep.patient_id IN $pids
RETURN
    ep.patient_id  AS pid,
    ep.status      AS status,
    ep.cancer_type AS site,
    ep.referral_date AS ref_date
ORDER BY ep.patient_id, ep.referral_date
"""

from datetime import date


def _age_label(ref_str: str | None) -> str:
    if not ref_str:
        return "no-ref-date"
    try:
        ref = date.fromisoformat(str(ref_str)[:10])
        days = (date.today() - ref).days
        if days <= 90:
            return "<3 mo"
        if days <= 180:
            return "3-6 mo"
        if days <= 365:
            return "6-12 mo"
        if days <= 730:
            return "1-2 yr"
        return ">2 yr"
    except Exception:
        return "?"


def main() -> None:
    from libs.neo4j_client.client import PatientGraphClient

    client = PatientGraphClient()

    open_rows = client.run(_Q_OPEN) or []
    print(f"Total in_progress episodes: {len(open_rows)}")
    print()

    # Group open episodes by patient
    open_by_pid: dict[str, list[dict]] = defaultdict(list)
    for row in open_rows:
        open_by_pid[row["pid"]].append(dict(row))

    pids = list(open_by_pid.keys())

    # Pull ALL episodes for these patients to show what else they have
    all_rows = client.run(_Q_ALL, pids=pids) or []
    all_by_pid: dict[str, list[dict]] = defaultdict(list)
    for row in all_rows:
        all_by_pid[row["pid"]].append(dict(row))

    client.close()

    # Summary by referral age bucket
    age_buckets: dict[str, int] = defaultdict(int)
    spec_seen_count = 0
    mixed_patients = 0  # patients with BOTH open and closed episodes

    print(
        f"{'PID':<14} {'SITE':<22} {'REF DATE':<12} {'AGE':<8} {'SPEC':<5} {'OTHER EPISODES'}"
    )
    print("-" * 90)

    for pid in sorted(pids):
        open_eps = open_by_pid[pid]
        all_eps = all_by_pid[pid]
        closed_eps = [
            e for e in all_eps if e["status"] in ("completed", "closed_benign")
        ]
        has_closed = bool(closed_eps)
        if has_closed:
            mixed_patients += 1

        for ep in open_eps:
            ref_str = ep.get("ref_date") or ep.get("referral_date") or ""
            age = _age_label(ref_str)
            age_buckets[age] += 1
            spec = "Y" if ep.get("spec_seen") else "N"
            if ep.get("spec_seen"):
                spec_seen_count += 1

            site = (ep.get("site") or "unknown")[:20]
            ref_display = str(ref_str)[:10] if ref_str else "???"

            # Describe other episodes on same patient
            if closed_eps:
                other = ", ".join(
                    f"{e['status']}:{(e.get('site') or '?')[:12]}" for e in closed_eps
                )
            else:
                other = "--"

            print(f"{pid:<14} {site:<22} {ref_display:<12} {age:<8} {spec:<5} {other}")

    print()
    print("=" * 90)
    print("BREAKDOWN")
    print("=" * 90)
    print(f"  Total in_progress episodes : {len(open_rows)}")
    print(f"  Distinct patients          : {len(pids)}")
    print(f"  Patients with OTHER closed/completed episodes (mixed) : {mixed_patients}")
    print(
        f"  Patients with ONLY in_progress episodes               : {len(pids) - mixed_patients}"
    )
    print()
    print("  Referral age distribution:")
    for bucket in ("<3 mo", "3-6 mo", "6-12 mo", "1-2 yr", ">2 yr", "no-ref-date", "?"):
        n = age_buckets.get(bucket, 0)
        if n:
            print(f"    {bucket:<12}: {n}")
    print()
    print(f"  Specialist seen (spec=Y)    : {spec_seen_count}")
    print(f"  No specialist yet (spec=N)  : {len(open_rows) - spec_seen_count}")


if __name__ == "__main__":
    main()
