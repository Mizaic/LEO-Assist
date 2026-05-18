"""One-shot promotion: stage_of_diagnosis ValueSet, Concept stubs, SurfaceForms, patient :DOCUMENTS.

The clinical audit dashboard, analytics-api domain registry, and episode/anchor
pipelines load subdomain SNOMED allow-lists from the **Knowledge Graph**::

    (AuditDomain {id: 'cancer_audit'})-[:HAS_SUBDOMAIN]->(:ValueSet {id: 'ncda-...'})

``DomainRegistry.from_fhir`` reads ``ValueSet.rawJson`` (see ``libs/domain_config``,
``libs/pipeline_graph/subgraphs/anchor.py``).  Hybrid coding resolution matches
encounter text to SNOMED via **Knowledge Graph**::

    (:SurfaceForm {normalized})-[:MAPS_TO]->(:Concept {id: snomed_id})

This script sequences:

1. Upsert ``ncda-stage-of-diagnosis`` + link to ``cancer_audit`` (same as
   ``scripts/investigations/_seed_stage_of_diagnosis_subdomain.py``).
2. ``MERGE`` minimal ``:Concept`` rows for every code in
   ``configs/snomed/snomed_ncda_stage_of_diagnosis_mapping.json``.
3. Upsert ``SurfaceForm`` pins (synonyms + encounter-shaped phrases).
4. Optionally backfill **patient graph** ``:DOCUMENTS`` / ``:HAS_*`` for known
   uncoded encounters (see ``run_staging_document_backfill``).

Usage::

    # Dry-run patient writes; still writes KG (unless skipped)
    python scripts/ncda/promote_stage_of_diagnosis.py

    # Full apply including patient graph
    python scripts/ncda/promote_stage_of_diagnosis.py --apply-backfill

    # Only refresh KG (no patient graph)
    python scripts/ncda/promote_stage_of_diagnosis.py --skip-backfill

    # Only Concepts + SurfaceForms (ValueSet already current)
    python scripts/ncda/promote_stage_of_diagnosis.py --skip-valueset

Restart services that cache ``DomainRegistry`` after step (1) if applicable.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets
from libs.ncda.stage_of_diagnosis_kg import (
    ensure_concepts_for_mapping,
    ensure_surface_forms_for_mapping,
    load_mapping,
    seed_valueset_to_kg,
    verify_subdomain_linked,
)
from libs.neo4j_client.client import KnowledgeGraphClient

load_keyvault_secrets()


def _load_backfill_runner():
    path = ROOT / "scripts" / "investigations" / "_backfill_uncoded_staging_documents.py"
    spec = importlib.util.spec_from_file_location("_staging_backfill", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load backfill module from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.run_staging_document_backfill


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-valueset",
        action="store_true",
        help="Do not upsert ValueSet / HAS_SUBDOMAIN (steps 2-3 still run).",
    )
    parser.add_argument(
        "--skip-surface",
        action="store_true",
        help="Skip Concept MERGE and SurfaceForm MAPS_TO.",
    )
    parser.add_argument(
        "--skip-backfill",
        action="store_true",
        help="Do not run patient-graph DOCUMENTS backfill.",
    )
    parser.add_argument(
        "--apply-backfill",
        action="store_true",
        help="Write patient :DOCUMENTS; default is backfill dry-run only.",
    )
    args = parser.parse_args()

    mapping = load_mapping()

    if not args.skip_valueset:
        print("== 1. ValueSet ncda-stage-of-diagnosis + cancer_audit link")
        seed_valueset_to_kg(mapping)
    else:
        print("== 1. SKIP ValueSet upsert")

    kg = KnowledgeGraphClient()
    try:
        if not verify_subdomain_linked(kg):
            print(
                "WARN: stage_of_diagnosis ValueSet not linked or empty — "
                "fix before relying on audit/dashboard expansion."
            )
        if not args.skip_surface:
            print("== 2. Concept stubs from mapping")
            n_concepts = ensure_concepts_for_mapping(kg, mapping)
            print(f"     MERGE Concept count: {n_concepts}")
            print("== 3. SurfaceForm MAPS_TO pins")
            w, sk = ensure_surface_forms_for_mapping(kg, mapping)
            print(f"     Surface upserts: {w}, duplicate pairs skipped: {sk}")
        else:
            print("== 2-3. SKIP Concept / SurfaceForm")
    finally:
        kg.close()

    if args.skip_backfill:
        print("== 4. SKIP patient-graph backfill")
        return

    print("== 4. Patient graph staging DOCUMENTS backfill")
    run_bf = _load_backfill_runner()
    run_bf(apply=args.apply_backfill)


if __name__ == "__main__":
    main()
