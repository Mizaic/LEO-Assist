"""Quick summary of all audit DBs."""

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "scripts" / "investigations"

for db_path in sorted(BASE.rglob("encounter_audit.db")):
    con = sqlite3.connect(str(db_path))
    total = con.execute("SELECT COUNT(*) FROM encounters").fetchone()[0]
    status_rows = con.execute(
        "SELECT status, COUNT(*) FROM encounters GROUP BY status ORDER BY 2 DESC"
    ).fetchall()
    assess_rows = con.execute(
        "SELECT json_extract(result_json, '$.encounter_assessment') as a,"
        " COUNT(*) n FROM encounters WHERE status='done'"
        " GROUP BY a ORDER BY n DESC"
    ).fetchall()

    def _count(table: str) -> int:
        try:
            return con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except sqlite3.OperationalError:
            return -1

    gaps = _count("surface_form_gaps")
    wrong = _count("wrong_concepts")
    ner = _count("ner_examples")
    con.close()

    name = db_path.parent.name
    status_str = "  ".join(f"{s}={n}" for s, n in status_rows)
    print(f"\n=== {name} (total={total}) ===")
    print(f"  status:      {status_str}")
    print(
        f"  assessments: " + "  ".join(f"{(a or 'null')}={n}" for a, n in assess_rows)
    )
    print(f"  surface_gaps={gaps}  wrong_concepts={wrong}  ner_examples={ner}")
