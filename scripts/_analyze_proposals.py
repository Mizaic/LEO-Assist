"""Quick analysis of what's stuck in proposals in the latest audit trail."""
import json
import statistics
import collections
import sys

trail = sys.argv[1] if len(sys.argv) > 1 else "scripts/agentic_audit_trail_20260306_175817.jsonl"

snomed_confs = []
remove_text = []
remove_label = []
missing_samples = []
needs_review_assertion = []

with open(trail) as f:
    for line in f:
        rec = json.loads(line)
        for p in rec.get("proposals", []):
            v = p.get("verdict", "")
            field = str(p.get("field", ""))
            conf = p.get("confidence", 0)
            rat = p.get("rationale", "")[:100]

            if v == "needs_review" and field == "snomed_score":
                snomed_confs.append(conf)
            elif v == "remove" and field == "text":
                remove_text.append((conf, rat))
            elif v == "remove" and field == "label":
                remove_label.append((conf, rat))
            elif v == "missing":
                missing_samples.append(p)
            elif v == "needs_review" and field == "assertion":
                needs_review_assertion.append((conf, rat))


def conf_stats(confs, label):
    if not confs:
        print(f"{label}: 0")
        return
    print(f"{label}: {len(confs)}")
    print(f"  min={min(confs):.2f}  mean={statistics.mean(confs):.2f}  max={max(confs):.2f}")
    print(f"  >=0.80: {sum(1 for c in confs if c >= 0.80)}  >=0.85: {sum(1 for c in confs if c >= 0.85)}  >=0.90: {sum(1 for c in confs if c >= 0.90)}")


conf_stats(snomed_confs, "needs_review/snomed_score")
print()
conf_stats([c for c, _ in remove_text], "remove/text (entity removal)")
print("  Sample rationales:")
for conf, rat in remove_text[:6]:
    print(f"    [{conf:.2f}] {rat}")

print()
conf_stats([c for c, _ in remove_label], "remove/label")
print("  Sample rationales:")
for conf, rat in remove_label[:6]:
    print(f"    [{conf:.2f}] {rat}")

print()
conf_stats([c for c, _ in needs_review_assertion], "needs_review/assertion")
print("  Sample rationales:")
for conf, rat in needs_review_assertion[:6]:
    print(f"    [{conf:.2f}] {rat}")

print()
print(f"missing entities: {len(missing_samples)}")
for m in missing_samples[:5]:
    idx = m.get("entity_index")
    rat = m.get("rationale", "")[:100]
    print(f"  entity_idx={idx}  {rat}")
