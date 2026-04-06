"""Remove medication review surface forms added by _pin_audit_gaps_v3.py.

Medication review done (314530002) is an administrative process code --
it should not be captured by the NER pipeline as a clinical entity.

Run:
    python scripts/investigations/_remove_medication_review_surface_forms.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets
from libs.terminology.surface_normalize import normalize_surface

load_keyvault_secrets()

from libs.auth.service_auth import get_service_auth_header

BASE = "http://localhost:8001"
SESSION = requests.Session()
SESSION.headers.update(get_service_auth_header())

CONCEPT_ID = "314530002"

_FORMS = [
    "medication review done",
    "medicines review done",
    "medication review",
    "medicines optimisation review",
    "pharmacist medication review",
]


def main() -> None:
    print(f"Removing {len(_FORMS)} medication review surface forms ...\n")
    ok = fail = 0
    for form in _FORMS:
        normalized = normalize_surface(form)
        url = f"{BASE}/terminology/surface-forms/{normalized}"
        try:
            r = SESSION.delete(url, params={"concept_id": CONCEPT_ID}, timeout=30)
            if r.status_code in (200, 204):
                print(f"  [OK  ] {form!r} removed")
                ok += 1
            elif r.status_code == 404:
                print(f"  [SKIP] {form!r} not found (already absent)")
                ok += 1
            else:
                print(f"  [FAIL] {form!r} -> HTTP {r.status_code}: {r.text[:80]}")
                fail += 1
        except Exception as exc:
            print(f"  [FAIL] {form!r} -> {exc}")
            fail += 1
        time.sleep(0.05)

    print()
    print("=" * 60)
    print(f"Removed/skipped: {ok}  Failed: {fail}")
    if fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
