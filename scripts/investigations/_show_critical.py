"""Show all critical-severity missing codes found so far."""
import json
import sqlite3

DB = (
    r"c:\Users\RobertSmith\Documents\GitHub\LEO-AI-CORE"
    r"\scripts\investigations\encounter_audit\encounter_audit.db"
)

db = sqlite3.connect(DB)
done_rows = db.execute(
    "SELECT encounter_id, result_json FROM encounters WHERE status='done'"
).fetchall()

print(f"{'PATIENT':<15} {'DATE':<12} {'SEV':<8} {'TERM'}")
print("-" * 90)

by_patient: dict[str, list] = {}
for (enc_id, r) in done_rows:
    if not r:
        continue
    d = json.loads(r)
    meta = d.get("_meta", {})
    patient = meta.get("patient_id", "?")
    date = meta.get("date", "?")
    for m in d.get("missing", []):
        sev = m.get("severity", "")
        if sev in ("critical", "high"):
            entry = {
                "encounter_id": enc_id,
                "patient": patient,
                "date": date,
                "severity": sev,
                "term": m.get("term", ""),
                "reason": m.get("reason", ""),
                "snomed_search": m.get("snomed_search", ""),
                "suggested_assertion": m.get("suggested_assertion", ""),
            }
            by_patient.setdefault(patient, []).append(entry)

for patient, entries in sorted(by_patient.items()):
    crits = [e for e in entries if e["severity"] == "critical"]
    highs = [e for e in entries if e["severity"] == "high"]
    total = len(crits) + len(highs)
    print(
        f"\n=== Patient {patient}  "
        f"({len(crits)} critical, {len(highs)} high, {total} total) ==="
    )
    for e in sorted(entries, key=lambda x: (x["date"], x["severity"])):
        print(
            f"  [{e['severity'].upper():<8}] {e['date']}  "
            f"{e['term']}"
        )
        if e["reason"]:
            print(f"             Reason: {e['reason']}")

db.close()
