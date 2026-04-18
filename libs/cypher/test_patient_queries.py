"""Cypher queries for the centralised test-patient library.

Test patients are reusable, reviewer-curated synthetic patient profiles
that exercise every part of the AI: NLP (reading clinical notes),
Episodes (building the patient story), Guidelines (rule firing) and
Summarisation (SBAR handover). They live in the patient graph next to
real patients, but always under a separate :TestPatient label so that
production queries against :Patient cannot return them.

Per DI-59824215 / DI-7625C251 (Atlas) -- the source of truth for the
data model lives in those design inputs.

Key invariants enforced here:

1. Every :TestPatient node carries `is_test = true` and an `aspect`
   property in {"nlp","episodes","guidelines","summarisation"}. Risk
   R-8C0CC94B is mitigated by the structural separation: production
   queries (`MATCH (p:Patient) ...`) never return :TestPatient nodes.

2. Test patients can either be authored from scratch (existing flow,
   guidelines aspect only today) or cloned from a real patient via
   `services.test_patient_clone`. Cloned subgraphs (encounters,
   documents, concept relationships) all carry `is_test = true` so
   any future label-agnostic query can also filter them out.

3. The display name of every test patient starts with "test_" so a
   clinician seeing one in any surface can tell at a glance.

Legacy guideline-specific edges (:FIXTURE_FOR, :EXPECTED_RESULT) are
preserved unchanged so the existing replay flow keeps working while
phases B-D bring up the per-aspect replay backends.
"""

# Aspect vocabulary -- every TestPatient must carry exactly one of
# these values in its `aspect` property. Mirrors the four parts of
# the AI we run regression against.
TEST_PATIENT_ASPECTS: tuple[str, ...] = (
    "nlp",
    "episodes",
    "guidelines",
    "summarisation",
)


# Schema constraints / indexes.  Wire into CODING_SCHEMA_CONSTRAINTS.
TEST_PATIENT_CONSTRAINTS = [
    "CREATE CONSTRAINT test_patient_id IF NOT EXISTS FOR (tp:TestPatient) REQUIRE tp.id IS UNIQUE",
    "CREATE INDEX test_patient_guideline IF NOT EXISTS FOR (tp:TestPatient) ON (tp.guideline_id)",
    "CREATE INDEX test_patient_content_hash IF NOT EXISTS FOR (tp:TestPatient) ON (tp.content_hash)",
    "CREATE INDEX test_patient_aspect IF NOT EXISTS FOR (tp:TestPatient) ON (tp.aspect)",
    "CREATE INDEX test_patient_is_test IF NOT EXISTS FOR (tp:TestPatient) ON (tp.is_test)",
    "CREATE INDEX test_patient_source IF NOT EXISTS FOR (tp:TestPatient) ON (tp.source_patient_id)",
    "CREATE CONSTRAINT ruleset_replay_id IF NOT EXISTS FOR (rv:RulesetReplay) REQUIRE rv.id IS UNIQUE",
    "CREATE INDEX ruleset_replay_version IF NOT EXISTS FOR (rv:RulesetReplay) ON (rv.ruleset_version)",
]


# One-shot backfill -- stamp `is_test = true` and a default aspect on
# any pre-existing :TestPatient node that was created before the
# centralised library landed. Safe to run repeatedly; it only updates
# rows missing the new fields.
BACKFILL_LEGACY_TEST_PATIENTS = """
MATCH (tp:TestPatient)
WHERE tp.is_test IS NULL OR tp.aspect IS NULL
SET tp.is_test = true,
    tp.aspect  = coalesce(tp.aspect, 'guidelines')
RETURN count(tp) AS updated
"""


# Look up an existing test patient by content hash inside one guideline,
# so the generator and the manual save flow can skip duplicates.
FIND_BY_CONTENT_HASH = """
MATCH (tp:TestPatient { content_hash: $content_hash })
      -[:FIXTURE_FOR]->(g:Guideline { id: $guideline_id })
RETURN tp.id AS id
LIMIT 1
"""


