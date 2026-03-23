"""Deep investigation of HITL coding review queue."""
import json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / "secrets" / ".env")
load_dotenv(Path(__file__).resolve().parents[1] / "secrets" / ".env.secrets", override=True)
from neo4j import GraphDatabase

d = GraphDatabase.driver(os.getenv("NEO4J_URI"), auth=("neo4j", os.getenv("NEO4J_PASSWORD")))
s = d.session()

# ===========================================================================
# 1. UNCODED items — what text is failing to resolve?
# ===========================================================================
print("\n" + "="*70)
print("1. UNCODED ITEMS — top entity texts with no SNOMED match")
print("="*70)
rows = s.run("""
    MATCH (cr:CodingReview)-[:REVIEWS_CODING]->(t:TrainingLabel)
    WHERE t.include = true AND cr.resolved = false
      AND cr.coded = false
    RETURN
        cr.entity_text  AS text,
        cr.entity_label AS label,
        cr.assertion    AS assertion,
        count(cr)       AS occurrences
    ORDER BY occurrences DESC
    LIMIT 30
""")
for r in rows:
    print(f"  [{r['occurrences']:4d}x]  [{r['label']}] [{r['assertion']}]  '{r['text']}'")

# ===========================================================================
# 2. UNCODED by entity label — which labels are hardest to code?
# ===========================================================================
print("\n" + "="*70)
print("2. UNCODED — breakdown by entity label")
print("="*70)
rows = s.run("""
    MATCH (cr:CodingReview)-[:REVIEWS_CODING]->(t:TrainingLabel)
    WHERE t.include = true AND cr.resolved = false
      AND cr.coded = false
    RETURN
        cr.entity_label AS label,
        count(cr) AS cnt
    ORDER BY cnt DESC
""")
for r in rows:
    print(f"  [{r['cnt']:5d}]  {r['label']}")

# ===========================================================================
# 3. UNCODED — sample with encounter context
# ===========================================================================
print("\n" + "="*70)
print("3. UNCODED — sample 15 with encounter context")
print("="*70)
rows = s.run("""
    MATCH (cr:CodingReview)-[:REVIEWS_CODING]->(t:TrainingLabel)
    WHERE t.include = true AND cr.resolved = false
      AND cr.coded = false
    RETURN
        cr.entity_text  AS text,
        cr.entity_label AS label,
        cr.assertion    AS assertion,
        substring(t.text, 0, 150) AS encounter
    ORDER BY rand()
    LIMIT 15
""")
for i, r in enumerate(rows, 1):
    print(f"\n  [{i}] [{r['label']}] '{r['text']}' (assertion={r['assertion']})")
    print(f"       encounter: {r['encounter']}")

# ===========================================================================
# 4. OBSERVABLE_ENTITY → PROCEDURE — is the SNOMED concept actually right?
#    Sample 20 to judge if we should just accept these
# ===========================================================================
print("\n" + "="*70)
print("4. observable_entity -> procedure mismatches (sample 20)")
print("   QUESTION: Is the procedure code actually correct for these?")
print("="*70)
rows = s.run("""
    MATCH (cr:CodingReview)-[:REVIEWS_CODING]->(t:TrainingLabel)
    WHERE t.include = true AND cr.resolved = false
      AND cr.entity_label = 'observable_entity'
      AND cr.suggested_label = 'procedure'
    RETURN
        cr.entity_text       AS text,
        cr.snomed_concept_id AS concept_id,
        cr.snomed_term       AS snomed_term,
        cr.score             AS score,
        cr.tag_mismatch_delta AS delta
    ORDER BY cr.entity_text
    LIMIT 20
""")
seen = set()
for r in rows:
    key = r['text']
    if key not in seen:
        seen.add(key)
        print(f"  '{r['text']}'")
        print(f"    -> {r['concept_id']} | {r['snomed_term']}  score={r['score']}  delta={r['delta']}")

# ===========================================================================
# 5. FINDING → DISORDER — these may be genuine borderline cases
# ===========================================================================
print("\n" + "="*70)
print("5. finding -> disorder mismatches (all unique entity texts)")
print("="*70)
rows = s.run("""
    MATCH (cr:CodingReview)-[:REVIEWS_CODING]->(t:TrainingLabel)
    WHERE t.include = true AND cr.resolved = false
      AND cr.entity_label = 'finding'
      AND cr.suggested_label = 'disorder'
    RETURN DISTINCT
        cr.entity_text       AS text,
        cr.snomed_concept_id AS concept_id,
        cr.snomed_term       AS snomed_term,
        cr.score             AS score,
        cr.tag_mismatch_delta AS delta
    ORDER BY delta DESC
    LIMIT 30
""")
for r in rows:
    print(f"  [{r['delta']:.2f}] '{r['text']}'")
    print(f"         -> {r['concept_id']} | {r['snomed_term']}  score={r['score']}")

# ===========================================================================
# 6. LOW CONFIDENCE (tier 3) — what's failing to score well?
# ===========================================================================
print("\n" + "="*70)
print("6. LOW CONFIDENCE tier-3 items")
print("="*70)
rows = s.run("""
    MATCH (cr:CodingReview)-[:REVIEWS_CODING]->(t:TrainingLabel)
    WHERE t.include = true AND cr.resolved = false
      AND cr.decision_tier = 3
    RETURN
        cr.entity_text       AS text,
        cr.entity_label      AS label,
        cr.snomed_concept_id AS concept_id,
        cr.snomed_term       AS snomed_term,
        cr.score             AS score,
        substring(t.text, 0, 120) AS encounter
    ORDER BY cr.score ASC
    LIMIT 20
""")
for i, r in enumerate(rows, 1):
    print(f"\n  [{i}] [{r['label']}] '{r['text']}'  score={r['score']}")
    print(f"       -> {r['concept_id']} | {r['snomed_term']}")
    print(f"       encounter: {r['encounter']}")

# ===========================================================================
# 7. How many unique entity texts are in the mismatch queue?
#    (useful to know if bulk-resolving some patterns would clear the queue)
# ===========================================================================
print("\n" + "="*70)
print("7. Mismatch queue — unique entity texts by mismatch type")
print("="*70)
rows = s.run("""
    MATCH (cr:CodingReview)-[:REVIEWS_CODING]->(t:TrainingLabel)
    WHERE t.include = true AND cr.resolved = false
      AND cr.suggested_label IS NOT NULL
    RETURN
        cr.entity_label   AS extracted,
        cr.suggested_label AS suggested,
        count(DISTINCT cr.entity_text) AS unique_texts,
        count(cr) AS total_items
    ORDER BY total_items DESC
    LIMIT 15
""")
for r in rows:
    print(f"  {r['extracted']} -> {r['suggested']}: {r['unique_texts']} unique texts / {r['total_items']} total items")

s.close()
d.close()
