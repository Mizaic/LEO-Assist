"""Audit surface forms for the place-of-presentation SNOMED concepts.

For each confirmed place concept:
1. Fetches all Term synonyms and SurfaceForm nodes already in the KG
2. Fetches IS_A descendants (variant concepts)
3. Checks a list of candidate colloquial surface forms
4. Reports which are present and which need adding

Output:
    scripts/investigations/output/place_surface_form_audit.json
    Printed summary to stdout.

Usage:
    python scripts/investigations/_place_surface_form_audit.py
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

OUTPUT_FILE = Path(__file__).parent / "output" / "place_surface_form_audit.json"

# ---------------------------------------------------------------------------
# Confirmed place-of-presentation concepts (from user)
# ---------------------------------------------------------------------------
PLACE_CONCEPTS = [
    {
        "concept_id": "4525004",
        "label": "Emergency department patient visit",
        "candidates": [
            "a&e", "ae", "accident and emergency", "accident & emergency",
            "emergency department", "ed", "emergency room", "er",
            "a and e", "a+e", "a & e", "casualty", "emergency dept",
            "attended a&e", "seen in a&e", "went to a&e",
        ],
    },
    {
        "concept_id": "185202000",
        "label": "Seen in general practitioner surgery",
        "candidates": [
            "gp surgery", "gp practice", "gp appointment", "gp visit",
            "gp clinic", "seen by gp", "seen at gp", "attended gp",
            "general practitioner", "general practice", "primary care",
            "family doctor", "gp consultation", "gp review",
            "surgery appointment", "seen in surgery",
        ],
    },
    {
        "concept_id": "386472008",
        "label": "Telephone consultation",
        "candidates": [
            "telephone consultation", "telephone appointment", "phone consultation",
            "phone call", "telephone call", "tel consult", "telephone consult",
            "phone appointment", "telephone review", "phone review",
            "spoke by phone", "called by phone", "telephone advice",
        ],
    },
    {
        "concept_id": "439708006",
        "label": "Home visit",
        "candidates": [
            "home visit", "domiciliary visit", "home call", "visited at home",
            "seen at home", "house call", "housecall", "home consultation",
            "domiciliary", "home assessment", "visited patient at home",
        ],
    },
    {
        "concept_id": "185463005",
        "label": "Visit out of hours",
        "candidates": [
            "out of hours", "ooh", "out-of-hours", "out of hours visit",
            "ooh visit", "out of hours gp", "ooh gp", "ooh service",
            "nhs 111", "111", "evening appointment", "weekend appointment",
            "urgent out of hours", "out of hours consultation",
        ],
    },
    {
        "concept_id": "557761000005104",
        "label": "E-mail consultation",
        "candidates": [
            "email consultation", "e-mail consultation", "email consult",
            "e-consult", "econsult", "online form", "askmygp",
            "emailed gp", "electronic consultation", "online consultation request",
            "sent message to gp", "accubook", "patchs",
        ],
    },
    {
        "concept_id": "719410009",
        "label": "Consultation via video conference",
        "candidates": [
            "video consultation", "video call", "video appointment",
            "video conference", "video consult", "online video",
            "microsoft teams consultation", "teams call", "zoom consultation",
            "attend anywhere", "video review", "remote video consultation",
            "online consultation", "virtual consultation", "virtual appointment",
        ],
    },
    {
        "concept_id": "286901000000107",
        "label": "Bowel cancer screening programme",
        "candidates": [
            "bowel cancer screening", "bowel screening", "colorectal screening",
            "fit test", "faecal immunochemical test", "fobt",
            "faecal occult blood test", "bowel scope", "colonoscopy screening",
            "nhs bowel cancer screening", "bowel cancer check",
        ],
    },
    {
        "concept_id": "268547008",
        "label": "Screening for malignant neoplasm of breast",
        "candidates": [
            "breast screening", "mammogram", "mammography",
            "breast cancer screening", "nhs breast screening",
            "breast check", "mammogram appointment", "breast x-ray",
            "screening mammogram", "breast screening appointment",
        ],
    },
    {
        "concept_id": "171149006",
        "label": "Screening for malignant neoplasm of cervix",
        "candidates": [
            "cervical screening", "smear test", "smear", "cervical smear",
            "pap smear", "pap test", "cervical cancer screening",
            "nhs cervical screening", "colposcopy", "hpv test",
            "cervical check", "routine smear",
        ],
    },
    {
        "concept_id": "275981009",
        "label": "Screening for malignant neoplasm of lung",
        "candidates": [
            "lung cancer screening", "lung screening", "ldct",
            "low dose ct scan", "lung check", "chest ct screening",
            "targeted lung health check", "tlhc", "lung health check",
        ],
    },
    {
        "concept_id": "307778003",
        "label": "Seen in primary care establishment",
        "candidates": [
            "primary care", "primary care visit", "seen in primary care",
            "seen at primary care", "primary care appointment",
            "community care", "gp led", "community health centre",
            "health centre", "walk-in centre", "minor injuries unit",
            "urgent treatment centre", "utc", "ucc", "miu",
        ],
    },
    {
        "concept_id": "185211000",
        "label": "Seen in hospital outpatient department",
        "candidates": [
            "outpatient", "outpatients", "opd", "outpatient department",
            "outpatient appointment", "outpatient clinic", "outpatient visit",
            "hospital outpatient", "seen in outpatients", "clinic appointment",
            "hospital clinic", "attended outpatients", "seen at hospital",
            "hospital appointment", "specialist outpatient",
        ],
    },
    {
        "concept_id": "185289007",
        "label": "Seen by dental surgeon",
        "candidates": [
            "dental", "dentist", "dental appointment", "seen by dentist",
            "dental visit", "dental surgeon", "oral surgeon",
            "dental consultation", "seen at dentist",
        ],
    },
    {
        "concept_id": "305856003",
        "label": "Seen by optometry service",
        "candidates": [
            "optician", "optometry", "eye test", "seen by optician",
            "optometrist", "eye appointment", "optics appointment",
            "vision test", "eye examination", "seen at optician",
        ],
    },
    {
        "concept_id": "305751001",
        "label": "Seen by community-based nurse",
        "candidates": [
            "community nurse", "district nurse", "community nursing",
            "seen by nurse", "nurse visit", "nurse appointment",
            "practice nurse", "community health nurse", "nurse consultation",
            "nursing visit", "nurse review", "seen at nurse clinic",
        ],
    },
]

# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

_EXISTING_MAPPINGS_Q = """
MATCH (c:Concept {id: $concept_id})
OPTIONAL MATCH (t:Term)-[:DESCRIBES]->(c)
OPTIONAL MATCH (sf:SurfaceForm)-[:MAPS_TO]->(c)
RETURN
    collect(DISTINCT toLower(t.normalized_form)) AS existing_terms,
    collect(DISTINCT sf.normalized)              AS existing_surface_forms
