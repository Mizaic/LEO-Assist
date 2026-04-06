"""Inspect what is actually stored in the terminology server for specific
surface forms. Tries several API patterns to find the stored mappings.
"""
import sys, requests, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets
load_keyvault_secrets()
from libs.auth.service_auth import get_service_auth_header

BASE = "http://localhost:8001"
SESSION = requests.Session()
SESSION.headers.update(get_service_auth_header())

FORMS = ["nafld", "NAFLD", "type 2 diabetes", "type2diabetes"]


def try_get(path: str, params: dict | None = None) -> tuple[int, any]:
    r = SESSION.get(f"{BASE}{path}", params=params, timeout=10)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, r.text


# 1. Try listing surface forms for each term
print("=== Trying surface-form lookup endpoints ===")
print()
for form in FORMS:
    norm = form.lower().strip()
    paths = [
        f"/terminology/surface-forms/{norm}",
        f"/terminology/surface-forms/mappings/{norm}",
        f"/terminology/surface-forms/by-form/{norm}",
        "/terminology/surface-forms",
        "/terminology/surface-forms/mappings",
    ]
    for path in paths:
        status, body = try_get(path, params={"form": form} if "mappings" not in path and path == "/terminology/surface-forms" else None)
        if status not in (404, 405, 422):
            print(f"  [{status}] GET {path} (form={form})")
            print(f"    {json.dumps(body)[:300]}")
            print()
            break

# 2. Try resolve endpoint directly and look at raw response
print("=== Raw /terminology/resolve response ===")
for form in ["NAFLD", "type 2 diabetes"]:
    r = SESSION.post(
        f"{BASE}/terminology/resolve",
        json={"terms": [form]},
        timeout=15,
    )
    print(f"  '{form}' -> HTTP {r.status_code}")
    if r.status_code == 200:
        body = r.json()
        results = body.get("results", body)
        hits = results.get(form, results.get(form.lower(), []))
        for h in hits[:3]:
            print(f"    concept_id={h.get('snomed_concept_id')} "
                  f"score={h.get('score', '?')} "
                  f"source={h.get('source', '?')} "
                  f"term={h.get('snomed_term', '?')[:50]}")
    print()

# 3. Try DELETE endpoints to remove wrong mappings
print("=== Testing DELETE endpoints ===")
for form in ["nafld", "type 2 diabetes", "type2diabetes"]:
    delete_paths = [
        f"/terminology/surface-forms/{form}",
        f"/terminology/surface-forms/mappings/{form}",
        f"/terminology/surface-forms/{form}/revoke",
    ]
    for path in delete_paths:
        r = SESSION.delete(f"{BASE}{path}", timeout=10)
        if r.status_code not in (404, 405):
            print(f"  [{r.status_code}] DELETE {path}: {r.text[:100]}")