# Create a test patient and link it to its guideline.
# Snapshot expectations are written separately via WRITE_EXPECTED_RESULT.
#
# Always stamps `is_test = true` and `aspect = 'guidelines'` -- this
# is the legacy guideline-firing flow. Other aspects (NLP, Episodes,
# Summarisation) use CREATE_TEST_PATIENT_FOR_ASPECT or the clone tool.
CREATE_TEST_PATIENT = """
MATCH (g:Guideline { id: $guideline_id })
CREATE (tp:TestPatient {
    id:                $id,
    name:              $name,
    description:       $description,
    codes:             $codes,
    age:               $age,
    sex:               $sex,
    pathway_id:        $pathway_id,
    scope_type:        $scope_type,
    scope_id:          $scope_id,
    generation_source: $generation_source,
    content_hash:      $content_hash,
    guideline_id:      $guideline_id,
    aspect:            'guidelines',
    is_test:           true,
    created_by:        $created_by,
    created_at:        datetime(),
    updated_at:        datetime()
})
MERGE (tp)-[:FIXTURE_FOR]->(g)
RETURN tp.id AS id
"""


# Create a test patient for any aspect, optionally linked to a source
# (real) patient via SOURCE_OF_TEST. The display name is forced to
# carry a "test_" prefix; the service layer is responsible for
# stripping any patient PII before passing props in.
CREATE_TEST_PATIENT_FOR_ASPECT = """
CREATE (tp:TestPatient {
    id:                 $id,
    name:               $name,
    description:        $description,
    aspect:             $aspect,
    is_test:            true,
    source_patient_id:  $source_patient_id,
    generation_source:  $generation_source,
    age:                $age,
    sex:                $sex,
    created_by:         $created_by,
    created_at:         datetime(),
    updated_at:         datetime()
})
WITH tp
OPTIONAL MATCH (src:Patient { id: $source_patient_id })
FOREACH (_ IN CASE WHEN src IS NULL THEN [] ELSE [1] END |
    MERGE (src)-[:SOURCE_OF_TEST]->(tp)
)
RETURN tp.id AS id
"""


# Snapshot one expectation against a specific rule.
WRITE_EXPECTED_RESULT = """
MATCH (tp:TestPatient { id: $test_patient_id })
MATCH (rule:AppropriatenessRule { id: $rule_id })
MERGE (tp)-[r:EXPECTED_RESULT { rule_id: $rule_id }]->(rule)
SET   r.fires                    = $fires,
      r.matched_branch_node_ids  = $matched_branch_node_ids,
      r.snapshot_at              = datetime(),
      r.ruleset_version          = $ruleset_version,
      r.snapshot_by              = $snapshot_by
RETURN r.rule_id AS rule_id
"""


# List patients with optional filters. Common to all aspects.
#   - $aspect filters on tp.aspect (None or "all" => no filter)
#   - $guideline_id / $rule_id / $node_id are guideline-aspect specific
#   - The result row carries the aspect so the UI can colour rows
#     correctly when "All" is selected.
LIST_TEST_PATIENTS = """
MATCH (tp:TestPatient)
WHERE coalesce(tp.is_test, false) = true
  AND ($aspect IS NULL OR $aspect = 'all' OR coalesce(tp.aspect, 'guidelines') = $aspect)
OPTIONAL MATCH (tp)-[:FIXTURE_FOR]->(g:Guideline)
WHERE ($guideline_id IS NULL OR g.id = $guideline_id)
OPTIONAL MATCH (tp)-[er:EXPECTED_RESULT]->(rule:AppropriatenessRule)
WITH tp, g,
     collect(DISTINCT {
         rule_id:                  er.rule_id,
         fires:                    er.fires,
         matched_branch_node_ids:  er.matched_branch_node_ids,
         snapshot_at:              toString(er.snapshot_at),
         ruleset_version:          er.ruleset_version
     }) AS expectations
WHERE ($rule_id IS NULL OR any(e IN expectations WHERE e.rule_id = $rule_id))
  AND ($node_id  IS NULL OR
       any(e IN expectations WHERE $node_id IN coalesce(e.matched_branch_node_ids, [])))
RETURN tp.id              AS id,
       tp.name            AS name,
       tp.description     AS description,
       coalesce(tp.aspect, 'guidelines') AS aspect,
       coalesce(tp.is_test, true)        AS is_test,
       tp.source_patient_id              AS source_patient_id,
       tp.codes           AS codes,
       tp.age             AS age,
       tp.sex             AS sex,
       tp.pathway_id      AS pathway_id,
       tp.scope_type      AS scope_type,
       tp.scope_id        AS scope_id,
       tp.generation_source AS generation_source,
       tp.content_hash    AS content_hash,
       g.id               AS guideline_id,
       g.title            AS guideline_title,
       toString(tp.created_at) AS created_at,
       tp.created_by      AS created_by,
       [e IN expectations WHERE e.rule_id IS NOT NULL] AS expectations
ORDER BY tp.created_at DESC
LIMIT $limit
"""


