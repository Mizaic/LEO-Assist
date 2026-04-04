"""Check if NAD surface form exists and revoke if present."""
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
import requests, json

h = get_service_auth_header()
r = requests.get("http://localhost:8001/terminology/surface-forms", params={"limit": 500}, headers=h, timeout=15)
data = r.json()
items = data.get("items", [])
print(f"Total surface forms: {len(items)}")
print(f"Response keys: {list(data.keys())}")

nad_items = [i for i in items if "nad" in i.get("normalized", "").lower()]
print(f"NAD-related forms found: {len(nad_items)}")
for item in nad_items:
    print(json.dumps(item, indent=2))

n_items = [i["normalized"] for i in items if i.get("normalized", "").startswith("n")]
print(f"n* normalized forms: {n_items}")
