"""Print has_issues rows from an audit SQLite DB."""
import json
import sqlite3
import sys
from pathlib import Path

db = Path(sys.argv[1])
con = sqlite3.connect(str(db))
con.row_factory = sqlite3.Row
for row in con.execute(
    "SELECT encounter_id, result_json FROM encounters WHERE status='done'"
):
    d = json.loads(row["result_json"])
    if d.get("encounter_assessment") != "has_issues":
        continue
    eid = row["encounter_id"]
    print(
        eid[:8],
        "m",
        len(d.get("missing") or []),
        "o",
        len(d.get("overcoded") or []),
        "w",
        len(d.get("wrong_assertion") or []),
    )
con.close()
