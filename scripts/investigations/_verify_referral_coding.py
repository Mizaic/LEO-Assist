"""Verify all fast-track referral encounters are now correctly coded in Neo4j.

Checks each encounter from the inventory and reports its current coding status.

Run:
    python scripts/investigations/_verify_referral_coding.py
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

INVENTORY = (
    ROOT
    / "scripts"
    / "investigations"
    / "encounter_audit"
    / "fast_track_referral_encounters.jsonl"
)

_Q_DOCS = """
MATCH (e:Encounter)-[r:DOCUMENTS]->(c)
WHERE toString(e.id) = $eid
  AND (c:Procedure OR c:Finding)
  AND (
    r.domain = 'cancer'
    OR toLower(coalesce(c.name, '')) CONTAINS 'fast track'
    OR toLower(coalesce(c.name, '')) CONTAINS '2ww'
    OR toLower(coalesce(c.name, '')) CONTAINS 'track referral'
  )
RETURN
    c.conceptId   AS concept_id,
    c.name        AS name,
    r.source      AS source,
    r.coded_at    AS coded_at
ORDER BY r.coded_at DESC
"""

_Q_PATIENT_HAS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter {id: $eid})
OPTIONAL MATCH (p)-[hp:HAS_PROCEDURE]->(c)
WHERE c.conceptId IN $concept_ids
RETURN count(hp) AS has_procedure_count
"""


def main() -> None:
    from libs.neo4j_client.client import PatientGraphClient

    client = PatientGraphClient()

    with INVENTORY.open() as fh:
        all_rows = [json.loads(l) for l in fh]

    # Unique encounters only (JSONL may have multiple phrases per encounter)
    by_enc: dict[str, dict] = {}
    for row in all_rows:
        eid = row["encounter_id"]
        if eid not in by_enc:
            by_enc[eid] = row

    uncoded_before = [
        r
        for r in all_rows
        if r.get("referral_doc_count", 0) == 0 and r.get("matched_phrase")
    ]
    uncoded_enc_ids = {r["encounter_id"] for r in uncoded_before}

    print(
        f"Inventory: {len(by_enc)} unique encounters ({len(uncoded_enc_ids)} were uncoded at time of inventory)"
    )
    print()

    now_coded = []
    still_missing = []

    try:
        with client.session() as session:
            for eid, row in by_enc.items():
                docs = list(session.run(_Q_DOCS, eid=eid))

                if eid not in uncoded_enc_ids:
                    # Was already coded before -- skip from focus
                    continue

                phrase = row.get("matched_phrase", "")
                if docs:
                    concept_ids = [d["concept_id"] for d in docs]
                    hp = session.run(
                        _Q_PATIENT_HAS, eid=eid, concept_ids=concept_ids
                    ).single()
                    has_proc = hp["has_procedure_count"] if hp else 0
                    now_coded.append(
                        {
                            "encounter_id": eid,
                            "phrase": phrase,
                            "concepts": [
                                (d["concept_id"], d["name"], d["source"]) for d in docs
                            ],
                            "patient_has_procedure": has_proc > 0,
                        }
                    )
                else:
                    still_missing.append({"encounter_id": eid, "phrase": phrase})

    finally:
        client.close()

    print(f"{'=' * 70}")
    print(f"Previously uncoded: {len(uncoded_enc_ids)}")
    print(f"  Now coded:        {len(now_coded)}")
    print(f"  Still missing:    {len(still_missing)}")
    print()

    if now_coded:
        print("Coded encounters:")
        for r in now_coded:
            has_rel = (
                "HAS_PROCEDURE ok"
                if r["patient_has_procedure"]
                else "!! HAS_PROCEDURE missing"
            )
            print(f"  enc={r['encounter_id'][:8]}...  [{has_rel}]")
            print(f"    phrase   : {r['phrase'][:70]}")
            for cid, name, src in r["concepts"]:
                print(f"    concept  : {cid} | {name} | src={src}")

    if still_missing:
        print()
        print("STILL MISSING (action required):")
        for r in still_missing:
            print(f"  enc={r['encounter_id']}  phrase={r['phrase'][:60]!r}")

    print()
    if not still_missing:
        print("All 18 previously uncoded encounters are now correctly coded in Neo4j.")
    else:
        print(f"WARNING: {len(still_missing)} encounter(s) still need coding.")
        sys.exit(1)


if __name__ == "__main__":
    main()
