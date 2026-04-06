"""Categorise the 276 remaining GCL situation edges as wrong vs legitimate."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
rows = json.loads(
    (ROOT / "scripts" / "investigations" / "gcl_remaining_situations.json").read_text(encoding="utf-8")
)

LEGIT_SIGNALS = (
    "declined", "offered", "done", "excluded", "ruled out",
    "history", "screening", "discussed with patient",
    "family history", "h/o", "cancer history",
)

wrong = []
legit = []
for r in rows:
    form_low = (r.get("form") or "").lower()
    if any(s in form_low for s in LEGIT_SIGNALS):
        legit.append(r)
    else:
        wrong.append(r)

print(f"WRONG situation mappings ({len(wrong)}):")
for r in wrong:
    form = r.get("form", "?")
    cid = r.get("concept_id", "?")
    fsn = r.get("concept_fsn", "?")
    print(f"  {form!r} -> {cid} | {fsn}")

print(f"\nLEGITIMATE situation mappings ({len(legit)}) -- keeping:")
for r in legit[:25]:
    form = r.get("form", "?")
    cid = r.get("concept_id", "?")
    fsn = r.get("concept_fsn", "?")
    print(f"  {form!r} -> {cid} | {fsn}")
if len(legit) > 25:
    print(f"  ... and {len(legit) - 25} more")

# Write the wrong ones for targeted fixing
out = ROOT / "scripts" / "investigations" / "gcl_wrong_situation_no_alt.json"
out.write_text(json.dumps(wrong, indent=2, ensure_ascii=True), encoding="utf-8")
print(f"\nWrong (no alternative) written to: {out}")
