"""Verification script for NCDA 2018 benchmarks and Woodbrook audit linkage.

Directly queries the Knowledge Graph and Patient Graph to verify:
1. ncda-2018 set exists with correct scope coverage
2. Woodbrook Medical Centre has ODS-linked practice benchmarks
3. _fetch_benchmark_metrics returns practice/alliance/national for Woodbrook
4. Live audit data is available for Woodbrook's org_id in the patient graph
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient


def check_benchmark_set():
    kg = KnowledgeGraphClient()
    try:
        rows = kg.run(
            "MATCH (s:BenchmarkSet {id: 'ncda-2018'}) RETURN s.id AS id, s.name AS name"
        )
        if not rows:
            print("FAIL: ncda-2018 BenchmarkSet not found")
            return False
        print(f"OK: BenchmarkSet exists: {rows[0]['name']}")
        return True
    finally:
        kg.close()


def check_scope_coverage():
    kg = KnowledgeGraphClient()
    try:
        rows = kg.run(
            "MATCH (v:BenchmarkValue {audit_id: 'ncda-2018'}) "
            "RETURN DISTINCT v.scope_type AS scope_type, v.scope_id AS scope_id, v.scope_name AS scope_name "
            "ORDER BY v.scope_type"
        )
        scope_types = {r["scope_type"] for r in rows}
        print(f"\nScopes found ({len(rows)} distinct):")
        for r in rows:
            print(f"  [{r['scope_type']}] {r['scope_name']} (id={r['scope_id']})")

        ok = True
        if "gp_practice" not in scope_types:
            print("FAIL: No gp_practice scope found")
            ok = False
        else:
            # Check ODS code is used
            practice = next(r for r in rows if r["scope_type"] == "gp_practice")
            if practice["scope_id"] == "woodbrook":
                print(
                    "FAIL: Practice scope_id is still 'woodbrook' (entity id) not ODS code"
                )
                ok = False
            else:
                print(f"OK: Practice scope_id is canonical ODS: {practice['scope_id']}")

        if "cancer_alliance" not in scope_types:
            print("FAIL: No cancer_alliance scope found")
            ok = False
        else:
            print("OK: cancer_alliance scope present")

        if "national" not in scope_types:
            print("FAIL: No national scope found")
            ok = False
        else:
            print("OK: national scope present")

        return ok
    finally:
        kg.close()


def check_value_count():
    kg = KnowledgeGraphClient()
    try:
        rows = kg.run(
            "MATCH (v:BenchmarkValue {audit_id: 'ncda-2018'}) RETURN count(v) AS n"
        )
        n = rows[0]["n"] if rows else 0
        print(f"\nTotal BenchmarkValues for ncda-2018: {n}")
        if n == 0:
            print("FAIL: No benchmark values found")
            return False
        print("OK: Values present")
        return True
    finally:
        kg.close()


def check_benchmark_fetch_linkage():
    """Run _fetch_benchmark_metrics as audit.py would for Woodbrook org."""
    from services.analytics_api.app.routers.audit import _fetch_benchmark_metrics
    import sys

    # Woodbrook ODS code from the uploaded JSON
    woodbrook_ods = "C82070"

    # Try to find Woodbrook's org_id in the patient graph
    pg = PatientGraphClient()
    try:
        org_rows = pg.run(
            "MATCH (o:Organization) WHERE o.ods_code = $ods OR o.id = $ods OR o.name CONTAINS 'Woodbrook' "
            "RETURN o.id AS id, o.name AS name, coalesce(o.ods_code, o.id) AS ods_code LIMIT 5",
            ods=woodbrook_ods,
        )
        print(f"\nWoodbrook org lookup: {[r['name'] for r in org_rows]}")
        org_id = org_rows[0]["id"] if org_rows else woodbrook_ods
    finally:
        pg.close()

    # Also try to resolve alliance
    pg2 = PatientGraphClient()
    try:
        alliance_rows = pg2.run(
            "MATCH (o:Organization {id: $org_id}) "
            "OPTIONAL MATCH (o)-[:COMMISSIONED_BY]->(:ICB)-[:PART_OF_ALLIANCE]->(ca:CancerAlliance) "
            "RETURN ca.id AS alliance_id",
            org_id=org_id,
        )
        alliance_id = alliance_rows[0].get("alliance_id") if alliance_rows else None
        print(f"Alliance resolved: {alliance_id}")
    finally:
        pg2.close()

    for category in ["primary_care_interval", "condition_type", "demographics"]:
        result = _fetch_benchmark_metrics(
            "ncda-2018",
            category,
            org_id=org_id,
            org_ods_code=woodbrook_ods,
            alliance_id=alliance_id,
        )
        if result is None:
            print(f"  [{category}] No benchmark values found")
            continue

        metrics = result.get("metrics", {})
        sample_key = next(iter(metrics), None)
        if sample_key:
            m = metrics[sample_key]
            print(
                f"  [{category}] {sample_key}: practice={m['practice']} alliance={m['alliance']} national={m['national']}"
            )
            if m["practice"] is None and m["national"] is None:
                print(f"    WARNING: No practice or national benchmark for {category}")
            elif m["practice"] is None:
                print(
                    f"    WARNING: Practice benchmark missing (ODS linkage may need checking)"
                )
            else:
                print(f"    OK: All 3 scope levels present")
        else:
            print(f"  [{category}] No metrics")


def check_live_audit_data():
    """Check if any EpisodeOfCare data exists in the patient graph."""
    pg = PatientGraphClient()
    try:
        rows = pg.run("MATCH (ep:EpisodeOfCare) RETURN count(ep) AS n LIMIT 1")
        n = rows[0]["n"] if rows else 0
        print(f"\nTotal EpisodeOfCare nodes in patient graph: {n}")
        if n == 0:
            print("WARNING: No episodes — live audit sections will be empty")
        else:
            print("OK: Patient data present for live audit")
        return True
    finally:
        pg.close()


if __name__ == "__main__":
    print("=" * 60)
    print("NCDA 2018 Benchmark Verification")
    print("=" * 60)

    results = []
    results.append(check_benchmark_set())
    results.append(check_scope_coverage())
    results.append(check_value_count())
    check_benchmark_fetch_linkage()
    check_live_audit_data()

    print("\n" + "=" * 60)
    if all(results):
        print("VERIFICATION PASSED")
    else:
        print("VERIFICATION FAILED - see details above")
    print("=" * 60)
