"""Pull all encounters in a window around an episode for a single patient.

Usage:
  python scripts/_pull_patient_window.py <patient_id> [--episode <episode_id>]
                                         [--days-after 90]
                                         [--days-before 14]

Prints, for the requested patient, every encounter whose date falls in
[referral_date - days_before, referral_date + days_after]. If no episode_id
is given, picks the FIRST stale episode for that patient. The window starts
14 days before referral by default to capture the GP referral note itself.

Output is a deterministic, line-based dump intended to be consumed by an
investigating sub-agent.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=True)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=True)

from libs.neo4j_client.client import PatientGraphClient  # noqa: E402

Q_PICK_EP = """
MATCH (ep:EpisodeOfCare {patient_id: $pid})
WHERE ep.status IN ['stale_post_specialist','stale_no_diagnosis']
OPTIONAL MATCH (e:Encounter)-[r:IS_PART_OF {milestone_type:'referral'}]->(ep)
WITH ep, min(date(e.date)) AS rd
RETURN ep.episode_id AS episode_id,
       coalesce(ep.cancer_type,'non_site_specific') AS cancer_type,
       ep.status AS status,
       toString(coalesce(date(ep.referral_date), rd)) AS referral_date
ORDER BY referral_date
LIMIT 1
"""

Q_PICK_EP_BY_ID = """
MATCH (ep:EpisodeOfCare {patient_id: $pid, episode_id: $eid})
OPTIONAL MATCH (e:Encounter)-[r:IS_PART_OF {milestone_type:'referral'}]->(ep)
WITH ep, min(date(e.date)) AS rd
RETURN ep.episode_id AS episode_id,
       coalesce(ep.cancer_type,'non_site_specific') AS cancer_type,
       ep.status AS status,
       toString(coalesce(date(ep.referral_date), rd)) AS referral_date
"""

Q_EP_MILESTONES = """
MATCH (e:Encounter)-[r:IS_PART_OF]->(ep:EpisodeOfCare {episode_id: $eid})
RETURN e.id AS encounter_id, toString(date(e.date)) AS date,
       r.milestone_type AS milestone
ORDER BY e.date
"""

Q_PATIENT_ENCS = """
MATCH (p:Patient {id: $pid})-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE date(e.date) >= date($d_from) AND date(e.date) <= date($d_to)
OPTIONAL MATCH (e)-[r:IS_PART_OF]->(ep:EpisodeOfCare)
WITH e, collect(DISTINCT {ep_id: ep.episode_id,
                          milestone: r.milestone_type}) AS link
RETURN e.id AS eid,
       toString(date(e.date)) AS date,
       coalesce(e.text, '') AS text,
       link AS link
ORDER BY date(e.date)
"""


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("patient_id")
    ap.add_argument("--episode", default=None)
    ap.add_argument("--days-after", type=int, default=90)
    ap.add_argument("--days-before", type=int, default=14)
    ap.add_argument("--max-text", type=int, default=4000,
                    help="max chars of encounter text to print")
    return ap.parse_args()


def main() -> None:
    args = _parse_args()
    c = PatientGraphClient()
    try:
        if args.episode:
            ep = (
                list(c.run(Q_PICK_EP_BY_ID,
                           pid=args.patient_id, eid=args.episode))
                or [None]
            )[0]
        else:
            ep = (
                list(c.run(Q_PICK_EP, pid=args.patient_id))
                or [None]
            )[0]

        if ep is None:
            print(f"NO_STALE_EPISODE_FOUND patient={args.patient_id}")
            return

        ref_str = ep.get("referral_date")
        if not ref_str or ref_str in ("None", "null"):
            print(f"NO_REFERRAL_DATE patient={args.patient_id} episode={ep['episode_id']}")
            return
        ref_date = datetime.strptime(ref_str[:10], "%Y-%m-%d").date()
        d_from = (ref_date - timedelta(days=args.days_before)).isoformat()
        d_to = (ref_date + timedelta(days=args.days_after)).isoformat()

        print("=" * 70)
        print(f"PATIENT      : {args.patient_id}")
        print(f"EPISODE      : {ep['episode_id']}")
        print(f"CANCER_TYPE  : {ep['cancer_type']}")
        print(f"STATUS       : {ep['status']}")
        print(f"REFERRAL     : {ref_date}")
        print(f"WINDOW       : {d_from} .. {d_to} "
              f"(referral -{args.days_before}d .. +{args.days_after}d)")
        print("=" * 70)

        ms = list(c.run(Q_EP_MILESTONES, eid=ep["episode_id"]))
        print()
        print("Episode milestones (in episode IS_PART_OF graph):")
        if not ms:
            print("  <none recorded>")
        for m in ms:
            print(f"  {m['date']}  {m['milestone'] or '-':<22}  enc={m['encounter_id']}")

        encs = list(c.run(
            Q_PATIENT_ENCS,
            pid=args.patient_id, d_from=d_from, d_to=d_to,
        ))
        print()
        print(f"Encounters in window (n={len(encs)}):")
        print()
        for i, e in enumerate(encs, 1):
            in_ep = [
                lk for lk in (e["link"] or [])
                if lk.get("ep_id") == ep["episode_id"]
            ]
            tag = "[IN-EP]" if in_ep else "[other]"
            ms_tags = sorted({lk.get("milestone") for lk in (e["link"] or [])
                              if lk.get("milestone")})
            print(f"--- {i:02d} {e['date']} {tag} milestones={ms_tags} eid={e['eid']} ---")
            txt = (e["text"] or "").strip()
            if not txt:
                print("  <empty>")
            else:
                print(txt[: args.max_text])
                if len(txt) > args.max_text:
                    print(f"  ... [truncated, {len(txt) - args.max_text} chars more]")
            print()
    finally:
        c.close()


if __name__ == "__main__":
    main()
