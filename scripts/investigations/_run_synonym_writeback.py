"""
Write verified clinical synonym surface forms to the terminology server.

Includes corrections from manual review of pass-1 results:
  - decreased appetite / not eating: corrected from 102608004 to 64379006
  - vomiting: corrected from 225586007 to 249497008
  - low mood: corrected from 225455004 to 366979004
  - confusion: corrected from 40917007 to 130987000
  - rectal bleeding: corrected from 414991007 to 405729008
  - bruising: corrected from 373600006 to 297950006
  - lump: corrected from 237557003 to 248527007
  - reflux: user confirmed 698065002 (acid reflux finding)
  - swollen glands / lymph node swelling: 30746006 (lymphadenopathy disorder)

Also writes structured result format phrases:
  glycosuria, proteinuria, leucocytes in urine, PSA raised,
  Hb low, raised creatinine, neutrophilia, eosinophilia.

NAD is intentionally excluded -- ambiguous between 'No abnormality detected'
and 'No apparent distress'; handled by the always-ignore list in the client.

Run:
  python scripts/investigations/_run_synonym_writeback.py --dry-run
  python scripts/investigations/_run_synonym_writeback.py
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "services" / "api"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_ROOT / "secrets" / ".env.config", override=True)
try:
    from libs.keyvault.loader import load_keyvault_secrets  # noqa: E402

    load_keyvault_secrets()
except Exception as _kv_exc:
    print(f"[WARN] Key Vault load failed ({_kv_exc}); proceeding with env only")

import requests  # noqa: E402
from libs.auth.service_auth import get_service_auth_header  # noqa: E402

BASE = "http://localhost:8001"
UPSERT_URL = f"{BASE}/terminology/surface-forms/upsert-mapping"
PROVENANCE = "synonym_audit_april_2026"

# ---------------------------------------------------------------------------
# (surface_form, concept_id, preferred_term, group, note)
# ---------------------------------------------------------------------------
SURFACE_FORMS: list[tuple[str, str, str, str, str]] = [
    # -- Fatigue --
    ("tiredness", "84229001", "Fatigue", "Fatigue", ""),
    ("tired", "84229001", "Fatigue", "Fatigue", ""),
    ("exhaustion", "84229001", "Fatigue", "Fatigue", ""),
    ("chronically tired", "84229001", "Fatigue", "Fatigue", ""),
    ("lethargy", "214264003", "Lethargy", "Fatigue", ""),
    ("lethargic", "214264003", "Lethargy", "Fatigue", ""),
    ("no energy", "248274002", "Lack of energy", "Fatigue", ""),
    ("lack of energy", "248274002", "Lack of energy", "Fatigue", ""),
    # -- Appetite --
    ("poor appetite", "64379006", "Decrease in appetite", "Appetite", ""),
    ("reduced appetite", "64379006", "Decrease in appetite", "Appetite", ""),
    ("appetite reduced", "64379006", "Decrease in appetite", "Appetite", ""),
    (
        "decreased appetite",
        "64379006",
        "Decrease in appetite",
        "Appetite",
        "CORRECTED - was 102608004 Excessive appetite",
    ),
    (
        "not eating",
        "64379006",
        "Decrease in appetite",
        "Appetite",
        "CORRECTED - was 102608004",
    ),
    ("loss of appetite", "79890006", "Loss of appetite", "Appetite", ""),
    ("anorexia", "79890006", "Loss of appetite", "Appetite", "GP synonym use"),
    # -- Back pain --
    ("backache", "161891005", "Backache", "Back pain", ""),
    ("back ache", "161891005", "Backache", "Back pain", ""),
    ("lower back pain", "161891005", "Backache", "Back pain", ""),
    ("low back pain", "279039007", "Low back pain", "Back pain", ""),
    ("lumbar pain", "279039007", "Low back pain", "Back pain", ""),
    ("lumbago", "279039007", "Low back pain", "Back pain", ""),
    ("thoracic back pain", "279038004", "Thoracic back pain", "Back pain", ""),
    # -- Breathlessness --
    ("breathlessness", "267036007", "Dyspnea", "Breathlessness", ""),
    ("short of breath", "267036007", "Dyspnea", "Breathlessness", ""),
    ("can't breathe", "267036007", "Dyspnea", "Breathlessness", ""),
    ("difficulty breathing", "230145002", "Difficulty breathing", "Breathlessness", ""),
    ("breathing difficulty", "230145002", "Difficulty breathing", "Breathlessness", ""),
    # -- Weight --
    ("weight loss", "262285001", "Weight decreased", "Weight", ""),
    ("losing weight", "262285001", "Weight decreased", "Weight", ""),
    (
        "unintentional weight loss",
        "448765001",
        "Unintentional weight loss",
        "Weight",
        "",
    ),
    ("unexplained weight loss", "422868009", "Unexplained weight loss", "Weight", ""),
    ("weight gain", "262286000", "Weight increased", "Weight", ""),
    # -- Abdominal pain --
    ("tummy pain", "21522001", "Abdominal pain", "Abdo", ""),
    ("stomach pain", "21522001", "Abdominal pain", "Abdo", ""),
    ("belly pain", "21522001", "Abdominal pain", "Abdo", ""),
    ("abdo pain", "21522001", "Abdominal pain", "Abdo", ""),
    # -- Nausea/vomiting --
    ("nausea", "422587007", "Nausea", "Nausea", ""),
    (
        "vomiting",
        "249497008",
        "Vomiting symptom",
        "Nausea",
        "CORRECTED - was 225586007 Vomiting food",
    ),
    (
        "nausea and vomiting",
        "415709002",
        "Tendency to nausea and vomiting",
        "Nausea",
        "",
    ),
    # -- Bowel --
    ("diarrhoea", "62315008", "Diarrhea", "Bowel", ""),
    ("diarrhea", "62315008", "Diarrhea", "Bowel", ""),
    ("loose stools", "398032003", "Loose stool", "Bowel", ""),
    ("constipation", "14760008", "Constipation", "Bowel", ""),
    ("bloating", "116289008", "Abdominal bloating", "Bowel", ""),
    ("wind", "249504006", "Passing flatus", "Bowel", ""),
    ("indigestion", "162031009", "Indigestion", "Bowel", ""),
    ("dyspepsia", "162031009", "Indigestion", "Bowel", ""),
    ("heartburn", "16331000", "Heartburn", "Bowel", ""),
    (
        "reflux",
        "698065002",
        "Acid reflux",
        "Bowel",
        "User confirmed - finding not disorder",
    ),
    ("blood in stool", "405729008", "Hematochezia", "Bowel", ""),
    (
        "rectal bleeding",
        "405729008",
        "Hematochezia",
        "Bowel",
        "CORRECTED - was 414991007 Painful rectal bleeding",
    ),
    # -- Urinary --
    ("blood in urine", "34436003", "Blood in urine", "Urinary", ""),
    ("haematuria", "34436003", "Blood in urine", "Urinary", ""),
    ("passing blood", "34436003", "Blood in urine", "Urinary", ""),
    (
        "urinary frequency",
        "162116003",
        "Increased frequency of urination",
        "Urinary",
        "",
    ),
    (
        "frequency of urination",
        "162116003",
        "Increased frequency of urination",
        "Urinary",
        "",
    ),
    ("nocturia", "139394000", "Nocturia", "Urinary", ""),
    ("dysuria", "49650001", "Dysuria", "Urinary", ""),
    ("burning urine", "49650001", "Dysuria", "Urinary", ""),
    ("urinary incontinence", "165232002", "Urinary incontinence", "Urinary", ""),
    # -- Systemic --
    ("night sweats", "42984000", "Night sweats", "Systemic", ""),
    ("drenching sweats", "42984000", "Night sweats", "Systemic", ""),
    ("dizziness", "404640003", "Dizziness", "Systemic", ""),
    ("dizzy", "404640003", "Dizziness", "Systemic", ""),
    ("headache", "25064002", "Headache", "Systemic", ""),
    ("palpitations", "80313002", "Palpitations", "Systemic", ""),
    ("ankle swelling", "26237000", "Ankle edema", "Systemic", ""),
    ("oedema", "267038008", "Edema", "Systemic", ""),
    ("jaundice", "18165001", "Jaundice", "Systemic", ""),
    ("itch", "418363000", "Itching of skin", "Systemic", ""),
    ("itching", "418363000", "Itching of skin", "Systemic", ""),
    ("pruritus", "418363000", "Itching of skin", "Systemic", ""),
    ("easy bruising", "424131007", "Easy bruising", "Systemic", ""),
    (
        "bruising",
        "297950006",
        "Finding related to bruising",
        "Systemic",
        "CORRECTED - was 373600006 Multiple bruising",
    ),
    (
        "lump",
        "248527007",
        "Single lump",
        "Systemic",
        "CORRECTED - was 237557003 Mass of thyroid gland",
    ),
    (
        "swollen glands",
        "30746006",
        "Lymphadenopathy",
        "Systemic",
        "NOT FOUND pass1 - resolved via direct search",
    ),
    (
        "lymph node swelling",
        "30746006",
        "Lymphadenopathy",
        "Systemic",
        "NOT FOUND pass1 - resolved via direct search",
    ),
    (
        "swollen lymph nodes",
        "30746006",
        "Lymphadenopathy",
        "Systemic",
        "NOT FOUND pass1 - resolved via direct search",
    ),
    # -- Pain --
    ("chest tightness", "23924001", "Tight chest", "Pain", ""),
    ("pleuritic pain", "2237002", "Pleuritic pain", "Pain", ""),
    ("bone pain", "12584003", "Bone pain", "Pain", ""),
    ("joint pain", "57676002", "Pain of joint", "Pain", ""),
    ("arthralgia", "57676002", "Pain of joint", "Pain", ""),
    ("myalgia", "68962001", "Muscle pain", "Pain", ""),
    ("muscle pain", "68962001", "Muscle pain", "Pain", ""),
    ("hip pain", "49218002", "Pain of hip region", "Pain", ""),
    ("knee pain", "9990010001", "Pain of knee region", "Pain", ""),
    ("shoulder pain", "45326000", "Pain of shoulder region", "Pain", ""),
    ("neck pain", "81680005", "Neck pain", "Pain", ""),
    # -- Mental health --
    (
        "low mood",
        "366979004",
        "Depressed mood",
        "Mental health",
        "CORRECTED - was 225455004 Sociable mood (wrong)",
    ),
    ("depression", "35489007", "Depressive disorder", "Mental health", ""),
    ("anxiety", "48694002", "Anxiety", "Mental health", ""),
    ("brain fog", "386806002", "Impaired cognition", "Mental health", ""),
    ("memory problems", "386807006", "Memory impairment", "Mental health", ""),
    (
        "confusion",
        "130987000",
        "Acute confusion",
        "Mental health",
        "CORRECTED - was 40917007 Clouded consciousness",
    ),
    # -- Structured result format phrases (Option A) --
    ("glycosuria", "45154002", "Glycosuria", "Lab results", ""),
    ("glucose in urine", "45154002", "Glycosuria", "Lab results", ""),
    (
        "urine glucose positive",
        "45154002",
        "Glycosuria",
        "Lab results",
        "dipstick format",
    ),
    ("glucose +", "45154002", "Glycosuria", "Lab results", "dipstick format"),
    ("proteinuria", "29738008", "Proteinuria", "Lab results", ""),
    ("protein in urine", "29738008", "Proteinuria", "Lab results", ""),
    (
        "urine protein positive",
        "29738008",
        "Proteinuria",
        "Lab results",
        "dipstick format",
    ),
    ("protein +", "29738008", "Proteinuria", "Lab results", "dipstick format"),
    ("leucocytes in urine", "275741008", "Leukocytes in urine", "Lab results", ""),
    ("leukocytes in urine", "275741008", "Leukocytes in urine", "Lab results", ""),
    ("WBC in urine", "275741008", "Leukocytes in urine", "Lab results", ""),
    ("PSA elevated", "396152005", "PSA above reference range", "Lab results", ""),
    ("PSA raised", "396152005", "PSA above reference range", "Lab results", ""),
    ("raised PSA", "396152005", "PSA above reference range", "Lab results", ""),
    (
        "low haemoglobin",
        "165397008",
        "Hemoglobin below reference range",
        "Lab results",
        "",
    ),
    ("low Hb", "165397008", "Hemoglobin below reference range", "Lab results", ""),
    ("Hb low", "165397008", "Hemoglobin below reference range", "Lab results", ""),
    (
        "haemoglobin low",
        "165397008",
        "Hemoglobin below reference range",
        "Lab results",
        "",
    ),
    (
        "raised creatinine",
        "166717003",
        "Serum creatinine above reference range",
        "Lab results",
        "",
    ),
    (
        "elevated creatinine",
        "166717003",
        "Serum creatinine above reference range",
        "Lab results",
        "",
    ),
    (
        "creatinine elevated",
        "166717003",
        "Serum creatinine above reference range",
        "Lab results",
        "",
    ),
    ("neutrophilia", "165518003", "Neutrophilia", "Lab results", ""),
    (
        "eosinophilia",
        "386789004",
        "Eosinophil count above reference range",
        "Lab results",
        "",
    ),
]


def upsert(form: str, concept_id: str, dry_run: bool) -> dict:
    payload = {
        "normalized": form.strip().lower(),
        "form": form,
        "concept_id": concept_id,
        "confidence": 1.0,
        "source": "manual",
        "provenance": PROVENANCE,
    }
    if dry_run:
        return {"status": "dry_run"}
    headers = get_service_auth_header()
    r = requests.post(UPSERT_URL, json=payload, headers=headers, timeout=15)
    r.raise_for_status()
    return r.json()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--group", help="Only write forms for this group (e.g. 'Fatigue')")
    args = ap.parse_args()

    mode = "DRY RUN" if args.dry_run else "LIVE WRITEBACK"
    forms = SURFACE_FORMS
    if args.group:
        forms = [f for f in forms if f[3] == args.group]

    print(f"Synonym surface form writeback -- {mode}")
    print(f"Endpoint: {UPSERT_URL}")
    print(f"Forms:    {len(forms)}")
    print()

    current_group = None
    ok = fail = 0
    for sf, cid, term, group, note in forms:
        if group != current_group:
            current_group = group
            print(f"  -- {group} --")
        try:
            upsert(sf, cid, args.dry_run)
            flag = " [CORRECTED]" if note.startswith("CORRECTED") else ""
            status = "DRY" if args.dry_run else "OK "
            print(f"    {status} {sf:<35} -> [{cid}] {term[:45]}{flag}")
            ok += 1
        except requests.HTTPError as exc:
            print(
                f"    FAIL {sf:<35} HTTP {exc.response.status_code}: {exc.response.text[:100]}"
            )
            fail += 1
        except Exception as exc:
            print(f"    ERR  {sf:<35} {exc}")
            fail += 1
        time.sleep(0.05)

    print()
    print(f"Done. Success: {ok}  Failed: {fail}")
    if args.dry_run:
        print("(No changes written -- rerun without --dry-run to submit)")
    if fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
