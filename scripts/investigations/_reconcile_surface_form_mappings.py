"""Reconcile TS mappings for curated surface forms.

Reads:
  scripts/investigations/output/missing_surface_form_snomed.json

For each form:
1) Check current TS mapping(s)
2) Ensure intended concept mapping exists
3) Remove competing mappings for that form
4) Re-check what TS exact lookup returns

Usage:
  python scripts/investigations/_reconcile_surface_form_mappings.py
  python scripts/investigations/_reconcile_surface_form_mappings.py --apply
  python scripts/investigations/_reconcile_surface_form_mappings.py --category symptom
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from libs.keyvault.loader import load_keyvault_secrets
from libs.neo4j_client.client import KnowledgeGraphClient
from services.terminology_api.app.queries.terminology import (
    EXACT_SURFACE_FORM_QUERY,
    KEEP_SURFACE_FORM_MAPPING,
    UPSERT_SURFACE_FORM_MAPPING,
)

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
load_keyvault_secrets()

INPUT_FILE = (
    ROOT / "scripts" / "investigations" / "output" / "missing_surface_form_snomed.json"
)
APPLY = "--apply" in sys.argv
CATEGORY_FILTER = None


def _cli_norm(s: str) -> str:
    return " ".join(str(s or "").lower().strip().split())


if "--category" in sys.argv:
    idx = sys.argv.index("--category")
    if idx + 1 >= len(sys.argv):
        raise ValueError("Expected value after --category")
    CATEGORY_FILTER = _cli_norm(sys.argv[idx + 1])

_CURRENT_Q = """
MATCH (sf:SurfaceForm {normalized: $normalized})-[m:MAPS_TO]->(c:Concept)
RETURN c.id AS concept_id, c.fsn AS fsn, coalesce(m.confidence, 0.0) AS confidence
ORDER BY confidence DESC, c.id
"""

_CONCEPT_EXISTS_Q = """
MATCH (c:Concept {id: $concept_id})
WHERE c.active = true
RETURN c.id AS concept_id, c.fsn AS fsn
"""


def _norm(s: str) -> str:
    return " ".join(str(s or "").lower().strip().split())


def main() -> None:
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"Missing input file: {INPUT_FILE}")

    curated = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    rows = []
    seen = set()
    for e in curated:
        category = _norm(e.get("category"))
        if CATEGORY_FILTER and category != CATEGORY_FILTER:
            continue
        n = _norm(e.get("normalised"))
        cid = str(e.get("concept_id") or "").strip()
        form = str(e.get("raw") or n).strip()
        if not n or not cid:
            continue
        key = (n, cid)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "normalized": n,
                "form": form,
                "concept_id": cid,
                "label": str(e.get("label") or ""),
                "category": category,
            }
        )

    category_note = f", category={CATEGORY_FILTER!r}" if CATEGORY_FILTER else ""
    print(
        f"Loaded {len(rows)} unique curated mappings from {INPUT_FILE.name}; "
        f"mode={'APPLY' if APPLY else 'DRY RUN'}{category_note}"
    )

    kg = KnowledgeGraphClient()
    try:
        total_upserts = 0
        total_keeps = 0
        changed = 0
        skipped = 0

        for r in rows:
            normalized = r["normalized"]
            concept_id = r["concept_id"]

            concept_exists = kg.run(_CONCEPT_EXISTS_Q, concept_id=concept_id) or []
            if not concept_exists:
                print(f"SKIP {normalized!r}: concept {concept_id} not active/in KG")
                skipped += 1
                continue

            before = kg.run(_CURRENT_Q, normalized=normalized) or []
            before_ids = [str(x.get("concept_id")) for x in before]

            need_upsert = concept_id not in before_ids
            need_keep = bool(before_ids) and any(
                cid != concept_id for cid in before_ids
            )

            if not need_upsert and not need_keep:
                continue

            changed += 1
            print(
                f"\nPATCH {normalized!r} -> {concept_id} "
                f"(before={before_ids if before_ids else 'none'})"
            )

            if APPLY:
                if need_upsert:
                    out = (
                        kg.run(
                            UPSERT_SURFACE_FORM_MAPPING,
                            normalized=normalized,
                            form=r["form"],
                            concept_id=concept_id,
                            confidence=0.98,
                            source="manual_curation",
                            provenance="surface_form_reconcile_2026",
                        )
                        or []
                    )
                    if out:
                        total_upserts += 1
                        print("  upsert: OK")
                    else:
                        print("  upsert: WARN no row returned")
                if need_keep:
                    keep = (
                        kg.run(
                            KEEP_SURFACE_FORM_MAPPING,
                            normalized=normalized,
                            keep_concept_id=concept_id,
                        )
                        or []
                    )
                    removed = int(keep[0].get("removed", 0)) if keep else 0
                    total_keeps += removed
                    print(f"  prune-other-maps: removed={removed}")
            else:
                if need_upsert:
                    print("  would upsert intended mapping")
                if need_keep:
                    print("  would remove competing mappings")

            after = kg.run(_CURRENT_Q, normalized=normalized) or []
            after_ids = [str(x.get("concept_id")) for x in after]
            if APPLY:
                print(f"  after={after_ids}")
            else:
                # Show expected final state in dry run for readability.
                print(f"  expected_after={[concept_id]}")

        # Quick TS-exact check for top results from the same query TS uses.
        print("\nVerifying exact-surface lookup responses ...")
        verify_fail = 0
        for r in rows:
            out = (
                kg.run(
                    EXACT_SURFACE_FORM_QUERY,
                    normalized=r["normalized"],
                    k=3,
                )
                or []
            )
            if not out:
                verify_fail += 1
                print(f"  NO RESULT  {r['normalized']!r}")
                continue
            top = str(out[0].get("concept_id") or "")
            if top != r["concept_id"]:
                verify_fail += 1
                print(
                    f"  MISMATCH  {r['normalized']!r}: top={top}, expected={r['concept_id']}"
                )

        print("\nSummary")
        print(f"  changed_forms: {changed}")
        print(f"  skipped_forms: {skipped}")
        if APPLY:
            print(f"  upserts_written: {total_upserts}")
            print(f"  competing_maps_removed: {total_keeps}")
        print(f"  verify_failures: {verify_fail}")
    finally:
        kg.close()


if __name__ == "__main__":
    main()
