"""Quick check of pipeline progress via Neo4j."""

import os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / "secrets" / ".env")
from neo4j import GraphDatabase

d = GraphDatabase.driver(
    os.getenv("NEO4J_URI"), auth=("neo4j", os.getenv("NEO4J_PASSWORD"))
)
d.verify_connectivity()
s = d.session()

r = s.run(
    "MATCH (t:TrainingLabel) WHERE t.include = true "
    "RETURN count(t) AS total, "
    "  sum(CASE WHEN t.verified_at IS NOT NULL THEN 1 ELSE 0 END) AS verified, "
    "  sum(CASE WHEN t.entities_json IS NOT NULL THEN 1 ELSE 0 END) AS has_entities"
).single()
print(
    f"TrainingLabels: total={r['total']}, verified={r['verified']}, has_entities={r['has_entities']}"
)

r2 = s.run(
    "MATCH (cr:CodingReview)-[:REVIEWS_CODING]->(t:TrainingLabel) "
    "WHERE t.include = true "
    "RETURN count(cr) AS total, "
    "  sum(CASE WHEN cr.resolved = true THEN 1 ELSE 0 END) AS resolved, "
    "  sum(CASE WHEN cr.resolved = false THEN 1 ELSE 0 END) AS pending"
).single()
print(
    f"CodingReviews: total={r2['total']}, resolved={r2['resolved']}, pending={r2['pending']}"
)

r3 = s.run(
    "MATCH (r:LabelVerificationReview)-[:REVIEWS_LABEL]->(t:TrainingLabel) "
    "WHERE t.include = true RETURN count(r) AS total"
).single()
print(f"LabelVerificationReviews: {r3['total']}")

s.close()
d.close()
