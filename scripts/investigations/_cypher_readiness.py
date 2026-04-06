"""Assess whether the dry-run DB has enough data to generate Cypher fixes."""
import sqlite3, json
from pathlib import Path
from collections import Counter

con = sqlite3.connect(
    "scripts/investigations/encounter_audit_dryrun/encounter_audit.db"
)

missing_ready, missing_no_concept, missing_no_patient = [], [], []
overcoded_ready, overcoded_no_encounter = [], []

rows = con.execute(
    "SELECT encounter_id, result_json FROM encounters WHERE status='done'"
).fetchall()

for eid, rj in rows:
    if not rj:
        continue
    d = json.loads(rj)
    meta = d.get("_meta") or {}
    pid = meta.get("patient_id")
    enc_date = meta.get("date")

    for m in d.get("missing") or []:
        cid = m.get("snomed_concept_id") or m.get("concept_id")
        term = m.get("preferred_term") or m.get("term")
        rec = {
            "encounter_id": eid,
            "patient_id": pid,
            "date": enc_date,
            "concept_id": cid,
            "preferred_term": term,
            "assertion": m.get("suggested_assertion", "present"),
            "severity": m.get("severity"),
            "sentence": m.get("sentence"),
        }
        if not pid:
            missing_no_patient.append(rec)
        elif not cid:
            missing_no_concept.append(rec)
        else:
            missing_ready.append(rec)

    for o in d.get("overcoded") or []:
        cid = o.get("conceptId") or o.get("concept_id")
        rec = {
            "encounter_id": eid,
            "patient_id": pid,
            "concept_id": cid,
            "name": o.get("name"),
            "reason": o.get("reason"),
        }
        if pid and cid:
            overcoded_ready.append(rec)
        else:
            overcoded_no_encounter.append(rec)

print("=== MISSING CODES ===")
print(f"  Ready to Cypher (have patient + concept ID): {len(missing_ready)}")
print(f"  Need concept ID resolved first:              {len(missing_no_concept)}")
print(f"  No patient ID (shouldn't happen):            {len(missing_no_patient)}")

print("\n=== OVERCODED ===")
print(f"  Ready to Cypher (have patient + concept ID): {len(overcoded_ready)}")
print(f"  Missing data:                                {len(overcoded_no_encounter)}")

print("\n=== SAMPLE -- MISSING ready for Cypher ===")
for r in missing_ready[:5]:
    print(f"  patient={r['patient_id'][:8]}.. enc={r['encounter_id'][:8]}..")
    print(f"    add [{r['concept_id']}] {r['preferred_term']!r}")
    print(f"    assertion={r['assertion']}  severity={r['severity']}")
    print(f"    sentence: {str(r['sentence'])[:80]}")

print("\n=== SAMPLE -- MISSING missing concept ID (need resolve) ===")
for r in missing_no_concept[:5]:
    print(f"  patient={str(r['patient_id'])[:8]}.. term={r['preferred_term']!r}")

print("\n=== SAMPLE -- OVERCODED ready for Cypher ===")
for r in overcoded_ready[:5]:
    print(f"  patient={r['patient_id'][:8]}.. enc={r['encounter_id'][:8]}..")
    print(f"    remove [{r['concept_id']}] {r['name']!r}")
    print(f"    reason: {str(r['reason'])[:80]}")

con.close()
