"""Pin surface form mappings for confirmed T1/T2 phrases to 395100000.

'in remission' is deliberately EXCLUDED -- it resolves to schizophrenia/diabetes
remission in this cohort, not cancer remission.

Run:
    python scripts/investigations/_pin_no_cancer_surface_forms.py
"""

from __future__ import annotations

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

TARGET_CONCEPT = "395100000"
TARGET_NAME = "No evidence of cancer found (situation)"

# Phrases that need surface form pins to 395100000 (No evidence of cancer found).
# These are all EXCLUSION phrases -- cancer was investigated and NOT found.
# Post-treatment phrases ("in remission", "disease free", "no evidence of recurrence")
# are deliberately excluded -- they imply a prior diagnosis, not an exclusion.
PINS = [
    # Core definitive exclusions
    "no evidence of cancer",
    "no evidence of malignancy",
    "no evidence of cancer found",
    "no malignancy",
    "negative for malignancy",
    "neg for malignancy",
    "negative for cancer",
    "malignancy excluded",
    "cancer excluded",
    "sarcoma excluded",
    "malignancy ruled out",
    "cancer ruled out",
    "sarcoma ruled out",
    "no malignant cells",
    "no malignant cells seen",
    "negative for malignant cells",
    "no evidence of malignant cells",
    "no evidence of neoplasm",
    "no neoplasm",
    "no evidence of tumour",
    "no evidence of tumor",
    "negative for tumour",
    "negative for tumor",
    "no evidence of carcinoma",
    "no evidence of sarcoma",
    "no metastases",
    "no metastatic disease",
    "no evidence of metastatic disease",
    "no mets",
    "no mets detected",
    "malignancy not identified",
    "cancer not identified",
    "malignancy not seen",
    "cancer not seen",
    "does not suggest malignancy",
    "does not support malignancy",
    "not in keeping with malignancy",
    "not in keeping with cancer",
    "in keeping with benign",
    "argues against malignancy",
    "inconsistent with malignancy",
    "inconsistent with cancer",
    "malignancy unlikely",
    "cancer unlikely",
    # Pathology / histology exclusions
    "benign histology",
    "benign on histology",
    "benign pathology",
    "benign on pathology",
    "benign cytology",
    "biopsy benign",
    "biopsy negative for malignancy",
    "histology benign",
    "histology negative for malignancy",
    "cytology benign",
    "cytology negative",
    "no histological evidence of malignancy",
    "no pathological evidence of malignancy",
    "no neoplastic cells",
    "no tumour cells seen",
    "no tumor cells seen",
    "features are benign",
    "findings are benign",
]


def _upsert(form: str) -> tuple[bool, int]:
    from libs.terminology.surface_normalize import normalize_surface

    norm = normalize_surface(form)
    payload = {
        "form": form,
        "normalized": norm,
        "concept_id": TARGET_CONCEPT,
        "confidence": 1.0,
        "source": "manual",
        "provenance": "no-cancer-phrase-audit-2026-04-06",
    }
    r = SESSION.post(
        f"{BASE}/terminology/surface-forms/upsert-mapping",
        json=payload,
        timeout=60,
    )
    return r.status_code in (200, 201, 204), r.status_code


def main() -> None:
    print(f"Pinning {len(PINS)} surface forms -> {TARGET_CONCEPT} ({TARGET_NAME})")
    print()
    ok_count = 0
    fail_count = 0
    for form in PINS:
        ok, code = _upsert(form)
        status = "OK  " if ok else "FAIL"
        print(f"  [{status}] HTTP {code}  {form!r}")
        if ok:
            ok_count += 1
        else:
            fail_count += 1

    print()
    print(f"Done. Pinned: {ok_count}  Failed: {fail_count}")


if __name__ == "__main__":
    main()
