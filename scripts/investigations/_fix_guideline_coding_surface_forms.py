"""Fix missing and wrong surface form mappings for NG12 guideline coding.

Identified errors (pre-commit audit of guidance_rule_extraction pipeline):

  1. 'new-onset diabetes' / 'new onset diabetes'
     Resolver returns 233821000 (New onset ANGINA) -- completely wrong concept.
     Correct: 405749004 (Newly diagnosed diabetes).

  2. 'chest infection'
     Resolver returns 240871004 (Capillaria aerophila chest infection) -- a rare
     parasitic lung infection, not a generic chest infection.
     Correct: 50417007 (Lower respiratory tract infection).

  3. 'reflux dyspepsia'
     Resolver returns 149941000119100 (Vesicoureteral reflux) -- urological reflux,
     not the GI symptom in the oesophageal cancer recommendation (NG12 1.2.1).
     Correct: 235595009 (Gastroesophageal reflux disease).

  4. 'unexplained fatigue'
     Resolver returns 237145004 (Unexplained INFERTILITY) -- wrong concept.
     Correct: 84229001 (Fatigue finding).

  5. 'pleural disease' / 'chest signs compatible with pleural disease'
     Resolver returns 860791002 (Pleural effusion due to neoplastic disease) --
     too specific and clinically leading.
     Correct: 88075009 (Disorder of pleura -- broad, non-specific).

  6. 'raised platelet count'
     Resolver returns 61928009 (Platelet count procedure) -- a procedure, not a
     finding. The criterion is a clinical finding.
     Correct: 6631009 (Thrombocytosis disorder).

  7. 'fast track referral for suspected mesothelioma'
     No mesothelioma-specific fast track exists in SNOMED CT.
     NICE NG12 manages mesothelioma on the lung cancer pathway.
     Correct action: 276491000000101 (Fast track referral for suspected lung cancer).

All fixes go through /terminology/surface-forms/upsert-mapping so the in-memory
resolver cache is updated immediately without a Neo4j direct write.

Run:
    python scripts/investigations/_fix_guideline_coding_surface_forms.py

Then verify:
    python scripts/investigations/_fix_guideline_coding_surface_forms.py --verify-only
"""

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

load_keyvault_secrets()

from libs.auth.service_auth import get_service_auth_header

BASE = "http://localhost:8001"
PROVENANCE = "fix-guideline-coding-ng12-2026-04-05"

SESSION = requests.Session()
SESSION.headers.update(get_service_auth_header())

