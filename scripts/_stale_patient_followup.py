"""For each stale 2024/2025 patient, check whether they appear in any
LATER episode (different episode_id) so we can tell 'lost-to-follow-up'
from 'continued on a different pathway'.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=True)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=True)

from libs.neo4j_client.client import PatientGraphClient  # noqa: E402

Q = """
MATCH (ep:EpisodeOfCare)
WHERE ep.status IN ['stale_post_specialist', 'stale_no_diagnosis']
WITH ep
OPTIONAL MATCH (e:Encounter)-[:IS_PART_OF]->(ep)
WITH ep, max(date(e.date)) AS stale_last
OPTIONAL MATCH (ep2:EpisodeOfCare {patient_id: ep.patient_id})
WHERE ep2.episode_id <> ep.episode_id
OPTIONAL MATCH (e2:Encounter)-[r2:IS_PART_OF]->(ep2)
WITH ep, stale_last, ep2,
     min(date(e2.date)) AS ep2_start,
     max(date(e2.date)) AS ep2_end,
     collect(DISTINCT r2.milestone_type) AS ep2_milestones
RETURN
    ep.patient_id  AS patient_id,
    ep.episode_id  AS stale_episode_id,
    ep.status      AS stale_status,
    coalesce(ep.cancer_type, 'non_site_specific') AS stale_site,
    toString(stale_last)              AS stale_last_enc,
    ep2.episode_id                    AS later_episode_id,
    coalesce(ep2.cancer_type, 'non_site_specific') AS later_site,
    coalesce(ep2.status, '<null>')    AS later_status,
    toString(ep2_start)               AS later_start,
    toString(ep2_end)                 AS later_end,
    ep2_milestones                    AS later_milestones
ORDER BY ep.patient_id, ep.episode_id
"""


def main() -> None:
    c = PatientGraphClient()
    try:
        rows = list(c.run(Q))
    finally:
        c.close()

    by_patient: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_patient[r["patient_id"]].append(r)

    print()
    print("Stale patients - do they appear on a LATER episode for the same patient?")
    print("=" * 110)
    truly_lost = 0
    has_followup = 0
    has_diagnosis_followup = 0
    has_treatment_followup = 0

    for pid, items in sorted(by_patient.items()):
        stale = items[0]
        later_eps = [
            r for r in items
            if r.get("later_episode_id")
            and r.get("later_start")
            and r.get("later_start") > (stale.get("stale_last_enc") or "0000-00-00")
        ]

        if not later_eps:
            truly_lost += 1
            print(
                f"  [{pid}] LOST  stale_ep={stale['stale_episode_id'][:14]} "
                f"({stale['stale_status']}, {stale['stale_site']}, "
                f"last={stale['stale_last_enc']}) -- no later episode"
            )
            continue

        has_followup += 1
        had_dx = any("diagnosis_confirmed" in (r["later_milestones"] or [])
                     for r in later_eps)
        had_tx = any("treatment_started" in (r["later_milestones"] or [])
                     for r in later_eps)
        if had_dx:
            has_diagnosis_followup += 1
        if had_tx:
            has_treatment_followup += 1

        print(
            f"  [{pid}] FOLLOW-UP  stale_ep={stale['stale_episode_id'][:14]} "
            f"({stale['stale_status']}, {stale['stale_site']}, "
            f"last={stale['stale_last_enc']})"
        )
        for lr in later_eps[:5]:
            print(
                f"       -> later_ep={lr['later_episode_id'][:14]} "
                f"site={lr['later_site']:<22} status={lr['later_status']:<24} "
                f"{lr['later_start']}..{lr['later_end']} "
                f"milestones={sorted(lr['later_milestones'] or [])}"
            )

    total = truly_lost + has_followup
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Total stale patients (distinct):  {total}")
    print(f"  Truly lost to follow-up:          {truly_lost}")
    print(f"  Have a later episode:             {has_followup}")
    print(f"    ...later episode reached diagnosis: {has_diagnosis_followup}")
    print(f"    ...later episode reached treatment: {has_treatment_followup}")


if __name__ == "__main__":
    main()
