"""Check current MAPS_TO edges for multi-mapped forms with decisions."""
from neo4j import GraphDatabase

NORMS = [
    "pre existing diabetes mellitus",
    "smoker",
    "current smoker",
    "obese",
    "night sweats",
    "congestive heart failure",
    "monocyte count observation",
    "fit",
    "fit 10",
]

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password"))
with driver.session() as s:
    res = s.run(
        """
        MATCH (sf:SurfaceForm)-[r:MAPS_TO]->(c:Concept)
        WHERE sf.normalized IN $norms
        RETURN sf.normalized AS norm, c.cid AS cid, c.fsn AS fsn
        ORDER BY norm, cid
        """,
        norms=NORMS,
    )
    for row in res:
        print(f"{row['norm']!r:50s} -> {row['cid']:25s} {row['fsn']}")
driver.close()
