"""Compare text search vs concept match for 'Seen in fast track' encounters.

Text search: encounters whose note/text contains 'seen in fast track' (case-insensitive).
Concept match: patients with any specialist_visit concept from the cancer domain (IS_A expanded).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from libs.keyvault.loader import load_keyvault_secrets
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
load_keyvault_secrets()

from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient

DOMAIN_ID = "cancer_audit"

_Q_DOMAIN_SPECIALIST_VS = (
    "MATCH (d:AuditDomain {id: $domain_id})-[:HAS_SUBDOMAIN]->(v:ValueSet) "
    "WHERE v.milestoneType = 'specialist_visit' "
    "RETURN v.rawJson AS raw_json"
)

_Q_ISA = (
    "MATCH (ancestor:Concept)<-[:IS_A*1..5]-(d:Concept) "
    "WHERE ancestor.id IN $ids AND d.active = true "
    "RETURN d.id AS child_id"
)

# Text search in encounter note fields
_Q_TEXT_SEARCH = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toLower(coalesce(e.text, '') + ' ' +
              coalesce(e.note, '') + ' ' +
              coalesce(e.description, '') + ' ' +
              coalesce(e.title, '')) CONTAINS 'seen in fast track'
RETURN
    toString(p.id)   AS patient_id,
    toString(e.id)   AS encounter_id,
    toString(e.date) AS date,
    coalesce(e.text, e.note, e.description, e.title, '') AS matched_text
ORDER BY patient_id, date
"""

# What concept properties exist on encounters
_Q_ENCOUNTER_PROPS = "MATCH (e:Encounter) RETURN keys(e) AS props LIMIT 1"

# Concepts coded on encounters that text-matched but concept-missed
_Q_CONCEPTS_FOR_ENCOUNTER = """
MATCH (e:Encounter {id: $eid})-[:DOCUMENTS]->(c)
RETURN c.conceptId AS cid, c.name AS name, labels(c) AS lbl
"""

# All concept nodes with "fast track" in name
_Q_FASTTRACK_CONCEPTS_IN_PATIENT_GRAPH = """
MATCH (c)
WHERE toLower(coalesce(c.name,'')) CONTAINS 'seen in fast track'
   OR toLower(coalesce(c.name,'')) CONTAINS 'seen at fast track'
RETURN DISTINCT c.conceptId AS cid, c.name AS name, labels(c) AS lbl
ORDER BY name
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
    # -- Load domain specialist concept IDs + IS_A expansion --
    kg = KnowledgeGraphClient()
    try:
        vs_rows = kg.run(_Q_DOMAIN_SPECIALIST_VS, domain_id=DOMAIN_ID)
        parent_ids = [code for row in vs_rows for code in _extract_ids(row["raw_json"])]
        print(f"Specialist subdomain parents: {parent_ids}")
        isa_rows = kg.run(_Q_ISA, ids=parent_ids) if parent_ids else []
        covered_ids = set(parent_ids) | {r["child_id"] for r in isa_rows}
        print(f"After IS_A expansion: {len(covered_ids)} concept IDs\n")
    finally:
        kg.close()

    pg = PatientGraphClient()
    try:
        # -- Concept-matched patients --
        concept_rows = pg.run(
            "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[:DOCUMENTS]->(c) "
            "WHERE c.conceptId IN $ids "
            "RETURN DISTINCT toString(p.id) AS pid, "
            "       c.conceptId AS cid, c.name AS cname",
            ids=list(covered_ids),
        )
        concept_patients: dict[str, list] = {}
        for r in concept_rows:
            concept_patients.setdefault(r["pid"], []).append(f"{r['cid']} {r['cname']}")

        # -- Check what properties encounters have --
        props = pg.run(_Q_ENCOUNTER_PROPS)
        enc_props = props[0]["props"] if props else []
        text_fields = [p for p in enc_props if p in ("text", "note", "description", "title", "content", "narrative")]
        print(f"Encounter text properties available: {text_fields}\n")

        # -- Text search --
        text_rows = pg.run(_Q_TEXT_SEARCH)
        text_patients: dict[str, list] = {}
        for r in text_rows:
            snippet = r["matched_text"][:120].replace("\n", " ")
            text_patients.setdefault(r["patient_id"], []).append(
                f"{r['date']}  {snippet}"
            )

        # -- All "seen in fast track" concept nodes in patient graph --
        ft_concepts = pg.run(_Q_FASTTRACK_CONCEPTS_IN_PATIENT_GRAPH)

        print("=" * 70)
        print("'SEEN IN FAST TRACK' CONCEPTS IN PATIENT GRAPH (all)")
        print("=" * 70)
        for r in ft_concepts:
            in_domain = str(r["cid"]) in covered_ids
            status = "OK " if in_domain else "GAP"
            pat_count = pg.run(
                "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(:Encounter)-[:DOCUMENTS]->(c) "
                "WHERE c.conceptId = $cid RETURN count(DISTINCT p) AS n",
                cid=str(r["cid"]),
            )[0]["n"]
            print(f"  [{status}] {str(r['cid']):20s}  {pat_count:3d} patients  {r['name']}")

        print()
        print("=" * 70)
        print("COMPARISON: text search vs concept match")
        print("=" * 70)
        text_set    = set(text_patients.keys())
        concept_set = set(concept_patients.keys())
        both        = text_set & concept_set
        text_only   = text_set - concept_set
        concept_only = concept_set - text_set

        print(f"  Text 'seen in fast track':   {len(text_set)} patients")
        print(f"  Concept match (domain IS_A): {len(concept_set)} patients")
        print(f"  Both:                        {len(both)}")
        print(f"  Text only (concept MISSED):  {len(text_only)}")
        print(f"  Concept only (no text):      {len(concept_only)}")

        if text_only:
            print(f"\n  Patients found by TEXT but NOT by concept ({len(text_only)}):")
            for pid in sorted(text_only):
                print(f"    {pid}")
                for snippet in text_patients[pid][:3]:
                    print(f"      {snippet}")

        if concept_only:
            print(f"\n  Patients found by CONCEPT but not text ({len(concept_only)}):")
            for pid in sorted(concept_only):
                print(f"    {pid}  concepts: {concept_patients[pid]}")

        if not text_set:
            print("\n  (No encounters had 'seen in fast track' in their text fields)")
            print(f"  Encounter text properties searched: {text_fields}")

        print("=" * 70)
    finally:
        pg.close()


if __name__ == "__main__":
    main()
