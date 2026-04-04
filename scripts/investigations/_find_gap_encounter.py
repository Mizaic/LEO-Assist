import json, sqlite3
DB = r"scripts\investigations\encounter_audit\encounter_audit.db"
db = sqlite3.connect(DB)
rows = db.execute(
    "SELECT encounter_id, result_json FROM encounters "
    "WHERE status='done' ORDER BY RANDOM() LIMIT 200"
).fetchall()
best_id, best_missing = None, 0
for eid, rj in rows:
    if not rj:
        continue
    d = json.loads(rj)
    n = len(d.get("missing", []))
    if n > best_missing:
        best_missing, best_id = n, eid
print(f"Best encounter: {best_id}  missing={best_missing}")
db.close()
