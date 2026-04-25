"""One-off: count care_obstruction milestones across the cohort.

Used to measure cohort impact of DI-LEO-AI-219 (Pattern N5: off-pathway
non-cancer Problem-header guard) before/after a wipe + rebuild.

Reports:
  - total IS_PART_OF edges with milestone_type = 'care_obstruction'
  - distinct EpisodeOfCare nodes that carry at least one such edge
  - distinct Patient nodes that own one of those episodes
  - per-patient breakdown for the top 10 patients (by edge count)
  - optional deep-dive for one patient id (``CARE_OBSTRUCTION_DEBUG_PATIENT_ID``;
    default: synthetic pattern-guard exemplar)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=True)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=True)

from libs.testing.synthetic_patient_ids import (  # noqa: E402
    PATTERN_GUARD_CARE_OBSTRUCTION_EXEMPLAR,
)

_Q_TOTAL = """
MATCH (e:Encounter)-[r:IS_PART_OF]->(ep:EpisodeOfCare)
WHERE r.milestone_type = 'care_obstruction'
RETURN count(r) AS edges,
       count(DISTINCT ep) AS episodes,
       count(DISTINCT e) AS encounters
"""

_Q_PATIENTS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
      -[r:IS_PART_OF]->(ep:EpisodeOfCare)
WHERE r.milestone_type = 'care_obstruction'
RETURN count(DISTINCT p) AS patients
"""

_Q_TOP = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
      -[r:IS_PART_OF]->(ep:EpisodeOfCare)
WHERE r.milestone_type = 'care_obstruction'
RETURN toString(p.id) AS pid,
       count(r) AS edges,
       count(DISTINCT ep) AS episodes
ORDER BY edges DESC
LIMIT 10
"""

_Q_PATIENT_DETAIL = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
      -[r:IS_PART_OF]->(ep:EpisodeOfCare)
WHERE toString(p.id) = $pid AND r.milestone_type = 'care_obstruction'
RETURN toString(date(e.date)) AS date,
       e.id AS eid,
       ep.episode_id AS episode_id,
       coalesce(ep.cancer_type, '') AS cancer_type,
       substring(coalesce(e.text, ''), 0, 240) AS text_head
ORDER BY e.date, e.id
"""


def main() -> None:
    from libs.neo4j_client.client import PatientGraphClient

    detail_pid = os.environ.get(
        "CARE_OBSTRUCTION_DEBUG_PATIENT_ID", PATTERN_GUARD_CARE_OBSTRUCTION_EXEMPLAR
    )
    client = PatientGraphClient()
    try:
        total = client.run(_Q_TOTAL) or [{}]
        patients = client.run(_Q_PATIENTS) or [{}]
        top = client.run(_Q_TOP) or []
        detail = client.run(_Q_PATIENT_DETAIL, pid=detail_pid) or []
    finally:
        client.close()

    t = total[0] if total else {}
    print("=" * 80)
    print("CARE_OBSTRUCTION COHORT SNAPSHOT")
    print("-" * 80)
    print(f"Total IS_PART_OF edges (milestone=care_obstruction): {t.get('edges', 0)}")
    print(
        f"Distinct EpisodeOfCare with obstruction:             {t.get('episodes', 0)}"
    )
    print(
        f"Distinct Encounter nodes implicated:                 {t.get('encounters', 0)}"
    )
    print(
        f"Distinct Patients implicated:                        {patients[0].get('patients', 0)}"
    )
    print()
    print("Top 10 patients by care_obstruction edge count:")
    print("-" * 80)
    if top:
        print(f"{'PID':<14} {'edges':>6} {'episodes':>10}")
        for row in top:
            print(f"{row['pid']:<14} {row['edges']:>6} {row['episodes']:>10}")
    else:
        print("  (none)")
    print()
    print(
        f"Patient {detail_pid} (set CARE_OBSTRUCTION_DEBUG_PATIENT_ID to override) --"
    )
    print("care_obstruction encounters:")
    print("-" * 80)
    if detail:
        for row in detail:
            print(
                f"  {row['date']}  ep={row['episode_id']}  "
                f"site={row['cancer_type']!r}  eid={row['eid']}"
            )
            print(f"    text: {row['text_head'].strip()[:200]!r}")
    else:
        print("  (none -- no care_obstruction milestones for this patient)")
    print("=" * 80)


if __name__ == "__main__":
    main()
