"""
Correct verification: uses 'offset' not 'skip', checks the 'total' field.
Also queries individual surface forms directly to confirm write persistence.
"""
import requests

BASE = "http://localhost:8001"

# Check total count from the response
r = requests.get(f"{BASE}/terminology/surface-forms", timeout=15)
data = r.json()
total = data.get("total", "not returned")
items_p1 = data.get("items", [])
print(f"Page 1: {r.status_code}, total={total}, items_returned={len(items_p1)}")

# Page 2 using correct 'offset' parameter
r2 = requests.get(f"{BASE}/terminology/surface-forms", params={"offset": 50}, timeout=15)
data2 = r2.json()
items_p2 = data2.get("items", [])
print(f"Page 2 (offset=50): {r2.status_code}, total={data2.get('total')}, items={len(items_p2)}")

# Page 3
r3 = requests.get(f"{BASE}/terminology/surface-forms", params={"offset": 100}, timeout=15)
data3 = r3.json()
items_p3 = data3.get("items", [])
print(f"Page 3 (offset=100): {r3.status_code}, total={data3.get('total')}, items={len(items_p3)}")

all_items = items_p1 + items_p2 + items_p3
norm_set = {f.get("normalized", "").lower() for f in all_items}
print(f"\nTotal loaded: {len(all_items)} unique normalized: {len(norm_set)}")

# Spot-check a few key forms
spot_checks = [
    "2ww", "twoc", "ooh", "htn", "sll", "cll",
    "nad",                # must be absent
    "tiredness", "tired", "low mood", "decreased appetite",
    "vomiting", "rectal bleeding", "bruising", "lump",
    "swollen glands", "reflux", "confusion",
    "glycosuria", "glucose +", "proteinuria",
    "psa elevated", "low hb", "raised creatinine", "neutrophilia",
]
print()
print("Spot-check (True = present):")
for norm in spot_checks:
    present = norm.lower() in norm_set
    flag = "OK " if (norm != "nad" and present) or (norm == "nad" and not present) else "MISS" if not present else "WARN"
    print(f"  {flag} {norm:<28} {'PRESENT' if present else 'absent'}")

# Try direct filter for 'tiredness'
print()
print("Direct search for 'tiredness':")
r_t = requests.get(f"{BASE}/terminology/surface-forms", params={"q": "tiredness"}, timeout=15)
print(f"  Status: {r_t.status_code}, total: {r_t.json().get('total')}, items: {len(r_t.json().get('items',[]))}")
