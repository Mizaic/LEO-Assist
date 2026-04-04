"""
Identify encounters that had terminology_not_found skips and remove them
from enc_processed so the next --resume pass will reprocess them.

Surface forms added in batches 3-6 will now resolve many of those terms.
Sonnet will correctly gate any that are already coded in Neo4j.

Usage:
    python scripts/investigations/_requeue_skips.py --dry-run
    python scripts/investigations/_requeue_skips.py
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

DB = Path("scripts/investigations/encounter_audit/remediation.db")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db = sqlite3.connect(DB)
    cur = db.cursor()

    total_processed = cur.execute(
        "SELECT COUNT(*) FROM enc_processed"
    ).fetchone()[0]
    print(f"enc_processed total           : {total_processed}")

    skip_total = cur.execute(
        "SELECT COUNT(*) FROM remediated WHERE applied=0 AND sonnet_reason='terminology_not_found'"
    ).fetchone()[0]
    print(f"terminology_not_found skips   : {skip_total}")

    affected = cur.execute("""
        SELECT DISTINCT encounter_id FROM remediated
        WHERE applied=0 AND sonnet_reason='terminology_not_found'
    """).fetchall()
    enc_ids = [r[0] for r in affected]
    print(f"Distinct encounters affected  : {len(enc_ids)}")

    # also show what fraction processed BEFORE batch-3 surface forms (~Apr 4 12:36)
    before_batch3 = cur.execute("""
        SELECT COUNT(DISTINCT encounter_id) FROM remediated
        WHERE applied=0 AND sonnet_reason='terminology_not_found'
        AND processed_at < '2026-04-04T13:00:00'
    """).fetchone()[0]
    print(f"  of which processed before batch-3 surface forms: {before_batch3}")

    print("\nTop 40 skipped terms (terminology_not_found):")
    rows = cur.execute("""
        SELECT concept_id, COUNT(*) AS n FROM remediated
        WHERE applied=0 AND sonnet_reason='terminology_not_found'
        GROUP BY concept_id ORDER BY n DESC LIMIT 40
    """).fetchall()
    for term, n in rows:
        print(f"  {n:4d}x  {term}")

    if args.dry_run:
        print(f"\nDRY RUN -- would remove {len(enc_ids)} rows from enc_processed")
        db.close()
        return

    chunk = 500
    deleted = 0
    for i in range(0, len(enc_ids), chunk):
        batch = enc_ids[i : i + chunk]
        placeholders = ",".join("?" * len(batch))
        cur.execute(
            f"DELETE FROM enc_processed WHERE encounter_id IN ({placeholders})",
            batch,
        )
        deleted += cur.rowcount
    db.commit()
    db.close()
    print(f"\nDeleted {deleted} rows from enc_processed.")
    print("Re-run the remediation script with --resume to catch all previously-skipped encounters.")


if __name__ == "__main__":
    main()
