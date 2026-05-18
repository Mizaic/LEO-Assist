"""Seed stage_of_diagnosis ValueSet into cancer_audit domain.

Run:
    python scripts/investigations/_seed_stage_of_diagnosis_subdomain.py
    python scripts/investigations/_seed_stage_of_diagnosis_subdomain.py --verify-only

Full stack (ValueSet + Concept stubs + SurfaceForm + optional patient backfill)::

    python scripts/ncda/promote_stage_of_diagnosis.py --apply-backfill

Implementation: :mod:`libs.ncda.stage_of_diagnosis_kg`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets
from libs.ncda.stage_of_diagnosis_kg import (
    VS_ID,
    VS_NAME,
    load_mapping,
    seed_valueset_to_kg,
    verify_subdomain_linked,
)
from libs.neo4j_client.client import KnowledgeGraphClient

load_keyvault_secrets()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()

    kg = KnowledgeGraphClient()
    try:
        if not args.verify_only:
            mapping = load_mapping()
            seed_valueset_to_kg(mapping)
            print(f"Upserted {VS_ID} and linked to cancer_audit.")
        ok = verify_subdomain_linked(kg)
        if ok:
            raw = kg.run(
                "MATCH (v:ValueSet {id: $id}) RETURN v.rawJson AS raw",
                id=VS_ID,
            )
            vs = json.loads(raw[0]["raw"]) if raw and raw[0].get("raw") else {}
            n = sum(
                len(inc.get("concept") or [])
                for inc in (vs.get("compose") or {}).get("include") or []
            )
            print(
                "PASS:"
                f" linked=true, name={VS_NAME!r}, milestoneType=diagnosis,"
                f" concept_count={n}"
            )
        else:
            print("FAIL: stage_of_diagnosis ValueSet is not linked to cancer_audit.")
            sys.exit(1)
    finally:
        kg.close()


if __name__ == "__main__":
    main()
