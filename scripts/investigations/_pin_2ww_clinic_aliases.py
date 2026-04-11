"""Pin surface forms for 'Seen in 2WW clinic' shorthand variants and benign
pathway discharge phrases.

Covers two gap categories found in the 39-episode referral-only audit:

  1. EMIS 'Seen in 2WW Clinic?' shorthand -- GP systems record specialist
     attendance using a generic 'Seen in 2WW Clinic?' or 'Was seen on 2WW'
     phrase rather than the full 'Seen in fast track suspected X clinic' text.
     These phrases are pinned to the appropriate SNOMED CT UK extension
     clinical-finding concepts.

  2. Benign pathway discharge phrases -- histopathology and clinic discharge
     letters use 'benign histology', 'benign on biopsy', etc. to close a 2WW
     cancer investigation pathway. These are pinned to 395100000
     (No evidence of cancer found) which is NOT a routine screening negative.

Run:
    python scripts/investigations/_pin_2ww_clinic_aliases.py

    # Verify only (no writes):
    python scripts/investigations/_pin_2ww_clinic_aliases.py --verify-only
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

from libs.auth.service_auth import get_service_auth_header
from libs.terminology.surface_normalize import normalize_surface

import requests

BASE = "http://localhost:8001"
PROVENANCE = "pin-2ww-clinic-aliases-2026-04-06"

SESSION = requests.Session()
SESSION.headers.update(get_service_auth_header())

# ---------------------------------------------------------------------------
# Surface forms -- Seen in 2WW clinic variants (specialist visit milestone)
# Source: SNOMED CT UK extension clinical findings for cancer pathway milestones
# Generic concept: 382761000000101 - Seen in fast track suspected cancer clinic
# ---------------------------------------------------------------------------
_2WW_CLINIC_ALIASES: list[tuple[str, str, str]] = [
    # -- Generic (no site specified) ------------------------------------------
    (
        "Seen in 2WW Clinic",
        "382761000000101",
        "Seen in fast track suspected cancer clinic (finding)",
    ),
    (
        "Seen in 2WW Clinic?",
        "382761000000101",
        "Seen in fast track suspected cancer clinic (finding)",
    ),
    (
        "seen in 2ww clinic",
        "382761000000101",
        "Seen in fast track suspected cancer clinic (finding)",
    ),
    (
        "was seen on 2ww",
        "382761000000101",
        "Seen in fast track suspected cancer clinic (finding)",
    ),
    (
        "Was seen on 2WW",
        "382761000000101",
        "Seen in fast track suspected cancer clinic (finding)",
    ),
    (
        "attended 2ww clinic",
        "382761000000101",
        "Seen in fast track suspected cancer clinic (finding)",
    ),
    (
        "Seen in 2WW Clinic 2WW",
        "382761000000101",
        "Seen in fast track suspected cancer clinic (finding)",
    ),
    # -- Breast ---------------------------------------------------------------
    (
        "Seen in 2WW Breast Clinic",
        "382431000000103",
        "Seen in fast track suspected breast cancer clinic (finding)",
    ),
    (
        "seen in 2ww breast clinic",
        "382431000000103",
        "Seen in fast track suspected breast cancer clinic (finding)",
    ),
    (
        "seen at breast clinic",
        "382431000000103",
        "Seen in fast track suspected breast cancer clinic (finding)",
    ),
    (
        "seen at breast cancer clinic",
        "382431000000103",
        "Seen in fast track suspected breast cancer clinic (finding)",
    ),
    # -- Colorectal / lower GI ------------------------------------------------
    (
        "Seen in 2WW Colorectal Clinic",
        "382651000000108",
        "Seen in fast track suspected colorectal cancer clinic (finding)",
    ),
    (
        "seen in 2ww colorectal clinic",
        "382651000000108",
        "Seen in fast track suspected colorectal cancer clinic (finding)",
    ),
    (
        "seen in 2ww lower gi clinic",
        "382651000000108",
        "Seen in fast track suspected colorectal cancer clinic (finding)",
    ),
    (
        "seen at colorectal clinic",
        "382651000000108",
        "Seen in fast track suspected colorectal cancer clinic (finding)",
    ),
    # -- Upper GI -------------------------------------------------------------
    (
        "Seen in 2WW Upper GI Clinic",
        "382811000000108",
        "Seen in fast track suspected upper gastrointestinal cancer clinic (finding)",
    ),
    (
        "seen in 2ww upper gi clinic",
        "382811000000108",
        "Seen in fast track suspected upper gastrointestinal cancer clinic (finding)",
    ),
    (
        "seen at upper gi clinic",
        "382811000000108",
        "Seen in fast track suspected upper gastrointestinal cancer clinic (finding)",
    ),
    # -- Head and neck --------------------------------------------------------
    (
        "Seen in 2WW Head and Neck Clinic",
        "382621000000103",
        "Seen in fast track suspected head and neck cancer clinic (finding)",
    ),
    (
        "seen in 2ww head and neck clinic",
        "382621000000103",
        "Seen in fast track suspected head and neck cancer clinic (finding)",
    ),
    (
        "seen at head and neck clinic",
        "382621000000103",
        "Seen in fast track suspected head and neck cancer clinic (finding)",
    ),
    (
        "seen at ent clinic 2ww",
        "382621000000103",
        "Seen in fast track suspected head and neck cancer clinic (finding)",
    ),
    # -- Skin -----------------------------------------------------------------
    (
        "Seen in 2WW Skin Clinic",
        "382711000000103",
        "Seen in fast track suspected skin cancer clinic (finding)",
    ),
    (
        "seen in 2ww skin clinic",
        "382711000000103",
        "Seen in fast track suspected skin cancer clinic (finding)",
    ),
    (
        "seen at dermatology clinic 2ww",
        "382711000000103",
        "Seen in fast track suspected skin cancer clinic (finding)",
    ),
    # -- Urological -----------------------------------------------------------
    (
        "Seen in 2WW Urological Clinic",
        "382841000000109",
        "Seen in fast track suspected urological cancer clinic (finding)",
    ),
    (
        "seen in 2ww urological clinic",
        "382841000000109",
        "Seen in fast track suspected urological cancer clinic (finding)",
    ),
    (
        "seen in 2ww urology clinic",
        "382841000000109",
        "Seen in fast track suspected urological cancer clinic (finding)",
    ),
    (
        "seen at urology clinic 2ww",
        "382841000000109",
        "Seen in fast track suspected urological cancer clinic (finding)",
    ),
    # -- Gynaecological -------------------------------------------------------
    (
        "Seen in 2WW Gynaecological Clinic",
        "382511000000105",
        "Seen in fast track suspected gynaecological cancer clinic (finding)",
    ),
    (
        "seen in 2ww gynaecological clinic",
        "382511000000105",
        "Seen in fast track suspected gynaecological cancer clinic (finding)",
    ),
    (
        "seen in 2ww gynae clinic",
        "382511000000105",
        "Seen in fast track suspected gynaecological cancer clinic (finding)",
    ),
    # -- Haematological -------------------------------------------------------
    (
        "Seen in 2WW Haematological Clinic",
        "382581000000103",
        "Seen in fast track suspected haematological malignancy clinic (finding)",
    ),
    (
        "seen in 2ww haematological clinic",
        "382581000000103",
        "Seen in fast track suspected haematological malignancy clinic (finding)",
    ),
    (
        "seen in 2ww haematology clinic",
        "382581000000103",
        "Seen in fast track suspected haematological malignancy clinic (finding)",
    ),
    # -- Lung -----------------------------------------------------------------
    (
        "Seen in 2WW Lung Clinic",
        "382681000000102",
        "Seen in fast track suspected lung cancer clinic (finding)",
    ),
    (
        "seen in 2ww lung clinic",
        "382681000000102",
        "Seen in fast track suspected lung cancer clinic (finding)",
    ),
    (
        "seen at lung clinic 2ww",
        "382681000000102",
        "Seen in fast track suspected lung cancer clinic (finding)",
    ),
    # -- Children's tumour ----------------------------------------------------
    (
        "Seen in 2WW Childrens Tumour Clinic",
        "383201000000101",
        "Seen in fast track suspected childrens tumour clinic (finding)",
    ),
    (
        "seen in 2ww childrens tumour clinic",
        "383201000000101",
        "Seen in fast track suspected childrens tumour clinic (finding)",
    ),
    (
        "seen in 2ww children's tumour clinic",
        "383201000000101",
        "Seen in fast track suspected childrens tumour clinic (finding)",
    ),
    (
        "seen at childrens tumour clinic",
        "383201000000101",
        "Seen in fast track suspected childrens tumour clinic (finding)",
    ),
]

# ---------------------------------------------------------------------------
# Surface forms -- benign pathway discharge phrases -> 395100000
# Only for explicit pathway-level statements (biopsy, histopathology,
# clinic discharge letter). NOT for routine screening negatives.
# ---------------------------------------------------------------------------
_BENIGN_DISCHARGE_ALIASES: list[tuple[str, str, str]] = [
    (
        "benign histology",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "benign on biopsy",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "benign biopsy",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "benign biopsy result",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "benign pathology",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "confirmed benign",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "benign result",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "benign on pathology",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "benign on histopathology",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "no malignancy on biopsy",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "no malignancy on histology",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "no malignancy found on biopsy",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "benign on histology",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
]

_ALL_ALIASES = _2WW_CLINIC_ALIASES + _BENIGN_DISCHARGE_ALIASES


def _upsert(form: str, concept_id: str, preferred_term: str) -> tuple[bool, str]:
    payload = {
        "form": form,
        "normalized": normalize_surface(form),
        "concept_id": concept_id,
        "confidence": 1.0,
        "source": "manual",
        "provenance": PROVENANCE,
    }
    try:
        r = SESSION.post(
            f"{BASE}/terminology/surface-forms/upsert-mapping",
            json=payload,
            timeout=60,
        )
        return r.status_code in (200, 201), f"HTTP {r.status_code}"
    except Exception as exc:
        return False, str(exc)


def _resolve(phrase: str) -> tuple[str | None, str | None]:
    try:
        r = SESSION.post(
            f"{BASE}/terminology/resolve",
            json={"terms": [phrase]},
            timeout=20,
        )
        results = (r.json().get("results") or {}).get(phrase) or []
        top = results[0] if results else {}
        cid = str(top.get("snomed_concept_id") or "") or None
        term = top.get("snomed_term")
        return cid, term
    except Exception:
        return None, None


def run_fixes() -> None:
    print(f"Pinning {len(_ALL_ALIASES)} surface form aliases ...")
    print(f"  {len(_2WW_CLINIC_ALIASES)} specialist-visit (2WW clinic) aliases")
    print(f"  {len(_BENIGN_DISCHARGE_ALIASES)} benign pathway discharge aliases")
    print()
    pinned = already_ok = failed = 0

    for form, cid, label in _ALL_ALIASES:
        resolved_id, _ = _resolve(form)
        if resolved_id == cid:
            print(f"  [OK  ] {form!r} -> {cid}")
            already_ok += 1
            time.sleep(0.05)
            continue

        ok, msg = _upsert(form, cid, label)
        status = "PINNED" if ok else "FAIL  "
        print(f"  [{status}] {form!r}")
        print(f"           -> {cid} | {label}")
        if ok:
            pinned += 1
        else:
            print(f"           Error: {msg}")
            failed += 1
        time.sleep(0.1)

    print()
    print("=" * 70)
    print(f"Done. Pinned: {pinned}  Already OK: {already_ok}  Failed: {failed}")
    if failed:
        sys.exit(1)


def run_verify() -> None:
    print(f"Verifying {len(_ALL_ALIASES)} surface form aliases ...")
    print()
    ok_count = fail_count = 0

    for form, exp_id, _ in _ALL_ALIASES:
        resolved_id, resolved_term = _resolve(form)
        ok = resolved_id == exp_id
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {form!r}")
        print(f"         got={resolved_id} ({resolved_term}) want={exp_id}")
        if ok:
            ok_count += 1
        else:
            fail_count += 1
        time.sleep(0.05)

    print()
    print("=" * 70)
    print(f"Verification: {ok_count} passed  {fail_count} failed")
    if fail_count:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pin 2WW clinic alias and benign discharge surface forms"
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify; do not write surface forms.",
    )
    args = parser.parse_args()

    if args.verify_only:
        run_verify()
    else:
        run_fixes()
        print()
        print("Running post-pin verification ...")
        print()
        run_verify()


if __name__ == "__main__":
    main()
