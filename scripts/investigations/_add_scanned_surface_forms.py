"""Add human-confirmed encounter surface forms to terminology mapping.

Input:
  scripts/investigations/output/ngram_scan_results.json
  key: confirmed_additions

Expected confirmed_additions entry shape:
  {
    "ngram": "gp appointment",
    "form": "GP appointment",     # optional; defaults to ngram
    "concept_id": "185202000",
    "category": "place"           # optional
  }

Dry-run by default.
Use --apply to commit changes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from libs.keyvault.loader import load_keyvault_secrets
from libs.neo4j_client.client import KnowledgeGraphClient
from services.terminology_api.app.queries.terminology import UPSERT_SURFACE_FORM_MAPPING

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
load_keyvault_secrets()

INPUT_FILE = ROOT / "scripts" / "investigations" / "output" / "ngram_scan_results.json"
APPLY = "--apply" in sys.argv

_CONCEPT_EXISTS_Q = """
MATCH (c:Concept {id: $concept_id})
WHERE c.active = true
RETURN c.id AS concept_id, c.fsn AS fsn
"""


def _normalize(text: str) -> str:
    return " ".join(str(text or "").lower().strip().split())


def _load_confirmed() -> list[dict[str, Any]]:
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"Missing input file: {INPUT_FILE}")
    payload = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    confirmed = list(payload.get("confirmed_additions") or [])
    return confirmed


def _validate_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for idx, e in enumerate(entries, 1):
        concept_id = str(e.get("concept_id") or "").strip()
        ngram = str(e.get("ngram") or "").strip()
        form = str(e.get("form") or ngram).strip()
        norm = _normalize(form)
        if not concept_id or not norm:
            print(f"  skip entry #{idx}: missing concept_id or ngram/form")
            continue
        key = (norm, concept_id)
        if key in seen:
            continue
        seen.add(key)
        normalized_rows.append(
            {
                "normalized": norm,
                "form": form,
                "concept_id": concept_id,
                "ngram": ngram,
                "category": str(e.get("category") or ""),
            }
        )
    return normalized_rows


def main() -> None:
    confirmed = _load_confirmed()
    rows = _validate_entries(confirmed)
    print(f"Loaded {len(confirmed)} confirmed additions, {len(rows)} valid unique rows")
    if not rows:
        print("Nothing to add. Populate confirmed_additions in ngram_scan_results.json")
        return

    kg = KnowledgeGraphClient()
    try:
        # Validate concept IDs first.
        valid_rows = []
        for r in rows:
            c = kg.run(_CONCEPT_EXISTS_Q, concept_id=r["concept_id"]) or []
            if not c:
                print(
                    f"  INVALID concept_id: {r['concept_id']} for form {r['normalized']!r} -- skipping"
                )
                continue
            valid_rows.append(r)

        print(f"Concept validation: {len(valid_rows)}/{len(rows)} rows valid")
        if not valid_rows:
            return

        if not APPLY:
            print("\nDRY RUN (no writes). Re-run with --apply to commit.\n")
            for r in valid_rows:
                print(
                    f"  ADD {r['normalized']!r:35s} -> {r['concept_id']} "
                    f"({r.get('category') or 'unspecified'})"
                )
            return

        written = 0
        print("\nApplying mappings ...")
        for r in valid_rows:
            out = kg.run(
                UPSERT_SURFACE_FORM_MAPPING,
                normalized=r["normalized"],
                form=r["form"],
                concept_id=r["concept_id"],
                confidence=0.95,
                source="manual_curation",
                provenance="encounter_surface_form_scan_2026",
            ) or []
            if out:
                written += 1
                print(f"  OK  {r['normalized']!r:35s} -> {r['concept_id']}")
            else:
                print(f"  WARN no write result for {r['normalized']!r} -> {r['concept_id']}")

        print(f"\nDone. Wrote {written}/{len(valid_rows)} mappings.")
    finally:
        kg.close()


if __name__ == "__main__":
    main()

