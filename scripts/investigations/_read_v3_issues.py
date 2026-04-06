"""Print detailed breakdown of has_issues encounters from v3 audit."""
from __future__ import annotations
import json
import pathlib

results_dir = pathlib.Path(
    "scripts/investigations/encounter_audit_v3/results"
)

has_issues = []
for f in sorted(results_dir.glob("*.json")):
    data = json.loads(f.read_text())
    rows = data if isinstance(data, list) else data.get("encounters", [])
    for enc in rows:
        result = enc.get("result", {})
        if result.get("encounter_assessment") == "has_issues":
            has_issues.append(enc)

print(f"Total has_issues encounters: {len(has_issues)}\n")

for enc in has_issues:
    eid = enc.get("encounter_id", "")[:8]
    date = enc.get("date", "")
    result = enc.get("result", {})
    conf = result.get("confidence", 0)
    gaps = result.get("missing", [])
    wrong = result.get("wrong_assertion", [])
    overcoded = result.get("overcoded", [])
    entities = result.get("entities", [])
    notes = result.get("notes", "")

    print(f"=== {eid} ({date})  conf={conf}  existing_coded={len(entities)} ===")

    if entities:
        for c in entities:
            sn = c.get("term", "?")
            sid = c.get("concept_id", "?")
            print(f"  EXISTING: {sn} ({sid})")

    if gaps:
        print("  GAPS:")
        for g in gaps:
            sev = g.get("severity", "?")
            sn = g.get("preferred_term", g.get("term", "?"))
            sid = g.get("snomed_concept_id", "?")
            assertion = g.get("suggested_assertion", "")
            sentence = g.get("sentence", "")
            reason = g.get("reason", "")
            print(f"    [{sev}] {sn} ({sid})  assertion={assertion}")
            if sentence:
                print(f"           evidence: \"{sentence[:100]}\"")
            if reason:
                print(f"           reason:   {reason[:120]}")

    if wrong:
        print("  WRONG ASSERTION:")
        for w in wrong:
            if isinstance(w, dict):
                sn = w.get("term", w.get("description", "?"))
                sid = w.get("concept_id", w.get("snomed_id", "?"))
                ea = w.get("existing_assertion", "?")
                sa = w.get("suggested_assertion", "?")
                print(f"    {sn} ({sid})  existing={ea} -> suggested={sa}")
                reason = w.get("reason", "")
                if reason:
                    print(f"      reason: {reason[:120]}")
            else:
                print(f"    {w}")

    if overcoded:
        print("  OVERCODED:")
        for o in overcoded:
            if isinstance(o, dict):
                sn = o.get("preferred_term", o.get("term", o.get("description", "?")))
                sid = o.get("snomed_concept_id", o.get("snomed_id", "?"))
                reason = o.get("reason", "")
                print(f"    {sn} ({sid})")
                if reason:
                    print(f"      reason: {reason[:120]}")
            else:
                print(f"    {o}")

    if notes:
        print(f"  NOTES: {notes[:200]}")
    print()
