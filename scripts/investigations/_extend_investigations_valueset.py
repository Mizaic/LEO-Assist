"""Extend ncda-investigations ValueSet with pathway-specific investigation concepts.

Adds skin, breast, urology, gynaecology and microbiology investigations that were
missing from the original imaging-focused ValueSet.  The new concepts were verified
against the LEO knowledge graph (concept IDs confirmed active via Cypher query
2026-04-30).

Usage:
    python scripts/investigations/_extend_investigations_valueset.py
    python scripts/investigations/_extend_investigations_valueset.py --verify-only
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "analytics_api"))

from dotenv import load_dotenv
from libs.keyvault.loader import load_keyvault_secrets

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
load_keyvault_secrets()

from app.routers.domains import _upsert_valueset_flat  # noqa: E402
from libs.neo4j_client.client import KnowledgeGraphClient  # noqa: E402

VS_ID = "ncda-investigations"
SNOMED_SYSTEM = "http://snomed.info/sct"

NEW_CONCEPTS = [
    # Breast pathway
    ("71651007",   "Mammography (procedure)"),
    ("46662001",   "Examination of breast (procedure)"),
    # Urology pathway
    ("142505009",  "Cystoscopy (procedure)"),
    ("27171005",   "Urinalysis (procedure)"),
    ("168132005",  "Microscopy, culture and sensitivities (procedure)"),
    ("63476009",   "Prostate specific antigen measurement (procedure)"),
    # Gynaecology pathway
    ("233545006",  "Hysteroscopy (procedure)"),
    # Lower GI pathway
    ("24420007",   "Sigmoidoscopy (procedure)"),
    # Skin pathway
    ("446078004",  "Dermoscopic photography (procedure)"),
    ("252983000",  "Skin lesion photography (procedure)"),
    ("240977001",  "Biopsy of skin (procedure)"),
]


def _load_raw(kg: KnowledgeGraphClient, vs_id: str) -> dict:
    rows = kg.run(
        "MATCH (v:ValueSet {id: $id}) RETURN v.rawJson AS rj",
        id=vs_id,
    )
    if not rows or not rows[0].get("rj"):
        raise RuntimeError(f"ValueSet '{vs_id}' not found or has no rawJson")
    raw = rows[0]["rj"]
    return json.loads(raw) if isinstance(raw, str) else raw


def _add_concepts(vs: dict, additions: list[tuple[str, str]]) -> int:
    compose = vs.setdefault("compose", {})
    includes = compose.setdefault("include", [])
    snomed_inc = next((i for i in includes if i.get("system") == SNOMED_SYSTEM), None)
    if not snomed_inc:
        snomed_inc = {"system": SNOMED_SYSTEM, "concept": []}
        includes.append(snomed_inc)
    concepts = snomed_inc.setdefault("concept", [])
    existing = {str(c.get("code")) for c in concepts}
    added = 0
    for code, display in additions:
        if code in existing:
            print(f"  {code}  {display[:50]}  -- already present, skipping")
        else:
            concepts.append({"code": code, "display": display, "designation": []})
            print(f"  + {code}  {display}")
            added += 1
    return added


def main(verify_only: bool = False) -> None:
    kg = KnowledgeGraphClient()
    try:
        vs = _load_raw(kg, VS_ID)
        current = sum(len(i.get("concept", [])) for i in vs.get("compose", {}).get("include", []))
        print(f"{VS_ID}: currently {current} concept(s)\n")

        if verify_only:
            codes = {
                str(c["code"])
                for inc in vs.get("compose", {}).get("include", [])
                for c in inc.get("concept", [])
            }
            print("Status of new concepts:")
            for code, display in NEW_CONCEPTS:
                status = "OK" if code in codes else "MISSING"
                print(f"  [{status}] {code}  {display}")
            return

        n_added = _add_concepts(vs, NEW_CONCEPTS)
        if n_added == 0:
            print("Nothing to add — all concepts already present.")
            return

        _upsert_valueset_flat(VS_ID, vs)
        new_total = current + n_added
        print(f"\nSaved. {VS_ID} now has {new_total} concept(s) (+{n_added}).")
    finally:
        kg.close()


if __name__ == "__main__":
    verify_only = "--verify-only" in sys.argv
    main(verify_only=verify_only)
