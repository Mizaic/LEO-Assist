"""Check Neo4j terminology graph state."""
import sys
import os
from dotenv import load_dotenv
from neo4j import GraphDatabase

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
load_dotenv("secrets/.env")

uri = os.getenv("NEO4J_URI")
user = os.getenv("NEO4J_USER")
pwd = os.getenv("NEO4J_PASSWORD")

driver = GraphDatabase.driver(uri, auth=(user, pwd))
with driver.session() as session:
    result = session.run("CALL db.labels() YIELD label RETURN label ORDER BY label")
    labels = [r["label"] for r in result]
    print("Node labels:", labels)

    result = session.run("SHOW FULLTEXT INDEXES")
    indexes = [dict(r) for r in result]
    for idx in indexes:
        name = idx.get("name", "?")
        labs = idx.get("labelsOrTypes", [])
        props = idx.get("properties", [])
        print(f"Fulltext index: {name}, labels: {labs}, props: {props}")

    for label in ["Concept", "Description", "UmlsConcept", "ReadCode", "Icd10Code", "SurfaceForm"]:
        result = session.run(f"MATCH (n:{label}) RETURN count(n) as cnt")
        cnt = result.single()["cnt"]
        print(f"  {label}: {cnt}")

    result = session.run("""
        MATCH (d:Description)-[:DESCRIBES]->(c:Concept)
        OPTIONAL MATCH (c)-[:SAME_AS]-(u:UmlsConcept)
        RETURN c.id AS concept_id, d.term AS term, u.cui AS cui
        LIMIT 5
    """)
    print("\nSample concepts with descriptions:")
    for r in result:
        print(f"  concept={r['concept_id']}, term={r['term']}, cui={r['cui']}")

    result = session.run("""
        MATCH (d:Description)-[:DESCRIBES]->(c:Concept)
        RETURN count(d) as desc_count, count(DISTINCT c) as concept_count
    """)
    rec = result.single()
    print(f"\nDescriptions->Concepts: {rec['desc_count']} descriptions, {rec['concept_count']} concepts")

    result = session.run("""
        MATCH (sf:SurfaceForm)-[:SURFACE_FORM_OF]->(c:Concept)
        RETURN count(sf) as sf_count
    """)
    print(f"SurfaceForms: {result.single()['sf_count']}")

driver.close()
