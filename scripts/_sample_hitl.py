"""Sample HITL coding review items from Neo4j."""
import json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / "secrets" / ".env")
load_dotenv(Path(__file__).resolve().parents[1] / "secrets" / ".env.secrets", override=True)
from neo4j import GraphDatabase

d = GraphDatabase.driver(os.getenv("NEO4J_URI"), auth=("neo4j", os.getenv("NEO4J_PASSWORD")))
d.verify_connectivity()
s = d.session()

# --- 1. Tier distribution
print("\n=== TIER DISTRIBUTION ===")
rows = s.run("""
    MATCH (cr:CodingReview)-[:REVIEWS_CODING]->(t:TrainingLabel)
    WHERE t.include = true AND cr.resolved = false
    RETURN
        coalesce(cr.decision_tier, -1) AS tier,
        cr.tier_decision AS decision,
        count(cr) AS cnt
    ORDER BY tier ASC, cnt DESC
""")
for r in rows:
    print(f"  tier={r['tier']}  decision={r['decision']}  count={r['cnt']}")

# --- 2. Top reasons
print("\n=== TOP TIER REASONS ===")
rows = s.run("""
    MATCH (cr:CodingReview)-[:REVIEWS_CODING]->(t:TrainingLabel)
    WHERE t.include = true AND cr.resolved = false
    RETURN cr.tier_reason AS reason, count(cr) AS cnt
    ORDER BY cnt DESC LIMIT 15
""")
for r in rows:
    print(f"  [{r['cnt']:5d}]  {r['reason']}")

# --- 3. Semantic tag mismatch summary
print("\n=== SEMANTIC TAG MISMATCHES ===")
rows = s.run("""
    MATCH (cr:CodingReview)-[:REVIEWS_CODING]->(t:TrainingLabel)
    WHERE t.include = true AND cr.resolved = false AND cr.suggested_label IS NOT NULL
    RETURN
        cr.entity_label AS extracted,
        cr.suggested_label AS suggested,
        count(cr) AS cnt,
        round(avg(cr.tag_mismatch_delta)*100)/100 AS avg_delta
    ORDER BY cnt DESC LIMIT 20
""")
for r in rows:
    print(f"  [{r['cnt']:4d}]  {r['extracted']} -> {r['suggested']}  avg_delta={r['avg_delta']}")

# --- 4. Sample 10 HITL items with full shape
print("\n=== SAMPLE HITL ITEMS (full shape) ===")
rows = s.run("""
    MATCH (cr:CodingReview)-[:REVIEWS_CODING]->(t:TrainingLabel)
    WHERE t.include = true AND cr.resolved = false
    RETURN
        cr.review_id          AS review_id,
        cr.entity_text        AS entity_text,
        cr.entity_label       AS entity_label,
        cr.coded              AS coded,
        cr.snomed_concept_id  AS snomed_concept_id,
        cr.snomed_term        AS snomed_term,
        cr.score              AS score,
        cr.semantic_tag       AS semantic_tag,
        cr.assertion          AS assertion,
        cr.decision_tier      AS decision_tier,
        cr.tier_reason        AS tier_reason,
        cr.tier_decision      AS tier_decision,
        cr.suggested_label    AS suggested_label,
        cr.tag_mismatch_delta AS tag_mismatch_delta,
        substring(t.text, 0, 120) AS encounter_text_preview
    ORDER BY cr.decision_tier ASC, cr.score ASC
    LIMIT 10
""")
for i, r in enumerate(rows, 1):
    print(f"\n  [{i}] {r['review_id']}")
    print(f"       entity_text:   {r['entity_text']}")
    print(f"       entity_label:  {r['entity_label']}")
    print(f"       coded:         {r['coded']}")
    print(f"       snomed:        {r['snomed_concept_id']} | {r['snomed_term']}")
    print(f"       score:         {r['score']}")
    print(f"       semantic_tag:  {r['semantic_tag']}")
    print(f"       assertion:     {r['assertion']}")
    print(f"       tier:          {r['decision_tier']} / {r['tier_decision']} / {r['tier_reason']}")
    if r['suggested_label']:
        print(f"       TAG MISMATCH:  suggested={r['suggested_label']}  delta={r['tag_mismatch_delta']}")
    print(f"       encounter:     {r['encounter_text_preview']}")

# --- 5. Coded vs uncoded
print("\n=== CODED vs UNCODED ===")
r = s.run("""
    MATCH (cr:CodingReview)-[:REVIEWS_CODING]->(t:TrainingLabel)
    WHERE t.include = true AND cr.resolved = false
    RETURN
        sum(CASE WHEN cr.coded = true THEN 1 ELSE 0 END) AS coded,
        sum(CASE WHEN cr.coded = false THEN 1 ELSE 0 END) AS uncoded,
        sum(CASE WHEN cr.suggested_label IS NOT NULL THEN 1 ELSE 0 END) AS tag_mismatches,
        count(cr) AS total
""").single()
print(f"  total={r['total']}  coded={r['coded']}  uncoded={r['uncoded']}  tag_mismatches={r['tag_mismatches']}")

s.close()
d.close()
