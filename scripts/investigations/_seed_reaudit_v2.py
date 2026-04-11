"""Seed encounter_audit_v2/ with the same 100 encounters from the v1 dry-run.

Copies encounter_id, patient_id, date, text_len from the existing dry-run DB
into a fresh v2 DB with all encounters set to status='pending'.
The old results are untouched for before/after comparison.

Run:
    python scripts/investigations/_seed_reaudit_v2.py
Then:
    python scripts/investigations/audit_encounter_coding.py --yes --resume \
        --output scripts/investigations/encounter_audit_v2
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

SRC_DB = ROOT / "scripts/investigations/encounter_audit_dryrun/encounter_audit.db"
DST_DIR = ROOT / "scripts/investigations/encounter_audit_v2"
DST_DB = DST_DIR / "encounter_audit.db"


def main() -> None:
    if not SRC_DB.exists():
        print(f"ERROR: source DB not found: {SRC_DB}")
        sys.exit(1)

    DST_DIR.mkdir(parents=True, exist_ok=True)

    src = sqlite3.connect(str(SRC_DB))
    src.row_factory = sqlite3.Row

    rows = src.execute(
        "SELECT encounter_id, patient_id, date, text_len"
        " FROM encounters WHERE status = 'done'"
        " ORDER BY patient_id, date"
    ).fetchall()
    src.close()

    if not rows:
        print("ERROR: no done encounters found in source DB.")
        sys.exit(1)

    print(f"Seeding {len(rows)} encounters into {DST_DB}")

    from scripts.investigations._audit_db import CheckpointDB

    dst = CheckpointDB(DST_DB)
    inserted = dst.insert_encounters(
        [
            {
                "encounter_id": r["encounter_id"],
                "patient_id": r["patient_id"],
                "date": r["date"],
                "text_len": r["text_len"],
            }
            for r in rows
        ]
    )
    dst.close()

    print(f"Inserted: {inserted} new rows (0 = all already existed)")
    print()
    print("Next step:")
    print(
        "  python scripts/investigations/audit_encounter_coding.py"
        " --yes --resume"
        " --output scripts/investigations/encounter_audit_v2"
    )


if __name__ == "__main__":
    main()
