"""Look up specific label_ids across all audit trails and show what the auditor said."""
import json, glob, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Label IDs from the user's screenshots (partial matches ok)
target_prefixes = [
    "0ec929254b2a02bc7364",           # elevated plts -> body temperature (wrong SNOMED)
    "3e87964d9ef5b9222ccc",           # DVT -> Health condition label
    "85cb0afc865efd3ec9e6",           # HDL cholesterol - spurious qualifier
    "13f3dea83478da3b1934",           # Abdo pain -> abdominal wall veins (wrong SNOMED)
]

trail_files = sorted(glob.glob("scripts/agentic_audit_trail_*.jsonl"))

found = {}
for path in trail_files:
    fname = path.split("\\")[-1].split("/")[-1]
    with open(path) as f:
        for line in f:
            try:
                rec = json.loads(line)
                lid = rec.get("label_id", "")
                for prefix in target_prefixes:
                    if lid.startswith(prefix):
                        key = (prefix, fname)
                        if key not in found or rec.get("timestamp","") > found.get((prefix, fname), {}).get("timestamp",""):
                            found[(prefix, fname)] = rec
            except Exception:
                pass

for prefix in target_prefixes:
    print(f"\n{'='*80}")
    print(f"Label ID prefix: {prefix}")
    hits = {k: v for k, v in found.items() if k[0] == prefix}
    if not hits:
        print("  NOT FOUND in any audit trail!")
        continue
    # Show most recent
    latest = max(hits.items(), key=lambda x: x[1].get("timestamp",""))
    (_, fname), rec = latest
    print(f"  Found in: {fname}")
    print(f"  Timestamp: {rec.get('timestamp')}")
    print(f"  Record verdict: {rec.get('record_verdict')}")
    print(f"  Error: {rec.get('error','')}")
    print(f"  Auto-fixes: {len(rec.get('auto_fixes',[]))}")
    for fx in rec.get("auto_fixes", []):
        print(f"    [{fx.get('verdict')}] field={fx.get('field')} {fx.get('current')} -> {fx.get('suggested')} conf={fx.get('confidence')} | {fx.get('rationale','')[:80]}")
    print(f"  Proposals: {len(rec.get('proposals',[]))}")
    for p in rec.get("proposals", []):
        print(f"    [{p.get('verdict')}] field={p.get('field')} {p.get('current')} -> {p.get('suggested')} conf={p.get('confidence')} | {p.get('rationale','')[:80]}")
    print(f"  Data quality flags: {len(rec.get('data_quality_flags',[]))}")
    for d in rec.get("data_quality_flags", []):
        print(f"    [{d.get('verdict')}] field={d.get('field')} conf={d.get('confidence')} | {d.get('rationale','')[:80]}")
    print(f"  Missing entities: {len(rec.get('missing_entities',[]))}")
    for m in rec.get("missing_entities", []):
        print(f"    text={m.get('text')} label={m.get('label')} assertion={m.get('assertion')} | {m.get('rationale','')[:80]}")
    print(f"  Entity verdicts:")
    for ev in rec.get("entity_verdicts", []):
        print(f"    idx={ev.get('entity_index')} verdict={ev.get('verdict')}")
        for iss in ev.get("issues", []):
            print(f"      field={iss.get('field')} conf={iss.get('confidence')} | {iss.get('rationale','')[:80]}")
