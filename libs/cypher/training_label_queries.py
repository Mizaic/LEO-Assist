"""Cypher queries for the TrainingLabel node — the single source of truth

Atlas trace:
  DO: DO-BE96444E
  DI: DI-BAC284B4
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-BE96444E")

for all NER training data.

Every learning source (HITL approvals, coding-UX corrections, offline
anchor-mining scripts) writes here.  The training microservice reads from
here when building a spaCy DocBin for fine-tuning.

Schema contract
---------------
(:TrainingLabel {
    label_id,           # SHA256(encounter_id + sorted entity fingerprint)
    encounter_id,
    patient_id_hash,    # de-identified (SHA256 of raw patient_id)
    text,               # de-identified encounter sentence text
    entities_json,      # JSON list of canonical span dicts
    source,             # "hitl_approval" | "coding_correction" |
                        #  "anchor_mining" | "seed"
    source_ref,         # candidate_id / task_id / script run_id
    include,            # bool: can be excluded without deleting
    excluded_reason,    # string if include=false
    quality_score,      # 0.0–1.0 from precision gate
    schema_version,     # canonical schema version used
    created_at,
    updated_at
})
"""

# ------------------------------------------------------------------
# Indexes (run once at service startup or migration)
# ------------------------------------------------------------------

CREATE_TRAINING_LABEL_INDEXES = [
    "CREATE INDEX training_label_id IF NOT EXISTS FOR (t:TrainingLabel) ON (t.label_id)",
    "CREATE INDEX training_label_encounter IF NOT EXISTS FOR (t:TrainingLabel) ON (t.encounter_id)",
    "CREATE INDEX training_label_source IF NOT EXISTS FOR (t:TrainingLabel) ON (t.source)",
    "CREATE INDEX training_label_include IF NOT EXISTS FOR (t:TrainingLabel) ON (t.include)",
]

# ------------------------------------------------------------------
# Write queries
# ------------------------------------------------------------------

UPSERT_TRAINING_LABEL = """
MERGE (t:TrainingLabel {label_id: $label_id})
ON CREATE SET
    t.encounter_id     = $encounter_id,
    t.patient_id_hash  = $patient_id_hash,
    t.text             = $text,
    t.entities_json    = $entities_json,
    t.source           = $source,
    t.source_ref       = $source_ref,
    t.include          = true,
    t.excluded_reason  = null,
    t.quality_score    = $quality_score,
    t.schema_version   = $schema_version,
    t.created_at       = datetime(),
    t.updated_at       = datetime()
ON MATCH SET
    t.text             = $text,
    t.entities_json    = $entities_json,
    t.quality_score    = $quality_score,
    t.schema_version   = $schema_version,
    t.updated_at       = datetime()
RETURN t.label_id AS label_id, t.include AS include
"""

EXCLUDE_TRAINING_LABEL = """
MATCH (t:TrainingLabel {label_id: $label_id})
SET t.include          = false,
    t.excluded_reason  = $reason,
    t.updated_at       = datetime()
RETURN t.label_id AS label_id
"""

INCLUDE_TRAINING_LABEL = """
MATCH (t:TrainingLabel {label_id: $label_id})
SET t.include          = true,
    t.excluded_reason  = null,
    t.updated_at       = datetime()
RETURN t.label_id AS label_id
"""

UPDATE_TRAINING_LABEL_ENTITIES = """
MATCH (t:TrainingLabel {label_id: $label_id})
SET t.entities_json = $entities_json,
    t.updated_at    = datetime()
RETURN t.label_id AS label_id, t.entities_json AS entities_json
"""

# ------------------------------------------------------------------
# Read queries
# ------------------------------------------------------------------

GET_TRAINING_LABEL_STATS = """
MATCH (t:TrainingLabel)
WITH
    count(t)                                                          AS total,
    sum(CASE WHEN t.include = true  THEN 1 ELSE 0 END)               AS included,
    sum(CASE WHEN t.include = false THEN 1 ELSE 0 END)               AS excluded,
    sum(CASE WHEN t.source = 'hitl_approval'    AND t.include THEN 1 ELSE 0 END) AS hitl,
    sum(CASE WHEN t.source = 'coding_correction' AND t.include THEN 1 ELSE 0 END) AS coding_correction,
    sum(CASE WHEN t.source = 'anchor_mining'    AND t.include THEN 1 ELSE 0 END) AS anchor_mining,
    sum(CASE WHEN t.source = 'seed'             AND t.include THEN 1 ELSE 0 END) AS seed
RETURN total, included, excluded, hitl, coding_correction, anchor_mining, seed
"""

GET_TRAINING_LABELS_PAGE = """
MATCH (t:TrainingLabel)
WHERE ($source IS NULL OR t.source = $source)
  AND ($include IS NULL OR t.include = $include)
  AND ($search IS NULL OR t.text CONTAINS $search)
RETURN
    t.label_id        AS label_id,
    t.encounter_id    AS encounter_id,
    t.text            AS text,
    t.entities_json   AS entities_json,
    t.source          AS source,
    t.source_ref      AS source_ref,
    t.include         AS include,
    t.excluded_reason AS excluded_reason,
    t.quality_score   AS quality_score,
    t.schema_version  AS schema_version,
    toString(t.created_at) AS created_at,
    toString(t.updated_at) AS updated_at
ORDER BY t.updated_at DESC
SKIP $skip
LIMIT $limit
"""

COUNT_TRAINING_LABELS_PAGE = """
MATCH (t:TrainingLabel)
WHERE ($source IS NULL OR t.source = $source)
  AND ($include IS NULL OR t.include = $include)
  AND ($search IS NULL OR t.text CONTAINS $search)
RETURN count(t) AS total
"""

GET_TRAINING_LABEL_BY_ID = """
MATCH (t:TrainingLabel {label_id: $label_id})
RETURN
    t.label_id        AS label_id,
    t.encounter_id    AS encounter_id,
    t.patient_id_hash AS patient_id_hash,
    t.text            AS text,
    t.entities_json   AS entities_json,
    t.source          AS source,
    t.source_ref      AS source_ref,
    t.include         AS include,
    t.excluded_reason AS excluded_reason,
    t.quality_score   AS quality_score,
    t.schema_version  AS schema_version,
    toString(t.created_at) AS created_at,
    toString(t.updated_at) AS updated_at
"""

GET_ALL_INCLUDED_LABELS_FOR_EXPORT = """
MATCH (t:TrainingLabel)
WHERE t.include = true
  AND t.entities_json IS NOT NULL
RETURN
    t.label_id       AS label_id,
    t.encounter_id   AS encounter_id,
    t.text           AS text,
    t.entities_json  AS entities_json,
    t.source         AS source,
    t.quality_score  AS quality_score,
    toString(t.verified_at) AS verified_at
ORDER BY t.created_at ASC
"""

COUNT_EXPORTABLE_LABELS = """
MATCH (t:TrainingLabel)
WHERE t.include = true
  AND t.entities_json IS NOT NULL
RETURN count(t) AS total
"""

LABEL_ENTITY_TYPE_BREAKDOWN = """
MATCH (t:TrainingLabel)
WHERE t.include = true
UNWIND apoc.convert.fromJsonList(t.entities_json) AS ent
RETURN ent.label AS label, count(ent) AS n
ORDER BY n DESC
"""
