"""Pin surface forms identified as missing by the v3 audit run.

Gaps addressed:
  - D-dimer: wrong concept (25607008=organism) -> correct procedure 940711000000100
  - HRT started (170955009)
  - HRT stopped / historical (170958006)
  - Safeguarding concern about sexual abuse (1874111000000101)
  - Victim of child sexual abuse (700229002)
  - Low probability of DVT (513251000000101)
  - Soft tissue lesion of lower leg (240010005)
  - Wells DVT score low (replaces wrong body-structure codes)
  - Physical deconditioning (31031000119102)

Run:
    python scripts/investigations/_pin_audit_gaps_v3.py
    python scripts/investigations/_pin_audit_gaps_v3.py --verify-only
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
PROVENANCE = "pin-audit-gaps-v3-2026-04-05"

SESSION = requests.Session()
SESSION.headers.update(get_service_auth_header())

# ---------------------------------------------------------------------------
# Surface forms: (text, snomed_concept_id, preferred_term, confidence)
# confidence=1.0 for exact-match pins; 0.95 for alias phrasings
# ---------------------------------------------------------------------------
_CANONICAL = [
    # -- D-dimer: replace wrong organism concept with correct procedure ------
    (
        "d-dimer",
        "940711000000100",
        "Measurement of concentration of D-dimer in plasma specimen (procedure)",
        1.0,
    ),
    (
        "d dimer",
        "940711000000100",
        "Measurement of concentration of D-dimer in plasma specimen (procedure)",
        1.0,
    ),
    (
        "ddimer",
        "940711000000100",
        "Measurement of concentration of D-dimer in plasma specimen (procedure)",
        1.0,
    ),
    (
        "d-dimer test",
        "940711000000100",
        "Measurement of concentration of D-dimer in plasma specimen (procedure)",
        1.0,
    ),
    (
        "d-dimer result",
        "940711000000100",
        "Measurement of concentration of D-dimer in plasma specimen (procedure)",
        1.0,
    ),
    # -- HRT started --------------------------------------------------------
    (
        "hrt started",
        "170955009",
        "Hormone replacement therapy started (situation)",
        1.0,
    ),
    (
        "hormone replacement therapy started",
        "170955009",
        "Hormone replacement therapy started (situation)",
        1.0,
    ),
    (
        "started hrt",
        "170955009",
        "Hormone replacement therapy started (situation)",
        0.95,
    ),
    (
        "commenced hrt",
        "170955009",
        "Hormone replacement therapy started (situation)",
        0.95,
    ),
    (
        "initiated hormone replacement therapy",
        "170955009",
        "Hormone replacement therapy started (situation)",
        0.95,
    ),
    # -- HRT stopped --------------------------------------------------------
    (
        "hrt stopped",
        "170958006",
        "Hormonal replacement therapy stopped (situation)",
        1.0,
    ),
    (
        "hormone replacement therapy stopped",
        "170958006",
        "Hormonal replacement therapy stopped (situation)",
        1.0,
    ),
    (
        "hrt discontinued",
        "170958006",
        "Hormonal replacement therapy stopped (situation)",
        0.95,
    ),
    (
        "previous trial of hrt",
        "170958006",
        "Hormonal replacement therapy stopped (situation)",
        0.9,
    ),
    (
        "hrt patches unsuitable",
        "170958006",
        "Hormonal replacement therapy stopped (situation)",
        0.9,
    ),
    # Medication review done (314530002) intentionally excluded --
    # it is an administrative process code not a clinical entity.
    # -- Safeguarding concern: sexual abuse ---------------------------------
    (
        "safeguarding concern",
        "1874111000000101",
        "Safeguarding concern about sexual abuse (finding)",
        0.9,
    ),
    (
        "safeguarding concern sexual abuse",
        "1874111000000101",
        "Safeguarding concern about sexual abuse (finding)",
        1.0,
    ),
    (
        "safeguarding referral",
        "1874111000000101",
        "Safeguarding concern about sexual abuse (finding)",
        0.85,
    ),
    (
        "child safeguarding concern",
        "1874111000000101",
        "Safeguarding concern about sexual abuse (finding)",
        0.95,
    ),
    (
        "disclosure of abuse",
        "1874111000000101",
        "Safeguarding concern about sexual abuse (finding)",
        0.9,
    ),
    # -- Victim of child sexual abuse ---------------------------------------
    (
        "victim of child sexual abuse",
        "700229002",
        "Victim of child sexual abuse (finding)",
        1.0,
    ),
    (
        "childhood sexual abuse",
        "700229002",
        "Victim of child sexual abuse (finding)",
        0.95,
    ),
    (
        "history of child sexual abuse",
        "700229002",
        "Victim of child sexual abuse (finding)",
        0.95,
    ),
    (
        "sexually abused as a child",
        "700229002",
        "Victim of child sexual abuse (finding)",
        0.95,
    ),
    # -- Low probability of DVT (Wells score) -------------------------------
    (
        "low probability of dvt",
        "513251000000101",
        "Low probability of deep vein thrombosis (finding)",
        1.0,
    ),
    (
        "low risk dvt",
        "513251000000101",
        "Low probability of deep vein thrombosis (finding)",
        0.95,
    ),
    (
        "wells score low dvt",
        "513251000000101",
        "Low probability of deep vein thrombosis (finding)",
        0.95,
    ),
    (
        "wells dvt score low probability",
        "513251000000101",
        "Low probability of deep vein thrombosis (finding)",
        0.95,
    ),
    # -- Soft tissue lesion of lower leg ------------------------------------
    (
        "soft tissue sprain",
        "240010005",
        "Soft tissue lesion of lower leg and ankle (disorder)",
        0.9,
    ),
    (
        "soft tissue injury lower leg",
        "240010005",
        "Soft tissue lesion of lower leg and ankle (disorder)",
        0.95,
    ),
    (
        "soft tissue lesion lower leg",
        "240010005",
        "Soft tissue lesion of lower leg and ankle (disorder)",
        1.0,
    ),
    # -- Physical deconditioning --------------------------------------------
    (
        "deconditioning",
        "31031000119102",
        "Physical deconditioning (finding)",
        0.95,
    ),
    (
        "physical deconditioning",
        "31031000119102",
        "Physical deconditioning (finding)",
        1.0,
    ),
    (
        "likely some deconditioning",
        "31031000119102",
        "Physical deconditioning (finding)",
        0.9,
    ),
]

# Forms to verify after write (spot-check the most critical)
_VERIFY = [
    ("d-dimer", "940711000000100"),
    ("ddimer", "940711000000100"),
    ("medication review done", "314530002"),
    ("hrt started", "170955009"),
    ("safeguarding concern sexual abuse", "1874111000000101"),
    ("victim of child sexual abuse", "700229002"),
    ("low probability of dvt", "513251000000101"),
]


def _upsert(form: str, concept_id: str, confidence: float) -> tuple[bool, str]:
    payload = {
        "form": form,
        "normalized": normalize_surface(form),
        "concept_id": concept_id,
        "confidence": confidence,
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
    print(f"Pinning {len(_CANONICAL)} surface forms (v3 audit gaps) ...\n")
    ok_count = fail_count = 0
    for form, cid, label, conf in _CANONICAL:
        ok, msg = _upsert(form, cid, conf)
        status = "OK  " if ok else "FAIL"
        print(f"  [{status}] {form!r}")
        print(f"           -> {cid} | {label}")
        if not ok:
            print(f"           Error: {msg}")
            fail_count += 1
        else:
            ok_count += 1
        time.sleep(0.05)
    print()
    print("=" * 70)
    print(f"Written: {ok_count}  Failed: {fail_count}")
    if fail_count:
        sys.exit(1)


def run_verify() -> None:
    print(f"Verifying {len(_VERIFY)} critical lookups ...\n")
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
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pin surface forms for v3 audit gaps"
    )
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.verify_only:
        run_verify()
    else:
        run_fixes()
        print("\nRunning post-pin verification ...\n")
        run_verify()


if __name__ == "__main__":
    main()
