"""
Fix surface form tie-breaking issues and emphysema mapping.

1. Remove old GCL/conflicting edges that are now superseded by better audit-fix edges.
2. Fix emphysema: currently maps to 'Toxic emphysema' - find a better concept.
3. Report LOW_CONFIDENCE_MANUAL forms (manual forms with conf < 1.0).
"""

import os, sys, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()
from neo4j import GraphDatabase

kg_uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI")
kg_user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
kg_pass = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev")

_UPSERT = """
MATCH (c:Concept {id: $concept_id}) WHERE c.active = true
MERGE (sf:SurfaceForm {normalized: $normalized})
ON CREATE SET sf.form = $form, sf.source = 'manual',
              sf.status = 'active', sf.created_at = datetime()
MERGE (sf)-[m:MAPS_TO]->(c)
ON CREATE SET m.created_at = datetime(), m.approved_at = datetime()
SET m.confidence = 1.0, m.provenance = 'audit-fix-2026-04'
RETURN sf.normalized AS n, c.id AS id, c.fsn AS fsn
"""

driver = GraphDatabase.driver(kg_uri, auth=(kg_user, kg_pass))

with driver.session() as s:
    # -------------------------------------------------------------------
    # 1. Remove superseded edges where a better audit-fix edge now exists.
    #    Only delete old GCL edges when a conf=1.0 audit-fix edge is present.
    # -------------------------------------------------------------------
    # Surfaces where the old GCL target should be removed
    SUPERSEDE = [
        # (normalized_form, bad_concept_id)
        (
            "rectal bleeding",
            "12063002",
        ),  # Old: Rectal hemorrhage; new: Hematochezia 405729008
        ("pr bleeding", "12063002"),
    ]

    print("=== Removing superseded edges ===")
    for norm, bad_cid in SUPERSEDE:
        # Only delete if there's at least one other good edge still present
        check = s.run(
            """
            MATCH (sf:SurfaceForm {normalized: $normalized})-[m:MAPS_TO]->(c:Concept)
            WHERE c.id <> $bad_cid AND m.confidence >= 1.0
            RETURN count(m) AS n
        """,
            normalized=norm,
            bad_cid=bad_cid,
        ).data()
        if check and check[0]["n"] >= 1:
            r = s.run(
                """
                MATCH (sf:SurfaceForm {normalized: $normalized})-[m:MAPS_TO]->(c:Concept {id: $bad_cid})
                DELETE m RETURN count(m) AS deleted
            """,
                normalized=norm,
                bad_cid=bad_cid,
            ).data()
            print(f"  Deleted {r[0]['deleted']} edge(s): {norm!r} -> {bad_cid}")
        else:
            print(f"  Skipped {norm!r} -> {bad_cid} (no backup edge)")

    # -------------------------------------------------------------------
    # 2. Fix emphysema mapping
    # -------------------------------------------------------------------
    print("\n=== Emphysema ===")
    # Check what emphysema currently maps to
    current = s.run("""
        MATCH (sf:SurfaceForm)-[m:MAPS_TO]->(c:Concept)
        WHERE toLower(sf.form) = 'emphysema'
        RETURN sf.normalized, c.id, c.fsn, m.confidence, m.provenance
    """).data()
    print(f"Current emphysema mapping: {current}")

    # Search for the best emphysema concept
    results = s.run("""
        CALL db.index.fulltext.queryNodes('term_fulltext', 'pulmonary emphysema') YIELD node, score
        MATCH (node)-[:DESCRIBES]->(c:Concept)
        WHERE c.active = true AND c.semantic_tag = 'disorder'
        RETURN c.id AS id, c.fsn AS fsn, score ORDER BY score DESC LIMIT 5
    """).data()
    print("Pulmonary emphysema search:")
    for r in results:
        print(f"  {r['id']} | {r['fsn']} score={r['score']:.2f}")

    # Upsert correct emphysema if found
    if results:
        best = results[0]
        cid = best["id"]
        norm = "emphysema"
        r2 = s.run(_UPSERT, normalized=norm, form="Emphysema", concept_id=cid).data()
        print(f"  Upserted emphysema -> {cid} | {best['fsn']}: {bool(r2)}")
        # Also map variants
        for form in ["pulmonary emphysema", "COPD with emphysema", "emphysematous"]:
            norm2 = " ".join(re.findall(r"[a-z0-9]+", form.lower()))
            s.run(_UPSERT, normalized=norm2, form=form, concept_id=cid).data()
            print(f"  Upserted {form!r} -> {cid}")

    # -------------------------------------------------------------------
    # 3. Check LOW_CONFIDENCE_MANUAL forms
    # -------------------------------------------------------------------
    print("\n=== LOW_CONFIDENCE_MANUAL forms (manual, conf < 1.0) ===")
    low_conf = s.run("""
        MATCH (sf:SurfaceForm)-[m:MAPS_TO]->(c:Concept)
        WHERE m.provenance IN ['manual', 'audit-fix', 'audit-fix-2026-04',
                               'audit-fix-mh-orphan-2026-04', 'audit-fix-spot-check-2026-04',
                               'audit-fix-abbrev-2026-04']
          AND m.confidence < 1.0
        RETURN sf.form AS form, c.id AS cid, c.fsn AS fsn,
               m.confidence AS conf, m.provenance AS prov
        ORDER BY m.confidence ASC
        LIMIT 30
    """).data()
    print(f"Manual forms with conf<1.0: {len(low_conf)}")
    for r in low_conf:
        print(
            f"  {r['form']!r} -> {r['cid']} | {r['fsn']} conf={r['conf']} [{r['prov']}]"
        )

    # Count all manual surface forms
    counts = s.run("""
        MATCH (sf:SurfaceForm)-[m:MAPS_TO]->(c:Concept)
        WHERE m.provenance IN ['manual', 'audit-fix', 'audit-fix-2026-04',
                               'audit-fix-mh-orphan-2026-04', 'audit-fix-spot-check-2026-04',
                               'audit-fix-abbrev-2026-04']
        RETURN
          count(m) AS total,
          sum(CASE WHEN m.confidence >= 1.0 THEN 1 ELSE 0 END) AS high_conf,
          sum(CASE WHEN m.confidence < 1.0 THEN 1 ELSE 0 END) AS low_conf
    """).data()
    if counts:
        c = counts[0]
        print(
            f"\nAudit-fix surface forms: total={c['total']} high_conf={c['high_conf']} low_conf={c['low_conf']}"
        )

    # Check old 'manual' provenance forms
    old_manual = s.run("""
        MATCH (sf:SurfaceForm)-[m:MAPS_TO]->(c:Concept)
        WHERE m.provenance = 'manual' AND m.confidence < 1.0
        RETURN count(m) AS n
    """).data()
    print(
        f"Old 'manual' provenance forms with conf<1.0: {old_manual[0]['n'] if old_manual else 0}"
    )

    # Sample of all manual surface forms with any provenance
    all_manual = s.run("""
        MATCH (sf:SurfaceForm)-[m:MAPS_TO]->(c:Concept)
        WHERE m.provenance = 'manual' AND m.confidence < 1.0
        RETURN sf.form AS form, c.id AS cid, c.fsn AS fsn,
               m.confidence AS conf
        ORDER BY m.confidence ASC LIMIT 20
    """).data()
    print("\nSample old manual conf<1.0:")
    for r in all_manual:
        print(f"  {r['form']!r} -> {r['cid']} | {r['fsn']} conf={r['conf']}")

driver.close()
