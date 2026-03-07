"""
Check records where normalized is null/empty/identical to text (abbreviated surface forms).
These cause bad SNOMED lookups. Also look for snomed_score > 1.0 + wrong snomed_term pattern.
"""
import json, sys
sys.path.insert(0, ".")
from libs.domain_config.registry import get_neo4j_driver

driver = get_neo4j_driver()

query = """
MATCH (l:TrainingLabel)-[:HAS_ENTITY]->(e:Entity)
WHERE e.snomed_score IS NOT NULL
  AND (
    e.normalized IS NULL
    OR e.normalized = ''
    OR e.normalized = e.text
    OR e.snomed_score > 1.0
  )
RETURN
  l.label_id AS label_id,
  e.text AS text,
  e.normalized AS normalized,
  e.snomed_term AS snomed_term,
  e.snomed_score AS snomed_score,
  e.label AS label,
  l.encounter_text AS encounter_text
LIMIT 200
"""

missing_norm = []
score_overflow = []
norm_equals_text = []

with driver.session() as session:
    result = session.run(query)
    for row in result:
        r = dict(row)
        text = r.get("text","") or ""
        norm = r.get("normalized","") or ""
        score = r.get("snomed_score") or 0
        term = r.get("snomed_term","") or ""

        if not norm or norm.strip() == "":
            missing_norm.append(r)
        elif norm.strip().lower() == text.strip().lower():
            norm_equals_text.append(r)

        if score > 1.0:
            score_overflow.append(r)

print(f"Missing/empty normalized: {len(missing_norm)}")
for r in missing_norm[:10]:
    print(f"  text={r['text']!r:30s} normalized={r['normalized']!r:30s} snomed={r['snomed_term']!r:50s} score={r['snomed_score']}")

print(f"\nNormalized == text (no expansion): {len(norm_equals_text)}")
for r in norm_equals_text[:10]:
    print(f"  text={r['text']!r:30s} snomed={r['snomed_term']!r:50s} score={r['snomed_score']}")

print(f"\nsnomed_score > 1.0: {len(score_overflow)}")
for r in score_overflow[:10]:
    print(f"  text={r['text']!r:25s} score={r['snomed_score']:.4f} snomed={r['snomed_term']!r:50s}")
