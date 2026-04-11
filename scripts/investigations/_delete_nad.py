"""
Delete the NAD surface form from the terminology server.
NAD is ambiguous (No abnormality detected vs No apparent distress) and must not be auto-coded.
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

# First: check what NAD maps to
r = requests.get(f"{BASE}/terminology/surface-forms", params={"q": "nad"}, timeout=15)
data = r.json()
items = data.get("items", [])
exact = [i for i in items if i.get("normalized", "").lower() == "nad"]
print(f"NAD exact matches: {len(exact)}")
for i in exact:
    print(
        f"  normalized={i.get('normalized')} concept_id={i.get('concept_id')} "
        f"provenance={i.get('provenance')} created={i.get('created_at','')[:10]}"
    )

if not exact:
    print("NAD not found as exact normalized match - may be a substring match. Safe.")
    sys.exit(0)

# Delete the NAD surface form node entirely
print("\nDeleting NAD surface form...")
r_del = requests.delete(f"{BASE}/terminology/surface-forms/nad", headers=h, timeout=15)
print(f"  DELETE /surface-forms/nad: {r_del.status_code} {r_del.text[:200]}")

# Verify deletion
r_check = requests.get(
    f"{BASE}/terminology/surface-forms", params={"q": "nad"}, timeout=15
)
remaining = [
    i
    for i in r_check.json().get("items", [])
    if i.get("normalized", "").lower() == "nad"
]
print(f"  After deletion: {len(remaining)} exact NAD matches remaining")
if remaining:
    print("  WARNING: NAD still present after deletion!")
else:
    print("  NAD successfully deleted.")
