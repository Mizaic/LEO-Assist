"""Final run summary from audit trail."""
import json, collections, sys

trail = sys.argv[1] if len(sys.argv) > 1 else "scripts/agentic_audit_trail_20260306_175817.jsonl"
verdicts = collections.Counter()
total = 0
total_fixes = 0
total_proposals = 0
total_dqf = 0
total_added = 0
total_input_tok = 0
total_output_tok = 0
escalated = 0
errors = 0

with open(trail) as f:
    for line in f:
        rec = json.loads(line)
        total += 1
        verdicts[rec.get("record_verdict", "")] += 1
        fixes = rec.get("auto_fixes", [])
        total_fixes += len(fixes)
        total_added += sum(1 for fx in fixes if fx.get("verdict") == "add")
        total_proposals += len(rec.get("proposals", []))
        total_dqf += len(rec.get("data_quality_flags", []))
        total_input_tok += rec.get("input_tokens", 0)
        total_output_tok += rec.get("output_tokens", 0)
        if rec.get("error"):
            errors += 1
        ci = rec.get("consensus", {})
        if ci and ci.get("escalated"):
            escalated += 1

print(f"Records in trail:        {total}")
print(f"  pass:                  {verdicts['pass']}")
print(f"  has_issues:            {verdicts['has_issues']}")
print(f"  errors:                {errors}")
print(f"Auto-fixes applied:      {total_fixes}")
print(f"  of which add_entity:   {total_added}")
print(f"Proposals (manual):      {total_proposals}")
print(f"Data quality flags:      {total_dqf}")
print(f"Consensus escalated:     {escalated} / {total}")
print(f"Total input tokens:      {total_input_tok:,}")
print(f"Total output tokens:     {total_output_tok:,}")
