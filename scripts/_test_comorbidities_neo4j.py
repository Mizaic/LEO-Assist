"""Diagnose why comorbidity DOCUMENTS aren't matching concept IDs.

Usage:
    python -m scripts._test_comorbidities_neo4j
"""
from __future__ import annotations

import json
from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient
from libs.cypher.terminology_queries import DESCENDANTS_TEMPLATE

IS_A_DEPTH = 3
IS_A_LIMIT = 500


def section(title: str) -> None:
    print()
    print("=" * 65)
    print(title)
    print("=" * 65)


# ── Load subdomain concept IDs ────────────────────────────────
kg = KnowledgeGraphClient()
try:
    rows = kg.run(
        "MATCH (v:ValueSet {id: 'ncda-comorbidities'}) RETURN v.rawJson AS raw"
    )
    vs = json.loads(rows[0]["raw"])
    concept_entries = []
    for inc in (vs.get("compose") or {}).get("include") or []:
        for c in inc.get("concept") or []:
            concept_entries.append(c)
finally:
    kg.close()

# Build flat id list (top only for quick checks)
top_ids = [c["code"] for c in concept_entries]
print(f"Top-level concept codes: {top_ids}")

# ── Step A: inspect actual comorbidity DOCUMENTS ──────────────
section("A — What do comorbidity DOCUMENTS actually point to?")
pg = PatientGraphClient()
try:
    # Labels of target nodes
    label_rows = pg.run(
        "MATCH ()-[r:DOCUMENTS]->(d) "
        "WHERE r.domain = 'comorbidities' "
        "RETURN labels(d) AS lbl, count(*) AS n "
        "ORDER BY n DESC LIMIT 10"
    )
    print("  Node labels targeted by comorbidity DOCUMENTS:")
    for r in label_rows:
        print(f"    labels={r['lbl']}  n={r['n']}")

    # Sample a few comorbidity DOCUMENTS to see the properties
    sample_rows = pg.run(
        "MATCH (enc:Encounter)-[r:DOCUMENTS]->(d) "
        "WHERE r.domain = 'comorbidities' "
        "RETURN labels(d) AS lbl, d.conceptId AS concept_id, "
        "       d.name AS name, r.domain AS domain, r.context AS context "
        "LIMIT 20"
    )
    print(f"\n  Sample comorbidity DOCUMENTS (first 20):")
    print(f"  {'labels':<30} {'conceptId':<15} {'name':<40}")
    print(f"  {'-'*30} {'-'*15} {'-'*40}")
    for r in sample_rows:
        print(f"  {str(r.get('lbl')):<30} {str(r.get('concept_id') or ''):<15} "
              f"{str(r.get('name') or ''):<40}")

    # Check whether any top-level concept IDs appear without label filter
    section("B — Do our concept IDs appear at all? (no label filter)")
    any_match = pg.run(
        "MATCH ()-[r:DOCUMENTS]->(d) "
        "WHERE r.domain = 'comorbidities' AND d.conceptId IN $ids "
        "RETURN d.conceptId AS concept_id, labels(d) AS lbl, count(*) AS n "
        "ORDER BY n DESC LIMIT 20",
        ids=top_ids,
    )
    if any_match:
        print("  Matches on top-level concept IDs (no label filter):")
        for r in any_match:
            print(f"    {r['concept_id']}  labels={r['lbl']}  n={r['n']}")
    else:
        print("  No matches on top-level IDs either.")

    # Check conceptId format — could it be an integer?
    section("C — conceptId type check")
    type_rows = pg.run(
        "MATCH ()-[r:DOCUMENTS]->(d) "
        "WHERE r.domain = 'comorbidities' "
        "RETURN d.conceptId AS cid, "
        "       toString(d.conceptId) AS cid_str, "
        "       toInteger(d.conceptId) AS cid_int "
        "LIMIT 5"
    )
    print("  Sample conceptId values from comorbidity DOCUMENTS:")
    for r in type_rows:
        print(f"    raw={r.get('cid')!r}  as_str={r.get('cid_str')!r}  as_int={r.get('cid_int')!r}")

    # Try matching as integers
    section("D — Retry match with integer IDs")
    int_ids = [int(i) for i in top_ids if i.isdigit()]
    int_match = pg.run(
        "MATCH ()-[r:DOCUMENTS]->(d) "
        "WHERE r.domain = 'comorbidities' AND d.conceptId IN $ids "
        "RETURN d.conceptId AS concept_id, labels(d) AS lbl, count(*) AS n "
        "ORDER BY n DESC LIMIT 20",
        ids=int_ids,
    )
    if int_match:
        print("  Matches using INTEGER concept IDs:")
        for r in int_match:
            print(f"    {r['concept_id']}  labels={r['lbl']}  n={r['n']}")
    else:
        print("  Still no matches with integer IDs.")

    # Try expansion of IS_A with integer IDs  
    section("E — Try expanding via IS_A using string IDs (sample Hypertension)")
    htn_id = "38341003"
    kg2 = KnowledgeGraphClient()
    try:
        child_rows = kg2.run(
            DESCENDANTS_TEMPLATE.format(depth=3),
            concept_id=htn_id,
            semantic_tag=None,
            limit=50,
        )
        child_ids = [str(r["snomed_concept_id"]) for r in (child_rows or [])]
    finally:
        kg2.close()

    print(f"  Hypertension descendants ({len(child_ids)}): {child_ids[:10]}")

    # Search comorbidities using these child IDs
    htn_match = pg.run(
        "MATCH ()-[r:DOCUMENTS]->(d) "
        "WHERE r.domain = 'comorbidities' "
        "  AND (d.conceptId IN $str_ids OR d.conceptId IN $int_ids) "
        "RETURN d.conceptId AS cid, labels(d) AS lbl, count(*) AS n "
        "ORDER BY n DESC LIMIT 20",
        str_ids=[htn_id] + child_ids,
        int_ids=[int(i) for i in ([htn_id] + child_ids) if i.isdigit()],
    )
    if htn_match:
        print(f"  Hypertension group matches (str + int):")
        for r in htn_match:
            print(f"    {r['cid']}  labels={r['lbl']}  n={r['n']}")
    else:
        print(f"  No matches for hypertension IS_A expansion.")

    # Final: what concept IDs ARE used in comorbidity DOCUMENTS?
    section("F — What concept IDs appear in comorbidity DOCUMENTS? (sample 30)")
    used_ids = pg.run(
        "MATCH ()-[r:DOCUMENTS]->(d) "
        "WHERE r.domain = 'comorbidities' "
        "RETURN DISTINCT d.conceptId AS cid, d.name AS name "
        "LIMIT 30"
    )
    print("  Concept IDs actually in comorbidity DOCUMENTS:")
    for r in used_ids:
        print(f"    conceptId={r.get('cid')!r:20s}  name={r.get('name')!r}")

finally:
    pg.close()

print("\nDiagnosis complete.")
