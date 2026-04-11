"""Apply all duplicate removals: auto-generated list + manual extras."""

from __future__ import annotations
import json
import sys
import time
from pathlib import Path as _P

_ROOT = _P(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "services" / "api"))
from dotenv import load_dotenv

load_dotenv(_ROOT / "secrets" / ".env.config", override=True)
try:
    from libs.keyvault.loader import load_keyvault_secrets

    load_keyvault_secrets()
except Exception as e:
    print(f"KV: {e}")
from libs.auth.service_auth import get_service_auth_header
import requests

BASE = "http://localhost:8001"
h = get_service_auth_header()

# Auto-generated from duplicate_audit.json
auto_list = json.loads(
    _P("scripts/investigations/duplicates_to_remove.json").read_text(encoding="utf-8")
)

# Manual extras: biopsy and neutrophil count remaining duplicates
manual_extras = [
    {
        "normalized": "biopsy",
        "concept_id": "312968005",
        "reason": "Too specific (Excision biopsy of skin lesion); keep 86273004 Biopsy (procedure)",
    },
    {
        "normalized": "neutrophil count",
        "concept_id": "165519006",
        "reason": "Result interpretation (outside reference range), not the measurement; "
        "keep 1022551000000104 Neutrophil count (observable entity)",
    },
]

all_removals = auto_list + manual_extras
print(f"Total removals to apply: {len(all_removals)}")
print()

ok = fail = skip = 0
for item in all_removals:
    norm = item["normalized"]
    cid = item["concept_id"]
    reason = item.get("reason", "")[:80]
    r = requests.delete(
        f"{BASE}/terminology/surface-forms/{norm}",
        params={"concept_id": cid},
        headers=h,
        timeout=15,
    )
    if r.status_code == 200:
        removed = r.json().get("removed", 0)
        if removed == 0:
            print(f"  SKIP {norm!r:30} -> {cid}  (already gone)")
            skip += 1
        else:
            print(f"  OK   {norm!r:30} -> {cid}  removed {removed}")
            ok += 1
    else:
        print(f"  FAIL {norm!r:30} -> {cid}  HTTP {r.status_code}: {r.text[:80]}")
        fail += 1
    time.sleep(0.05)

print()
print(f"Done.  OK: {ok}  Skipped (already gone): {skip}  Failed: {fail}")