# ---------------------------------------------------------------------------
# Surface form corrections for NG12 guideline coding
# Format: (surface_form, correct_concept_id, reason)
# ---------------------------------------------------------------------------
FIXES = [
    # -- new-onset diabetes: resolver was returning New onset Angina (233821000) --
    (
        "new-onset diabetes",
        "405749004",
        "Resolver returned 233821000=new onset angina (wrong). "
        "NG12 1.2.5 red flag criterion. Correct=newly diagnosed diabetes.",
    ),
    (
        "new onset diabetes",
        "405749004",
        "Alternate spacing. Same fix as new-onset diabetes.",
    ),
    (
        "newly diagnosed diabetes",
        "405749004",
        "Preferred phrasing for 405749004 (Newly diagnosed diabetes disorder).",
    ),
    # -- chest infection: resolver returning parasitic lung infection (240871004) --
    (
        "chest infection",
        "50417007",
        "Resolver returned 240871004=Capillaria aerophila infection (parasitic, rare). "
        "NG12 1.1.3 sign of possible lung cancer. "
        "Correct=50417007 lower respiratory tract infection.",
    ),
    (
        "recurrent chest infection",
        "50417007",
        "NG12 1.1.3 explicit phrase. Same root concept as chest infection.",
    ),
    (
        "persistent chest infection",
        "50417007",
        "NG12 1.1.3 explicit phrase. Same root concept as chest infection.",
    ),
    # -- reflux dyspepsia: resolver returning vesicoureteral reflux (149941000119100) --
    (
        "reflux dyspepsia",
        "235595009",
        "Resolver returned 149941000119100=vesicoureteral reflux (urological, wrong). "
        "NG12 1.2.1/1.2.3 oesophageal cancer criterion. "
        "Correct=235595009 gastroesophageal reflux disease.",
    ),
    (
        "gastro-oesophageal reflux",
        "235595009",
        "UK spelling. Maps to 235595009 gastroesophageal reflux disease.",
    ),
    (
        "gastroesophageal reflux",
        "235595009",
        "US spelling. Maps to 235595009 gastroesophageal reflux disease.",
    ),
    # -- unexplained fatigue: resolver returning unexplained infertility (237145004) --
    (
        "unexplained fatigue",
        "84229001",
        "Resolver returned 237145004=unexplained infertility (wrong). "
        "NG12 1.1.2 lung cancer symptom. Correct=84229001 fatigue finding.",
    ),
    # -- pleural disease: resolver returning neoplastic pleural effusion (860791002) --
    (
        "pleural disease",
        "88075009",
        "Resolver returned 860791002=pleural effusion due to neoplastic disease "
        "(too specific and clinically leading). "
        "NG12 1.1.6 non-specific sign. Correct=88075009 disorder of pleura.",
    ),
    (
        "chest signs compatible with pleural disease",
        "88075009",
        "Exact NG12 1.1.6 phrase. Maps to 88075009 disorder of pleura.",
    ),
    # -- raised platelet count: resolver returning procedure (61928009) --
    (
        "raised platelet count",
        "6631009",
        "Resolver returned 61928009=platelet count (procedure, wrong semantic class). "
        "NG12 1.2.3 criterion is a clinical finding. "
        "Correct=6631009 thrombocytosis disorder.",
    ),
    (
        "high platelet count",
        "6631009",
        "Alternate phrasing for thrombocytosis criterion. Maps to 6631009.",
    ),
    # -- mesothelioma fast track: no SNOMED concept; map to lung cancer pathway --
    (
        "fast track referral for suspected mesothelioma",
        "276491000000101",
        "No mesothelioma-specific fast track exists in SNOMED CT. "
        "NICE NG12 manages mesothelioma on the thoracic/lung cancer pathway. "
        "Correct=276491000000101 fast track referral for suspected lung cancer.",
    ),
    # -- pancreatic cancer fast track: map to upper GI pathway --
    (
        "fast track referral for suspected pancreatic cancer",
        "276551000000108",
        "Pancreatic cancer falls under upper GI pathway. "
        "Correct=276551000000108 fast track referral for suspected upper GI cancer.",
    ),
    # -- examination sign decomposition: breath sounds -------------------------
    (
        "reduced breath sounds",
        "58840004",
        "Resolver returns generic 'Respiratory sounds' observable entity. "
        "Correct=58840004 Decreased breath sounds (finding) for the decomposed "
        "examination sign in chest/pleural disease criteria.",
    ),
    (
        "diminished breath sounds",
        "58840004",
        "Alternate phrasing. Same concept as reduced breath sounds.",
    ),
    (
        "decreased breath sounds",
        "58840004",
        "Direct preferred term. Maps to 58840004.",
    ),
    # -- examination sign decomposition: percussion ----------------------------
    (
        "dullness to percussion",
        "39180009",
        "Resolver returns 'Diaphragmatic dullness' (too specific). "
        "Correct=39180009 Chest dull to percussion (finding).",
    ),
    # -- examination sign decomposition: pleural rub ---------------------------
    (
        "pleuritic rub",
        "37636003",
        "Resolver returns 'Pleuritic pain' (wrong -- a pain, not a rub). "
        "Correct=37636003 Pleural friction rub (finding).",
    ),
    (
        "pleural friction rub",
        "37636003",
        "Preferred SNOMED term. Maps to 37636003.",
    ),
    # -- treatment-resistant dyspepsia: resolver returns mental disorder -------
    (
        "treatment-resistant dyspepsia",
        "162031009",
        "Resolver returns 'Mental disorder' due to 'treatment resistant' token. "
        "NG12 1.2.3 criterion is GI dyspepsia persisting despite treatment. "
        "Correct=162031009 Indigestion (finding) as the broadest safe GI code.",
    ),
    (
        "treatment resistant dyspepsia",
        "162031009",
        "Alternate spacing. Same fix as treatment-resistant dyspepsia.",
    ),
]

