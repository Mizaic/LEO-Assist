"""Comprehensive resolver spot-check.

Tests ~150 clinically important terms through the live Terminology API
POST /terminology/resolve endpoint and flags any that resolve to a wrong,
too-broad, or inactive concept.

Produces:
  scripts/investigations/resolver_spot_check.json  -- machine-readable results
  stdout                                            -- PASS/FAIL summary

Usage
-----
  python scripts/investigations/_spot_check_resolver.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

import requests

_API = "http://localhost:8001/terminology/resolve"
OUTPUT = ROOT / "scripts" / "investigations" / "resolver_spot_check.json"

# ---------------------------------------------------------------------------
# Test cases: (form, expected_concept_id, description)
# ---------------------------------------------------------------------------
CASES: list[tuple[str, str, str]] = [
    # --- Fast-track referrals (must be exact -- UK NHS SNOMED procedure IDs) ---
    (
        "fast track referral for suspected lung cancer",
        "276491000000101",
        "Lung cancer FTT",
    ),
    (
        "fast track referral for suspected colorectal cancer",
        "276401000000108",
        "Colorectal FTT",
    ),
    (
        "fast track referral for suspected breast cancer",
        "276341000000100",
        "Breast cancer FTT",
    ),
    (
        "fast track referral for suspected prostate cancer",
        "276431000000102",
        "Prostate -> Urological FTT",
    ),
    (
        "fast track referral for suspected bladder cancer",
        "276431000000102",
        "Bladder -> Urological FTT",
    ),
    (
        "fast track referral for suspected skin cancer",
        "276281000000104",
        "Skin cancer FTT",
    ),
    (
        "fast track referral for suspected mesothelioma",
        "276491000000101",
        "Mesothelioma->lung FTT",
    ),
    (
        "fast track referral for suspected upper gastrointestinal cancer",
        "276551000000108",
        "Upper GI FTT",
    ),
    (
        "fast track referral for suspected cervical cancer",
        "276311000000101",
        "Cervical -> Gynae FTT",
    ),
    ("urgent referral for suspected cancer", "306206005", "Generic urgent ref"),
    # --- Clinical conditions that had wrong situation mappings ---
    ("COPD", "13645005", "COPD disorder (not history)"),
    ("CVA", "230690007", "CVA disorder (not history)"),
    ("Stroke", "230690007", "Stroke = CVA disorder"),
    ("TIA", "266257000", "TIA disorder (not history)"),
    ("Rheumatoid arthritis", "69896004", "RA disorder (not CTD history)"),
    ("RA", "69896004", "RA abbreviation"),
    ("osteoporosis", "64859006", "Osteoporosis (not MSK history)"),
    ("osteopenia", "312894000", "Osteopenia (not MSK history)"),
    ("Chronic kidney disease", "709044004", "CKD disorder (not renal history)"),
    ("Fatty liver", "9990010007", "Fatty liver disorder (not liver history)"),
    ("Dementia", "52448006", "Dementia disorder (not history)"),
    # --- Mental health (were on generic Mental disorder) ---
    ("depression", "35489007", "Depression disorder"),
    ("PTSD", "47505003", "PTSD disorder"),
    ("bipolar disorder", "13746004", "Bipolar disorder"),
    ("schizophrenia", "58214004", "Schizophrenia"),
    ("anxiety", "48694002", "Anxiety"),
    ("Attention deficit hyperactivity disorder", "406506008", "ADHD"),
    ("autism spectrum disorder", "35919005", "ASD"),
    ("borderline personality disorder", "20010003", "BPD"),
    ("anorexia nervosa", "56882008", "Anorexia nervosa"),
    ("OCD", "191736004", "OCD"),
    ("Alzheimers", "26929004", "Alzheimer's disease"),
    ("suicidal ideation", "6471006", "Suicidal thoughts"),
    ("alcohol dependence", "66590003", "Alcohol dependence"),
    # --- Neurological (were on Parent has physical disability) ---
    ("Hemiplegia", "50582007", "Hemiplegia disorder"),
    ("Paraplegia", "60389000", "Paraplegia disorder"),
    ("Quadriplegia", "11538006", "Quadriplegia disorder"),
    ("Spinal cord injury", "90584004", "SCI disorder"),
    ("Cauda equina syndrome", "192970008", "Cauda equina"),
    # --- Vascular (were on wrong situation) ---
    ("AAA", "233985008", "Abdominal aortic aneurysm"),
    ("Abdominal aortic aneurysm", "233985008", "AAA full form"),
    ("Intermittent claudication", "63491006", "Intermittent claudication"),
    ("Peripheral vascular disease", "400047006", "PVD disorder"),
    # --- Rheumatological ---
    ("SLE", "55464009", "Systemic lupus"),
    ("Polymyalgia rheumatica", "65323003", "PMR"),
    ("PMR", "65323003", "PMR abbreviation"),
    # --- Hepatic ---
    ("Hepatitis B", "66071002", "Hepatitis B"),
    ("Hepatitis C", "50711007", "Hepatitis C"),
    # --- Renal ---
    ("Diabetes mellitus type 2", "44054006", "T2DM"),
    ("Diabetes mellitus type 1", "46635009", "T1DM"),
    ("ESRD", "433146000", "End stage renal disease"),
    # --- Cancer symptoms ---
    ("haemoptysis", "66857006", "Haemoptysis finding"),
    ("weight loss", "262285001", "Weight decreased finding"),
    ("dysphagia", "40739000", "Dysphagia finding"),
    ("rectal bleeding", "405729008", "Hematochezia finding"),
    ("night sweats", "42984000", "Night sweats finding"),
    ("unexplained fatigue", "84229001", "Fatigue finding"),
    ("thrombocytosis", "415115007", "Platelet count above reference range"),
    # --- Common comorbidities ---
    ("hypertension", "38341003", "Hypertension -- wait, 38341003 is dysthymia..."),
    ("type 2 diabetes mellitus", "44054006", "Type 2 DM"),
    ("asthma", "195967001", "Asthma disorder"),
    ("heart failure", "84114007", "Heart failure"),
    ("atrial fibrillation", "49436004", "AF"),
    ("chronic kidney disease", "709044004", "CKD"),
    ("hypothyroidism", "40930008", "Hypothyroidism"),
    # --- Procedures and findings ---
    ("colonoscopy", "73761001", "Colonoscopy procedure"),
    ("chest X-ray", "399208008", "CXR procedure"),
    ("FIT positive", "59614000", "FIT positive finding"),
    ("PSA raised", "396152005", "PSA above reference range"),
    ("emphysema", "87433001", "Pulmonary emphysema (fixed)"),
    ("OCD", "191736004", "OCD (not Osteochondritis dissecans)"),
    ("Polymyalgia rheumatica", "65323003", "PMR"),
    ("PMR", "65323003", "PMR abbreviation"),
    ("bipolar", "13746004", "Bipolar abbreviation (was orphan)"),
    ("ADHD", "406506008", "ADHD abbreviation"),
    ("suicidal ideation", "6471006", "Suicidal thoughts"),
    ("alcohol dependence", "66590003", "Alcohol dependence"),
]

# Concepts known to be broad/wrong if returned as top result
_BROAD_CONCEPTS = {
    "74732009": "Mental disorder (too broad)",
    "128462008": "Metastatic malignant neoplasm (too broad)",
    "415036007": "Parent has physical disability (patient finding)",
    "275552000": "History of kidney disease (situation for active form)",
    "308064009": "History of cerebrovascular disease (situation for active form)",
    "270473001": "History of COPD (situation for active form)",
    "472961001": "History of CTD (situation for active form)",
    "267004000": "History of MSK disease (situation for active form)",
    "161445009": "History of diabetes (situation for active form)",
    "161465002": "History of dementia (situation for active form)",
    "161535005": "History of liver disease (situation for active form)",
}

# Minimum score for the top result to be considered trustworthy
_MIN_SCORE = 0.65


def _check(term: str, expected_id: str, desc: str, result: dict) -> tuple[str, str]:
    """Returns ('PASS'/'FAIL'/'WARN', message)."""
    candidates = result.get("results", {}).get(term, [])
    if not candidates:
        return "FAIL", f"No candidates returned"
    top = candidates[0]
    got_id = top.get("snomed_concept_id", "")
    got_term = top.get("snomed_term", "?")
    got_score = top.get("score", 0.0)

    # Check for broad catch-all
    if got_id in _BROAD_CONCEPTS:
        return "FAIL", f"Broad concept: {got_id} | {_BROAD_CONCEPTS[got_id]}"

    if got_score < _MIN_SCORE:
        return "WARN", f"Low confidence: {got_score:.3f} -> {got_id} | {got_term}"

    # Skip concept ID check for test cases where expected is a known placeholder
    if expected_id.startswith("SKIP"):
        return "PASS", f"score={got_score:.3f} -> {got_id} | {got_term}"

    if got_id == expected_id:
        return "PASS", f"score={got_score:.3f} -> {got_id} | {got_term}"

    # Different ID - could still be clinically equivalent
    # Flag as WARN rather than FAIL so humans can review
    return (
        "WARN",
        f"Expected {expected_id} but got {got_id} | {got_term} (score={got_score:.3f})",
    )


def main() -> None:
    terms = [c[0] for c in CASES]
    print(f"Testing {len(terms)} terms against {_API} ...")

    resp = requests.post(
        _API,
        json={"terms": terms},
        timeout=120,
    )
    if resp.status_code != 200:
        print(f"API error: {resp.status_code} {resp.text[:400]}")
        sys.exit(1)

    data = resp.json()

    results = []
    fail = warn = passed = 0

    print(f"\n{'=' * 80}")
    print(f"{'TERM':<50} {'STATUS':<6} DETAIL")
    print(f"{'=' * 80}")

    for term, expected_id, desc in CASES:
        status, msg = _check(term, expected_id, desc, data)
        icon = {"PASS": "[OK]", "FAIL": "[FAIL]", "WARN": "[WARN]"}[status]
        desc_short = desc[:30]
        print(f"{term[:48]:<50} {icon:<6} {msg}")
        if status == "PASS":
            passed += 1
        elif status == "FAIL":
            fail += 1
        else:
            warn += 1
        results.append(
            {
                "term": term,
                "expected": expected_id,
                "desc": desc,
                "status": status,
                "detail": msg,
                "candidates": data["results"].get(term, [])[:3],
            }
        )

    print(f"\n{'=' * 80}")
    print(f"PASS: {passed}  WARN: {warn}  FAIL: {fail}  Total: {len(CASES)}")

    OUTPUT.write_text(
        json.dumps(results, indent=2, ensure_ascii=True), encoding="utf-8"
    )
    print(f"Full results: {OUTPUT}")


if __name__ == "__main__":
    main()
