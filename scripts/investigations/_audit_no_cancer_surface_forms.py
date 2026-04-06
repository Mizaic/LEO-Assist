"""Audit surface forms mapped to 395100000 (No evidence of cancer found).

Checks the terminology server for any surface form that maps to this concept
and flags those that look like routine screening negatives rather than
post-pathway discharge confirmations.  Deletes bad ones if --fix is passed.

Run:
    python scripts/investigations/_audit_no_cancer_surface_forms.py
    python scripts/investigations/_audit_no_cancer_surface_forms.py --fix
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets
load_keyvault_secrets()
from libs.auth.service_auth import get_service_auth_header
import requests

SESSION = requests.Session()
SESSION.headers.update(get_service_auth_header())
BASE = "http://localhost:8001"

CONCEPT_ID = "395100000"

SCREENING_PATTERNS = [
    "cervical smear",
    "cervical cytology",
    "smear negative",
    "smear: negative",
    "hpv not detected",
    "hpv test",
    "high risk hpv",
    "negative fit",
    "fobt",
    "faecal",
    "overall negative",
    "bowel cancer screening",
    "normal recall",
    "no cytology",
    "cytology normal",
    "cytology negative",
    "cytology laboratory",
    "screening negative",
    "negative result",
]


def _fetch_surface_forms(concept_id: str) -> list[dict]:
    """Fetch all surface forms mapped to a given concept from the terminology API."""
    r = SESSION.get(
        f"{BASE}/terminology/surface-forms",
        params={"concept_id": concept_id, "limit": 500},
        timeout=30,
    )
    if r.status_code == 404:
        return []
    r.raise_for_status()
    data = r.json()
    return data.get("items") or data.get("surface_forms") or (data if isinstance(data, list) else [])


def _delete_surface_form(form_id: str) -> bool:
    r = SESSION.delete(f"{BASE}/terminology/surface-forms/{form_id}", timeout=30)
    return r.status_code in (200, 204)


def is_screening_form(form: str) -> bool:
    fl = form.lower()
    return any(p in fl for p in SCREENING_PATTERNS)


def main(fix: bool) -> None:
    print(f"Fetching surface forms for concept {CONCEPT_ID} ...")
    forms = _fetch_surface_forms(CONCEPT_ID)
    print(f"Found {len(forms)} surface form(s) mapped to {CONCEPT_ID}")
    print()

    if not forms:
        print("No surface forms found -- nothing to check.")
        return

    bad: list[dict] = []
    ok_forms: list[dict] = []

    for sf in forms:
        form_text = sf.get("form") or sf.get("surface_form") or sf.get("normalized") or ""
        is_bad = is_screening_form(form_text)
        if is_bad:
            bad.append(sf)
        else:
            ok_forms.append(sf)

    print(f"Legitimate forms ({len(ok_forms)}):")
    for sf in ok_forms:
        form_text = sf.get("form") or sf.get("surface_form") or sf.get("normalized") or ""
        print(f"  [OK ] {form_text!r}")

    print()
    print(f"Screening false positives ({len(bad)}):")
    for sf in bad:
        form_text = sf.get("form") or sf.get("surface_form") or sf.get("normalized") or ""
        fid = sf.get("id") or sf.get("form_id") or ""
        tag = "[FIX]" if fix else "[BAD]"
        print(f"  {tag} id={fid}  form={form_text!r}")

    if not bad:
        print("  None -- surface forms look clean.")
        return

    if fix:
        print()
        deleted = 0
        for sf in bad:
            fid = sf.get("id") or sf.get("form_id") or ""
            if not fid:
                print(f"  [SKIP] No ID for form -- cannot delete: {sf}")
                continue
            ok = _delete_surface_form(str(fid))
            status = "DELETED" if ok else "FAILED"
            form_text = sf.get("form") or sf.get("surface_form") or ""
            print(f"  [{status}] {form_text!r}")
            if ok:
                deleted += 1
        print(f"\nDeleted {deleted}/{len(bad)} bad surface forms.")
    else:
        print()
        print(f"Run with --fix to delete these {len(bad)} bad form(s).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fix", action="store_true", help="Delete bad surface forms")
    args = parser.parse_args()
    main(fix=args.fix)
