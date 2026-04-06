"""Resolve unique T1+T2 uncoded phrases via the terminology server.

Reads no_cancer_phrase_inventory.jsonl, takes every unique matched phrase
from uncoded encounters, resolves each via POST /terminology/resolve, and
reports whether it maps to 395100000, something else, or nothing.

Run:
    python scripts/investigations/_resolve_no_cancer_phrases.py
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
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

INVENTORY = (
    ROOT / "scripts" / "investigations" / "encounter_audit"
    / "no_cancer_phrase_inventory.jsonl"
)
TARGET_CONCEPT = "395100000"


def resolve_phrase(phrase: str) -> dict:
    try:
        r = SESSION.post(
            f"{BASE}/terminology/resolve",
            json={"terms": [phrase]},
            timeout=30,
        )
        r.raise_for_status()
        results = r.json().get("results", {})
        hits = results.get(phrase) or []
        if hits:
            top = hits[0]
            return {
                "phrase": phrase,
                "resolved_concept_id": str(top.get("snomed_concept_id", "")),
                "resolved_name": top.get("snomed_term", ""),
                "score": top.get("score", 0),
                "status": "correct" if str(top.get("snomed_concept_id", "")) == TARGET_CONCEPT else "wrong_concept",
            }
        return {"phrase": phrase, "resolved_concept_id": "", "resolved_name": "", "score": 0, "status": "no_match"}
    except Exception as exc:
        return {"phrase": phrase, "resolved_concept_id": "", "resolved_name": "", "score": 0, "status": f"error:{exc}"}


def main() -> None:
    with INVENTORY.open() as fh:
        rows = [json.loads(l) for l in fh]

    # Gather unique phrases from uncoded, non-excluded encounters
    uncoded_phrases: set[str] = set()
    uncoded_encounters: dict[str, list[str]] = defaultdict(list)  # phrase -> enc_ids
    for row in rows:
        if row.get("already_coded_395100000") or row.get("excluded"):
            continue
        for phrase in row.get("matched_phrases", []):
            uncoded_phrases.add(phrase)
            uncoded_encounters[phrase].append(row["encounter_id"])

    print(f"Unique uncoded phrases to resolve: {len(uncoded_phrases)}")
    print()

    correct   = []
    wrong     = []
    no_match  = []
    errors    = []

    for phrase in sorted(uncoded_phrases):
        result = resolve_phrase(phrase)
        enc_count = len(uncoded_encounters[phrase])
        status = result["status"]

        if status == "correct":
            correct.append((phrase, result, enc_count))
        elif status == "wrong_concept":
            wrong.append((phrase, result, enc_count))
        elif status == "no_match":
            no_match.append((phrase, result, enc_count))
        else:
            errors.append((phrase, result, enc_count))

    print("=" * 70)
    print(f"Resolves CORRECTLY to 395100000 ({len(correct)}):")
    for phrase, result, n in correct:
        print(f"  [{n} enc] {phrase!r}  score={result['score']:.2f}")

    print()
    print(f"Resolves to WRONG concept ({len(wrong)}):")
    for phrase, result, n in wrong:
        print(f"  [{n} enc] {phrase!r}")
        print(f"    -> {result['resolved_concept_id']} | {result['resolved_name']} | score={result['score']:.2f}")

    print()
    print(f"No match found ({len(no_match)}):")
    for phrase, result, n in no_match:
        print(f"  [{n} enc] {phrase!r}")

    if errors:
        print()
        print(f"Errors ({len(errors)}):")
        for phrase, result, n in errors:
            print(f"  [{n} enc] {phrase!r}  -> {result['status']}")

    print()
    print("=" * 70)
    print("Summary:")
    print(f"  Correct (->395100000)     : {len(correct)}")
    print(f"  Wrong concept             : {len(wrong)}")
    print(f"  No match (need pin)       : {len(no_match)}")
    print(f"  Errors                    : {len(errors)}")
    print()

    # Phrases that need surface form pins (either wrong or no match)
    to_pin = [(p, r, n) for p, r, n in wrong + no_match]
    print(f"Phrases needing surface form pin to 395100000: {len(to_pin)}")
    for phrase, _, n in to_pin:
        print(f"  [{n} enc] {phrase!r}")


if __name__ == "__main__":
    main()
