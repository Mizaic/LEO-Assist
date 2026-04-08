"""Find the correct SNOMED concept for each missing surface form.

Reads surface_form_coverage.json, takes the 42 missing forms,
and for each one searches the KG fulltext index to find the best
matching active Concept.  Results are printed and saved to
output/missing_surface_form_snomed.json for review before adding.

Usage:
    python scripts/investigations/_find_snomed_for_missing_forms.py
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

INPUT_FILE = Path(__file__).parent / "output" / "surface_form_coverage.json"
OUTPUT_FILE = Path(__file__).parent / "output" / "missing_surface_form_snomed.json"

# -- Fulltext search returning top 3 candidates per query ------------------
_SEARCH_Q = """
CALL {
    CALL db.index.fulltext.queryNodes("term_fulltext", $q) YIELD node, score
    MATCH (node)-[:DESCRIBES]->(c:Concept)
    WHERE c.active = true
    RETURN c, score
    UNION
    CALL db.index.fulltext.queryNodes("surface_form_fulltext", $q) YIELD node, score
    MATCH (node)-[:MAPS_TO]->(c:Concept)
    WHERE c.active = true
    RETURN c, score * 1.2 AS score
}
WITH c, max(score) AS best
RETURN c.id            AS concept_id,
       c.preferredTerm AS preferred_term,
       c.fsn           AS fsn,
       c.semantic_tag  AS semantic_tag,
       best            AS score
