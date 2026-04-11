"""Pull all encounters ON OR AFTER the referral date for every in_progress
EpisodeOfCare, and write them to a flat text file for manual review.

Run:
    python scripts/investigations/_pull_inprogress_encounters.py
"""

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

OUT = (
    ROOT / "scripts" / "investigations" / "encounter_audit" / "inprogress_83_review.txt"
)

_Q_OPEN = """
MATCH (ep:EpisodeOfCare)
WHERE ep.status = 'in_progress'
RETURN
    ep.patient_id    AS pid,
    ep.cancer_type   AS site,
    ep.referral_date AS ref_date,
    ep.episode_id    AS ep_id,
    ep.specialist_seen AS spec_seen
ORDER BY ep.patient_id, ep.referral_date
"""

_Q_ENCOUNTERS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE p.id = $pid
  AND toString(e.date) >= $from_date
OPTIONAL MATCH (e)-[doc:DOCUMENTS]->(concept)
WITH e, collect(
    coalesce(concept.name, toString(concept.conceptId))
    + CASE WHEN doc.assertion IS NOT NULL THEN ' [' + doc.assertion + ']' ELSE '' END
) AS codings
RETURN
    toString(e.id)                              AS eid,
    toString(e.date)                            AS edate,
    coalesce(e.text, e.note, e.description, '') AS enc_text,
    codings
ORDER BY e.date
"""


def _fmt_encounter(eid: str, edate: str, enc_text: str, codings: list[str]) -> str:
    lines = [f"  [{edate}] eid={eid}"]
    if codings:
        lines.append("    CODED: " + " | ".join(c for c in codings if c.strip()))
    text = (enc_text or "").strip()
    if text:
        for chunk in text.splitlines():
            chunk = chunk.strip()
            if chunk:
                lines.append("    " + chunk)
    return "\n".join(lines)


def main() -> None:
    from libs.neo4j_client.client import PatientGraphClient

    client = PatientGraphClient()

    open_rows = client.run(_Q_OPEN) or []
    print(f"in_progress episodes: {len(open_rows)}")

    # Group by patient -> list of episodes (site, ref_date)
    from collections import defaultdict

    eps_by_pid: dict[str, list[dict]] = defaultdict(list)
    for row in open_rows:
        eps_by_pid[row["pid"]].append(
            {
                "site": row["site"],
                "ref_date": str(row["ref_date"] or ""),
                "ep_id": row["ep_id"],
                "spec_seen": row["spec_seen"],
            }
        )

    with OUT.open("w", encoding="utf-8") as fh:
        for pid in sorted(eps_by_pid.keys()):
            episodes = eps_by_pid[pid]
            fh.write("=" * 80 + "\n")
            fh.write(f"PATIENT {pid}  ({len(episodes)} in_progress episodes)\n")
            fh.write("=" * 80 + "\n")

            for ep in episodes:
                ref = ep["ref_date"][:10] if ep["ref_date"] else "???"
                spec = "specialist_seen=Y" if ep["spec_seen"] else "specialist_seen=N"
                fh.write(f"\n  EPISODE: site={ep['site']}  ref_date={ref}  {spec}\n")
                fh.write("  " + "-" * 60 + "\n")

                if not ref or ref == "???":
                    fh.write("  (no referral date - pulling all encounters)\n")
                    from_date = "2000-01-01"
                else:
                    # Two weeks before referral to catch the referral encounter itself
                    from datetime import date, timedelta

                    ref_dt = date.fromisoformat(ref)
                    from_date = (ref_dt - timedelta(days=14)).isoformat()

                encs = client.run(_Q_ENCOUNTERS, pid=pid, from_date=from_date) or []
                if not encs:
                    fh.write("  (no encounters found after referral date)\n")
                else:
                    for enc in encs:
                        fh.write(
                            _fmt_encounter(
                                enc["eid"],
                                enc["edate"],
                                enc["enc_text"],
                                enc["codings"] or [],
                            )
                        )
                        fh.write("\n")
                fh.write("\n")

            fh.write("\n")

    client.close()
    print(f"Written to {OUT}")
    print(f"Lines: {sum(1 for _ in OUT.open(encoding='utf-8'))}")


if __name__ == "__main__":
    main()
