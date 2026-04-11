"""
Write approved abbreviation -> SNOMED surface form mappings to the
terminology server. Uses /terminology/surface-forms/upsert-mapping.

Only processes abbreviation_writeback_approved.json.
The 5 entries in abbreviation_writeback_review.json are skipped
until clinical sign-off.

Run:  python scripts/investigations/_run_writeback.py
      python scripts/investigations/_run_writeback.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import os
import sys
from pathlib import Path as _Path

# Make project root importable (same pattern as audit_encounter_coding.py)
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
PROVENANCE = "abbreviation_audit_april_2026"


def _normalise(text: str) -> str:
    """Match how the terminology server normalises surface forms."""
    return text.strip().lower()


def upsert(form: str, concept_id: str, dry_run: bool) -> dict:
    payload = {
        "normalized": _normalise(form),
        "form": form,
        "concept_id": concept_id,
        "confidence": 1.0,
        "source": "manual",
        "provenance": PROVENANCE,
    }
    if dry_run:
        return {"status": "dry_run", "payload": payload}
    headers = get_service_auth_header()
    r = requests.post(UPSERT_URL, json=payload, headers=headers, timeout=15)
    r.raise_for_status()
    return r.json()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be sent without submitting",
    )
    args = ap.parse_args()

    approved_path = Path("scripts/investigations/abbreviation_writeback_approved.json")
    if not approved_path.exists():
        print("ERROR: approved list not found - run _build_writeback_list.py first")
        sys.exit(1)

    entries = json.loads(approved_path.read_text(encoding="utf-8"))

    results = []
    ok = fail = 0

    print("=" * 100)
    mode = "DRY RUN" if args.dry_run else "LIVE WRITEBACK"
    print(f"Terminology server surface form writeback -- {mode}")
    print(f"Endpoint: {UPSERT_URL}")
    print(f"Entries:  {len(entries)}")
    print("=" * 100)

    for e in entries:
        abbrev = e["abbreviation"]
        concept_id = e["recommended_concept_id"]
        term = e["recommended_term"] or ""
        corrected = "CORRECTED" if e.get("correction_applied") else ""

        try:
            resp = upsert(abbrev, concept_id, args.dry_run)
            status = "OK" if not args.dry_run else "DRY"
            ok += 1
            print(f"  {status}  {abbrev:<8} -> [{concept_id}] {term[:55]}  {corrected}")
            results.append(
                {
                    "abbreviation": abbrev,
                    "concept_id": concept_id,
                    "term": term,
                    "status": status,
                    "response": resp,
                }
            )
        except requests.HTTPError as exc:
            fail += 1
            status = f"HTTP {exc.response.status_code}"
            body = exc.response.text[:200]
            print(f"  FAIL {abbrev:<8} -> {status}: {body}")
            results.append(
                {
                    "abbreviation": abbrev,
                    "concept_id": concept_id,
                    "status": "FAIL",
                    "error": str(exc),
                }
            )
        except Exception as exc:
            fail += 1
            print(f"  ERR  {abbrev:<8} -> {exc}")
            results.append(
                {
                    "abbreviation": abbrev,
                    "concept_id": concept_id,
                    "status": "ERROR",
                    "error": str(exc),
                }
            )

        time.sleep(0.05)

    print()
    print("=" * 100)
    print(f"Done.  Success: {ok}  Failed: {fail}")
    if args.dry_run:
        print("(No changes written - rerun without --dry-run to submit)")
    print()
    print("Skipped (needs clinical review):")
    review_path = Path("scripts/investigations/abbreviation_writeback_review.json")
    for rev in json.loads(review_path.read_text(encoding="utf-8")):
        print(
            f"  {rev['abbreviation']:<8} [{rev['recommended_concept_id']}] "
            f"{rev['recommended_term']}"
        )

    out = Path("scripts/investigations/writeback_results.json")
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nFull results: {out}")

    if fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
