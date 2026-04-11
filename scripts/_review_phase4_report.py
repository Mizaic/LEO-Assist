import json

d = json.load(open("scripts/hitl_phase4_report.json"))

hits = [r for r in d["reviews_resolved"] if r.get("resolved_count", 0) > 0]
total = sum(r["resolved_count"] for r in hits)
print(f"Reviews that will resolve: {len(hits)} unique texts, {total} total reviews")
for r in hits:
    print(
        f"  {r['entity_text']:45s} -> {r['concept_id']:20s} (count={r['resolved_count']})"
    )

print()
igns = d["ignore_rules_added"]
print(f"Ignore rules: {len(igns)}")
for i in igns:
    print(f"  {i['entity_text']:45s} pending={i.get('resolved_count', 0)}")

print()
ejs = d["entities_json_updated"]
print(f"entities_json updates: {len(ejs)}")
for e in ejs:
    print(f"  {e['entity_text']:45s} {e['old_label']} -> {e['new_label']}")
