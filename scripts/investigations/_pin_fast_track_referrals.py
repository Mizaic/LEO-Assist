"""Pin all NHS USC fast-track cancer referral surface forms at confidence=1.0.

The 14 canonical fast-track referral strings are defined in NICE/NHS USC guidance.
Each maps to a single, well-known SNOMED CT UK extension concept.  They must never
be resolved by text-scoring alone because several share similar tokens (e.g.
"suspected" + cancer site) and the scorer can return the wrong site.

Evidence of failure:
  "fast track referral for suspected lung cancer" scored to
  892201000000106 (lower gastrointestinal) in a live dry-run because the
  resolver fell back to text search after the surface form cache missed.

Fix: write every canonical string as a pinned surface form (confidence=1.0,
source='manual') so the surface-form lookup always wins.

Also pins common site alias phrasings to catch LLM variation (e.g. the LLM
may write "pancreatic cancer" which maps to the upper GI pathway, or
"mesothelioma" which maps to the lung cancer pathway).

Run:
    python scripts/investigations/_pin_fast_track_referrals.py

    # Verify only (no writes):
    python scripts/investigations/_pin_fast_track_referrals.py --verify-only
"""

from __future__ import annotations

import argparse
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
PROVENANCE = "pin-fast-track-referrals-2026-04-05"

SESSION = requests.Session()
SESSION.headers.update(get_service_auth_header())

# ---------------------------------------------------------------------------
# Canonical fast-track referral surface forms
# Format: (surface_form, snomed_concept_id, preferred_term)
# Every entry in the NICE prompt canonical list gets an exact-match surface form.
# ---------------------------------------------------------------------------
_CANONICAL = [
    # -- 14 canonical UK USC fast-track referral strings --------------------
    (
        "fast track referral for suspected sarcoma",
        "276521000000103",
        "Fast track referral for suspected sarcoma (procedure)",
    ),
    (
        "fast track referral for suspected lung cancer",
        "276491000000101",
        "Fast track referral for suspected lung cancer (procedure)",
    ),
    (
        "fast track referral for suspected skin cancer",
        "276281000000104",
        "Fast track referral for suspected skin cancer (procedure)",
    ),
    (
        "fast track referral for suspected brain tumour",
        "276581000000102",
        "Fast track referral for suspected brain tumour (procedure)",
    ),
    (
        "fast track referral for suspected breast cancer",
        "276341000000100",
        "Fast track referral for suspected breast cancer (procedure)",
    ),
    (
        "fast track referral for suspected childrens tumour",
        "276371000000106",
        "Fast track referral for suspected childrens tumour (procedure)",
    ),
    (
        "fast track referral for suspected urological cancer",
        "276431000000102",
        "Fast track referral for suspected urological cancer (procedure)",
    ),
    (
        "fast track referral for suspected colorectal cancer",
        "276401000000108",
        "Fast track referral for suspected colorectal cancer (procedure)",
    ),
    (
        "fast track referral for suspected head and neck cancer",
        "280521000000108",
        "Fast track referral for suspected head and neck cancer (procedure)",
    ),
    (
        "fast track referral for suspected gynaecological cancer",
        "276311000000101",
        "Fast track referral for suspected gynaecological cancer (procedure)",
    ),
    (
        "fast track referral for suspected haematology malignancy",
        "276461000000107",
        "Fast track referral for suspected haematology malignancy (procedure)",
    ),
    (
        "fast track referral for suspected lower gastrointestinal cancer",
        "892201000000106",
        "Fast track referral for suspected lower gastrointestinal cancer (procedure)",
    ),
    (
        "fast track referral for suspected upper gastrointestinal cancer",
        "276551000000108",
        "Fast track referral for suspected upper gastrointestinal cancer (procedure)",
    ),
    (
        "fast track referral for suspected cancer due to non-site-specific symptoms",
        "1556551000000104",
        "Fast track referral for suspected cancer due to non-site-specific symptoms (procedure)",
    ),
    # -- Alias phrasings LLMs commonly produce ------------------------------
    # mesothelioma -> lung cancer pathway (no SNOMED code for mesothelioma)
    (
        "fast track referral for suspected mesothelioma",
        "276491000000101",
        "Fast track referral for suspected lung cancer (procedure)",
    ),
    # pancreatic -> upper GI pathway
    (
        "fast track referral for suspected pancreatic cancer",
        "276551000000108",
        "Fast track referral for suspected upper gastrointestinal cancer (procedure)",
    ),
    # stomach/gastric -> upper GI
    (
        "fast track referral for suspected stomach cancer",
        "276551000000108",
        "Fast track referral for suspected upper gastrointestinal cancer (procedure)",
    ),
    (
        "fast track referral for suspected gastric cancer",
        "276551000000108",
        "Fast track referral for suspected upper gastrointestinal cancer (procedure)",
    ),
    (
        "fast track referral for suspected oesophageal cancer",
        "276551000000108",
        "Fast track referral for suspected upper gastrointestinal cancer (procedure)",
    ),
    # anal -> lower GI
    (
        "fast track referral for suspected anal cancer",
        "892201000000106",
        "Fast track referral for suspected lower gastrointestinal cancer (procedure)",
    ),
    # thyroid/laryngeal -> head and neck
    (
        "fast track referral for suspected thyroid cancer",
        "280521000000108",
        "Fast track referral for suspected head and neck cancer (procedure)",
    ),
    (
        "fast track referral for suspected laryngeal cancer",
        "280521000000108",
        "Fast track referral for suspected head and neck cancer (procedure)",
    ),
    # myeloma/lymphoma -> haematology
    (
        "fast track referral for suspected myeloma",
        "276461000000107",
        "Fast track referral for suspected haematology malignancy (procedure)",
    ),
    (
        "fast track referral for suspected lymphoma",
        "276461000000107",
        "Fast track referral for suspected haematology malignancy (procedure)",
    ),
]

