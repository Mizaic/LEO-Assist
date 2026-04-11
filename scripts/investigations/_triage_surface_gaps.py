"""Triage the 14,410 surface form gaps into valid vs noise.

Categories:
  VALID   -- short clean phrase, no admin patterns, worth pinning
  LONG    -- phrase > 100 chars (a sentence, not a surface form)
  ADMIN   -- routing/scheduling/demographic noise
  NUMBER  -- bare numeric value (BP reading, BMI value, etc.)
  DUPE    -- normalises to same phrase as another gap

For VALID phrases that contain an embedded lab value (e.g. 'Serum albumin 40 g/L'),
the value+unit is stripped so the surface form pinned is the clean label
('Serum albumin'). This matches what the observable_post_processor does at runtime.

Outputs a summary + valid_gaps.json ready for feed_audit_gaps_to_surface_forms.py
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from libs.terminology.surface_normalize import strip_observable_value  # noqa: E402

GAPS_FILE = (
    ROOT / "scripts" / "investigations" / "encounter_audit" / "surface_form_gaps.json"
)
OUT_VALID = (
    ROOT
    / "scripts"
    / "investigations"
    / "encounter_audit"
    / "surface_form_gaps_valid.json"
)

gaps = json.loads(GAPS_FILE.read_text(encoding="utf-8"))
print(f"Loaded {len(gaps)} gaps")


# ---------------------------------------------------------------------------
# Reject / classify rules
# ---------------------------------------------------------------------------
ADMIN_PATTERNS = [
    "entered at:",
    "care started",
    "care ended",
    "lll spa",
    "llr spa",
    "woodbrook",
    "university hospitals",
    "admission to",
    "ambulance",
    "receptionist",
    "surgery:",
    "it will take place",
    "video or in person",
    "patient request via",
    "contact trigger",
    "walk in / front desk",
    "breast clinic to",
    "oncology to",
    "to woodbrook",
    "to university",
    "seen in fast track",
    "seen in general",
    "nhs 111",
    "111 report",
    "appointment",
    "sms reminder",
    "text reminder",
    "friends and family",
    "please rate",
    "would you recommend",
    "satisfaction",
    "reasons for request:",
]

NUMERIC_RE = re.compile(
    r"^[\d\s\./,:\-]+$"
    r"|^\d+[\./]\d+$"
    r"|^bp\s*\d"
    r"|^bmi\s*[\d\.]"
    r"|^\d+\s*(mg|mmol|iu|ml|l|g|kg|cm|mm|ng|ug|pg|nmol|umol|miu)\b",
    re.IGNORECASE,
)


def classify(ev: str) -> str:
    low = ev.lower()
    if len(ev) > 100:
        return "LONG"
    if any(pat in low for pat in ADMIN_PATTERNS):
        return "ADMIN"
    if NUMERIC_RE.match(ev):
        return "NUMBER"
    if len(ev) > 60 and (ev.count(",") >= 3 or ev.count(";") >= 2):
        return "LONG"
    sentence_starters = (
        "patient ",
        "she ",
        "he ",
        "they ",
        "this ",
        "there ",
        "it ",
        "please ",
        "we ",
        "i ",
        "you ",
    )
    if any(low.startswith(s) for s in sentence_starters) and len(ev) > 50:
        return "LONG"
    return "VALID"


# ---------------------------------------------------------------------------
# Main triage loop
# ---------------------------------------------------------------------------
buckets: dict[str, list] = {"VALID": [], "LONG": [], "ADMIN": [], "NUMBER": []}
seen_normalised: set[str] = set()
dupes = 0
stripped_count = 0

for gap in gaps:
    raw_ev = (gap.get("evidence") or "").strip()
    cat = classify(raw_ev)

    if cat == "VALID":
        # Strip embedded lab value -- may change the evidence to a clean label
        clean_ev = strip_observable_value(raw_ev)
        if clean_ev != raw_ev:
            stripped_count += 1
            # After stripping, re-classify (a 2-char remainder would be NUMBER)
            if classify(clean_ev) != "VALID":
                cat = "NUMBER"
            else:
                gap = dict(gap)
                gap["evidence"] = clean_ev
                gap["_original_evidence"] = raw_ev

    key = f"{(gap.get('evidence') or '').strip().lower()}|{gap.get('expected_snomed')}"
    if key in seen_normalised:
        dupes += 1
        continue
    seen_normalised.add(key)
    buckets.setdefault(cat, []).append(gap)

print(f"\n=== Triage results ===")
for cat, items in sorted(buckets.items(), key=lambda x: -len(x[1])):
    print(f"  {cat:<8} {len(items):>5}")
print(f"  {'DUPE':<8} {dupes:>5}  (already excluded)")
total_valid = len(buckets["VALID"])
print(f"\n  VALID and unique:         {total_valid}")
print(f"  Of which had value stripped: {stripped_count}")

for cat in ("LONG", "ADMIN", "NUMBER"):
    items = buckets.get(cat, [])
    print(f"\n-- {cat} sample (5 of {len(items)}) --")
    for g in items[:5]:
        print(f"  '{g['evidence'][:90]}'  ->  {g.get('expected_name', '')[:50]}")

print(f"\n-- VALID sample (25, showing stripped) --")
shown = 0
for g in buckets["VALID"]:
    if shown >= 25:
        break
    orig = g.get("_original_evidence")
    ev = g["evidence"]
    name = g.get("expected_name", "")[:45]
    gt = g.get("gap_type", "")
    if orig:
        print(f"  STRIPPED '{orig[:45]}' -> '{ev}'  ({name})")
    else:
        print(f"  CLEAN    '{ev[:55]}'  ->  {name}  [{gt}]")
    shown += 1

OUT_VALID.write_text(json.dumps(buckets["VALID"], indent=2), encoding="utf-8")
print(f"\nWritten {total_valid} valid gaps to:\n  {OUT_VALID}")
