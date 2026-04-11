"""Check which pre-referral surface forms already exist in the KG.

Reads scripts/investigations/output/pre_referral_surface_forms.json,
normalises each candidate surface form the same way the terminology
service does (lowercase + strip), then queries the KG for existing
SurfaceForm and Term nodes.

Output:
    scripts/investigations/output/surface_form_coverage.json
    Printed summary to stdout.

Usage:
    python scripts/investigations/_check_surface_forms_exist.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()
from libs.neo4j_client.client import KnowledgeGraphClient

INPUT_FILE = Path(__file__).parent / "output" / "pre_referral_surface_forms.json"
OUTPUT_FILE = Path(__file__).parent / "output" / "surface_form_coverage.json"

# -- Batch lookup: check SurfaceForm and Term nodes in one query -----------

_BATCH_CHECK = """
UNWIND $forms AS form
OPTIONAL MATCH (sf:SurfaceForm {normalized: form})-[:MAPS_TO]->(sc:Concept)
OPTIONAL MATCH (t:Term {normalized_form: form})-[:DESCRIBES]->(tc:Concept)
RETURN form,
       sf.normalized      AS sf_normalized,
       sc.id              AS sf_concept_id,
       sc.preferredTerm   AS sf_concept_term,
       t.normalized_form  AS term_normalized,
       tc.id              AS term_concept_id,
       tc.preferredTerm   AS term_concept_term
"""


def _normalise(text: str) -> str:
    """Match the terminology service normalisation: lowercase + strip."""
    return text.lower().strip()


def main() -> None:
    data = json.loads(INPUT_FILE.read_text(encoding="utf-8"))

    # Collect every unique surface form string across symptoms and places
    candidate_forms: dict[str, dict] = {}  # normalised -> metadata

    for section_key in ("symptoms", "places_of_presentation"):
        for entry in data.get(section_key, []):
            label = entry["label"]
            category = entry["category"]
            for raw_form, count in entry.get("surface_forms", {}).items():
                norm = _normalise(raw_form)
                if norm not in candidate_forms:
                    candidate_forms[norm] = {
                        "raw": raw_form,
                        "label": label,
                        "category": category,
                        "count": count,
                    }
                else:
                    # Keep highest count if same form appears under multiple labels
                    if count > candidate_forms[norm]["count"]:
                        candidate_forms[norm]["count"] = count

    print(f"Checking {len(candidate_forms)} unique surface forms against the KG ...")

    kg = KnowledgeGraphClient()
    try:
        rows = kg.run(_BATCH_CHECK, forms=list(candidate_forms.keys())) or []
    finally:
        kg.close()

    # Index results by normalised form
    results_by_form: dict[str, dict] = {}
    for row in rows:
        form = str(row.get("form") or "")
        results_by_form[form] = {
            "sf_normalized": row.get("sf_normalized"),
            "sf_concept_id": row.get("sf_concept_id"),
            "sf_concept_term": row.get("sf_concept_term"),
            "term_normalized": row.get("term_normalized"),
            "term_concept_id": row.get("term_concept_id"),
            "term_concept_term": row.get("term_concept_term"),
        }

    # Classify each candidate
    exists_as_surface_form: list[dict] = []
    exists_as_term: list[dict] = []
    missing: list[dict] = []

    for norm, meta in sorted(candidate_forms.items(), key=lambda x: -x[1]["count"]):
        hit = results_by_form.get(norm, {})
        entry = {
            "normalised": norm,
            "raw": meta["raw"],
            "label": meta["label"],
            "category": meta["category"],
            "count": meta["count"],
            **hit,
        }
        if hit.get("sf_concept_id"):
            exists_as_surface_form.append(entry)
        elif hit.get("term_concept_id"):
            exists_as_term.append(entry)
        else:
            missing.append(entry)

    # Save
    output = {
        "summary": {
            "total_candidates": len(candidate_forms),
            "exists_as_surface_form": len(exists_as_surface_form),
            "exists_as_snomed_term": len(exists_as_term),
            "missing_entirely": len(missing),
        },
        "exists_as_surface_form": exists_as_surface_form,
        "exists_as_snomed_term": exists_as_term,
        "missing": missing,
    }
    OUTPUT_FILE.write_text(
        json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Saved -> {OUTPUT_FILE}\n")

    # --- Print summary ---
    print("=" * 60)
    print(f"Total candidate forms : {len(candidate_forms)}")
    print(f"Already a SurfaceForm : {len(exists_as_surface_form)}")
    print(f"Already a SNOMED Term : {len(exists_as_term)}")
    print(f"Missing entirely      : {len(missing)}")
    print("=" * 60)

    if exists_as_surface_form:
        print(f"\n-- Already have as SurfaceForm ({len(exists_as_surface_form)}) --")
        for e in exists_as_surface_form:
            print(
                f"  [{e['count']:4d}]  {e['normalised']!r:35s} -> {e['sf_concept_id']} {e['sf_concept_term']}"
            )

    if exists_as_term:
        print(f"\n-- Already a SNOMED Term ({len(exists_as_term)}) --")
        for e in exists_as_term:
            print(
                f"  [{e['count']:4d}]  {e['normalised']!r:35s} -> {e['term_concept_id']} {e['term_concept_term']}"
            )

    if missing:
        print(
            f"\n-- Missing entirely ({len(missing)}) -- need adding to terminology server --"
        )
        for e in missing:
            print(
                f"  [{e['count']:4d}]  {e['category']:<25s}  {e['label']:<35s}  {e['normalised']!r}"
            )


if __name__ == "__main__":
    main()
