"""Quick inspect of both audit DBs."""
import sqlite3
import pathlib
import json

ROOT = pathlib.Path(__file__).parents[2]

for rel in [
    "scripts/investigations/encounter_audit/encounter_audit.db",
    "scripts/investigations/encounter_audit_dryrun/encounter_audit.db",
]:
    db = ROOT / rel
    if not db.exists():
        print(f"\n{rel} -- NOT FOUND")
        continue

    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    cur.execute("PRAGMA table_info(encounters)")
    cols = [r["name"] for r in cur.fetchall()]

    cur.execute("SELECT status, COUNT(*) n FROM encounters GROUP BY status")
    counts = {r["status"]: r["n"] for r in cur.fetchall()}

    # Try to extract prompt version from result_json
    cur.execute(
        "SELECT result_json FROM encounters WHERE result_json IS NOT NULL LIMIT 3"
    )
    prompt_versions = set()
    for row in cur.fetchall():
        try:
            d = json.loads(row["result_json"])
            pv = (d.get("metadata") or {}).get("prompt_version")
            if pv:
                prompt_versions.add(pv)
        except Exception:
            pass

    # File timestamps
    stat = db.stat()
    import datetime
    mtime = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")

    con.close()

    print(f"\n{rel}")
    print(f"  last modified : {mtime}")
    print(f"  columns       : {cols}")
    print(f"  counts        : {counts}")
    print(f"  prompt_versions in results: {prompt_versions or '(none stored)'}")