# Count test patients grouped by aspect. Backs the four count tiles
# at the top of the Knowledge > Test Patients page.
COUNT_TEST_PATIENTS_BY_ASPECT = """
MATCH (tp:TestPatient)
WHERE coalesce(tp.is_test, false) = true
RETURN coalesce(tp.aspect, 'guidelines') AS aspect,
       count(tp)                         AS total
"""


# Picker for the "Clone from real patient" dialog -- returns the most
# recently active real patients with a coarse activity signal so the
# reviewer can pick a meaningful source.
LIST_REAL_PATIENTS_FOR_CLONE_PICKER = """
MATCH (p:Patient)
WHERE coalesce(p.is_test, false) = false
OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(e:Encounter)
WITH p, count(DISTINCT e) AS encounter_count
ORDER BY encounter_count DESC, p.id ASC
LIMIT $limit
RETURN p.id            AS id,
       coalesce(p.displayName, p.id) AS display_name,
       encounter_count
"""


GET_TEST_PATIENT = """
MATCH (tp:TestPatient { id: $id })
WHERE coalesce(tp.is_test, false) = true
OPTIONAL MATCH (tp)-[:FIXTURE_FOR]->(g:Guideline)
OPTIONAL MATCH (tp)-[er:EXPECTED_RESULT]->(rule:AppropriatenessRule)
WITH tp, g,
     collect(DISTINCT {
         rule_id:                  er.rule_id,
         fires:                    er.fires,
         matched_branch_node_ids:  er.matched_branch_node_ids,
         snapshot_at:              toString(er.snapshot_at),
         ruleset_version:          er.ruleset_version
     }) AS expectations
RETURN tp.id              AS id,
       tp.name            AS name,
       tp.description     AS description,
       coalesce(tp.aspect, 'guidelines') AS aspect,
       coalesce(tp.is_test, true)        AS is_test,
       tp.source_patient_id              AS source_patient_id,
       tp.codes           AS codes,
       tp.age             AS age,
       tp.sex             AS sex,
       tp.pathway_id      AS pathway_id,
       tp.scope_type      AS scope_type,
       tp.scope_id        AS scope_id,
       tp.generation_source AS generation_source,
       tp.content_hash    AS content_hash,
       g.id               AS guideline_id,
       g.title            AS guideline_title,
       toString(tp.created_at) AS created_at,
       tp.created_by      AS created_by,
       [e IN expectations WHERE e.rule_id IS NOT NULL] AS expectations
"""


# -- Clone-from-real-patient helpers ----------------------------------
#
# The Python service in services/api/app/services/test_patient_clone.py
# orchestrates these in sequence under a single transaction. They are
# split into small queries so each step is easy to test in isolation.

