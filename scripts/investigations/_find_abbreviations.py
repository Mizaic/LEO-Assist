"""
Find medical abbreviations in surface_form_gaps.json that need surface forms.
An abbreviation is: short (<=8 chars), mostly uppercase, appears as a
standalone token or small phrase in an evidence string.
"""
import json
import re
from collections import defaultdict
from pathlib import Path

gap_path = Path(__file__).parent / "encounter_audit" / "surface_form_gaps.json"
gaps = json.loads(gap_path.read_text(encoding="utf-8"))

# Focus on not_found gaps - these are pure vocab misses
nf = [g for g in gaps if g.get("gap_type") == "not_found"]

# Regex: find standalone abbreviation-like tokens in evidence strings
# Abbreviation = 2-6 uppercase letters (with optional digits), possibly
# followed by digits, possibly hyphenated
ABBREV_RE = re.compile(r"\b([A-Z]{2,6}(?:[0-9]+[a-zA-Z]?)?)\b")

# Also catch well-known lowercase abbreviations
KNOWN_LOWER = {"2ww", "gord", "copd", "uti", "dvt", "pe", "mi", "af", "ra",
               "oa", "hf", "dm", "htn", "ckd", "aki", "sob", "nof", "tia",
               "ptsd", "ocd", "bmi", "ibs", "pnd", "pvd", "pad", "luts",
               "bph", "hrqol", "prn", "od", "bd", "tds", "qds"}

IGNORE = {
    # Common English words that happen to be uppercase
    "GP", "NHS", "LLR", "SPA", "CT", "MRI", "ECG", "CXR", "USS",
    # Already well-known / in resolver
    "COPD", "UTI", "DVT", "PE", "AF", "RA", "OA",
    # Too short / too generic
    "A", "B", "C", "I", "II", "III", "IV", "V", "DM",
    # Admin/location
    "LGI", "QMC", "RCH", "NOK",
}

abbrev_hits: dict[str, dict] = defaultdict(
    lambda: {"count": 0, "targets": set(), "contexts": []}
)

for g in nf:
    ev = g.get("evidence") or ""
    target = g.get("expected_name") or ""
    ev_stripped = ev.strip()

    # Whole phrase is a short abbreviation (e.g. "2WW", "SLL", "CLL")
    if re.match(r"^[A-Z0-9]{2,6}\.?$", ev_stripped) or ev_stripped.lower() in KNOWN_LOWER:
        key = ev_stripped.upper().rstrip(".")
        abbrev_hits[key]["count"] += 1
        abbrev_hits[key]["targets"].add(target)
        abbrev_hits[key]["contexts"].append(ev_stripped)
        continue

    # Find abbreviations embedded in longer phrases
    for match in ABBREV_RE.finditer(ev_stripped):
        tok = match.group(1)
        if tok in IGNORE or len(tok) < 2:
            continue
        # Only keep if it looks like a medical abbreviation
        # (not a regular word that happens to be uppercase in a sentence)
        abbrev_hits[tok]["count"] += 1
        abbrev_hits[tok]["targets"].add(target)
        if len(abbrev_hits[tok]["contexts"]) < 3:
            abbrev_hits[tok]["contexts"].append(ev_stripped[:80])

# Also scan wrong_rank gaps for abbreviation evidence
for g in [g for g in gaps if g.get("gap_type") == "wrong_rank"]:
    ev = (g.get("evidence") or "").strip()
    if re.match(r"^[A-Z0-9]{2,6}\.?$", ev) or ev.lower() in KNOWN_LOWER:
        key = ev.upper().rstrip(".")
        abbrev_hits[key]["count"] += 1
        abbrev_hits[key]["targets"].add(g.get("expected_name") or "")
        abbrev_hits[key]["contexts"].append(("WRONG_RANK: " + ev)[:60])

# Sort by count desc
sorted_abbrevs = sorted(abbrev_hits.items(), key=lambda x: -x[1]["count"])

print(f"Abbreviations found in surface form gaps: {len(sorted_abbrevs)}")
print()
print(f"{'Abbrev':<12} {'Count':>5}  Targets + example contexts")
print("-" * 100)
for abbrev, d in sorted_abbrevs:
    targets = " | ".join(sorted(d["targets"]))[:80]
    ctx = d["contexts"][0][:70] if d["contexts"] else ""
    print(f"{abbrev:<12} {d['count']:>5}  -> {targets}")
    if ctx and ctx != abbrev:
        print(f"             {'':5}  ctx: [{ctx}]")

# Also: scan all nf evidence for known abbreviation patterns in context
print("\n\n=== Known clinical abbreviations found in context (not as standalone) ===")
CLINICAL_ABBREVS = {
    "2WW": "Fast track cancer referral",
    "SLL": "Small lymphocytic lymphoma",
    "CLL": "Chronic lymphocytic leukaemia",
    "HTN": "Hypertension",
    "FOBT": "Faecal occult blood test",
    "FOB": "Faecal occult blood",
    "MSK": "Musculoskeletal",
    "OGD": "Oesophagogastroduodenoscopy",
    "ERCP": "Endoscopic retrograde cholangiopancreatography",
    "TURP": "Transurethral resection of prostate",
    "BPH": "Benign prostatic hyperplasia",
    "LUTS": "Lower urinary tract symptoms",
    "GORD": "Gastro-oesophageal reflux disease",
    "IBS": "Irritable bowel syndrome",
    "IBD": "Inflammatory bowel disease",
    "PSA": "Prostate specific antigen",
    "CEA": "Carcinoembryonic antigen",
    "CA125": "Cancer antigen 125",
    "CA19": "Cancer antigen 19-9",
    "LFT": "Liver function test",
    "TFT": "Thyroid function test",
    "FBC": "Full blood count",
    "U&E": "Urea and electrolytes",
    "HbA1c": "Haemoglobin A1c",
    "eGFR": "Estimated glomerular filtration rate",
    "ACR": "Albumin creatinine ratio",
    "SOB": "Shortness of breath",
    "NOF": "Neck of femur",
    "TIA": "Transient ischaemic attack",
    "PTSD": "Post-traumatic stress disorder",
    "OCD": "Obsessive compulsive disorder",
    "AKI": "Acute kidney injury",
    "CKD": "Chronic kidney disease",
}

for abbrev, meaning in CLINICAL_ABBREVS.items():
    hits = [
        g for g in nf
        if re.search(r"\b" + re.escape(abbrev) + r"\b",
                     g.get("evidence") or "", re.IGNORECASE)
    ]
    if hits:
        targets = sorted({h.get("expected_name") or "" for h in hits})
        print(f"  {abbrev:<10} {len(hits):>3}x  ({meaning})  -> {', '.join(targets[:3])}")
