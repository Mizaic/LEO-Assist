"""Pin surface forms for 'Seen in fast track suspected X clinic' phrases.

Reads the phrase inventory produced by _inventory_fast_track_specialist_encounters.py,
resolves each unique phrase against the terminology server, and upserts a pinned
surface form (confidence=1.0, source='manual') for any phrase that resolves wrong
or not at all.

Canonical concept mappings follow the NHS/SNOMED CT UK extension. Each
'Seen in fast track suspected X clinic' clinical finding maps to a unique concept.

Run:
    python scripts/investigations/_pin_fast_track_specialist_visits.py

    # Verify only (no writes):
    python scripts/investigations/_pin_fast_track_specialist_visits.py --verify-only
"""

from __future__ import annotations

import argparse
import json
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
PROVENANCE = "pin-fast-track-specialist-visits-2026-04-06"
INVENTORY = (
    ROOT
    / "scripts"
    / "investigations"
    / "encounter_audit"
    / "fast_track_specialist_encounters.jsonl"
)

SESSION = requests.Session()
SESSION.headers.update(get_service_auth_header())

# ---------------------------------------------------------------------------
# Canonical surface-form -> concept mappings for 'Seen in fast track' visits
# Source: SNOMED CT UK extension clinical findings for cancer pathway milestones
# ---------------------------------------------------------------------------
_CANONICAL = [
    # -- 12 canonical 'Seen in fast track suspected X clinic' concepts --
    # IDs verified against terminology server 2026-04-06
    (
        "seen in fast track suspected brain tumour clinic",
        "382401000000109",
        "Seen in fast track suspected brain tumour clinic (finding)",
    ),
    (
        "seen in fast track suspected breast cancer clinic",
        "382431000000103",
        "Seen in fast track suspected breast cancer clinic (finding)",
    ),
    (
        "seen in fast track suspected childrens tumour clinic",
        "383201000000101",
        "Seen in fast track suspected childrens tumour clinic (finding)",
    ),
    (
        "seen in fast track suspected colorectal cancer clinic",
        "382651000000108",
        "Seen in fast track suspected colorectal cancer clinic (finding)",
    ),
    (
        "seen in fast track suspected gynaecological cancer clinic",
        "382511000000105",
        "Seen in fast track suspected gynaecological cancer clinic (finding)",
    ),
    (
        "seen in fast track suspected haematological malignancy clinic",
        "382581000000103",
        "Seen in fast track suspected haematological malignancy clinic (finding)",
    ),
    (
        "seen in fast track suspected head and neck cancer clinic",
        "382621000000103",
        "Seen in fast track suspected head and neck cancer clinic (finding)",
    ),
    (
        "seen in fast track suspected lung cancer clinic",
        "382681000000102",
        "Seen in fast track suspected lung cancer clinic (finding)",
    ),
    (
        "seen in fast track suspected sarcoma clinic",
        "382361000000100",
        "Seen in fast track suspected sarcoma clinic (finding)",
    ),
    (
        "seen in fast track suspected skin cancer clinic",
        "382711000000103",
        "Seen in fast track suspected skin cancer clinic (finding)",
    ),
    (
        "seen in fast track suspected upper gastrointestinal cancer clinic",
        "382811000000108",
        "Seen in fast track suspected upper gastrointestinal cancer clinic (finding)",
    ),
    (
        "seen in fast track suspected urological cancer clinic",
        "382841000000109",
        "Seen in fast track suspected urological cancer clinic (finding)",
    ),
    # -- Alias phrasings found in patient data or LLM output --
    # "upper GI" -> upper gastrointestinal
    (
        "seen in fast track suspected upper gi cancer clinic",
        "382811000000108",
        "Seen in fast track suspected upper gastrointestinal cancer clinic (finding)",
    ),
    # "haematological cancer" -> haematological malignancy
    (
        "seen in fast track suspected haematological cancer clinic",
        "382581000000103",
        "Seen in fast track suspected haematological malignancy clinic (finding)",
    ),
    # generic fallback for un-sited "seen in fast track" encounters
    (
        "seen in fast track suspected cancer clinic",
        "382761000000101",
        "Seen in fast track suspected cancer clinic (finding)",
    ),
]

