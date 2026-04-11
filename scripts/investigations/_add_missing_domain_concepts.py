"""Add two missing concepts to the cancer_audit domain ValueSets.

276341000000107 -> ncda-fast-track-referrals  (referral milestone)
382841000000109 -> ncda-seen-by-specialist    (specialist_visit milestone)

Follows the same rawJson + flat-property update pattern as the domains API.
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

SNOMED_SYSTEM = "http://snomed.info/sct"

ADDITIONS = [
    {
        "vs_id": "ncda-fast-track-referrals",
        "concept_id": "276341000000107",
        "display": "Fast track referral for suspected breast cancer (procedure)",
    },
    {
        "vs_id": "ncda-seen-by-specialist",
        "concept_id": "382841000000109",
        "display": "Seen in fast track suspected urological cancer clinic (finding)",
    },
]


def _load_raw(kg, vs_id: str) -> dict:
    rows = kg.run(
        "MATCH (v:ValueSet {id: $id}) RETURN v.rawJson AS rj",
        id=vs_id,
    )
    if not rows or not rows[0].get("rj"):
        raise RuntimeError(f"ValueSet '{vs_id}' not found or has no rawJson")
    raw = rows[0]["rj"]
    return json.loads(raw) if isinstance(raw, str) else raw


def _add_concept(vs: dict, code: str, display: str) -> bool:
    compose = vs.setdefault("compose", {})
    includes = compose.setdefault("include", [])
    snomed_inc = next((i for i in includes if i.get("system") == SNOMED_SYSTEM), None)
    if not snomed_inc:
        snomed_inc = {"system": SNOMED_SYSTEM, "concept": []}
        includes.append(snomed_inc)
    concepts = snomed_inc.setdefault("concept", [])
    if any(str(c.get("code")) == code for c in concepts):
        print(f"  {code} already present -- skipping")
        return False
    concepts.append({"code": code, "display": display, "designation": []})
    return True


def main() -> None:
    kg = KnowledgeGraphClient()
    try:
        for item in ADDITIONS:
            vs_id = item["vs_id"]
            code = item["concept_id"]
            display = item["display"]
            print(f"\nAdding {code} to {vs_id}...")
            vs = _load_raw(kg, vs_id)
            changed = _add_concept(vs, code, display)
            if changed:
                _upsert_valueset_flat(vs_id, vs)
                print(
                    f"  Saved. ValueSet now has "
                    f"{sum(len(i.get('concept', [])) for i in vs['compose']['include'])} concept(s)"
                )
    finally:
        kg.close()

    # Verify
    print("\nVerifying...")
    kg2 = KnowledgeGraphClient()
    try:
        for item in ADDITIONS:
            row = kg2.run(
                "MATCH (v:ValueSet {id: $id}) RETURN v.rawJson AS rj",
                id=item["vs_id"],
            )
            vs = json.loads(row[0]["rj"]) if row and row[0].get("rj") else {}
            codes = [
                c["code"]
                for inc in vs.get("compose", {}).get("include", [])
                for c in inc.get("concept", [])
            ]
            found = item["concept_id"] in codes
            status = "OK" if found else "MISSING"
            print(f"  [{status}] {item['vs_id']} contains {item['concept_id']}")
    finally:
        kg2.close()


if __name__ == "__main__":
    main()
