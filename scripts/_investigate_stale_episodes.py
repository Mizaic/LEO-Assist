"""Investigate stale episodes (no diagnosis, no benign outcome).

For 2024 + 2025, list every patient whose episode ended in
'stale_post_specialist' or 'stale_no_diagnosis' and print:
  - episode_id, patient_id, status, cancer_type
  - referral_date, first_seen_date, last_encounter_date
  - days since last encounter
  - milestones reached (referral / first_seen / diagnosis_confirmed /
    treatment_started)
  - count of encounters in episode
  - text of the LAST encounter (truncated)

Then print a summary of WHY each cohort is stale.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=True)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=True)

from libs.neo4j_client.client import PatientGraphClient  # noqa: E402

Q_STALE = """
MATCH (ep:EpisodeOfCare)
WHERE ep.status IN ['stale_post_specialist', 'stale_no_diagnosis']
OPTIONAL MATCH (e:Encounter)-[r:IS_PART_OF]->(ep)
WITH ep, collect(DISTINCT {
        date: toString(date(e.date)),
        milestone: r.milestone_type,
        eid: e.id,
        text: substring(coalesce(e.full_text, e.note_text, ''), 0, 240)
     }) AS encs
RETURN
    ep.episode_id  AS episode_id,
    ep.patient_id  AS patient_id,
    coalesce(ep.cancer_type, 'non_site_specific') AS cancer_type,
    ep.status      AS status,
    toString(date(ep.referral_date))   AS referral_date,
    toString(date(ep.first_seen_date)) AS first_seen_date,
    toString(date(ep.end_date))        AS end_date,
    encs           AS encs
"""


def _date(s):
    if not s or s in ("None", "null"):
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _episode_year(ep):
    """Earliest meaningful date year for the episode."""
    candidates = []
    for k in ("referral_date", "first_seen_date", "end_date"):
        d = _date(ep.get(k))
        if d:
            candidates.append(d.year)
    for e in ep.get("encs") or []:
        d = _date(e.get("date"))
        if d:
            candidates.append(d.year)
    return min(candidates) if candidates else None


def _diagnostic_summary(ep, today):
    encs = sorted(
        (e for e in ep.get("encs") or [] if _date(e.get("date"))),
        key=lambda x: _date(x["date"]),
    )
    milestones = {e.get("milestone") for e in encs if e.get("milestone")}
    last = encs[-1] if encs else None
    last_date = _date(last["date"]) if last else None
    days_since = (today - last_date).days if last_date else None
    last_text = (last or {}).get("text", "")
    return {
        "n_encs": len(encs),
        "milestones": milestones,
        "last_date": last_date.isoformat() if last_date else None,
        "days_since_last": days_since,
        "last_text": last_text.strip().replace("\n", " ")[:200],
    }


def main() -> None:
    today = date.today()
    c = PatientGraphClient()
    try:
        rows = list(c.run(Q_STALE))
    finally:
        c.close()

    by_year: dict[int, list[dict]] = defaultdict(list)
    for ep in rows:
        y = _episode_year(ep)
        if y is None or y not in (2024, 2025):
            continue
        ep["__year__"] = y
        ep["__diag__"] = _diagnostic_summary(ep, today)
        by_year[y].append(ep)

    # Detail print per year per status
    for y in sorted(by_year):
        eps = sorted(by_year[y], key=lambda e: (e["status"], e["patient_id"]))
        print()
        print(f"=== {y}: {len(eps)} stale episodes ===")
        for s in ("stale_post_specialist", "stale_no_diagnosis"):
            sub = [e for e in eps if e["status"] == s]
            if not sub:
                continue
            print()
            print(f"  --- {s} ({len(sub)}) ---")
            print(
                f"  {'patient':<14} {'episode':<22} {'site':<22} "
                f"{'ref':<11} {'last_enc':<11} "
                f"{'days_idle':>9} {'#enc':>5} milestones"
            )
            for ep in sub:
                d = ep["__diag__"]
                print(
                    f"  {ep['patient_id']:<14} "
                    f"{ep['episode_id'][:22]:<22} "
                    f"{ep['cancer_type'][:22]:<22} "
                    f"{(ep.get('referral_date') or '-'):<11} "
                    f"{(d['last_date'] or '-'):<11} "
                    f"{(d['days_since_last'] if d['days_since_last'] is not None else 0):>9d} "
                    f"{d['n_encs']:>5d} "
                    f"{sorted(d['milestones'])}"
                )

    # Aggregated diagnosis pattern
    print()
    print("=" * 70)
    print("WHY these patients are stale - milestone pattern counts")
    print("=" * 70)
    pattern_counts: dict[tuple[int, str, tuple], int] = defaultdict(int)
    for y, eps in by_year.items():
        for ep in eps:
            ms = tuple(sorted(ep["__diag__"]["milestones"]))
            pattern_counts[(y, ep["status"], ms)] += 1
    for (y, status, ms), n in sorted(pattern_counts.items()):
        print(f"  {y}  {status:<25}  n={n:<3}  milestones={list(ms)}")

    # Idle-time buckets
    print()
    print("=" * 70)
    print("How long since last encounter (idle days)")
    print("=" * 70)
    bucket_def = [
        ("<=90", lambda d: d is not None and d <= 90),
        ("91-180", lambda d: d is not None and 91 <= d <= 180),
        ("181-365", lambda d: d is not None and 181 <= d <= 365),
        (">365", lambda d: d is not None and d > 365),
    ]
    for y, eps in sorted(by_year.items()):
        print(f"  {y}: total={len(eps)}")
        for label, pred in bucket_def:
            n = sum(1 for ep in eps if pred(ep["__diag__"]["days_since_last"]))
            print(f"    {label:>8}: {n}")

    # Sample of last-encounter text snippets to show what reviewers are seeing
    print()
    print("=" * 70)
    print("Sample of last encounter text snippets")
    print("=" * 70)
    for y in sorted(by_year):
        for s in ("stale_post_specialist", "stale_no_diagnosis"):
            sub = [e for e in by_year[y] if e["status"] == s][:5]
            if not sub:
                continue
            print(f"\n  -- {y} / {s} (sample {len(sub)} of "
                  f"{sum(1 for e in by_year[y] if e['status'] == s)}) --")
            for ep in sub:
                d = ep["__diag__"]
                print(
                    f"  [{ep['patient_id']}] last={d['last_date']} "
                    f"({d['days_since_last']}d idle) :: {d['last_text'][:160]}"
                )


if __name__ == "__main__":
    main()