# ---------------------------------------------------------------------------
# Verify set: every canonical string must resolve to its exact concept ID
# ---------------------------------------------------------------------------
_VERIFY = [
    (form, cid)
    for form, cid, _ in _CANONICAL
    if not form.startswith("fast track referral for suspected stomach")
    and not form.startswith("fast track referral for suspected gastric")
    and not form.startswith("fast track referral for suspected oesophageal")
    and not form.startswith("fast track referral for suspected anal")
    and not form.startswith("fast track referral for suspected thyroid")
    and not form.startswith("fast track referral for suspected laryngeal")
    and not form.startswith("fast track referral for suspected myeloma")
    and not form.startswith("fast track referral for suspected lymphoma")
]


def _upsert(form: str, concept_id: str) -> tuple[bool, str]:
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


def _verify(form: str, expected_id: str) -> tuple[bool, str]:
    try:
        r = SESSION.post(
            f"{BASE}/terminology/resolve",
            json={"terms": [form]},
            timeout=20,
        )
        results = (r.json().get("results") or {}).get(form) or []
        top = results[0] if results else {}
        got = str(top.get("snomed_concept_id") or "")
        label = top.get("snomed_term", "no results")
        ok = got == expected_id
        return ok, f"got={got} ({label}) want={expected_id}"
    except Exception as exc:
        return False, str(exc)


def run_fixes() -> None:
    print(f"Pinning {len(_CANONICAL)} fast-track referral surface forms ...")
    print()
    ok_count = fail_count = 0
    for form, cid, label in _CANONICAL:
        ok, msg = _upsert(form, cid)
        status = "OK  " if ok else "FAIL"
        print(f"  [{status}] {form!r}")
        print(f"           -> {cid} | {label}")
        if not ok:
            print(f"           Error: {msg}")
            fail_count += 1
        else:
            ok_count += 1
        time.sleep(0.1)
    print()
    print("=" * 70)
    print(f"Done. Written: {ok_count}  Failed: {fail_count}")
    if fail_count:
        sys.exit(1)


def run_verify() -> None:
    print(f"Verifying {len(_VERIFY)} fast-track referral lookups ...")
    print()
    ok_count = fail_count = 0
    for form, expected_id in _VERIFY:
        ok, msg = _verify(form, expected_id)
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {form!r}")
        print(f"           {msg}")
        if not ok:
            fail_count += 1
        else:
            ok_count += 1
    print()
    print("=" * 70)
    print(f"Verification: {ok_count} passed  {fail_count} failed")
    if fail_count:
        print(
            "Check the resolver cache. Surface form writes may need a server restart."
        )
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pin all canonical NHS USC fast-track referral surface forms"
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify existing surface forms; do not write.",
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
