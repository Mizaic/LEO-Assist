"""Read and print disputes as clean JSON."""

import json
from pathlib import Path

disputes = Path("scripts/investigations/encounter_audit/disputes.jsonl")
records = []
with open(disputes, encoding="utf-8", errors="replace") as f:
    for line in f:
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except Exception:
                pass

# Only the most recent run (last 9 entries)
recent = records[-9:]
print(json.dumps(recent, indent=2, ensure_ascii=False))
