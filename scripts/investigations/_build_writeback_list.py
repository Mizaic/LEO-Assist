"""
Build the final curated writeback list from the verification JSON,
applying manual corrections where the auto-recommendation was wrong.

Outputs:
  abbreviation_writeback_approved.json  - safe to submit to terminology writeback
  abbreviation_writeback_review.json    - need clinical sign-off before writing
"""

from __future__ import annotations

import json
from pathlib import Path

# ---------------------------------------------------------------------------
# Manual corrections identified from the targeted follow-up searches.
# Format: abbreviation -> (correct_concept_id, correct_term, reason)
# ---------------------------------------------------------------------------
CORRECTIONS = {
    "CLL": (
        "92814006",
        "Chronic lymphoid leukemia, disease (disorder)",
        "Auto-recommended 'Smoldering CLL' (430338009) which is a subtype. "
        "Main CLL concept is 92814006.",
    ),
    "BCC": (
        "254701007",
        "Basal cell carcinoma of skin (disorder)",
        "Auto-recommended 'Gorlin syndrome' (69408002) which is a genetic syndrome, "
        "not BCC itself. Correct concept is 254701007.",
    ),
    "IDDM": (
        "46635009",
        "Diabetes mellitus type 1 (disorder)",
        "Auto-recommended type IB subtype (28032008). IDDM is the general abbreviation "
        "for T1DM; parent concept 46635009 is correct.",
    ),
    "HbA1c": (
        "1003671000000109",
        "Haemoglobin A1c level (observable entity)",
        "Auto-recommended 'Ordinal level of hemoglobin A1c' (443911005). "
        "UK-specific concept 1003671000000109 is the standard HbA1c measurement.",
    ),
    "CBG": (
        "434912009",
        "Blood glucose concentration (observable entity)",
        "Auto-recommended overly specific self-monitoring concept (1464731000000106). "
        "General blood glucose concentration (434912009) is correct for clinical CBG use.",
    ),
    "PR": (
        "405729008",
        "Hematochezia (finding)",
        "Auto-recommended 'On examination - per rectum - rectum empty' (163328008) "
        "which is an examination finding, not bleeding. "
        "Hematochezia (405729008) = visible rectal blood, matches 'PR bleeding' context.",
    ),
    "MSK": (
        "279069000",
        "Musculoskeletal pain (finding)",
        "Auto-recommended 'Musculoskeletal hypomobility' (10379002). "
        "MSK in clinical notes typically means musculoskeletal pain/complaint. "
        "279069000 is more accurate but flag for review.",
    ),
}

# ---------------------------------------------------------------------------
# Entries that need clinical review before writing back
# (ambiguous meaning, low confidence, or no good SNOMED match)
# ---------------------------------------------------------------------------
NEEDS_REVIEW = {
    "TWOC": (
        "43748006",
        "Removal of urinary bladder catheter (procedure)",
        "TWOC = Trial Without Catheter. No exact SNOMED match. "
        "Closest is catheter removal (43748006). "
        "CLINICAL REVIEW REQUIRED before writing.",
    ),
    "CA": (
        "363346000",
        "Malignant neoplastic disease (disorder)",
        "CA as abbreviation is context-dependent: 'prostate CA', 'CA breast'. "
        "The generic malignant neoplasm concept is the correct parent, but "
        "site-specific surface forms (e.g. 'prostate CA' -> prostate cancer concept) "
        "would be more precise. CLINICAL REVIEW RECOMMENDED.",
    ),
    "MSK": (
        "279069000",
        "Musculoskeletal pain (finding)",
        "MSK is used as a context qualifier as well as a standalone finding. "
        "CLINICAL REVIEW RECOMMENDED for intended mapping.",
    ),
    "OOH": (
        "185511000000107",
        "Seen in out of hours centre (finding)",
        "OOH in encounter notes may be a source description rather than a clinical "
        "finding. Consider whether coding this is appropriate. REVIEW RECOMMENDED.",
    ),
    "NAD": (
        "281900007",
        "No abnormality detected (finding)",
        "NAD applies broadly (XR NAD, FOBT NAD). Context-specific NAD findings exist "
        "but the general concept is reasonable as a catch-all. REVIEW RECOMMENDED.",
    ),
}

# ---------------------------------------------------------------------------
# Load the verification JSON and apply corrections
# ---------------------------------------------------------------------------
raw = json.loads(
    Path("scripts/investigations/abbreviation_snomed_verification.json").read_text(
        encoding="utf-8"
    )
)

approved = []
review = []

for entry in raw:
    abbrev = entry["abbreviation"]

    if abbrev in CORRECTIONS:
        cid, term, reason = CORRECTIONS[abbrev]
        entry = {
            **entry,
            "recommended_concept_id": cid,
            "recommended_term": term,
            "correction_applied": reason,
            "source": "manual_correction",
        }
    else:
        entry = {**entry, "source": "auto_verified"}

    if abbrev in NEEDS_REVIEW:
        _, _, reason = NEEDS_REVIEW[abbrev]
        entry["review_note"] = reason
        review.append(entry)
    else:
        approved.append(entry)

# Write outputs
out_approved = Path("scripts/investigations/abbreviation_writeback_approved.json")
out_review = Path("scripts/investigations/abbreviation_writeback_review.json")
out_approved.write_text(json.dumps(approved, indent=2), encoding="utf-8")
out_review.write_text(json.dumps(review, indent=2), encoding="utf-8")

print("=" * 100)
print("APPROVED FOR WRITEBACK - verified SNOMED concepts")
print("=" * 100)
print(f"{'Abbrev':<8} {'Concept ID':<20} {'SNOMED Term':<60} Source")
print("-" * 100)
for e in approved:
    term = (e["recommended_term"] or "")[:58]
    src = "CORRECTED" if e.get("correction_applied") else "auto"
    print(f"{e['abbreviation']:<8} {e['recommended_concept_id']:<20} {term:<60} {src}")

print()
print("=" * 100)
print("NEEDS CLINICAL REVIEW BEFORE WRITEBACK")
print("=" * 100)
for e in review:
    print(
        f"  {e['abbreviation']:<8} [{e['recommended_concept_id']}] {e['recommended_term']}"
    )
    print(f"           {e.get('review_note','')}")
    print()

print(f"Approved: {len(approved)} | Needs review: {len(review)}")
print(f"Written: {out_approved} | {out_review}")
