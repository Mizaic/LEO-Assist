"""Spot check resolver: clean terms vs long evidence phrases."""

import httpx, json

URL = "http://localhost:8001/terminology/resolve"

# Clean short clinical terms (should resolve well)
clean = [
    "nausea",
    "Vitamin B12 deficiency anaemia",
    "ECG",
    "Serum TSH",
    "emphysema",
    "sciatica",
    "platelet count",
    "breast pain",
    "weight",
]

# Long evidence phrases (should return nothing -- these are sentences, not surface forms)
long_phrases = [
    "Serum TSH level 1.3 mIU/L",
    "Emphysema diagnosed with CT scan - see Resp letter",
    "Recent CXR reported as normal.",
    "ECG done today for fluttering feeling in the chest - no abno",
    "Long standing right sided sciatica due to spinal stenosis.",
]

# Previously-bad: qualifier value / geographic location should NOT appear
formerly_bad = [
    ("Serum TSH level 1.3 mIU/L", "milliinternational unit"),  # was returning unit
    (
        "Emphysema diagnosed with CT scan - see Resp letter",
        "Holy See",
    ),  # was returning geography
    ("Recent CXR reported as normal.", "Recent air travel"),  # was returning event
]

print("=== Clean clinical terms (should resolve) ===")
for phrase in clean:
    r = httpx.post(URL, json={"terms": [phrase]}, timeout=30)
    hits = r.json().get(phrase) or []
    top = hits[0] if hits else None
    if top:
        term = top.get("term") or top.get("snomed_term") or ""
        tag = top.get("semantic_tag") or ""
        score = top.get("score") or 0
        print(f"  OK  '{phrase}' -> {term[:55]} ({tag}) [{score:.2f}]")
    else:
        print(f"  --- '{phrase}' -> no results")

print("\n=== Long evidence phrases (should return nothing -- not surface forms) ===")
for phrase in long_phrases:
    r = httpx.post(URL, json={"terms": [phrase]}, timeout=30)
    hits = r.json().get(phrase) or []
    top = hits[0] if hits else None
    if top:
        term = top.get("term") or top.get("snomed_term") or ""
        tag = top.get("semantic_tag") or ""
        score = top.get("score") or 0
        print(
            f"  HIT '{phrase[:45]}' -> {term[:40]} ({tag}) [{score:.2f}]  <- CHECK THIS"
        )
    else:
        print(f"  --- '{phrase[:45]}' -> no results (good)")

print("\n=== Previously returned wrong non-clinical concepts (should be fixed) ===")
for phrase, bad_hint in formerly_bad:
    r = httpx.post(URL, json={"terms": [phrase]}, timeout=30)
    hits = r.json().get(phrase) or []
    top = hits[0] if hits else None
    if top:
        term = top.get("term") or top.get("snomed_term") or ""
        if bad_hint.lower() in term.lower():
            print(f"  STILL BAD '{phrase[:40]}' -> {term[:50]}")
        else:
            print(f"  FIXED     '{phrase[:40]}' -> {term[:50]}")
    else:
        print(f"  FIXED (empty) '{phrase[:40]}' -> no results")
