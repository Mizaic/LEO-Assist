"""Quick summary of the duplicate_audit.json file."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
audit_path = ROOT / "scripts" / "investigations" / "duplicate_audit.json"
audit = json.loads(audit_path.read_text())

total = len(audit)
by_action: dict[str, int] = {}
for a in audit:
    by_action[a["action"]] = by_action.get(a["action"], 0) + 1

print(f"Duplicate audit entries: {total}")
for k, v in sorted(by_action.items(), key=lambda x: -x[1]):
    print(f"  {k}: {v}")

print("\n--- Remove entries (sample top 20) ---")
removes = [a for a in audit if a["action"] == "remove"]
for a in removes[:20]:
    norm = a["normalized"]
    keeping = [m for m in a["mappings"] if m["concept_id"] not in a["remove_concept_ids"]]
    removing = [m for m in a["mappings"] if m["concept_id"] in a["remove_concept_ids"]]
    keep_str = ", ".join(
        f"{m['concept_id']} {m['concept_fsn'][:45]}" for m in keeping
    )
    rem_str = ", ".join(
        f"{m['concept_id']} {m['concept_fsn'][:45]} [{m['provenance']}]"
        for m in removing
    )
    print(f"  {norm!r:35s}  KEEP: {keep_str[:70]}")
    print(f"  {' ':35s}  DROP: {rem_str[:70]}")

print(f"\n--- keep_best entries (sample top 10) ---")
keeps = [a for a in audit if a["action"] == "keep_best"]
for a in keeps[:10]:
    norm = a["normalized"]
    print(f"  {norm!r:35s}  mappings: {len(a['mappings'])}")
    for m in a["mappings"]:
        print(f"    {m['concept_id']:22s}  {m['concept_fsn'][:55]}  [{m['provenance']}]")