# Index for quick lookup: normalised phrase -> (concept_id, preferred_term)
# Built from the full _CANONICAL list so aliases resolve too.
_CANONICAL_INDEX: dict[str, tuple[str, str]] = {
    normalize_surface(form): (cid, label) for form, cid, label in _CANONICAL
}


def _best_match(phrase: str) -> tuple[str, str] | None:
    """Return (concept_id, preferred_term) for the best canonical match, or None."""
    norm = normalize_surface(phrase)
    if norm in _CANONICAL_INDEX:
        return _CANONICAL_INDEX[norm]
    # Partial match: check if normalised phrase contains a canonical key
    for key, val in _CANONICAL_INDEX.items():
        if key in norm or norm in key:
            return val
    return None


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
    """Return (concept_id, preferred_term) from terminology server, or (None, None)."""
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


def _load_phrases() -> list[str]:
    """Return unique non-empty phrases from the inventory JSONL."""
    if not INVENTORY.exists():
        print(f"ERROR: Inventory file not found: {INVENTORY}")
        print("Run _inventory_fast_track_specialist_encounters.py first.")
        sys.exit(1)
    phrases: set[str] = set()
    with INVENTORY.open(encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            phrase = (row.get("matched_phrase") or "").strip()
            if phrase:
                phrases.add(phrase)
    return sorted(phrases)


def run_fixes(phrases: list[str]) -> None:
    print(f"Checking and pinning {len(phrases)} unique phrases ...")
    print()
    pinned = skipped = failed = 0

    for phrase in phrases:
        resolved_id, resolved_term = _resolve(phrase)
        expected = _best_match(phrase)

        if expected is None:
            print(f"  [WARN] No canonical mapping for: {phrase!r}")
            print(f"         Resolved to: {resolved_id} ({resolved_term})")
            skipped += 1
            continue

        exp_id, exp_term = expected
        if resolved_id == exp_id:
            print(f"  [OK  ] {phrase!r}")
            print(f"         Already resolves to {exp_id}")
            skipped += 1
            time.sleep(0.05)
            continue

        ok, msg = _upsert(phrase, exp_id, exp_term)
        status = "PINNED" if ok else "FAIL  "
        print(f"  [{status}] {phrase!r}")
        print(f"           -> {exp_id} | {exp_term}")
        if ok:
            pinned += 1
        else:
            print(f"           Error: {msg}")
            failed += 1
        time.sleep(0.1)

    # Also pin all canonical forms unconditionally to cover template variants
    print()
    print(f"Ensuring all {len(_CANONICAL)} canonical forms are pinned ...")
    for form, cid, label in _CANONICAL:
        ok, msg = _upsert(form, cid, label)
        if not ok:
            print(f"  [FAIL] {form!r}: {msg}")
            failed += 1
        time.sleep(0.05)

    print()
    print("=" * 70)
    print(f"Done. Pinned: {pinned}  Already OK: {skipped}  Failed: {failed}")
    if failed:
        sys.exit(1)


def run_verify(phrases: list[str]) -> None:
    print(f"Verifying {len(_CANONICAL)} canonical forms ...")
    print()
    ok_count = fail_count = 0

    for form, exp_id, _ in _CANONICAL:
        resolved_id, resolved_term = _resolve(form)
        ok = resolved_id == exp_id
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {form!r}")
        print(f"         got={resolved_id} ({resolved_term}) want={exp_id}")
        if ok:
            ok_count += 1
        else:
            fail_count += 1

    print()
    print("=" * 70)
    print(f"Verification: {ok_count} passed  {fail_count} failed")
    if fail_count:
        print("Surface form writes may need a server restart to take effect.")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pin surface forms for 'Seen in fast track' specialist visits"
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify; do not write surface forms.",
    )
    args = parser.parse_args()

    phrases = _load_phrases()
    print(f"Loaded {len(phrases)} unique phrases from inventory.")
    print()

    if args.verify_only:
        run_verify(phrases)
    else:
        run_fixes(phrases)
        print()
        print("Running post-pin verification ...")
        print()
        run_verify(phrases)


if __name__ == "__main__":
    main()
