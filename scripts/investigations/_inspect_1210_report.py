"""Inspect the dry-run report for 1.2.10 action candidates."""
import json
from pathlib import Path

data = json.loads(
    Path("scripts/investigations/ng12_dry_run_report.json").read_text(encoding="utf-8")
)
results = data if isinstance(data, list) else data.get("results", [])
for r in results:
    if r.get("rec_id") == "NG12:v1:CH002:SEC001:R009":
        action = r.get("action") or {}
        print("=== ACTION ===")
        print(json.dumps(action, indent=2))
        print("\n=== ERRORS ===")
        print(json.dumps(r.get("errors"), indent=2))
        break
