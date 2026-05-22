"""Cypher for lab result metadata stored in the Knowledge Graph.

Atlas trace:
  UN: UN-1DCDA92F
  DI: DI-6BA67DFF
  DO: DO-F34C6679
  Risk: R-77E35839
  VT: VT-6A6C90E0

Model:
  (:LabResultConfig {conceptId})-[:CONFIGURES_OBSERVABLE]->(:Concept)
  (:LabResultConfig)-[:HAS_UNIT_CONVERSION]->(:LabUnitConversion)
  (:LabResultConfig)-[:HAS_REFERENCE_RANGE]->(:LabReferenceRange)
  (:LabResultConfig)-[:INTERPRETS_AS {classification}]->(:Concept)
"""

LIST_LAB_RESULT_CONFIGS = """
MATCH (cfg:LabResultConfig)
OPTIONAL MATCH (cfg)-[:CONFIGURES_OBSERVABLE]->(obs)
WHERE $q IS NULL
   OR toLower(cfg.conceptId) CONTAINS toLower($q)
   OR toLower(coalesce(cfg.display_name, obs.fsn, obs.preferred_term, '')) CONTAINS toLower($q)
RETURN cfg.conceptId AS concept_id,
       coalesce(cfg.display_name, obs.fsn, obs.preferred_term, cfg.conceptId) AS display_name,
       cfg.canonical_unit AS canonical_unit,
       cfg.source AS source,
       toString(cfg.updated_at) AS updated_at
ORDER BY display_name, concept_id
LIMIT $limit
"""

GET_LAB_RESULT_CONFIG = """
MATCH (cfg:LabResultConfig {conceptId: $concept_id})
OPTIONAL MATCH (cfg)-[:CONFIGURES_OBSERVABLE]->(obs)
OPTIONAL MATCH (cfg)-[:HAS_UNIT_CONVERSION]->(conv:LabUnitConversion)
OPTIONAL MATCH (cfg)-[:HAS_REFERENCE_RANGE]->(rr:LabReferenceRange)
OPTIONAL MATCH (cfg)-[interp:INTERPRETS_AS]->(finding)
RETURN cfg.conceptId AS concept_id,
       coalesce(cfg.display_name, obs.fsn, obs.preferred_term, cfg.conceptId) AS display_name,
       cfg.canonical_unit AS canonical_unit,
       cfg.source AS source,
       toString(cfg.updated_at) AS updated_at,
       collect(DISTINCT {
         unit: conv.unit,
         factor: conv.factor,
         offset: conv.offset
       }) AS conversions,
       collect(DISTINCT {
         range_id: rr.range_id,
         sex: rr.sex,
         age_min: rr.age_min,
         age_max: rr.age_max,
         low: rr.low,
         high: rr.high,
         critical_low: rr.critical_low,
         critical_high: rr.critical_high,
         source: rr.source
       }) AS ranges,
       collect(DISTINCT {
         classification: interp.classification,
         concept_id: coalesce(finding.id, finding.conceptId),
         term: coalesce(finding.fsn, finding.preferred_term, finding.term)
       }) AS interpretations
"""

UPSERT_LAB_RESULT_CONFIG = """
MERGE (cfg:LabResultConfig {conceptId: $concept_id})
ON CREATE SET cfg.created_at = datetime()
SET cfg.display_name = $display_name,
    cfg.canonical_unit = $canonical_unit,
    cfg.source = $source,
    cfg.updated_by = $updated_by,
    cfg.updated_at = datetime()
WITH cfg
OPTIONAL MATCH (obs:Concept {id: $concept_id})
FOREACH (_ IN CASE WHEN obs IS NULL THEN [] ELSE [1] END |
  MERGE (cfg)-[:CONFIGURES_OBSERVABLE]->(obs)
)
RETURN cfg.conceptId AS concept_id
"""

UPSERT_UNIT_CONVERSION = """
MATCH (cfg:LabResultConfig {conceptId: $concept_id})
MERGE (cfg)-[:HAS_UNIT_CONVERSION]->(conv:LabUnitConversion {
  conceptId: $concept_id,
  unit: $unit
})
ON CREATE SET conv.conversion_id = randomUUID(), conv.created_at = datetime()
SET conv.factor = $factor,
    conv.offset = $offset,
    conv.updated_by = $updated_by,
    conv.updated_at = datetime()
RETURN conv.conversion_id AS conversion_id
"""

UPSERT_REFERENCE_RANGE = """
MATCH (cfg:LabResultConfig {conceptId: $concept_id})
MERGE (cfg)-[:HAS_REFERENCE_RANGE]->(rr:LabReferenceRange {range_id: $range_id})
ON CREATE SET rr.created_at = datetime()
SET rr.conceptId = $concept_id,
    rr.sex = $sex,
    rr.age_min = $age_min,
    rr.age_max = $age_max,
    rr.low = $low,
    rr.high = $high,
    rr.critical_low = $critical_low,
    rr.critical_high = $critical_high,
    rr.source = $source,
    rr.updated_by = $updated_by,
    rr.updated_at = datetime()
RETURN rr.range_id AS range_id
"""

UPSERT_INTERPRETATION = """
MATCH (cfg:LabResultConfig {conceptId: $concept_id})
MATCH (finding:Concept {id: $finding_concept_id})
MERGE (cfg)-[rel:INTERPRETS_AS {classification: $classification}]->(finding)
SET rel.updated_by = $updated_by,
    rel.updated_at = datetime()
RETURN rel.classification AS classification,
       coalesce(finding.id, finding.conceptId) AS finding_concept_id
"""

DELETE_REFERENCE_RANGE = """
MATCH (:LabResultConfig {conceptId: $concept_id})-[:HAS_REFERENCE_RANGE]->(rr:LabReferenceRange {range_id: $range_id})
DETACH DELETE rr
RETURN count(rr) AS deleted
"""

DELETE_UNIT_CONVERSION = """
MATCH (:LabResultConfig {conceptId: $concept_id})-[:HAS_UNIT_CONVERSION]->(conv:LabUnitConversion {unit: $unit})
DETACH DELETE conv
RETURN count(conv) AS deleted
"""

DELETE_INTERPRETATION = """
MATCH (:LabResultConfig {conceptId: $concept_id})-[rel:INTERPRETS_AS {classification: $classification}]->(:Concept)
DELETE rel
RETURN count(rel) AS deleted
"""
