"""Cypher queries for the frozen golden evaluation set.

Atlas trace:
  DO: DO-A35D2D57
  DI: DI-37B3DC71
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-A35D2D57")

The golden set is a stable, locked subset of GoldLabel nodes used to measure
model quality against a consistent benchmark. Unlike the dev split (which
changes every run), the golden set never changes once frozen, providing a
reliable regression signal across training versions.
"""

SET_GOLDEN_SET_FLAG = """
MATCH (g:GoldLabel {label_id: $label_id})
SET g.frozen_golden_set = $value,
    g.golden_set_updated_at = datetime(),
    g.golden_set_updated_by = $updated_by
RETURN g.label_id AS label_id, g.frozen_golden_set AS frozen_golden_set
"""

GET_GOLDEN_SET_LABELS = """
MATCH (g:GoldLabel)
WHERE g.frozen_golden_set = true
  AND g.entities_json IS NOT NULL
OPTIONAL MATCH (c:TrainingCandidate)-[:PRODUCED]->(g)
RETURN
    g.label_id AS label_id,
    g.text AS text,
    g.entities_json AS entities_json,
    g.source AS source,
    coalesce(g.candidate_id, c.candidate_id) AS candidate_id
ORDER BY g.created_at ASC
"""

COUNT_GOLDEN_SET = """
MATCH (g:GoldLabel)
WHERE g.frozen_golden_set = true
RETURN count(g) AS total
"""

GET_GOLDEN_SET_STATS = """
MATCH (g:GoldLabel)
WHERE g.frozen_golden_set = true
RETURN
    count(g) AS total,
    avg(g.quality_score) AS avg_quality_score,
    sum(CASE WHEN g.quality_score >= 0.8 THEN 1 ELSE 0 END) AS high_quality
"""