# ---------------------------------------------------------------------------
# Verification table: (surface_form, expected_concept_id)
# ---------------------------------------------------------------------------
VERIFY_CASES = [
    ("new-onset diabetes", "405749004"),
    ("new onset diabetes", "405749004"),
    ("chest infection", "50417007"),
    ("reflux dyspepsia", "235595009"),
    ("unexplained fatigue", "84229001"),
    ("pleural disease", "88075009"),
    ("raised platelet count", "6631009"),
    ("fast track referral for suspected mesothelioma", "276491000000101"),
    ("fast track referral for suspected pancreatic cancer", "276551000000108"),
    ("reduced breath sounds", "58840004"),
    ("dullness to percussion", "39180009"),
    ("pleuritic rub", "37636003"),
    ("treatment-resistant dyspepsia", "162031009"),
]


def upsert(surface_form: str, concept_id: str) -> tuple[bool, str]:
    """Write surface form -> concept via terminology server API."""
    payload = {
        "form": surface_form,
        "normalized": surface_form.lower().strip(),
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
        return r.status_code in (200, 201), f"HTTP {r.status_code}: {r.text[:120]}"
    except Exception as exc:
        return False, str(exc)


def verify(surface_form: str, expected_id: str) -> tuple[bool, str]:
    """Confirm the resolver returns the expected concept ID via surface form resolve.

    Uses /terminology/resolve (the same path the extraction pipeline uses) rather
    than /terminology/search, so surface form weights are honoured correctly.
    """
    try:
        r = SESSION.post(
            f"{BASE}/terminology/resolve",
            json={"terms": [surface_form]},
            timeout=20,
        )
        data = r.json()
        results = (data.get("results") or {}).get(surface_form) or []
        top = results[0] if results else {}
        got = str(top.get("snomed_concept_id") or "")
        ok = got == expected_id
        label = top.get("snomed_term", "no results")
        return ok, f"top={got} ({label}) expected={expected_id}"
    except Exception as exc:
        return False, str(exc)


def run_fixes() -> None:
    print(f"Applying {len(FIXES)} surface form corrections ...")
    print()
    ok_count = fail_count = 0
    for surface_form, concept_id, reason in FIXES:
        ok, msg = upsert(surface_form, concept_id)
        status = "OK  " if ok else "FAIL"
        print(f"  [{status}] '{surface_form}' -> [{concept_id}]")
        print(f"         Reason : {reason}")
        if not ok:
            print(f"         Error  : {msg}")
            fail_count += 1
        else:
            ok_count += 1
        print()
        time.sleep(0.1)
    print("=" * 70)
    print(f"Done. Applied: {ok_count}  Failed: {fail_count}")
    if fail_count:
        print("Investigate failed writes before running the audit.")
        sys.exit(1)


def run_verify() -> None:
    print(f"Verifying {len(VERIFY_CASES)} resolver lookups ...")
    print()
    ok_count = fail_count = 0
    for surface_form, expected_id in VERIFY_CASES:
        ok, msg = verify(surface_form, expected_id)
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] '{surface_form}'")
        print(f"         {msg}")
        if not ok:
            fail_count += 1
        else:
            ok_count += 1
        print()
    print("=" * 70)
    print(f"Verification: {ok_count} passed  {fail_count} failed")
    if fail_count:
        print("Some surface forms are not resolving correctly.")
        print("Check whether the terminology server cache was flushed after writes.")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fix guideline coding surface forms")
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify; do not write any surface forms.",
    )
    args = parser.parse_args()
    if args.verify_only:
        run_verify()
    else:
        run_fixes()
        print()
        print("Running post-fix verification ...")
        print()
        run_verify()
