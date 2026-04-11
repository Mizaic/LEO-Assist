"""Check surface forms where a pre-existing mapping may conflict with what we wrote."""

import requests

BASE = "http://localhost:8001"
CONFLICT_CHECKS = [
    ("low mood", "366979004", "Depressed mood (our write)"),
    ("rectal bleeding", "405729008", "Hematochezia (our write)"),
]

for term, expected_cid, desc in CONFLICT_CHECKS:
    r = requests.get(
        f"{BASE}/terminology/surface-forms", params={"q": term}, timeout=15
    )
    items = r.json().get("items", [])
    exact = [i for i in items if i.get("normalized", "").lower() == term.lower()]
    print(f"\n'{term}' -- {len(exact)} mapping(s):")
    for i in exact:
        cid = i.get("concept_id")
        fsn = i.get("concept_fsn", "")
        prov = i.get("provenance", "?")
        conf = i.get("confidence", 0)
        status = "OUR WRITE" if cid == expected_cid else "PRE-EXISTING"
        print(f"  [{status}] {cid}  {fsn[:55]}  conf={conf}  prov={prov}")
    if len(exact) > 1:
        print(f"  -> DUPLICATE MAPPINGS: run deduplicate or prefer highest-confidence")
    elif exact and exact[0].get("concept_id") != expected_cid:
        print(
            f"  -> Pre-existing mapping differs from our write: check if both MAPS_TO exist"
        )