"""

_DESCENDANTS_Q = """
MATCH (parent:Concept {id: $concept_id})<-[:IS_A*1..3]-(child:Concept)
WHERE child.active = true
RETURN child.id            AS concept_id,
       child.preferredTerm AS preferred_term,
       child.fsn           AS fsn
ORDER BY child.fsn
LIMIT 50
"""

_BATCH_CHECK_Q = """
UNWIND $forms AS form
OPTIONAL MATCH (sf:SurfaceForm {normalized: form})-[:MAPS_TO]->(sc:Concept)
OPTIONAL MATCH (t:Term {normalized_form: form})-[:DESCRIBES]->(tc:Concept)
RETURN form,
       sf.normalized   AS sf_normalized,
       sc.id           AS sf_concept_id,
       sc.fsn          AS sf_fsn,
       t.normalized_form AS term_normalized,
       tc.id           AS term_concept_id,
       tc.fsn          AS term_fsn
"""

_CONCEPT_INFO_Q = """
MATCH (c:Concept {id: $concept_id})
RETURN c.id AS concept_id, c.preferredTerm AS preferred_term,
       c.fsn AS fsn, c.semantic_tag AS semantic_tag, c.active AS active
"""


def _normalise(s: str) -> str:
    return s.lower().strip()


def main() -> None:
    kg = KnowledgeGraphClient()
    all_results = []

    try:
        for entry in PLACE_CONCEPTS:
            concept_id = entry["concept_id"]
            label = entry["label"]
            candidates = [_normalise(c) for c in entry["candidates"]]

            # -- Confirm concept exists in KG --------------------------------
            info_rows = kg.run(_CONCEPT_INFO_Q, concept_id=concept_id) or []
            if not info_rows:
                print(f"\n  [!] CONCEPT NOT IN KG: {concept_id} -- {label}")
                all_results.append({
                    "concept_id": concept_id,
                    "label": label,
                    "in_kg": False,
                    "fsn": None,
                    "preferred_term": None,
                    "existing_terms": [],
                    "existing_surface_forms": [],
                    "descendants": [],
                    "candidates_checked": [],
                })
                continue

            info = info_rows[0]
            fsn = str(info.get("fsn") or "")
            preferred_term = str(info.get("preferred_term") or "")

            print(f"\n{'=' * 70}")
            print(f"  {concept_id}  {fsn}")

            # -- Existing terms and surface forms ----------------------------
            map_rows = kg.run(_EXISTING_MAPPINGS_Q, concept_id=concept_id) or []
            existing_terms: list[str] = []
            existing_sfs: list[str] = []
            if map_rows:
                existing_terms = [t for t in (map_rows[0].get("existing_terms") or []) if t]
                existing_sfs = [sf for sf in (map_rows[0].get("existing_surface_forms") or []) if sf]

            print(f"  Existing terms       : {existing_terms[:8]}")
            print(f"  Existing surf. forms : {existing_sfs[:8]}")

            # -- Descendants -------------------------------------------------
            desc_rows = kg.run(_DESCENDANTS_Q, concept_id=concept_id) or []
            descendants = [dict(r) for r in desc_rows]
            if descendants:
                print(f"  IS_A descendants     : {len(descendants)}")
                for d in descendants[:5]:
                    print(f"    {d['concept_id']}  {d['fsn']}")

            # -- Check each candidate ----------------------------------------
            hit_rows = kg.run(_BATCH_CHECK_Q, forms=candidates) or []
            hit_by_form: dict[str, dict] = {
                str(r.get("form") or ""): dict(r) for r in hit_rows
            }

            already_covered: list[dict] = []
            missing: list[dict] = []
            mapped_to_other: list[dict] = []

            for cand in candidates:
                hit = hit_by_form.get(cand, {})
                sf_cid = hit.get("sf_concept_id")
                t_cid = hit.get("term_concept_id")

                if sf_cid == concept_id or t_cid == concept_id:
                    already_covered.append({
                        "form": cand,
                        "via": "surface_form" if sf_cid == concept_id else "term",
                    })
                elif sf_cid or t_cid:
                    mapped_to_other.append({
                        "form": cand,
                        "mapped_to": sf_cid or t_cid,
                        "fsn": hit.get("sf_fsn") or hit.get("term_fsn"),
                    })
                else:
                    missing.append({"form": cand})

            print(f"  Candidates covered   : {len(already_covered)}")
            print(f"  Missing (need adding): {len(missing)}")
            if missing:
                for m in missing:
                    print(f"    MISSING  {m['form']!r}")
            if mapped_to_other:
                print(f"  Mapped to other concept ({len(mapped_to_other)}):")
                for m in mapped_to_other[:4]:
                    print(f"    {m['form']!r} -> {m['mapped_to']}  {m['fsn']}")

            all_results.append({
                "concept_id": concept_id,
                "label": label,
                "in_kg": True,
                "fsn": fsn,
                "preferred_term": preferred_term,
                "existing_terms": existing_terms,
                "existing_surface_forms": existing_sfs,
                "descendants": descendants,
                "candidates": {
                    "already_covered": already_covered,
                    "missing": missing,
                    "mapped_to_other_concept": mapped_to_other,
                },
            })

    finally:
        kg.close()

    OUTPUT_FILE.write_text(
        json.dumps(all_results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\n\nSaved -> {OUTPUT_FILE}")

    # Summary
    total_missing = sum(
        len(r.get("candidates", {}).get("missing", []))
        for r in all_results if r.get("in_kg")
    )
    total_covered = sum(
        len(r.get("candidates", {}).get("already_covered", []))
        for r in all_results if r.get("in_kg")
    )
    not_in_kg = [r for r in all_results if not r.get("in_kg")]

    print(f"\n{'=' * 70}")
    print(f"Concepts checked : {len(all_results)}")
    print(f"Not in KG        : {len(not_in_kg)} {[r['concept_id'] for r in not_in_kg]}")
    print(f"Candidates covered already : {total_covered}")
    print(f"Candidates missing (to add): {total_missing}")


if __name__ == "__main__":
    main()
