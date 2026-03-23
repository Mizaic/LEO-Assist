import json
from pathlib import Path

r = json.loads(Path("scripts/hitl_remediation_report.json").read_text())
s = r["summary"]
print("=== DRY-RUN SUMMARY ===")
print(f"Surface forms to add:    {s['surface_forms_added']}")
print(f"Reviews to resolve:      {s['reviews_resolved']}")
print(f"entities_json to update: {s['entities_json_updated']}")
print(f"Ignore rules to add:     {s['ignore_rules_added']}")
print(f"Errors:                  {s['errors']}")
print()

print("=== TOP 20 REVIEWS RESOLVED (by count) ===")
resolved = sorted(r["reviews_resolved"], key=lambda x: -x["resolved_count"])
for item in resolved[:20]:
    print(f"  {item['resolved_count']:4d}  {repr(item['entity_text'][:60]):65s}  -> {item['concept_id']}")
print()

print("=== IGNORE RULES ===")
for ir in r["ignore_rules_added"]:
    print(f"  {ir['entity_text']}: {ir['reason'][:80]}")
print()

print("=== PHASE 2 LAB TESTS (first 20) ===")
phase2 = [x for x in r["reviews_resolved"] if not x.get("dry_run") is False and "procedure" not in x.get("concept_id", "")]
lab_tests = [x for x in r["reviews_resolved"] if x.get("resolved_count", 0) >= 1 and x.get("concept_id","").isdigit() and len(x.get("concept_id","")) > 8]
print(f"  Lab test texts in report: {len(lab_tests)}")
