"""One-off: count referral / first_seen milestones across the cohort.

Used to measure cohort impact of DI-LEO-AI-224 (Pattern N3:
structured-form-field restatement guard) before/after a wipe + rebuild.

Reports:
  - total IS_PART_OF edges with milestone_type = 'referral'
  - total IS_PART_OF edges with milestone_type = 'first_seen'
  - distinct EpisodeOfCare nodes that carry each
  - distinct Patient nodes implicated for each
  - per-patient breakdown for the top 10 patients (by edge count)
    for each milestone type
  - inspection of patient 9990003001's referral / first_seen
    milestones (canonical N3 regression anchor: should equal 1 / 1
    after the N3 rebuild)
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=True)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=True)


_Q_TOTAL = """
MATCH (e:Encounter)-[r:IS_PART_OF]->(ep:EpisodeOfCare)
WHERE r.milestone_type = $mtype
RETURN count(r) AS edges,
       count(DISTINCT ep) AS episodes,
       count(DISTINCT e) AS encounters
"""

_Q_PATIENTS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
      -[r:IS_PART_OF]->(ep:EpisodeOfCare)
WHERE r.milestone_type = $mtype
RETURN count(DISTINCT p) AS patients
"""

_Q_TOP = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
      -[r:IS_PART_OF]->(ep:EpisodeOfCare)
WHERE r.milestone_type = $mtype
RETURN toString(p.id) AS pid,
       count(r) AS edges,
       count(DISTINCT ep) AS episodes
ORDER BY edges DESC
LIMIT 10
"""

_Q_PATIENT_DETAIL = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
      -[r:IS_PART_OF]->(ep:EpisodeOfCare)
WHERE toString(p.id) = $pid AND r.milestone_type = $mtype
RETURN toString(date(e.date)) AS date,
       e.id AS eid,
       ep.episode_id AS episode_id,
       coalesce(ep.cancer_type, '') AS cancer_type,
       substring(coalesce(e.text, ''), 0, 240) AS text_head
ORDER BY e.date, e.id
"""


def _report(client, mtype: str, pid: str) -> None:
    total = client.run(_Q_TOTAL, mtype=mtype) or [{}]
    patients = client.run(_Q_PATIENTS, mtype=mtype) or [{}]
    top = client.run(_Q_TOP, mtype=mtype) or []
    detail = client.run(_Q_PATIENT_DETAIL, pid=pid, mtype=mtype) or []

    t = total[0] if total else {}
    print("=" * 80)
    print(f"{mtype.upper()} COHORT SNAPSHOT")
    print("-" * 80)
    print(f"Total IS_PART_OF edges (milestone={mtype}): {t.get('edges', 0)}")
    print(f"Distinct EpisodeOfCare with this milestone:  {t.get('episodes', 0)}")
    print(f"Distinct Encounter nodes implicated:         {t.get('encounters', 0)}")
    print(f"Distinct Patients implicated:                {patients[0].get('patients', 0)}")
    print()
    print(f"Top 10 patients by {mtype} edge count:")
    print("-" * 80)
    if top:
        print(f"{'PID':<14} {'edges':>6} {'episodes':>10}")
        for row in top:
            print(f"{row['pid']:<14} {row['edges']:>6} {row['episodes']:>10}")
    else:
        print("  (none)")
    print()
    print(f"Patient {pid} -- {mtype} encounters:")
    print("-" * 80)
    if detail:
        for row in detail:
            print(
                f"  {row['date']}  ep={row['episode_id']}  "
                f"site={row['cancer_type']!r}  eid={row['eid']}"
            )
            print(f"    text: {row['text_head'].strip()[:200]!r}")
    else:
        print(f"  (none -- no {mtype} milestones for this patient)")
    print()


def main() -> None:
    from libs.neo4j_client.client import PatientGraphClient

    pid = "9990003001"
    client = PatientGraphClient()
    try:
        _report(client, "referral", pid)
        _report(client, "first_seen", pid)
    finally:
        client.close()
    print("=" * 80)


if __name__ == "__main__":
    main()
