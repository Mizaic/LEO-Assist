import json, sys, re

rpt = json.load(open(sys.argv[1], "r", encoding="utf-8"))
n = int(sys.argv[2]) if len(sys.argv) > 2 else 20
rule_filter = sys.argv[3] if len(sys.argv) > 3 else None

if rule_filter == "summary":
    c = {}
    for f in rpt["failures"]:
        for msg in f.get("what_is_wrong", []):
            rid = msg.split()[0] if msg else "?"
            c[rid] = c.get(rid, 0) + 1
    print(f"Total rows: {rpt['rows']}")
    print(f"Passed: {rpt['passed_rows']} ({100*rpt['passed_rows']/rpt['rows']:.1f}%)")
    print(f"Failed: {rpt['failed_rows']} ({100*rpt['failed_rows']/rpt['rows']:.1f}%)")
    print()
    for k in sorted(c, key=lambda x: -c[x]):
        print(f"  {k} {c[k]}")
    sys.exit(0)

shown = 0
for f in rpt["failures"]:
    msgs = f["what_is_wrong"]
    if rule_filter:
        msgs = [m for m in msgs if m.startswith(rule_filter)]
    if not msgs:
        continue
    ln = f["line_number"]
    for m in msgs[:1]:
        print(f"L{ln}: {m[:250]}")
    print()
    shown += 1
    if shown >= n:
        break
