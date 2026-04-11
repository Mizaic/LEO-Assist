"""Pin surface forms for benign outcome phrases discovered in the 39-patient
manual encounter review (2026-04-06).

These are phrases found in GP records that confirm a cancer investigation
pathway ended without cancer, but are not currently being extracted as
SNOMED 395100000 (No evidence of cancer found).

Phrase categories:
  1. Haematology/oncology reassurance ("nil concerns raised about malig")
  2. Primary-care letters citing 2WW MDT outcome ("no cancer found on 2WW")
  3. Negative biopsy/pathology ("no dysplasia or malignancy")
  4. Post-investigation narrative ("endoscopy was normal" in cancer context)
  5. Nursing/admin 2WW closure notes ("was seen on 2WW, NAD")
  6. Alternative benign diagnosis in 2WW context ("polyp removed but no cancer")

Run:
    python scripts/investigations/_pin_benign_outcome_phrases.py

    # Verify only (no writes):
    python scripts/investigations/_pin_benign_outcome_phrases.py --verify-only
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
PROVENANCE = "pin-benign-outcome-phrases-2026-04-06"

SESSION = requests.Session()
SESSION.headers.update(get_service_auth_header())

# ---------------------------------------------------------------------------
# Surface forms -- benign outcome phrases from 39-patient manual review
# All map to 395100000 (No evidence of cancer found)
# Only for use within an active cancer investigation pathway context.
# ---------------------------------------------------------------------------
_BENIGN_OUTCOME_PHRASES: list[tuple[str, str, str]] = [
    # -- Haematology reassurance phrases (patient 4621680811) -----------------
    (
        "nil concerns raised about malignancy",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "nil concerns raised about malig",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "no concerns raised about malignancy",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "no concerns raised about malig",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    # -- Primary-care MDT outcome letters (patient 4245139757) ----------------
    (
        "no evidence of malignancy found on investigations",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "no evidence of malignancy found",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "cancer pathway has been completed with no cancer found",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "two-week wait cancer pathway has been completed with no cancer found",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "two week wait pathway completed with no cancer found",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "no cancer found on 2ww",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "no cancer found on two week wait",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "no sinister findings",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "no sinister findings on ct",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "no cancer found",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "no malignancy found",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    # -- Biopsy / pathology negatives (patient 4983118659) --------------------
    (
        "no dysplasia or malignancy",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "no dysplasia or malignancy on biopsy",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "biopsy negative for malignancy",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "biopsy - no malignancy",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "no evidence of malignancy on biopsy",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "biopsy of colon - normal",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "colonoscopy with biopsy - normal",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "colonoscopy - polyp removed but no cancer",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "polyp removed but no cancer",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    # -- Post-endoscopy/imaging narrative in cancer context -------------------
    (
        "endoscopy was normal",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "endoscopy which was normal",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "ogd - nad",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "upper gi endoscopy normal",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "shows small hiatus hernia only",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "hiatus hernia only",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    # -- Nursing/admin 2WW closure notes (patient 7343840665) -----------------
    (
        "was seen on 2ww, nad",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "was seen on 2ww nad",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "nad so safe to administer live vaccine",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    # -- Benign pathology found (patient 6519337463) ---------------------------
    (
        "benign pathology found",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    # -- US / imaging NAD in 2WW context (patients 7319972905, 4883794091) ----
    (
        "us scan of neck - nad",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "us scan of thyroid - nad",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "us scan of neck nad",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "no discrete nodules or concerning features",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "no concerning features in neck",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    # -- Reassurance / discharge phrases -------------------------------------
    (
        "reassured that the lump is not suspicious for malignancy",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "not suspicious for malignancy",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "not suspicious for cancer",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "normal histology",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
    (
        "had normal histology",
        "395100000",
        "No evidence of cancer found (finding)",
    ),
]


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


def run_fixes(verify_only: bool = False) -> None:
    print(
        f"{'Verifying' if verify_only else 'Pinning'} {len(_BENIGN_OUTCOME_PHRASES)} benign outcome phrase surface forms ..."
    )
    print()
    pinned = already_ok = failed = 0

    for form, cid, label in _BENIGN_OUTCOME_PHRASES:
        resolved_id, resolved_term = _resolve(form)
        if resolved_id == cid:
            print(f"  [OK  ] {form!r} -> {cid}")
            already_ok += 1
            time.sleep(0.05)
            continue

        if resolved_id and resolved_id != cid:
            print(f"  [DIFF] {form!r}")
            print(f"         expected={cid}  got={resolved_id} ({resolved_term})")

        if verify_only:
            print(f"  [MISS] {form!r} -> {cid} | {label}")
            failed += 1
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
    if verify_only:
        print(f"Verify complete: {already_ok} OK, {failed} missing/wrong")
    else:
        print(f"Complete: {pinned} pinned, {already_ok} already OK, {failed} failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    run_fixes(verify_only=args.verify_only)