# Pull the source patient row so the service can decide what to copy.
# Identifier fields (PII) are surfaced here so the service can prove
# they are absent from the resulting :TestPatient row.
GET_SOURCE_PATIENT_FOR_CLONE = """
MATCH (p:Patient { id: $source_patient_id })
WHERE coalesce(p.is_test, false) = false
OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(e:Encounter)
OPTIONAL MATCH (p)-[:HAS_DOCUMENT]->(d:Document)
WITH p, count(DISTINCT e) AS encounter_count, count(DISTINCT d) AS document_count
RETURN p.id          AS id,
       p.displayName AS display_name,
       p.age         AS age,
       p.sex         AS sex,
       encounter_count,
       document_count
"""


# Clone every (:Patient)-[:HAS_ENCOUNTER]->(:Encounter) edge under the
# new TestPatient. Each cloned encounter:
#   - gets a new id ("test_<hash>") so it cannot collide
#   - keeps every property except `id` (carried straight over)
#   - is stamped with `is_test = true`
#   - keeps its outbound DOCUMENTS-style relationships pointing at the
#     same SNOMED Concept nodes (concepts are reference data)
CLONE_PATIENT_ENCOUNTERS = """
MATCH (src:Patient { id: $source_patient_id })-[:HAS_ENCOUNTER]->(e:Encounter)
MATCH (tp:TestPatient { id: $test_patient_id })
WITH tp, e, $id_prefix + e.id AS new_id
CREATE (te:Encounter)
SET te = properties(e),
    te.id      = new_id,
    te.is_test = true
MERGE (tp)-[:HAS_ENCOUNTER]->(te)
WITH te, e
OPTIONAL MATCH (e)-[r:DOCUMENTS]->(c)
FOREACH (_ IN CASE WHEN c IS NULL THEN [] ELSE [1] END |
    MERGE (te)-[r2:DOCUMENTS]->(c)
    SET r2 = properties(r), r2.is_test = true
)
RETURN count(te) AS encounters_cloned
"""


# Same shape as CLONE_PATIENT_ENCOUNTERS but for the document subgraph.
# Documents may exist via :HAS_DOCUMENT or :HAS_DOCUMENT_REFERENCE; we
# clone whatever is present.
CLONE_PATIENT_DOCUMENTS = """
MATCH (src:Patient { id: $source_patient_id })
OPTIONAL MATCH (src)-[:HAS_DOCUMENT]->(d:Document)
WITH src, collect(DISTINCT d) AS docs
MATCH (tp:TestPatient { id: $test_patient_id })
UNWIND docs AS d
WITH tp, d
WHERE d IS NOT NULL
CREATE (td:Document)
SET td = properties(d),
    td.id      = $id_prefix + d.id,
    td.is_test = true
MERGE (tp)-[:HAS_DOCUMENT]->(td)
RETURN count(td) AS documents_cloned
"""


# Mirror direct concept relationships from the source patient onto
# the test patient (HAS_FINDING / HAS_DISORDER / HAS_OBSERVABLE /
# HAS_PROCEDURE / HAS_SITUATION / HAS_CONCEPT). The relationship is
# replayed pointing at the same Concept node (reference data) and is
# tagged is_test = true so any future relationship-property filter
# can exclude it.
CLONE_PATIENT_CONCEPT_RELATIONSHIPS = """
MATCH (src:Patient { id: $source_patient_id })-[r]->(c)
WHERE type(r) IN [
    'HAS_FINDING','HAS_DISORDER','HAS_OBSERVABLE',
    'HAS_PROCEDURE','HAS_SITUATION','HAS_CONCEPT'
  ]
MATCH (tp:TestPatient { id: $test_patient_id })
CALL apoc.merge.relationship(tp, type(r), {is_test: true}, properties(r), c, {})
YIELD rel
RETURN type(rel) AS rel_type, count(rel) AS rel_count
"""


