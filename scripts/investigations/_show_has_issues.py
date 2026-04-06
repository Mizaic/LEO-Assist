"""Show full detail for all has_issues encounters in v2."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "scripts/investigations/encounter_audit_v2/encounter_audit.db"

con = sqlite3.connect(str(DB))
con.row_factory = sqlite3.Row

rows = con.execute(
    "SELECT encounter_id, patient_id, date, result_json"
    " FROM encounters WHERE status='done'"
    " ORDER BY date"
).fetchall()
con.close()

issues = [r for r in rows if json.loads(r["result_json"] or "{}").get(
    "encounter_assessment") == "has_issues"]

for r in issues:
    d = json.loads(r["result_json"])
    print("=" * 70)
    print(f"ENC  : {r['encounter_id']}")
    print(f"PAT  : {r['patient_id']}   DATE: {r['date']}")
    print(f"CONF : {d.get('confidence', '?')}   NOTES: {d.get('notes', '')}")
    print()

    missing = d.get("missing") or []
    if missing:
        print(f"  MISSING ({len(missing)}):")
        for m in missing:
            cid = m.get("snomed_concept_id") or "?"
            pt = m.get("preferred_term") or m.get("term") or "?"
            sev = m.get("severity", "?")
            asrt = m.get("suggested_assertion", "?")
            reason = m.get("reason", "")
            sentence = m.get("sentence", "")
            print(f"    [{cid}] {pt}")
            print(f"      sev={sev}  assertion={asrt}")
            print(f"      reason : {reason}")
            if sentence:
                print(f"      source : {sentence[:120]}")

    overcoded = d.get("overcoded") or []
    if overcoded:
        print(f"  OVERCODED ({len(overcoded)}):")
        for o in overcoded:
            print(f"    [{o.get('conceptId','?')}] {o.get('name','?')}")
            print(f"      sev={o.get('severity','?')}  reason: {o.get('reason','')}")

    wrong = d.get("wrong_assertion") or []
    if wrong:
        print(f"  WRONG ASSERTION ({len(wrong)}):")
        for w in wrong:
            print(f"    [{w.get('conceptId','?')}] {w.get('name','?')}")
            print(f"      {w.get('current_assertion','?')} -> {w.get('suggested_assertion','?')}")
            print(f"      sev={w.get('severity','?')}  reason: {w.get('reason','')}")
    print()
