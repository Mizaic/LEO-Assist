"""Smoke-test the resolver fixes against the known bad cases."""
import sys
from pathlib import Path
import httpx

TERMINOLOGY_URL = "http://localhost:8001/terminology"

BAD_CASES = [
    # phrase                                         expected concept (what it SHOULD return)
    ("Serum TSH level 1.3 mIU/L",                  "Serum thyroid stimulating hormone level"),
    ("Emphysema diagnosed with CT scan",            "Emphysema"),
    ("Recent CXR reported as normal.",              "Normal"),
    ("Reports issues with nausea",                  "Nausea"),
    ("Weight 45 Kg",                                "Weight"),
    ("Platelet count 312 10^9/L",                   "Platelet count"),
    ("HDL cholesterol 1.45 mmol/L",                "HDL"),
    ("Long standing right sided sciatica due to spinal stenosis.", "Sciatica"),
    ("ECG done today for fluttering feeling in the chest - no abno", "Electrocardiogram"),
    ("sharp pain over left side of her breast",    "breast"),
]

print("Testing resolver fixes...\n")
for phrase, expected_hint in BAD_CASES:
    try:
        resp = httpx.post(
            f"{TERMINOLOGY_URL}/resolve",
            json={"terms": [phrase]},
            timeout=15,
        )
        results = resp.json().get(phrase) or []
        top = results[0] if results else None
        if top:
            term = top.get("term") or top.get("snomed_term") or ""
            tag = top.get("semantic_tag") or ""
            score = top.get("score") or 0
            ok = expected_hint.lower() in term.lower()
            flag = "OK " if ok else "BAD"
            print(f"  [{flag}] '{phrase[:50]}'")
            print(f"         got: {term[:60]} ({tag}) score={score:.2f}")
        else:
            print(f"  [---] '{phrase[:50]}'")
            print(f"         no results returned (better than wrong answer)")
    except Exception as exc:
        print(f"  [ERR] '{phrase[:50]}': {exc}")
    print()
