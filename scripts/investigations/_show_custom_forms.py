"""Show all non-guideline-config surface forms."""

import requests

BASE = "http://localhost:8001"
items = []
for skip in [0, 50, 100, 150]:
    params = {"skip": skip} if skip else {}
    r = requests.get(f"{BASE}/terminology/surface-forms", params=params, timeout=15)
    if r.status_code != 200:
        break
    batch = r.json().get("items", [])
    items.extend(batch)
    if len(batch) < 50:
        break

custom = [i for i in items if i.get("provenance") != "guideline_config_loader"]
print(f"Total items: {len(items)}")
print(f"Custom (non-guideline) forms: {len(custom)}")
print()
for i in custom:
    prov = i.get("provenance", "?")
    norm = i.get("normalized", "?")
    cid = i.get("concept_id", "?")
    status = i.get("status", "?")
    created = i.get("created_at", "?")[:10]
    print(f"  {prov:<35} {norm:<30} -> {cid}  ({status}, {created})")
