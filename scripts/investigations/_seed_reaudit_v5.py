"""Seed encounter_audit_v5/ with the same 100 done encounters from the dryrun DB."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

SRC_DB = ROOT / "scripts/investigations/encounter_audit_dryrun/encounter_audit.db"
DST_DIR = ROOT / "scripts/investigations/encounter_audit_v5"
DST_DB = DST_DIR / "encounter_audit.db"


def main() -> None:
    DST_DIR.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(str(SRC_DB))
    src.row_factory = sqlite3.Row
    rows = src.execute(
        "SELECT encounter_id, patient_id, date, text_len"
        " FROM encounters WHERE status = 'done'"
        " ORDER BY patient_id, date"
    ).fetchall()
    src.close()
    print(f"Seeding {len(rows)} encounters into {DST_DB}")
    from scripts.investigations._audit_db import CheckpointDB

    dst = CheckpointDB(DST_DB)
    dst.insert_encounters(
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
    print("Done.")


if __name__ == "__main__":
    main()
