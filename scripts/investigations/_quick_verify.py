"""Quick surface form persistence check -- no KV, no auth (GET is public)."""
import requests, sys, time

BASE = "http://localhost:8001"

# Fetch page 1 (default, no params)
r1 = requests.get(f"{BASE}/terminology/surface-forms", timeout=15)
print(f"Page 1: {r1.status_code}")
data1 = r1.json()
items1 = data1 if isinstance(data1, list) else data1.get("items", [])
print(f"Items page 1: {len(items1)}")

# Try skip=50 (page 2)
r2 = requests.get(f"{BASE}/terminology/surface-forms", params={"skip": 50}, timeout=15)
print(f"Page 2 (skip=50): {r2.status_code}")
if r2.status_code == 200:
    data2 = r2.json()
    items2 = data2 if isinstance(data2, list) else data2.get("items", [])
    print(f"Items page 2: {len(items2)}")
else:
    items2 = []
    print(f"  Error: {r2.text[:200]}")

# Try page=2 style
r3 = requests.get(f"{BASE}/terminology/surface-forms", params={"page": 2}, timeout=15)
print(f"page=2 style: {r3.status_code}, {r3.text[:100]}")

all_items = items1 + items2
norm_set = {f.get("normalized", "").lower() for f in all_items}
print(f"\nTotal loaded: {len(all_items)}")

by_prov = {}
for f in all_items:
    p = f.get("provenance", "unknown")
    by_prov[p] = by_prov.get(p, 0) + 1
print("\nBy provenance:")
for p, c in sorted(by_prov.items()):
    print(f"  {c:3d}  {p}")

checks = [
    # Previous batch
    ("2ww",              True,  "previous abbreviation batch"),
    ("twoc",             True,  "previous abbreviation batch"),
    ("ooh",              True,  "previous abbreviation batch"),
    ("nad",              False, "NAD must NOT be present"),
    # Current batch synonyms
    ("tiredness",        True,  "fatigue synonym"),
    ("tired",            True,  "fatigue synonym"),
    ("low mood",         True,  "corrected mental health"),
    ("decreased appetite", True, "corrected appetite"),
    ("vomiting",         True,  "corrected vomiting"),
    ("rectal bleeding",  True,  "corrected rectal"),
    ("bruising",         True,  "corrected bruising"),
    ("lump",             True,  "corrected lump"),
    ("swollen glands",   True,  "lymphadenopathy"),
    ("reflux",           True,  "acid reflux"),
    ("confusion",        True,  "corrected confusion"),
    # Lab phrases
    ("glycosuria",       True,  "lab phrase"),
    ("glucose +",        True,  "dipstick phrase"),
    ("proteinuria",      True,  "lab phrase"),
    ("psa elevated",     True,  "lab phrase"),
    ("low hb",           True,  "lab phrase"),
    ("raised creatinine",True,  "lab phrase"),
    ("neutrophilia",     True,  "lab phrase"),
    ("leucocytes in urine", True, "dipstick phrase"),
]

print("\nSpot-check:")
ok = miss = unexpected = 0
for norm, should_exist, desc in checks:
    present = norm.lower() in norm_set
    if should_exist and present:
        print(f"  OK    {norm:<28} {desc}")
        ok += 1
    elif not should_exist and not present:
        print(f"  OK    {norm:<28} Correctly absent -- {desc}")
        ok += 1
    elif should_exist and not present:
        print(f"  MISS  {norm:<28} {desc}")
        miss += 1
    else:
        print(f"  WARN  {norm:<28} Should be absent but found -- {desc}")
        unexpected += 1

print(f"\n{ok} OK | {miss} missing | {unexpected} unexpected")
if miss:
    sys.exit(1)
