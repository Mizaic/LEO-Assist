"""Re-run LLM coding for clinic_letter document_transfer encounters and window.

For each letter encounter (document_transfer + clinic_letter purpose), submits:
  - the letter encounter
  - all encounters for that patient with date in [letter_date-3d, letter_date+14d]

By default DRY RUN (counts only). Use --apply to call CodingPipeline (needs API/LLM).

Run:
    python scripts/investigations/_code_letter_surrounds.py
    python scripts/investigations/_code_letter_surrounds.py --apply --limit 2
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient

_Q_LETTERS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE e.classification_content_type = 'document_transfer'
  AND 'clinic_letter' IN coalesce(e.classification_encounter_purpose, [])
RETURN DISTINCT toString(p.id) AS pid,
       toString(e.id) AS letter_eid,
       substring(toString(e.date), 0, 10) AS letter_date
ORDER BY pid, letter_date
"""

_Q_WINDOW_IDS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(enc:Encounter)
WHERE toString(p.id) = $pid
  AND substring(toString(enc.date), 0, 10) >= $start_d
  AND substring(toString(enc.date), 0, 10) <= $end_d
RETURN DISTINCT toString(enc.id) AS eid
ORDER BY eid
"""


async def _run_apply(encounters: list[tuple[str, str]], dry_run: bool) -> None:
    from services.coding_worker.app.pipeline.pipeline_service import CodingPipeline

    pg = PatientGraphClient()
    kg = KnowledgeGraphClient()
    try:
        pipe = CodingPipeline(pg, kg, coding_mode="hitl")
        t0 = time.perf_counter()
        for patient_id, enc_id in encounters:
            await pipe.run_single_encounter(patient_id, enc_id, dry_run=dry_run)
        dt = time.perf_counter() - t0
        print(
            f"Processed {len(encounters)} encounters in {dt:.1f}s (dry_run={dry_run})"
        )
    finally:
        pg.close()
        kg.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--apply", action="store_true", help="Run CodingPipeline (not dry-run)"
    )
    ap.add_argument("--limit", type=int, default=0, help="Max letter rows (0=all)")
    args = ap.parse_args()

    pg = PatientGraphClient()
    try:
        letter_rows = pg.run(_Q_LETTERS) or []
        if args.limit:
            letter_rows = letter_rows[: args.limit]
        print(f"Letter rows: {len(letter_rows)}")
        all_jobs: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for r in letter_rows:
            pid, lid, dstr = r["pid"], r["letter_eid"], r["letter_date"]
            try:
                dt = datetime.strptime(dstr[:10], "%Y-%m-%d").date()
            except ValueError:
                continue
            start_d = (dt - timedelta(days=3)).isoformat()
            end_d = (dt + timedelta(days=14)).isoformat()
            eids = (
                pg.run(_Q_WINDOW_IDS, pid=str(pid), start_d=start_d, end_d=end_d) or []
            )
            for row in eids:
                eid = row["eid"]
                key = (pid, eid)
                if key not in seen:
                    seen.add(key)
                    all_jobs.append(key)
            keyl = (pid, lid)
            if keyl not in seen:
                seen.add(keyl)
                all_jobs.append(keyl)

        print(f"Unique (patient, encounter) jobs: {len(all_jobs)}")
        if not args.apply:
            print("Dry run only. Pass --apply to invoke CodingPipeline.")
            return

        asyncio.run(_run_apply(all_jobs, dry_run=False))
    finally:
        pg.close()


if __name__ == "__main__":
    main()
