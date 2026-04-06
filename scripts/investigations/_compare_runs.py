"""Compare v1 dry-run vs v2 re-audit results side by side."""
from __future__ import annotations

import collections
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

RUNS = [
    (
        ROOT / "scripts/investigations/encounter_audit_dryrun/encounter_audit.db",
        "v1 -- old prompt (v1.0-09006773)",
    ),
    (
        ROOT / "scripts/investigations/encounter_audit_v2/encounter_audit.db",
        "v2 -- bug fixes + new tools + combined strategy",
    ),
]


def summarise(db_path: Path, label: str) -> list[dict]:
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT encounter_id, result_json, input_tokens, output_tokens, cost_usd"
        " FROM encounters WHERE status = 'done'"
    ).fetchall()
    con.close()

    verdicts: collections.Counter = collections.Counter()
    findings = {"missing": 0, "overcoded": 0, "wrong_assertion": 0}
    has_issues: list[dict] = []
    total_cost = 0.0
    total_in = 0
    total_out = 0
    prompt_versions: set[str] = set()

    for r in rows:
        d = json.loads(r["result_json"]) if r["result_json"] else {}
        ea = d.get("encounter_assessment", "unknown")
        verdicts[ea] += 1
        m = len(d.get("missing") or [])
        o = len(d.get("overcoded") or [])
        w = len(d.get("wrong_assertion") or [])
        findings["missing"] += m
        findings["overcoded"] += o
        findings["wrong_assertion"] += w
        pv = (d.get("metadata") or {}).get("prompt_version", "")
        if pv:
            prompt_versions.add(pv)
        if ea == "has_issues":
            has_issues.append({
                "enc": r["encounter_id"][:8],
                "missing": m,
                "overcoded": o,
                "wrong": w,
                "notes": (d.get("notes") or "")[:80],
            })
        total_cost += r["cost_usd"] or 0.0
        total_in += r["input_tokens"] or 0
        total_out += r["output_tokens"] or 0

    n = len(rows)
    print()
    print(f"=== {label} ===")
    print(f"  encounters   : {n}")
    print(f"  prompt ver   : {prompt_versions or '(not stored)'}")
    print(f"  cost         : ${total_cost:.4f}  "
          f"({total_in:,} in / {total_out:,} out tokens)")
    print()
    for k, v in sorted(verdicts.items(), key=lambda x: -x[1]):
        bar = "#" * (v * 30 // n) if n else ""
        print(f"  {k:<26} {v:>3} ({v * 100 // n:>2}%)  {bar}")
    print()
    print(f"  {'finding':<20} count")
    print(f"  {'-'*26}")
    for k, v in findings.items():
        print(f"  {k:<20}   {v:>3}")
    if has_issues:
        print()
        print(f"  has_issues encounters ({len(has_issues)}):")
        for h in has_issues:
            print(
                f"    {h['enc']}...  "
                f"miss={h['missing']} over={h['overcoded']} wrong={h['wrong']}"
                f"  \"{h['notes']}\""
            )
    return has_issues


v1 = summarise(*RUNS[0])
v2 = summarise(*RUNS[1])

# Delta
v1_issues = {h["enc"] for h in v1}
v2_issues = {h["enc"] for h in v2}
resolved = v1_issues - v2_issues
new_issues = v2_issues - v1_issues

print()
print("=== DELTA (v1 -> v2) ===")
print(f"  Issues resolved  : {len(resolved)}  {sorted(resolved)}")
print(f"  New issues found : {len(new_issues)}  {sorted(new_issues)}")