ORDER BY best DESC
LIMIT 3
"""

# -- For place/setting concepts we also try exact label lookups ------------
# Known mappings that are unlikely to surface via fulltext (abbreviations,
# clinical shorthand) -- manually curated from SNOMED UK edition.
_MANUAL: dict[str, dict] = {
    "opd": {
        "concept_id": "225728007",
        "preferred_term": "Outpatient environment (environment)",
        "fsn": "Outpatient environment (environment)",
        "semantic_tag": "environment",
        "note": "OPD = outpatient department",
    },
    "primary care": {
        "concept_id": "63331000000100",  # Primary care organisation
        "preferred_term": "Primary care organisation (organisation)",
        "fsn": "Primary care organisation (organisation)",
        "semantic_tag": "organisation",
        "note": "General primary care setting",
    },
    "a&e": {
        "concept_id": "225728007",
        "preferred_term": "Accident and emergency department (environment)",
        "fsn": "Accident and emergency department (environment)",
        "semantic_tag": "environment",
        "note": "A&E abbreviation -> accident and emergency department",
    },
    "walk in centre": {
        "concept_id": "310390009",
        "preferred_term": "Walk-in centre (environment)",
        "fsn": "Walk-in centre (environment)",
        "semantic_tag": "environment",
        "note": "",
    },
    "ucc": {
        "concept_id": "310390009",
        "preferred_term": "Walk-in centre (environment)",
        "fsn": "Walk-in centre (environment)",
        "semantic_tag": "environment",
        "note": "UCC = urgent care centre -> maps to walk-in centre",
    },
    "gp appointment": {
        "concept_id": "185316007",
        "preferred_term": "Follow-up appointment (procedure)",
        "fsn": "Follow-up appointment (procedure)",
        "semantic_tag": "procedure",
        "note": "GP appointment context -> general practice encounter",
    },
    "accident and emergency": {
        "concept_id": "182992009",
        "preferred_term": "Accident and emergency department (environment)",
        "fsn": "Accident and emergency department (environment)",
        "semantic_tag": "environment",
        "note": "Full form of A&E",
    },
    "outpatient appointment": {
        "concept_id": "225728007",
        "preferred_term": "Outpatient environment (environment)",
        "fsn": "Outpatient environment (environment)",
        "semantic_tag": "environment",
        "note": "",
    },
    "blood in the stool": {
        "concept_id": "405729008",
        "preferred_term": "Haematochezia (finding)",
        "fsn": "Haematochezia (finding)",
        "semantic_tag": "finding",
        "note": "= PR / rectal bleeding",
    },
    "dribbling": {
        "concept_id": "85929007",
        "preferred_term": "Urinary dribbling (finding)",
        "fsn": "Urinary dribbling (finding)",
        "semantic_tag": "finding",
        "note": "LUTS symptom",
    },
    "blood in the urine": {
        "concept_id": "34436003",
        "preferred_term": "Blood in urine (finding)",
        "fsn": "Blood in urine (finding)",
        "semantic_tag": "finding",
        "note": "= haematuria",
    },
    "pr bleed": {
        "concept_id": "405729008",
        "preferred_term": "Haematochezia (finding)",
        "fsn": "Haematochezia (finding)",
        "semantic_tag": "finding",
        "note": "PR bleed = per rectum bleeding",
    },
    "pv bleeding": {
        "concept_id": "289530006",
        "preferred_term": "Vaginal bleeding (finding)",
        "fsn": "Vaginal bleeding (finding)",
        "semantic_tag": "finding",
        "note": "PV = per vaginum",
    },
    "pmb": {
        "concept_id": "76742009",
        "preferred_term": "Bleeding from female genital tract (finding)",
        "fsn": "Bleeding from female genital tract (finding)",
        "semantic_tag": "finding",
        "note": "PMB = postmenopausal bleeding",
    },
    "breast discomfort": {
        "concept_id": "53430007",
        "preferred_term": "Pain in breast (finding)",
        "fsn": "Pain in breast (finding)",
        "semantic_tag": "finding",
        "note": "= mastalgia / breast pain",
    },
    "high psa": {
        "concept_id": "396152005",
        "preferred_term": "Prostate specific antigen raised (finding)",
        "fsn": "Prostate specific antigen raised (finding)",
        "semantic_tag": "finding",
        "note": "= elevated PSA",
    },
    "psa high": {
        "concept_id": "396152005",
        "preferred_term": "Prostate specific antigen raised (finding)",
        "fsn": "Prostate specific antigen raised (finding)",
        "semantic_tag": "finding",
        "note": "= elevated PSA",
    },
    "nipple inversion": {
        "concept_id": "299024004",
        "preferred_term": "Inverted nipple (finding)",
        "fsn": "Inverted nipple (finding)",
        "semantic_tag": "finding",
        "note": "",
    },
    "changing mole": {
        "concept_id": "400010006",
        "preferred_term": "Mole - skin lesion (disorder)",
        "fsn": "Mole - skin lesion (disorder)",
        "semantic_tag": "disorder",
        "note": "Use with assertion=present and semantic context of change",
    },
    "coughing blood": {
        "concept_id": "66857006",
        "preferred_term": "Haemoptysis (finding)",
        "fsn": "Haemoptysis (finding)",
        "semantic_tag": "finding",
        "note": "= haemoptysis",
    },
    "online consultation": {
        "concept_id": "719410009",
        "preferred_term": "Video consultation (procedure)",
        "fsn": "Video consultation (procedure)",
        "semantic_tag": "procedure",
        "note": "Best available SNOMED match for online/remote consultation",
    },
    "telephone appointment": {
        "concept_id": "386472008",
        "preferred_term": "Telephone consultation (procedure)",
        "fsn": "Telephone consultation (procedure)",
        "semantic_tag": "procedure",
        "note": "",
    },
    "self-refer": {
        "concept_id": "306206005",
        "preferred_term": "Referral to service (procedure)",
        "fsn": "Referral to service (procedure)",
        "semantic_tag": "procedure",
        "note": "Self-referral",
    },
    "self refer": {
        "concept_id": "306206005",
        "preferred_term": "Referral to service (procedure)",
        "fsn": "Referral to service (procedure)",
        "semantic_tag": "procedure",
        "note": "Self-referral",
    },
    "self referral": {
        "concept_id": "306206005",
        "preferred_term": "Referral to service (procedure)",
        "fsn": "Referral to service (procedure)",
        "semantic_tag": "procedure",
        "note": "Self-referral",
    },
    "self referred": {
        "concept_id": "306206005",
        "preferred_term": "Referral to service (procedure)",
        "fsn": "Referral to service (procedure)",
        "semantic_tag": "procedure",
        "note": "Self-referral",
    },
    "screening programme": {
        "concept_id": "443390004",
        "preferred_term": "Screening for malignant neoplasm (procedure)",
        "fsn": "Screening for malignant neoplasm (procedure)",
        "semantic_tag": "procedure",
        "note": "General cancer screening",
    },
    "cervical screening": {
        "concept_id": "243804009",
        "preferred_term": "Cervical smear test (procedure)",
        "fsn": "Cervical smear test (procedure)",
        "semantic_tag": "procedure",
        "note": "",
    },
    "breast screening": {
        "concept_id": "310416002",
        "preferred_term": "Breast cancer screening (procedure)",
        "fsn": "Breast cancer screening (procedure)",
        "semantic_tag": "procedure",
        "note": "",
    },
    "emergency department": {
        "concept_id": "182992009",
        "preferred_term": "Accident and emergency department (environment)",
        "fsn": "Accident and emergency department (environment)",
        "semantic_tag": "environment",
        "note": "= A&E",
    },
    "night sweat": {
        "concept_id": "42984000",
        "preferred_term": "Night sweats (finding)",
        "fsn": "Night sweats (finding)",
        "semantic_tag": "finding",
        "note": "Singular form of night sweats",
    },
    "lump in the breast": {
        "concept_id": "89164003",
        "preferred_term": "Breast lump (finding)",
        "fsn": "Breast lump (finding)",
        "semantic_tag": "finding",
        "note": "",
    },
    "severe headache": {
        "concept_id": "25064002",
        "preferred_term": "Headache (finding)",
        "fsn": "Headache (finding)",
        "semantic_tag": "finding",
        "note": "No separate SNOMED code for severity qualifier in surface form context",
    },
    "worsening headache": {
        "concept_id": "25064002",
        "preferred_term": "Headache (finding)",
        "fsn": "Headache (finding)",
        "semantic_tag": "finding",
        "note": "No separate SNOMED code; qualifier captured in clinical context",
    },
    "pv bleed": {
        "concept_id": "289530006",
        "preferred_term": "Vaginal bleeding (finding)",
        "fsn": "Vaginal bleeding (finding)",
        "semantic_tag": "finding",
        "note": "PV bleed = per vaginum bleed",
    },
    "non-healing wound": {
        "concept_id": "225552003",
        "preferred_term": "Wound healing impaired (finding)",
        "fsn": "Wound healing impaired (finding)",
        "semantic_tag": "finding",
        "note": "",
    },
    "palpable lump": {
        "concept_id": "309530003",
        "preferred_term": "Palpable mass (finding)",
        "fsn": "Palpable mass (finding)",
        "semantic_tag": "finding",
        "note": "Generic palpable mass; more specific code assigned by context",
    },
    "difficulty swallow": {
        "concept_id": "40739000",
        "preferred_term": "Dysphagia (finding)",
        "fsn": "Dysphagia (finding)",
        "semantic_tag": "finding",
        "note": "Truncated form of 'difficulty swallowing'",
    },
    "vaginal bleed": {
        "concept_id": "289530006",
        "preferred_term": "Vaginal bleeding (finding)",
        "fsn": "Vaginal bleeding (finding)",
        "semantic_tag": "finding",
        "note": "",
    },
    "clinic appointment": {
        "concept_id": "225728007",
        "preferred_term": "Outpatient environment (environment)",
        "fsn": "Outpatient environment (environment)",
        "semantic_tag": "environment",
        "note": "Clinic appointment context -> outpatient environment",
    },
    "hospital outpatient": {
        "concept_id": "225728007",
        "preferred_term": "Outpatient environment (environment)",
        "fsn": "Outpatient environment (environment)",
        "semantic_tag": "environment",
        "note": "",
    },
}


def _verify_concept(kg: KnowledgeGraphClient, concept_id: str) -> dict | None:
    """Confirm a concept exists in the KG and return its preferred term."""
    rows = kg.run(
        "MATCH (c:Concept {id: $id}) WHERE c.active = true "
        "RETURN c.id AS concept_id, c.preferredTerm AS preferred_term, "
        "       c.fsn AS fsn, c.semantic_tag AS semantic_tag",
        id=concept_id,
    )
    return dict(rows[0]) if rows else None


def _search_concept(kg: KnowledgeGraphClient, query: str) -> list[dict]:
    """Search KG fulltext for top 3 matching active concepts."""
    try:
        rows = kg.run(_SEARCH_Q, q=query) or []
        return [dict(r) for r in rows]
    except Exception:
        return []


def main() -> None:
    coverage = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    missing = coverage.get("missing", [])
    print(f"Processing {len(missing)} missing surface forms ...\n")

    kg = KnowledgeGraphClient()
    results: list[dict] = []

    try:
        for entry in missing:
            norm = entry["normalised"]
            label = entry["label"]
            category = entry["category"]
            count = entry["count"]

            # Prefer manual mapping (curated SNOMED codes)
            if norm in _MANUAL:
                manual = _MANUAL[norm]
                # Verify the concept actually exists in this KG
                verified = _verify_concept(kg, manual["concept_id"])
                if verified:
                    result = {
                        "normalised": norm,
                        "raw": entry["raw"],
                        "label": label,
                        "category": category,
                        "count": count,
                        "source": "manual_curation",
                        "concept_id": verified["concept_id"],
                        "preferred_term": verified.get("preferred_term") or manual["preferred_term"],
                        "fsn": verified.get("fsn") or manual["fsn"],
                        "semantic_tag": verified.get("semantic_tag") or manual["semantic_tag"],
                        "note": manual.get("note", ""),
                        "candidates": [],
                    }
                else:
                    # Concept not in this KG -- fall back to fulltext search
                    candidates = _search_concept(kg, norm)
                    result = {
                        "normalised": norm,
                        "raw": entry["raw"],
                        "label": label,
                        "category": category,
                        "count": count,
                        "source": "search_fallback",
                        "concept_id": candidates[0]["concept_id"] if candidates else None,
                        "preferred_term": candidates[0]["preferred_term"] if candidates else None,
                        "fsn": candidates[0]["fsn"] if candidates else None,
                        "semantic_tag": candidates[0]["semantic_tag"] if candidates else None,
                        "note": f"Manual concept {manual['concept_id']} not in KG; used search",
                        "candidates": candidates,
                    }
            else:
                # No manual mapping -- use fulltext search
                candidates = _search_concept(kg, norm)
                best = candidates[0] if candidates else {}
                result = {
                    "normalised": norm,
                    "raw": entry["raw"],
                    "label": label,
                    "category": category,
                    "count": count,
                    "source": "search",
                    "concept_id": best.get("concept_id"),
                    "preferred_term": best.get("preferred_term"),
                    "fsn": best.get("fsn"),
                    "semantic_tag": best.get("semantic_tag"),
                    "note": "",
                    "candidates": candidates,
                }

            results.append(result)

            status = "OK" if result["concept_id"] else "NOT FOUND"
            print(
                f"  [{count:3d}] {status:9s} {norm!r:35s} "
                f"-> {result['concept_id'] or '---':20s} {(result['preferred_term'] or '')[:55]}"
            )

    finally:
        kg.close()

    # Save
    OUTPUT_FILE.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved -> {OUTPUT_FILE}")

    found = sum(1 for r in results if r["concept_id"])
    print(f"\nResolved : {found}/{len(results)}")
    unresolved = [r for r in results if not r["concept_id"]]
    if unresolved:
        print("Unresolved forms (manual review needed):")
        for r in unresolved:
            print(f"  {r['normalised']!r}  ({r['label']})")


if __name__ == "__main__":
    main()
