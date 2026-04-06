"""Print has_issues breakdown from v4 audit results."""
from __future__ import annotations
import json
import pathlib

results_dir = pathlib.Path("scripts/investigations/encounter_audit_v4/results")

has_issues = []
for f in sorted(results_dir.glob("*.json")):
    data = json.loads(f.read_text())
    rows = data if isinstance(data, list) else data.get("encounters", [])
    for enc in rows:
        result = enc.get("result", {})
        if result.get("encounter_assessment") == "has_issues":
            has_issues.append(enc)

print(f"Total has_issues: {len(has_issues)}\n")

for enc in has_issues:
    eid = enc.get("encounter_id", "")[:8]
    date = enc.get("date", "")
    result = enc.get("result", {})
    conf = result.get("confidence", 0)
    gaps = result.get("missing", [])
    wrong = result.get("wrong_assertion", [])
    overcoded = result.get("overcoded", [])
    notes = result.get("notes", "")

    print(f"=== {eid} ({date})  conf={conf} ===")
    if gaps:
        print("  GAPS:")
        for g in gaps:
            sev = g.get("severity", "?")
            sn = g.get("preferred_term", g.get("term", "?"))
            sid = g.get("snomed_concept_id", "?")
            assertion = g.get("suggested_assertion", "")
            sentence = g.get("sentence", "")[:90]
            print(f"    [{sev}] {sn} ({sid})  assertion={assertion}")
            if sentence:
                print(f"           \"{sentence}\"")
    if wrong:
        print("  WRONG ASSERTION:")
        for w in wrong:
            if isinstance(w, dict):
                sn = w.get("term", "?")
                ea = w.get("existing_assertion", "?")
                sa = w.get("suggested_assertion", "?")
                print(f"    {sn}  existing={ea} -> suggested={sa}")
    if overcoded:
        print("  OVERCODED:")
        for o in overcoded:
            if isinstance(o, dict):
                sn = o.get("preferred_term", o.get("term", "?"))
                sid = o.get("snomed_concept_id", "?")
                reason = o.get("reason", "")[:100]
                print(f"    {sn} ({sid})")
                if reason:
                    print(f"      {reason}")
    if notes:
        print(f"  NOTES: {notes[:200]}")
    print()
