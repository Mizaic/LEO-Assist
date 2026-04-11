"""Reset the dry-run DB encounters back to pending for a re-run."""

import sqlite3
from pathlib import Path

con = sqlite3.connect(
    "scripts/investigations/encounter_audit_dryrun/encounter_audit.db"
)
for col in ("input_tokens INTEGER", "output_tokens INTEGER", "cost_usd REAL"):
    try:
        con.execute(f"ALTER TABLE encounters ADD COLUMN {col}")
    except Exception:
        pass

con.execute(
    "UPDATE encounters SET status='pending', result_json=NULL,"
    " processed_at=NULL, input_tokens=NULL, output_tokens=NULL, cost_usd=NULL"
    " WHERE status='done'"
)
con.execute("DELETE FROM surface_form_gaps")
con.execute("DELETE FROM wrong_concepts")
con.execute("DELETE FROM ner_examples")
con.commit()

rows = con.execute("SELECT status, count(1) FROM encounters GROUP BY status").fetchall()
print("After reset:", rows)
con.close()
