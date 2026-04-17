"""Cypher queries for the persistent test-patient library.

Test patients are reusable, reviewer-curated synthetic patient profiles
that are replayed against AppropriatenessRules every time the
roaring-bitmap ruleset is recompiled. They live in the knowledge graph,
attached per-Guideline:

    (:TestPatient)-[:FIXTURE_FOR]->(:Guideline)
    (:TestPatient)-[:EXPECTED_RESULT { rule_id, fires, ... }]->(:AppropriatenessRule)

The content_hash field plus a uniqueness constraint enforces the
"unless they already exist" dedup rule when auto-generating fixtures.
"""

# Schema constraints / indexes.  Wire into CODING_SCHEMA_CONSTRAINTS.
TEST_PATIENT_CONSTRAINTS = [
    "CREATE CONSTRAINT test_patient_id IF NOT EXISTS FOR (tp:TestPatient) REQUIRE tp.id IS UNIQUE",
    "CREATE INDEX test_patient_guideline IF NOT EXISTS FOR (tp:TestPatient) ON (tp.guideline_id)",
    "CREATE INDEX test_patient_content_hash IF NOT EXISTS FOR (tp:TestPatient) ON (tp.content_hash)",
    "CREATE CONSTRAINT ruleset_replay_id IF NOT EXISTS FOR (rv:RulesetReplay) REQUIRE rv.id IS UNIQUE",
    "CREATE INDEX ruleset_replay_version IF NOT EXISTS FOR (rv:RulesetReplay) ON (rv.ruleset_version)",
]


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
    created_by:        $created_by,
    created_at:        datetime(),
    updated_at:        datetime()
})
MERGE (tp)-[:FIXTURE_FOR]->(g)
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


# List patients, optionally filtered by guideline.  When
# $rule_id is supplied, only patients with an EXPECTED_RESULT against
# that rule are returned.  When $node_id is supplied, only patients
# whose snapshot includes that branch node are returned.
LIST_TEST_PATIENTS = """
MATCH (tp:TestPatient)-[:FIXTURE_FOR]->(g:Guideline)
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


GET_TEST_PATIENT = """
MATCH (tp:TestPatient { id: $id })-[:FIXTURE_FOR]->(g:Guideline)
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


DELETE_TEST_PATIENT = """
MATCH (tp:TestPatient { id: $id })
DETACH DELETE tp
RETURN count(*) AS deleted
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
