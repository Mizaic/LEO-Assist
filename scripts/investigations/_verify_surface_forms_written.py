"""
Verify which surface forms are actually persisted in the terminology server.

Paginates correctly (no unsupported limit param).
Checks for a representative sample of each writeback batch.
Flags any that are missing.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path as _P

_ROOT = _P(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "services" / "api"))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(_ROOT / "secrets" / ".env.config", override=True)
try:
    from libs.keyvault.loader import load_keyvault_secrets  # noqa: E402
    load_keyvault_secrets()
except Exception as e:
    print(f"KV warn: {e}")

import requests  # noqa: E402
from libs.auth.service_auth import get_service_auth_header  # noqa: E402

BASE = "http://localhost:8001"
HEADERS = get_service_auth_header()


def fetch_all_surface_forms() -> list[dict]:
    """Paginate through /terminology/surface-forms using skip/offset pattern."""
    all_items: list[dict] = []
    skip = 0
    page_size = 50  # use the default -- don't send a limit param

    while True:
        params = {"skip": skip} if skip > 0 else {}
        r = requests.get(f"{BASE}/terminology/surface-forms", params=params,
                         headers=HEADERS, timeout=15)
        if r.status_code != 200:
            print(f"  [WARN] GET /surface-forms?skip={skip} -> {r.status_code}: {r.text[:200]}")
            break
        data = r.json()
        # Handle both list response and {"items": [...]} response
        if isinstance(data, list):
            items = data
        else:
            items = data.get("items", [])

        if not items:
            break
        all_items.extend(items)
        if len(items) < page_size:
            break  # last page
        skip += len(items)
        time.sleep(0.05)

    return all_items


def main() -> None:
    print("Fetching all surface forms from terminology server...")
    forms = fetch_all_surface_forms()
    normalized_set = {f.get("normalized", "").lower() for f in forms}
    print(f"Total surface forms found: {len(forms)}")
    print()

    # Group by provenance
    by_prov: dict[str, int] = {}
    for f in forms:
        p = f.get("provenance", "unknown")
        by_prov[p] = by_prov.get(p, 0) + 1
    print("By provenance:")
    for p, count in sorted(by_prov.items()):
        print(f"  {count:3d}  {p}")
    print()

    # Check representative samples from each batch
    checks = {
        # -- Previous session abbreviations --
        "2ww":          ("abbreviation_audit_april_2026", "2WW -> Fast track cancer referral"),
        "twoc":         ("abbreviation_audit_april_2026", "TWOC -> Trial without catheter"),
        "ooh":          ("abbreviation_audit_april_2026", "OOH -> Visit out of hours"),
        "htn":          ("abbreviation_audit_april_2026", "HTN -> Hypertension"),
        "sll":          ("abbreviation_audit_april_2026", "SLL -> Small lymphocytic lymphoma"),
        "cll":          ("abbreviation_audit_april_2026", "CLL -> Chronic lymphocytic leukaemia"),
        # -- NAD must NOT be present --
        "nad":          (None, "NAD must NOT be coded (always-ignore)"),
        # -- Current session synonyms --
        "tiredness":    ("synonym_audit_april_2026", "Fatigue synonym"),
        "tired":        ("synonym_audit_april_2026", "Fatigue synonym"),
        "low mood":     ("synonym_audit_april_2026", "Mental health -- corrected mapping"),
        "decreased appetite": ("synonym_audit_april_2026", "Appetite -- corrected from Excessive"),
        "vomiting":     ("synonym_audit_april_2026", "Nausea -- corrected from Vomiting food"),
        "rectal bleeding": ("synonym_audit_april_2026", "Bowel -- corrected from Painful"),
        "bruising":     ("synonym_audit_april_2026", "Systemic -- corrected"),
        "lump":         ("synonym_audit_april_2026", "Systemic -- corrected from thyroid"),
        "swollen glands": ("synonym_audit_april_2026", "Lymphadenopathy"),
        "lymph node swelling": ("synonym_audit_april_2026", "Lymphadenopathy"),
        "reflux":       ("synonym_audit_april_2026", "Acid reflux (finding)"),
        "confusion":    ("synonym_audit_april_2026", "Mental health -- corrected"),
        # -- Lab result phrases --
        "glycosuria":   ("synonym_audit_april_2026", "Lab results"),
        "glucose +":    ("synonym_audit_april_2026", "Lab results dipstick"),
        "proteinuria":  ("synonym_audit_april_2026", "Lab results"),
        "protein +":    ("synonym_audit_april_2026", "Lab results dipstick"),
        "psa elevated": ("synonym_audit_april_2026", "Lab results PSA"),
        "low hb":       ("synonym_audit_april_2026", "Lab results Hb"),
        "raised creatinine": ("synonym_audit_april_2026", "Lab results creatinine"),
        "neutrophilia": ("synonym_audit_april_2026", "Lab results"),
        "leucocytes in urine": ("synonym_audit_april_2026", "Lab results dipstick"),
    }

    print("Spot-check of expected surface forms:")
    print(f"  {'Status':<6} {'Normalized form':<28} {'Description'}")
    print("  " + "-" * 70)

    ok = missing = unexpected = 0
    for norm, (expected_prov, desc) in checks.items():
        present = norm.lower() in normalized_set
        if norm == "nad":
            if present:
                print(f"  WARN   {norm:<28} SHOULD NOT exist -- NAD is always-ignored")
                unexpected += 1
            else:
                print(f"  OK     {norm:<28} Not present (correct -- always-ignored)")
                ok += 1
        else:
            if present:
                print(f"  OK     {norm:<28} {desc}")
                ok += 1
            else:
                print(f"  MISS   {norm:<28} {desc} -- NOT FOUND")
                missing += 1

    print()
    print(f"Result: {ok} OK  |  {missing} missing  |  {unexpected} unexpected")
    if missing:
        print("\nMissing forms need to be re-written.")
    if not missing and not unexpected:
        print("All expected surface forms are present and NAD is correctly absent.")


if __name__ == "__main__":
    main()
