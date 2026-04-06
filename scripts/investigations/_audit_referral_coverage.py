"""Find all referral-like concepts in the patient graph not covered by the domain.

Searches for concepts whose name suggests a cancer referral but that fall
outside the IS_A expansion of the referral subdomain's parent concept.
Also reports how many patients they affect.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from libs.keyvault.loader import load_keyvault_secrets
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
load_keyvault_secrets()

import json
from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient

DOMAIN_ID = "cancer_audit"

_Q_DOMAIN_REFERRAL_VS = (
    "MATCH (d:AuditDomain {id: $domain_id})-[:HAS_SUBDOMAIN]->(v:ValueSet) "
    "WHERE v.milestoneType = 'referral' "
    "RETURN v.rawJson AS raw_json"
)

_Q_ISA = (
    "MATCH (ancestor:Concept)<-[:IS_A*1..5]-(d:Concept) "
    "WHERE ancestor.id IN $ids AND d.active = true "
    "RETURN d.id AS child_id"
)

# All DOCUMENTS concepts in the patient graph grouped by name/ID
_Q_ALL_CODED_CONCEPTS = """
MATCH (e:Encounter)-[:DOCUMENTS]->(c)
WHERE e IS NOT NULL
RETURN
    c.conceptId        AS concept_id,
    c.name             AS name,
    labels(c)          AS labels,
    count(DISTINCT e)  AS encounter_count,
    count(DISTINCT ((:Patient)-[:HAS_ENCOUNTER]->(e))) AS patient_count
ORDER BY patient_count DESC, encounter_count DESC
"""

# Referral-like concepts by name pattern
_Q_REFERRAL_LIKE = """
MATCH (e:Encounter)-[:DOCUMENTS]->(c)
WHERE toLower(c.name) CONTAINS 'referral'
   OR toLower(c.name) CONTAINS 'refer '
   OR toLower(c.name) CONTAINS '2ww'
   OR toLower(c.name) CONTAINS 'two week'
   OR toLower(c.name) CONTAINS 'fast track'
   OR toLower(c.name) CONTAINS 'suspected cancer'
   OR toLower(c.name) CONTAINS 'urgent cancer'
RETURN
    c.conceptId                    AS concept_id,
    c.name                         AS name,
    labels(c)                      AS labels,
    count(DISTINCT e)              AS encounter_count
ORDER BY encounter_count DESC
"""


def _extract_ids(raw_json) -> list[str]:
    try:
        vs = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
    except Exception:
        return []
    return [
        c.get("code", "")
        for inc in (vs.get("compose") or {}).get("include") or []
        for c in inc.get("concept") or []
        if c.get("code")
    ]


def main() -> None:
    # -- Load referral subdomain parent IDs and expand IS_A --
    kg = KnowledgeGraphClient()
    try:
        vs_rows = kg.run(_Q_DOMAIN_REFERRAL_VS, domain_id=DOMAIN_ID)
        parent_ids: list[str] = []
        for row in vs_rows:
            parent_ids.extend(_extract_ids(row["raw_json"]))

        print(f"Referral subdomain parent concepts: {parent_ids}")

        if parent_ids:
            isa_rows = kg.run(_Q_ISA, ids=parent_ids)
            covered_ids = set(parent_ids) | {r["child_id"] for r in (isa_rows or [])}
        else:
            covered_ids = set()

        print(f"Covered by IS_A expansion: {len(covered_ids)} concept IDs\n")
    finally:
        kg.close()

    # -- Scan patient graph for referral-like concepts --
    pg = PatientGraphClient()
    try:
        total_patients = pg.run(
            "MATCH (p:Patient) RETURN count(p) AS n"
        )[0]["n"]

        print(f"Total patients: {total_patients}\n")
        print("=" * 70)
        print("REFERRAL-LIKE CONCEPTS IN PATIENT GRAPH")
        print("(name contains: referral / 2ww / fast track / suspected cancer)")
        print("=" * 70)

        ref_rows = pg.run(_Q_REFERRAL_LIKE)
        covered_count = 0
        missing_count = 0

        for row in ref_rows:
            cid = str(row["concept_id"] or "")
            covered = cid in covered_ids
            status = "OK " if covered else "MISSING"
            if covered:
                covered_count += 1
            else:
                missing_count += 1
            # Count unique patients for this concept
            pat_rows = pg.run(
                "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[:DOCUMENTS]->(c) "
                "WHERE c.conceptId = $cid "
                "RETURN count(DISTINCT p) AS n",
                cid=cid,
            )
            n_patients = pat_rows[0]["n"] if pat_rows else 0
            print(
                f"  [{status}] {cid:20s}  {n_patients:3d} patients  {row['name']}"
            )

        print()
        print(f"  Covered by domain IS_A:  {covered_count}")
        print(f"  NOT covered (missing):   {missing_count}")

        if missing_count:
            print()
            print("MISSING concepts - patients affected:")
            for row in ref_rows:
                cid = str(row["concept_id"] or "")
                if cid not in covered_ids:
                    pat_rows = pg.run(
                        "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)"
                        "-[:DOCUMENTS]->(c) "
                        "WHERE c.conceptId = $cid "
                        "RETURN DISTINCT toString(p.id) AS pid",
                        cid=cid,
                    )
                    pids = [r["pid"] for r in pat_rows]
                    print(f"  {cid}  {row['name']}")
                    print(f"    {len(pids)} patients: {pids}")

        print("=" * 70)
    finally:
        pg.close()


if __name__ == "__main__":
    main()
