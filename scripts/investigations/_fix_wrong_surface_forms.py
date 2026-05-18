"""Fix confirmed wrong MAPS_TO edges found by the surface form audit.

Two categories of fixes:
  1. Wrong situation code beats correct disorder  (guideline_config_loader provenance)
  2. Over-broad 'Mental disorder' concept beats specific disorder

Action: for each bad form, DELETE the wrong MAPS_TO edge via the
Terminology API and BOOST the correct edge to conf=1.0 via upsert.
The API DELETE endpoint is:
  DELETE /terminology/surface-forms/{normalized}?concept_id={wrong_id}

Usage
-----
  python scripts/investigations/_fix_wrong_surface_forms.py [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

import os
import requests

_API = "http://localhost:8001"
_TOKEN = os.getenv("SERVICE_TOKEN", "")

# ---------------------------------------------------------------------------
# Normalisation helper (mirrors the Terminology API's own normalisation)
# ---------------------------------------------------------------------------


def _norm(text: str) -> str:
    low = text.lower().strip()
    nfkd = unicodedata.normalize("NFKD", low)
    ascii_only = nfkd.encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_only.split())


# ---------------------------------------------------------------------------
# Fixes: (surface_form, wrong_concept_id, correct_concept_id, correct_fsn)
# ---------------------------------------------------------------------------
# wrong_concept_id = the MAPS_TO edge to DELETE
# correct_concept_id = the MAPS_TO edge to BOOST to conf=1.0 (already present)
#
# Source: confirmed by _show_duplicates.py output - these are all cases where
# guideline_config_loader wrote a situation/broad concept at conf=1.0 that
# beats the correct specific disorder at lower confidence.

_SITUATION_BEATS_DISORDER = [
    # form, wrong_situation_id, correct_disorder_id, correct_fsn
    (
        "COPD",
        "270473001",  # History of chronic obstructive airway disease (situation)
        "13645005",  # Chronic obstructive pulmonary disease (disorder)
        "Chronic obstructive pulmonary disease (disorder)",
    ),
    (
        "CVA",
        "308064009",  # History of cerebrovascular disease (situation)
        "230690007",  # Cerebrovascular accident (disorder)
        "Cerebrovascular accident (disorder)",
    ),
    (
        "Stroke",
        "308064009",  # History of cerebrovascular disease (situation)
        "230690007",  # Cerebrovascular accident (disorder)
        "Cerebrovascular accident (disorder)",
    ),
    (
        "TIA",
        "308064009",  # History of cerebrovascular disease (situation)
        "266257000",  # Transient ischemic attack (disorder)
        "Transient ischemic attack (disorder)",
    ),
    (
        "Chronic kidney disease",
        "275552000",  # History of kidney disease (situation)
        "709044004",  # Chronic kidney disease (disorder)
        "Chronic kidney disease (disorder)",
    ),
    (
        "Chronic kidney disease stage 3",
        "275552000",
        "433144002",  # Chronic kidney disease stage 3 (disorder)
        "Chronic kidney disease stage 3 (disorder)",
    ),
    (
        "Chronic kidney disease stage 4",
        "275552000",
        "431857002",  # Chronic kidney disease stage 4 (disorder)
        "Chronic kidney disease stage 4 (disorder)",
    ),
    (
        "Chronic kidney disease stage 5",
        "275552000",
        "433146000",  # Chronic kidney disease stage 5 (disorder)
        "Chronic kidney disease stage 5 (disorder)",
    ),
    (
        "Fatty liver",
        "161535005",  # History of liver disease (situation)
        "9990010007",  # Metabolic dysfunction-associated steatotic liver disease
        "Metabolic dysfunction-associated steatotic liver disease (disorder)",
    ),
    (
        "RA",
        "472961001",  # History of disorder of connective tissue (situation)
        "69896004",  # Rheumatoid arthritis (disorder)
        "Rheumatoid arthritis (disorder)",
    ),
    (
        "Rheumatoid arthritis",
        "472961001",
        "69896004",
        "Rheumatoid arthritis (disorder)",
    ),
    (
        "osteopenia",
        "267004000",  # History of musculoskeletal disease (situation)
        "312894000",  # Osteopenia (disorder)
        "Osteopenia (disorder)",
    ),
    (
        "osteoporosis",
        "267004000",
        "64859006",  # Osteoporosis (disorder)
        "Osteoporosis (disorder)",
    ),
    (
        "Dementia",
        "161465002",  # History of dementia (situation)
        "52448006",  # Dementia (disorder)
        "Dementia (disorder)",
    ),
]

_BROAD_BEATS_SPECIFIC = [
    # form, wrong_broad_id, correct_specific_id, correct_fsn
    (
        "Active suicidal ideation",
        "74732009",  # Mental disorder (disorder) -- too broad
        "6471006",  # Suicidal thoughts (finding)
        "Suicidal thoughts (finding)",
    ),
    ("Passive suicidal ideation", "74732009", "6471006", "Suicidal thoughts (finding)"),
    ("Suicidal ideation", "74732009", "6471006", "Suicidal thoughts (finding)"),
    ("Suicidal thoughts", "74732009", "6471006", "Suicidal thoughts (finding)"),
    ("Thoughts of suicide", "74732009", "6471006", "Suicidal thoughts (finding)"),
    (
        "Adjustment reaction",
        "74732009",
        "17226007",  # Adjustment disorder (disorder)
        "Adjustment disorder (disorder)",
    ),
    ("Adjustment disorder", "74732009", "17226007", "Adjustment disorder (disorder)"),
    (
        "Anxiety disorder",
        "74732009",
        "21897009",  # Generalized anxiety disorder (disorder)
        "Generalized anxiety disorder (disorder)",
    ),
    (
        "Generalised anxiety disorder",
        "74732009",
        "21897009",
        "Generalized anxiety disorder (disorder)",
    ),
    (
        "Generalized anxiety disorder",
        "74732009",
        "21897009",
        "Generalized anxiety disorder (disorder)",
    ),
    (
        "Mixed anxiety depression",
        "74732009",
        "231504006",  # Mixed anxiety and depressive disorder
        "Mixed anxiety and depressive disorder (disorder)",
    ),
    (
        "Reactive depression",
        "74732009",
        "87414006",  # Reactive depression (situational) (disorder)
        "Reactive depression (situational) (disorder)",
    ),
    # bone metastases -- generic metastatic neoplasm beats site-specific
    (
        "bone metastases",
        "128462008",  # Metastatic malignant neoplasm (disorder) -- too broad
        "94222008",  # Metastatic malignant neoplasm to bone (disorder)
        "Secondary malignant neoplasm of bone (disorder)",
    ),
    # basal cell carcinoma -- generic skin malignancy beats BCC
    (
        "basal cell carcinoma",
        "372130007",  # Malignant neoplasm of skin (disorder) -- too broad
        "254701007",  # Basal cell carcinoma of skin (disorder)
        "Basal cell carcinoma of skin (disorder)",
    ),
]

ALL_FIXES = _SITUATION_BEATS_DISORDER + _BROAD_BEATS_SPECIFIC


def _delete_mapping(normalized: str, concept_id: str, dry_run: bool) -> bool:
    url = f"{_API}/terminology/surface-forms/{normalized}"
    params = {"concept_id": concept_id}
    if dry_run:
        print(f"    [DRY-RUN] DELETE {url}?concept_id={concept_id}")
        return True
    resp = requests.delete(
        url,
        params=params,
        headers={"Authorization": f"Bearer {_TOKEN}"},
        timeout=60,
    )
    if resp.status_code == 200:
        data = resp.json()
        removed = data.get("removed", "?")
        print(f"    Deleted: removed={removed}")
        return True
    print(f"    DELETE failed: {resp.status_code} {resp.text[:200]}")
    return False


def _boost_mapping(normalized: str, form: str, concept_id: str, dry_run: bool) -> bool:
    url = f"{_API}/terminology/surface-forms/upsert-mapping"
    payload = {
        "normalized": normalized,
        "form": form,
        "concept_id": concept_id,
        "confidence": 1.0,
        "source": "manual",
        "provenance": "audit-fix-wrong-surface-forms-2026-04",
    }
    if dry_run:
        print(f"    [DRY-RUN] BOOST {normalized!r} -> {concept_id} conf=1.0")
        return True
    resp = requests.post(
        url,
        json=payload,
        headers={"Authorization": f"Bearer {_TOKEN}"},
        timeout=60,
    )
    if resp.status_code == 200:
        data = resp.json()
        print(f"    Boosted: {data.get('concept_fsn')}")
        return True
    print(f"    BOOST failed: {resp.status_code} {resp.text[:200]}")
    return False


def main(dry_run: bool) -> None:
    mode = "DRY-RUN" if dry_run else "LIVE"
    print(f"{'=' * 70}")
    print(f"FIXING WRONG SURFACE FORM MAPPINGS ({mode})")
    print(f"  {len(ALL_FIXES)} fixes to apply")
    print(f"{'=' * 70}\n")

    ok = 0
    fail = 0

    for form, wrong_id, correct_id, correct_fsn in ALL_FIXES:
        normalized = _norm(form)
        print(f"Form: {form!r}  normalized={normalized!r}")
        print(f"  Remove  : {wrong_id}")
        print(f"  Keep/boost: {correct_id} | {correct_fsn}")

        deleted = _delete_mapping(normalized, wrong_id, dry_run)
        boosted = _boost_mapping(normalized, form, correct_id, dry_run)

        if deleted and boosted:
            ok += 1
            print("  OK\n")
        else:
            fail += 1
            print("  FAILED\n")

    print(f"{'=' * 70}")
    print(f"Done: {ok} succeeded, {fail} failed")
    if fail and not dry_run:
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions but do not modify the database",
    )
    args = parser.parse_args()
    main(dry_run=args.dry_run)
