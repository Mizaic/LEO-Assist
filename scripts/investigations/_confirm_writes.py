"""
Definitively confirm each written surface form by using the q= search filter.
This bypasses pagination entirely.
"""

import requests, time

BASE = "http://localhost:8001"


def check(term: str) -> tuple[bool, str]:
    r = requests.get(
        f"{BASE}/terminology/surface-forms", params={"q": term}, timeout=15
    )
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}"
    data = r.json()
    items = data.get("items", [])
    total = data.get("total", 0)
    # Check for exact normalized match
    exact = [i for i in items if i.get("normalized", "").lower() == term.lower()]
    if exact:
        cid = exact[0].get("concept_id", "?")
        prov = exact[0].get("provenance", "?")
        return True, f"[{cid}] prov={prov}"
    # Partial match
    if items:
        return True, f"partial match, total={total}"
    return False, "absent"


spot = [
    # Previous abbreviation batch
    "2ww",
    "twoc",
    "ooh",
    "htn",
    "sll",
    "cll",
    "adt",
    # NAD - must be absent
    "nad",
    # Corrected synonyms
    "tiredness",
    "tired",
    "low mood",
    "decreased appetite",
    "vomiting",
    "rectal bleeding",
    "bruising",
    "lump",
    "swollen glands",
    "lymph node swelling",
    "reflux",
    "confusion",
    "backache",
    "breathlessness",
    "night sweats",
    "dizziness",
    # Lab phrases
    "glycosuria",
    "glucose +",
    "proteinuria",
    "protein +",
    "psa elevated",
    "psa raised",
    "low hb",
    "hb low",
    "raised creatinine",
    "neutrophilia",
    "eosinophilia",
    "leucocytes in urine",
    "urine glucose positive",
]

print(f"{'Status':<6} {'Term':<30} {'Detail'}")
print("-" * 75)
ok = miss = 0
for term in spot:
    found, detail = check(term)
    if term == "nad":
        status = "OK " if not found else "WARN"
        note = "correctly absent" if not found else "SHOULD NOT exist"
        if not found:
            ok += 1
        else:
            miss += 1
        print(f"  {status}   {term:<30} {note}")
    else:
        status = "OK " if found else "MISS"
        if found:
            ok += 1
        else:
            miss += 1
        print(f"  {status}   {term:<30} {detail}")
    time.sleep(0.05)

print()
print(f"Result: {ok} OK | {miss} missing")
