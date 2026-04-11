"""
Targeted re-searches for the 10 mappings that came back wrong or not found
in the first pass, then builds the final approved writeback list.

Bad items from pass 1:
  decreased appetite / not eating  -> 102608004 Excessive appetite (WRONG)
  vomiting                         -> 225586007 Vomiting food (too specific)
  swollen glands/lymph node swell  -> NOT FOUND
  rash                             -> 398591002 Centripetal rash (too specific)
  lump                             -> 237557003 Mass of thyroid gland (too specific)
  bruising                         -> 373600006 Multiple bruising (qualifier wrong)
  low mood                         -> 225455004 Sociable mood (COMPLETELY WRONG)
  rectal bleeding                  -> 414991007 Painful rectal bleeding (qualifier wrong)
  confusion                        -> 40917007 Clouded consciousness (verify)
  reflux                           -> 235595009 GERD disorder (acceptable, verify)
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import requests

BASE = "http://localhost:8001"
SEARCH_URL = f"{BASE}/terminology/search"


def search(q: str, tag: str = None, limit: int = 8) -> list[dict]:
    params = {"q": q, "limit": limit}
    if tag:
        params["semantic_tag"] = tag
    r = requests.get(SEARCH_URL, params=params, timeout=10)
    r.raise_for_status()
    return r.json()


def show(label: str, hits: list[dict]) -> None:
    print(f"\n  {label}:")
    for h in hits[:5]:
        cid = h.get("snomed_concept_id", "?")
        term = h.get("term", "?")
        score = round(h.get("score", 0), 2)
        print(f"    {cid}  {term}  ({score})")


def top_id(hits: list[dict]) -> tuple[str, str]:
    for h in hits:
        if "snomed_concept_id" in h:
            return h["snomed_concept_id"], h["term"]
    return None, None


targeted = [
    # (label, query, semantic_tag)
    (
        "decrease in appetite (for decreased/not eating)",
        "decrease in appetite",
        "finding",
    ),
    ("vomiting plain", "vomiting", "finding"),
    ("lymphadenopathy", "lymphadenopathy", "finding"),
    ("lymph node enlarged", "enlarged lymph node", "finding"),
    ("skin eruption / rash", "skin eruption", "finding"),
    ("lump / body mass finding", "lump", "finding"),
    ("bruising (non-qualifier)", "bruising", "finding"),
    ("depressed mood", "depressed mood", "finding"),
    ("low mood (direct)", "low mood", "finding"),
    ("rectal haemorrhage", "rectal haemorrhage", "finding"),
    ("confusion / confusional state", "confusion", "finding"),
    ("confusional state", "confusional state", "finding"),
    # verify reflux finding vs disorder
    ("reflux finding", "reflux", "finding"),
    # structured result phrases
    ("blood in urine - dipstick", "blood in urine", "finding"),
    ("glycosuria", "glycosuria", "finding"),
    ("proteinuria", "proteinuria", "finding"),
    ("nitrites in urine", "nitrites in urine", "finding"),
    ("leucocytes in urine", "leucocytes in urine", "finding"),
    ("elevated C-reactive protein", "elevated CRP", "finding"),
    ("elevated PSA", "elevated PSA", "finding"),
    ("low haemoglobin", "low haemoglobin", "finding"),
    ("reduced eGFR", "reduced eGFR", "finding"),
    ("elevated HbA1c", "elevated HbA1c", "finding"),
    ("raised creatinine", "raised creatinine", "finding"),
    ("thrombocytopenia", "thrombocytopenia", "finding"),
    ("anaemia", "anaemia", "finding"),
    ("neutrophilia", "neutrophilia", "finding"),
    ("eosinophilia", "eosinophilia", "finding"),
]

for label, query, tag in targeted:
    hits = search(query, tag)
    show(label, hits)
    time.sleep(0.06)

print("\n\nDone.")
