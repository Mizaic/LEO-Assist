"""Diagnose OCD abbreviation and bladder cancer fast-track issues."""

import os, sys
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
driver = GraphDatabase.driver(kg_uri, auth=(kg_user, kg_pass))

with driver.session() as s:
    # OCD surface form mappings
    r1 = s.run("""
        MATCH (sf:SurfaceForm {normalized: 'ocd'})-[m:MAPS_TO]->(c:Concept)
        RETURN c.id AS id, c.fsn AS fsn, m.confidence AS conf, m.provenance AS prov
        ORDER BY m.confidence DESC
    """).data()
    print("OCD surface form mappings:")
    for r in r1:
        print(f"  {r['id']} | {r['fsn']} conf={r['conf']} [{r['prov']}]")

    # Does 191736004 exist?
    r2 = s.run(
        "MATCH (c:Concept {id: '191736004'}) RETURN c.id AS id, c.fsn AS fsn, c.active AS active"
    ).data()
    print(f"\nConcept 191736004: {r2}")

    # What Term nodes use 'ocd' as normalized_form?
    r3 = s.run("""
        MATCH (t:Term {normalized_form: 'ocd'})-[:DESCRIBES]->(c:Concept)
        WHERE c.active = true
        RETURN t.normalized_form AS norm, c.id AS id, c.fsn AS fsn
    """).data()
    print(f"\nTerm nodes with normalized='ocd':")
    for r in r3:
        print(f"  {r['id']} | {r['fsn']}")

    # Find OCD disorder via search
    r4 = s.run("""
        CALL db.index.fulltext.queryNodes('term_fulltext', 'obsessive compulsive disorder') YIELD node, score
        MATCH (node)-[:DESCRIBES]->(c:Concept)
        WHERE c.active = true AND c.semantic_tag = 'disorder'
        RETURN c.id AS id, c.fsn AS fsn, score
        ORDER BY score DESC LIMIT 3
    """).data()
    print(f"\nOCD full-text search:")
    for r in r4:
        print(f"  {r['id']} | {r['fsn']} score={r['score']:.2f}")

    # Bladder cancer fast-track forms
    r5 = s.run("""
        MATCH (sf:SurfaceForm)-[m:MAPS_TO]->(c:Concept)
        WHERE toLower(sf.form) CONTAINS 'bladder' OR toLower(sf.form) CONTAINS 'urological'
        RETURN sf.form AS form, c.id AS cid, c.fsn AS fsn, m.confidence AS conf
        ORDER BY sf.form
    """).data()
    print(f"\nBladder/urological surface forms:")
    for r in r5:
        print(f"  {r['form']!r} -> {r['cid']} | {r['fsn']} conf={r['conf']}")

    # What concept ID is the correct bladder fast-track?
    r6 = s.run("""
        CALL db.index.fulltext.queryNodes('term_fulltext', 'fast track referral suspected bladder') YIELD node, score
        MATCH (node)-[:DESCRIBES]->(c:Concept)
        WHERE c.active = true
        RETURN c.id AS id, c.fsn AS fsn, score
        ORDER BY score DESC LIMIT 5
    """).data()
    print(f"\nBladder fast-track search:")
    for r in r6:
        print(f"  {r['id']} | {r['fsn']} score={r['score']:.2f}")

driver.close()
