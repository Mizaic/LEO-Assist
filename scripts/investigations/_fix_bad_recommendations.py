"""
Targeted follow-up searches for concepts where the auto-recommendation
was incorrect or overly specific. Run this to get the right SNOMED IDs
before any writeback.
"""

from __future__ import annotations

import requests

BASE = "http://localhost:8001"


def search(q: str, tag: str = None, limit: int = 8) -> list[dict]:
    params = {"q": q, "limit": limit}
    if tag:
        params["semantic_tag"] = tag
    r = requests.get(f"{BASE}/terminology/search", params=params, timeout=10)
    r.raise_for_status()
    return r.json()


def show(label: str, q: str, tag: str = None) -> None:
    hits = search(q, tag)
    print(f"\n{label}")
    print(f"  search: '{q}'" + (f" [{tag}]" if tag else ""))
    for h in hits[:5]:
        cid = h.get("snomed_concept_id", "?")
        term = h.get("term", "?")
        score = h.get("score", 0)
        print(f"  [{cid}] {term}  score={score:.2f}")


# CLL: auto-recommended "Smoldering CLL" - should be the main CLL concept
show(
    "CLL - fix: need main chronic lymphocytic leukaemia",
    "chronic lymphoid leukemia disease",
    "disorder",
)

# BCC: auto-recommended "Gorlin syndrome" - completely wrong
show(
    "BCC - fix: need basal cell carcinoma of skin",
    "basal cell carcinoma skin",
    "disorder",
)
show(
    "BCC - try 2: BCC morphoeic rodent ulcer",
    "basal cell carcinoma",
    "morphologic abnormality",
)

# IDDM: auto-recommended T1DM subtype IB, better is main T1DM
show(
    "IDDM - fix: need Type 1 diabetes mellitus", "type 1 diabetes mellitus", "disorder"
)
show(
    "IDDM - try insulin dependent diabetes",
    "insulin dependent diabetes mellitus",
    "disorder",
)

# TWOC: auto-recommended "Clinical trial" - completely wrong
show(
    "TWOC - fix: trial without catheter / catheter removal",
    "removal urinary catheter",
    "procedure",
)
show("TWOC - try 2: voiding trial", "trial voiding catheter", "procedure")
show("TWOC - try 3: urethral catheter", "urethral catheterisation", "procedure")

# PR bleeding: auto-recommended "rectum empty on examination"
show("PR - fix: rectal bleeding", "rectal bleeding", "finding")
show("PR - try 2: haematochezia", "haematochezia blood stool", "finding")

# MSK: auto-recommended "musculoskeletal hypomobility" - too specific
show(
    "MSK - fix: musculoskeletal disorder / pain",
    "musculoskeletal pain disorder",
    "disorder",
)
show("MSK - try 2: musculoskeletal", "musculoskeletal structure", "body structure")
show("MSK - try 3: musculoskeletal finding", "musculoskeletal", "finding")

# HbA1c: auto-recommended "Ordinal level of hemoglobin A1c" - wrong concept type
show(
    "HbA1c - fix: haemoglobin A1c measurement",
    "haemoglobin A1c level",
    "observable entity",
)

# CBG: overly specific - need simpler capillary glucose concept
show(
    "CBG - fix: blood glucose capillary",
    "blood glucose concentration capillary",
    "observable entity",
)
show(
    "CBG - try 2: glucose capillary blood",
    "glucose capillary blood",
    "observable entity",
)
