"""
Estimate how many already-audited 'pass' records are at risk of missing
comma-list entities. Also check how many 'has_issues' records had their
missing_entities caught (old prompt) vs likely missed (no sentence_id in
missing entity data = old prompt was used).
"""
import json, re, collections, sys

NEGATION_COMMA_RE = re.compile(
    r'\b(?:no|nil|not|without|denies?|denied|absence of|no associated|'
    r'no history of|reports no)\b'
    r'[^.!?\n]{0,60},'  # some text then a comma
    r'[^.!?\n]{0,60},',  # another comma (so at least 3 items)
    re.IGNORECASE,
)

trails = [
    "scripts/agentic_audit_trail_20260306_082800.jsonl",
    "scripts/agentic_audit_trail_20260306_175817.jsonl",
]

at_risk_pass = 0
at_risk_has_issues = 0
old_prompt_missing = 0  # missing_entities without sentence_id = old prompt
new_prompt_missing = 0  # missing_entities with sentence_id = new prompt
auto_added = 0

for trail in trails:
    try:
        with open(trail) as f:
            for line in f:
                rec = json.loads(line)
                verdict = rec.get("record_verdict", "")
                # Check auto-added entities (new logic)
                for fix in rec.get("auto_fixes", []):
                    if fix.get("verdict") == "add":
                        auto_added += 1

                # Check missing entity prompt version
                for me in rec.get("missing_entities", []):
                    if "sentence_id" in me:
                        new_prompt_missing += 1
                    else:
                        old_prompt_missing += 1

    except FileNotFoundError:
        print(f"  (file not found: {trail})")

print(f"Missing entities WITHOUT sentence_id (old prompt): {old_prompt_missing}")
print(f"Missing entities WITH sentence_id (new prompt):    {new_prompt_missing}")
print(f"Auto-added entities (new fix logic active):        {auto_added}")