# Fallback for environments without APOC -- mirror only the most
# common concept relationship types as discrete MERGE statements.
CLONE_PATIENT_CONCEPT_RELATIONSHIPS_NO_APOC = """
MATCH (src:Patient { id: $source_patient_id })-[r]->(c)
WHERE type(r) IN [
    'HAS_FINDING','HAS_DISORDER','HAS_OBSERVABLE',
    'HAS_PROCEDURE','HAS_SITUATION','HAS_CONCEPT'
  ]
MATCH (tp:TestPatient { id: $test_patient_id })
WITH tp, type(r) AS rt, c, properties(r) AS rp
FOREACH (_ IN CASE WHEN rt = 'HAS_FINDING'    THEN [1] ELSE [] END |
    MERGE (tp)-[r2:HAS_FINDING]->(c)    SET r2 = rp, r2.is_test = true)
FOREACH (_ IN CASE WHEN rt = 'HAS_DISORDER'   THEN [1] ELSE [] END |
    MERGE (tp)-[r2:HAS_DISORDER]->(c)   SET r2 = rp, r2.is_test = true)
FOREACH (_ IN CASE WHEN rt = 'HAS_OBSERVABLE' THEN [1] ELSE [] END |
    MERGE (tp)-[r2:HAS_OBSERVABLE]->(c) SET r2 = rp, r2.is_test = true)
FOREACH (_ IN CASE WHEN rt = 'HAS_PROCEDURE'  THEN [1] ELSE [] END |
    MERGE (tp)-[r2:HAS_PROCEDURE]->(c)  SET r2 = rp, r2.is_test = true)
FOREACH (_ IN CASE WHEN rt = 'HAS_SITUATION'  THEN [1] ELSE [] END |
    MERGE (tp)-[r2:HAS_SITUATION]->(c)  SET r2 = rp, r2.is_test = true)
FOREACH (_ IN CASE WHEN rt = 'HAS_CONCEPT'    THEN [1] ELSE [] END |
    MERGE (tp)-[r2:HAS_CONCEPT]->(c)    SET r2 = rp, r2.is_test = true)
RETURN count(*) AS rel_count
"""


# Verification helper used by VT-5BDFE5F7 TC-002: prove a TestPatient
# carries no PII, has the test_ prefix and at least one cloned edge.
ASSERT_TEST_PATIENT_DEIDENTIFIED = """
MATCH (tp:TestPatient { id: $test_patient_id })
OPTIONAL MATCH (tp)-[:HAS_ENCOUNTER]->(e:Encounter)
OPTIONAL MATCH (tp)-[:HAS_DOCUMENT]->(d:Document)
RETURN tp.id                                  AS id,
       tp.name                                AS name,
       tp.aspect                              AS aspect,
       coalesce(tp.is_test, false)            AS is_test,
       tp.source_patient_id                   AS source_patient_id,
       tp.nhs_number                          AS nhs_number,
       tp.dateOfBirth                         AS date_of_birth,
       tp.address                             AS address,
       tp.phone                               AS phone,
       count(DISTINCT e)                      AS encounter_count,
       count(DISTINCT d)                      AS document_count
"""


DELETE_TEST_PATIENT = """
MATCH (tp:TestPatient { id: $id })
DETACH DELETE tp
RETURN count(*) AS deleted
"""


# Update a test patient's profile in place AND clear its existing
# EXPECTED_RESULT relationships so the caller can rewrite them.
# Returns one row when the patient exists, zero rows otherwise (the
# service layer translates that into a 404).  The expectation rewrite
# is a separate WRITE_EXPECTED_RESULT loop driven by the service
# (matching the create flow), so empty-expectation updates are
# still well-defined.
UPDATE_TEST_PATIENT = """
MATCH (tp:TestPatient { id: $id })
SET tp.name              = $name,
    tp.description       = $description,
    tp.codes             = $codes,
    tp.age               = $age,
    tp.sex               = $sex,
    tp.pathway_id        = $pathway_id,
    tp.content_hash      = $content_hash,
    tp.updated_at        = datetime(),
    tp.updated_by        = $updated_by
WITH tp
OPTIONAL MATCH (tp)-[er:EXPECTED_RESULT]->()
DELETE er
RETURN tp.id AS id
"""


