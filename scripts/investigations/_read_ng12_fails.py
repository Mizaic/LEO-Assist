"""Read NG12 dry run failures for analysis."""
import json
from pathlib import Path

data = json.loads(
    Path("scripts/investigations/ng12_dry_run_report.json").read_text(encoding="utf-8")
)

print("=== CH002 FAILURES (verifier_unresolved) ===")
for r in data:
    if r.get("status") != "ok" and "CH002" in r.get("rec_id", ""):
        errs = r.get("errors", [])
        print(f"\n--- {r['rec_id']} ({r['title']}) {r.get('elapsed_s')}s ---")
        for e in errs:
            print(" ", e)
        if not errs:
            print("  (no errors - silent empty extraction)")

print("\n\n=== CH003 FAILURES (silent) ===")
for r in data:
    if r.get("status") != "ok" and "CH003" in r.get("rec_id", ""):
        print(
            f"  {r['rec_id']} ({r['title']}) elapsed={r.get('elapsed_s')}s"
            f"  leaves={len(r.get('leaves', []))} action={r.get('action')}"
        )
