"""
Remove conflicting pre-existing surface form mappings, keeping our writes.

low mood:       remove 74732009 (Mental disorder - too broad), keep 366979004 (Depressed mood)
rectal bleeding: remove 12063002 (Rectal hemorrhage disorder), keep 405729008 (Hematochezia finding)
"""
from __future__ import annotations
import sys
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

removes = [
    ("low mood",        "74732009",  "Mental disorder -- too broad, keep Depressed mood 366979004"),
    ("rectal bleeding", "12063002",  "Rectal hemorrhage disorder -- keep Hematochezia finding 405729008"),
]

for norm, concept_id, reason in removes:
    print(f"Removing {norm!r} -> {concept_id}: {reason}")
    r = requests.delete(
        f"{BASE}/terminology/surface-forms/{norm}",
        params={"concept_id": concept_id},
        headers=h,
        timeout=15,
    )
    print(f"  {r.status_code}: {r.text[:200]}")

# Verify
print("\nVerifying:")
for term, keep_cid, _ in [
    ("low mood",        "366979004", ""),
    ("rectal bleeding", "405729008", ""),
]:
    r = requests.get(f"{BASE}/terminology/surface-forms", params={"q": term}, timeout=15)
    exact = [i for i in r.json().get("items", []) if i.get("normalized", "").lower() == term]
    print(f"  {term}: {[(i['concept_id'], i['concept_fsn'][:40]) for i in exact]}")
    if len(exact) == 1 and exact[0]["concept_id"] == keep_cid:
        print(f"    -> Clean: single correct mapping")
    elif len(exact) > 1:
        print(f"    -> WARN: still {len(exact)} mappings")
    else:
        print(f"    -> WARN: no mapping found")