# Collect rules in a scope.  Used by both the generator (to know what
# to synthesise fixtures for) and replay (to know what to evaluate).
#
# Status filter:
#   - When the caller targets a single rule by id we accept any non-
#     superseded / non-rejected status -- the reviewer is in the Edit
#     dialog and explicitly asked us to generate test patients for THIS
#     rule, even if it is still pending_review.
#   - For "all rules in a guideline" / "all guidelines" we restrict to
#     rules that the runtime evaluator would actually consider, i.e.
#     active or pending_review (drafts that have been generated and are
#     ready for sign-off).
LIST_RULES_IN_SCOPE = """
MATCH (rule:AppropriatenessRule)
WHERE
  CASE
    WHEN $rule_id IS NOT NULL
      THEN rule.id = $rule_id
           AND coalesce(rule.status, 'active') IN
               ['active', 'pending_review', 'approved', 'draft']
    ELSE coalesce(rule.status, 'active') IN ['active', 'pending_review']
  END
  AND ($guideline_id IS NULL OR
       EXISTS {
         MATCH (g:Guideline { id: $guideline_id })
               -[:HAS_RECOMMENDATION]->()-[:HAS_RULE]->(rule)
       })
OPTIONAL MATCH (rule)<-[:HAS_RULE]-(rec:Recommendation)
              <-[:HAS_RECOMMENDATION]-(g:Guideline)
RETURN rule.id          AS rule_id,
       rule.name        AS name,
       rule.logicJson   AS logic_json,
       coalesce(rule.status, 'active') AS status,
       g.id             AS guideline_id,
       g.title          AS guideline_title
ORDER BY rule.name
"""


# List guidelines (used by library page scope picker)
LIST_GUIDELINES_FOR_PICKER = """
MATCH (g:Guideline)
OPTIONAL MATCH (g)-[:HAS_RECOMMENDATION]->()-[:HAS_RULE]->(r:AppropriatenessRule {status: 'active'})
WITH g, count(DISTINCT r) AS active_rule_count
WHERE active_rule_count > 0
RETURN g.id AS id, g.title AS title, active_rule_count
ORDER BY g.title
LIMIT 200
"""


# Persist a replay report so it can be surfaced in the UI and
# re-loaded without re-running expensive evaluations.
WRITE_REPLAY_REPORT = """
MERGE (rv:RulesetReplay { id: $id })
ON CREATE SET rv.created_at = datetime()
SET rv.ruleset_version    = $ruleset_version,
    rv.scope_type         = $scope_type,
    rv.scope_id           = $scope_id,
    rv.guideline_id       = $guideline_id,
    rv.report_json        = $report_json,
    rv.regressions_count  = $regressions_count,
    rv.passes_count       = $passes_count,
    rv.drift_count        = $drift_count,
    rv.total_count        = $total_count,
    rv.completed_at       = datetime()
RETURN rv.id AS id
"""


LIST_REPLAY_REPORTS = """
MATCH (rv:RulesetReplay)
WHERE ($guideline_id IS NULL OR rv.guideline_id = $guideline_id)
  AND ($scope_type   IS NULL OR rv.scope_type   = $scope_type)
  AND ($scope_id     IS NULL OR rv.scope_id     = $scope_id)
RETURN rv.id                AS id,
       rv.ruleset_version   AS ruleset_version,
       rv.scope_type        AS scope_type,
       rv.scope_id          AS scope_id,
       rv.guideline_id      AS guideline_id,
       rv.regressions_count AS regressions_count,
       rv.passes_count      AS passes_count,
       rv.drift_count       AS drift_count,
       rv.total_count       AS total_count,
       toString(rv.created_at)   AS created_at,
       toString(rv.completed_at) AS completed_at
ORDER BY rv.completed_at DESC
LIMIT $limit
"""


GET_REPLAY_REPORT = """
MATCH (rv:RulesetReplay { id: $id })
RETURN rv.id              AS id,
       rv.ruleset_version AS ruleset_version,
       rv.scope_type      AS scope_type,
       rv.scope_id        AS scope_id,
       rv.guideline_id    AS guideline_id,
       rv.report_json     AS report_json,
       toString(rv.completed_at) AS completed_at
"""
