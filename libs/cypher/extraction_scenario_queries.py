"""Cypher queries for ExtractionScenario and ExtractionValidationRun nodes.

ExtractionScenario nodes store the phrase-level F1 validation corpus.
They live in the Knowledge Graph alongside SNOMED concepts, surface forms,
and test patients -- never the Patient Graph (no PHI here).

Only seeds when no ExtractionScenario nodes exist; skips if any are
already present to avoid overwriting user-modified data.

Atlas trace:
  DI: DI-1B3B5375, DI-B492CAFD
  DO: DO-416BA91D
  Risk: R-80E8BD96
  VT: VT-24D7A846, VT-C9325761
"""

# -- Schema ------------------------------------------------------------------

EXTRACTION_SCENARIO_CONSTRAINTS: list[str] = [
    "CREATE CONSTRAINT extraction_scenario_id IF NOT EXISTS "
    "FOR (s:ExtractionScenario) REQUIRE s.case_id IS UNIQUE",
    "CREATE INDEX extraction_scenario_site IF NOT EXISTS "
    "FOR (s:ExtractionScenario) ON (s.site)",
    "CREATE INDEX extraction_scenario_status IF NOT EXISTS "
    "FOR (s:ExtractionScenario) ON (s.review_status)",
    "CREATE CONSTRAINT extraction_validation_run_id IF NOT EXISTS "
    "FOR (r:ExtractionValidationRun) REQUIRE r.run_id IS UNIQUE",
    "CREATE INDEX extraction_validation_run_status IF NOT EXISTS "
    "FOR (r:ExtractionValidationRun) ON (r.status)",
    "CREATE INDEX extraction_validation_run_triggered IF NOT EXISTS "
    "FOR (r:ExtractionValidationRun) ON (r.triggered_at)",
]

# -- Counts ------------------------------------------------------------------

COUNT_EXTRACTION_SCENARIOS = """
MATCH (s:ExtractionScenario)
RETURN count(s) AS count
"""

COUNT_BY_STATUS = """
MATCH (s:ExtractionScenario)
RETURN
  count(s) AS total,
  count(CASE WHEN s.review_status = 'approved' THEN 1 END) AS approved,
  count(CASE WHEN s.review_status <> 'approved' THEN 1 END) AS draft
"""

# -- Seed (write) ------------------------------------------------------------

MERGE_EXTRACTION_SCENARIO = """
MERGE (s:ExtractionScenario {case_id: $case_id})
ON CREATE SET
  s.case_id               = $case_id,
  s.site                  = $site,
  s.format                = $format,
  s.phrase_classes        = $phrase_classes,
  s.difficulty            = $difficulty,
  s.review_status         = $review_status,
  s.expected_strings      = $expected_strings,
  s.expected_observables  = $expected_observables,
  s.must_not_extract      = $must_not_extract,
  s.markdown_body         = $markdown_body,
  s.source_template_markdown = $source_template_markdown,
  s.notes_for_clinician_review = $notes_for_clinician_review,
  s.synthetic_patient     = $synthetic_patient,
  s.blood_results         = $blood_results,
  s.schema_version        = $schema_version,
  s.created_at            = $created_at,
  s.updated_at            = $created_at
"""

SYNC_EXTRACTION_SCENARIO = """
MERGE (s:ExtractionScenario {case_id: $case_id})
ON CREATE SET
  s.case_id               = $case_id,
  s.site                  = $site,
  s.format                = $format,
  s.phrase_classes        = $phrase_classes,
  s.difficulty            = $difficulty,
  s.review_status         = $review_status,
  s.expected_strings      = $expected_strings,
  s.expected_observables  = $expected_observables,
  s.must_not_extract      = $must_not_extract,
  s.markdown_body         = $markdown_body,
  s.source_template_markdown = $source_template_markdown,
  s.notes_for_clinician_review = $notes_for_clinician_review,
  s.synthetic_patient     = $synthetic_patient,
  s.blood_results         = $blood_results,
  s.schema_version        = $schema_version,
  s.source                = $source,
  s.created_at            = $created_at,
  s.updated_at            = $created_at
ON MATCH SET
  s.site                  = $site,
  s.format                = $format,
  s.phrase_classes        = $phrase_classes,
  s.difficulty            = $difficulty,
  s.expected_strings      = $expected_strings,
  s.expected_observables  = $expected_observables,
  s.must_not_extract      = $must_not_extract,
  s.markdown_body         = $markdown_body,
  s.source_template_markdown = $source_template_markdown,
  s.notes_for_clinician_review = $notes_for_clinician_review,
  s.synthetic_patient     = $synthetic_patient,
  s.blood_results         = $blood_results,
  s.schema_version        = $schema_version,
  s.updated_at            = $updated_at
RETURN s.case_id AS case_id
"""

REFRESH_EXTRACTION_SCENARIO_MARKDOWN_BODY = """
MATCH (s:ExtractionScenario {case_id: $case_id})
WHERE
  s.markdown_body CONTAINS '## Expected Extracted Strings'
  OR s.markdown_body CONTAINS '## Must Not Extract'
  OR s.markdown_body CONTAINS '## Template Source'
  OR s.markdown_body CONTAINS '## Synthetic Patient Details'
  OR s.markdown_body CONTAINS '## Template Excerpt Used'
  OR s.markdown_body CONTAINS '## Completed Template Fields For This Scenario'
  OR s.markdown_body CONTAINS '## Clinician Review Notes'
  OR s.markdown_body CONTAINS 'Template field'
  OR s.markdown_body CONTAINS 'Scenario entry'
  OR s.markdown_body CONTAINS 'extraction scenario'
  OR s.markdown_body CONTAINS 'Reference range'
  OR s.markdown_body CONTAINS '| Flag |'
SET
  s.markdown_body = $markdown_body,
  s.updated_at = $updated_at
RETURN s.case_id AS case_id
"""

# -- List --------------------------------------------------------------------

LIST_EXTRACTION_SCENARIOS = """
MATCH (s:ExtractionScenario)
WHERE
  ($status IS NULL OR s.review_status = $status)
  AND ($site IS NULL OR s.site = $site)
  AND (
    $search IS NULL
    OR toLower(s.case_id) CONTAINS toLower($search)
    OR toLower(s.site) CONTAINS toLower($search)
  )
RETURN
  s.case_id               AS case_id,
  s.site                  AS site,
  s.format                AS format,
  s.phrase_classes        AS phrase_classes,
  s.difficulty            AS difficulty,
  s.review_status         AS review_status,
  s.expected_strings      AS expected_strings,
  s.expected_observables  AS expected_observables,
  s.must_not_extract      AS must_not_extract,
  s.notes_for_clinician_review AS notes_for_clinician_review,
  s.reviewed_by           AS reviewed_by,
  s.reviewed_at           AS reviewed_at,
  s.schema_version        AS schema_version,
  s.created_at            AS created_at,
  s.updated_at            AS updated_at
ORDER BY s.site, s.case_id
"""

# -- Detail ------------------------------------------------------------------

GET_EXTRACTION_SCENARIO = """
MATCH (s:ExtractionScenario {case_id: $case_id})
RETURN
  s.case_id               AS case_id,
  s.site                  AS site,
  s.format                AS format,
  s.phrase_classes        AS phrase_classes,
  s.difficulty            AS difficulty,
  s.review_status         AS review_status,
  s.expected_strings      AS expected_strings,
  s.expected_observables  AS expected_observables,
  s.must_not_extract      AS must_not_extract,
  s.markdown_body         AS markdown_body,
  s.source_template_markdown AS source_template_markdown,
  s.notes_for_clinician_review AS notes_for_clinician_review,
  s.synthetic_patient     AS synthetic_patient,
  s.blood_results         AS blood_results,
  s.reviewed_by           AS reviewed_by,
  s.reviewed_at           AS reviewed_at,
  s.schema_version        AS schema_version,
  s.created_at            AS created_at,
  s.updated_at            AS updated_at
"""

# -- Approve -----------------------------------------------------------------

APPROVE_EXTRACTION_SCENARIO = """
MATCH (s:ExtractionScenario {case_id: $case_id})
SET
  s.review_status = 'approved',
  s.reviewed_by   = $reviewed_by,
  s.reviewed_at   = $reviewed_at,
  s.updated_at    = $reviewed_at
RETURN s.case_id AS case_id, s.review_status AS review_status
"""

# -- CRUD --------------------------------------------------------------------

GET_EXTRACTION_SCENARIO_EXISTS = """
MATCH (s:ExtractionScenario {case_id: $case_id})
RETURN s.case_id AS case_id
LIMIT 1
"""

CREATE_EXTRACTION_SCENARIO = """
CREATE (s:ExtractionScenario {case_id: $case_id})
SET
  s.site                  = $site,
  s.format                = $format,
  s.phrase_classes        = $phrase_classes,
  s.difficulty            = $difficulty,
  s.review_status         = $review_status,
  s.expected_strings      = $expected_strings,
  s.expected_observables  = $expected_observables,
  s.must_not_extract      = $must_not_extract,
  s.markdown_body         = $markdown_body,
  s.source_template_markdown = $source_template_markdown,
  s.notes_for_clinician_review = $notes_for_clinician_review,
  s.synthetic_patient     = $synthetic_patient,
  s.blood_results         = $blood_results,
  s.schema_version        = $schema_version,
  s.source                = $source,
  s.created_at            = $created_at,
  s.updated_at            = $created_at
RETURN s.case_id AS case_id
"""

UPDATE_EXTRACTION_SCENARIO = """
MATCH (s:ExtractionScenario {case_id: $case_id})
SET
  s.site                  = $site,
  s.format                = $format,
  s.phrase_classes        = $phrase_classes,
  s.difficulty            = $difficulty,
  s.review_status         = 'draft_for_clinician_approval',
  s.expected_strings      = $expected_strings,
  s.expected_observables  = $expected_observables,
  s.must_not_extract      = $must_not_extract,
  s.markdown_body         = $markdown_body,
  s.source_template_markdown = $source_template_markdown,
  s.notes_for_clinician_review = $notes_for_clinician_review,
  s.synthetic_patient     = $synthetic_patient,
  s.blood_results         = $blood_results,
  s.reviewed_by           = null,
  s.reviewed_at           = null,
  s.updated_at            = $updated_at
RETURN s.case_id AS case_id, s.review_status AS review_status
"""

DELETE_EXTRACTION_SCENARIO = """
MATCH (s:ExtractionScenario {case_id: $case_id})
DETACH DELETE s
RETURN $case_id AS case_id
"""

# -- Validation run (create) -------------------------------------------------
#
# NOTE on resilience fields (added 2026-05-20):
#   case_ids, child_run_ids, plan_definition_id, case_count, publish_state,
#   published_count are persisted up-front so an API restart, a daemon-thread
#   kill, or a user logout cannot strand a run in "running" with no way to
#   recover. The sweeper (see FIND_STALE_VALIDATION_RUNS) and the GET fallback
#   in extraction_scenarios.get_run both rely on these fields to either
#   finalise the run from AuditEvent rows or mark it failed with a reason.
#
# publish_state vocabulary:
#   "publishing"     - publisher thread is still sending bus messages
#   "published"      - publisher sent every planned message successfully
#   "publish_failed" - publisher thread raised before finishing

CREATE_VALIDATION_RUN = """
MERGE (r:ExtractionValidationRun {run_id: $run_id})
ON CREATE SET
  r.run_id              = $run_id,
  r.triggered_by        = $triggered_by,
  r.status              = $status,
  r.pass_threshold      = $pass_threshold,
  r.model_version       = $model_version,
  r.triggered_at        = $triggered_at,
  r.plan_definition_id  = $plan_definition_id,
  r.model_mode          = $model_mode,
  r.case_ids            = $case_ids,
  r.child_run_ids       = $child_run_ids,
  r.case_count          = $case_count,
  r.publish_state       = $publish_state,
  r.published_count     = $published_count,
  r.atlas_vt_recorded   = false,
  r.atlas_val_recorded  = false
"""

# -- Validation run (publish progress) ---------------------------------------

MARK_VALIDATION_PUBLISH_COMPLETE = """
MATCH (r:ExtractionValidationRun {run_id: $run_id})
SET
  r.publish_state   = 'published',
  r.published_count = $published_count
"""

MARK_VALIDATION_PUBLISH_FAILED = """
MATCH (r:ExtractionValidationRun {run_id: $run_id})
SET
  r.publish_state   = 'publish_failed',
  r.published_count = $published_count,
  r.failure_reason  = $failure_reason
"""

# -- Validation run (complete) -----------------------------------------------

COMPLETE_VALIDATION_RUN = """
MATCH (r:ExtractionValidationRun {run_id: $run_id})
SET
  r.status            = $status,
  r.overall_f1        = $overall_f1,
  r.overall_precision = $overall_precision,
  r.overall_recall    = $overall_recall,
  r.passed            = $passed,
  r.per_case_results  = $per_case_results,
  r.completed_at      = $completed_at
"""

# -- Validation run (mark failed) --------------------------------------------
# Used by the sweeper and by the synchronous get_run fallback to clear stuck
# rows so the UI does not show phantom "running" indefinitely.

FAIL_VALIDATION_RUN = """
MATCH (r:ExtractionValidationRun {run_id: $run_id})
WHERE r.status IN ['queued','running'] AND r.completed_at IS NULL
SET
  r.status         = 'failed',
  r.completed_at   = $completed_at,
  r.failure_reason = $failure_reason,
  r.passed         = false
RETURN r.run_id AS run_id, r.failure_reason AS failure_reason
"""

CREATE_RAN_AGAINST_EDGE = """
MATCH (r:ExtractionValidationRun {run_id: $run_id})
MATCH (s:ExtractionScenario {case_id: $case_id})
MERGE (r)-[:RAN_AGAINST]->(s)
"""

# -- Validation run (read) ---------------------------------------------------

GET_VALIDATION_RUN = """
MATCH (r:ExtractionValidationRun {run_id: $run_id})
RETURN
  r.run_id              AS run_id,
  r.triggered_by        AS triggered_by,
  r.status              AS status,
  r.overall_f1          AS overall_f1,
  r.overall_precision   AS overall_precision,
  r.overall_recall      AS overall_recall,
  r.pass_threshold      AS pass_threshold,
  r.passed              AS passed,
  r.per_case_results    AS per_case_results,
  r.model_version       AS model_version,
  r.model_mode          AS model_mode,
  r.plan_definition_id  AS plan_definition_id,
  r.case_ids            AS case_ids,
  r.child_run_ids       AS child_run_ids,
  r.case_count          AS case_count,
  r.publish_state       AS publish_state,
  r.published_count     AS published_count,
  r.failure_reason      AS failure_reason,
  r.triggered_at        AS triggered_at,
  r.completed_at        AS completed_at,
  r.atlas_vt_recorded   AS atlas_vt_recorded,
  r.atlas_val_recorded  AS atlas_val_recorded
"""

# -- Sweeper: find stuck runs older than $cutoff_at --------------------------

FIND_STALE_VALIDATION_RUNS = """
MATCH (r:ExtractionValidationRun)
WHERE r.status IN ['queued','running']
  AND r.completed_at IS NULL
  AND r.triggered_at < $cutoff_at
RETURN
  r.run_id              AS run_id,
  r.triggered_at        AS triggered_at,
  r.case_ids            AS case_ids,
  r.child_run_ids       AS child_run_ids,
  r.case_count          AS case_count,
  r.publish_state       AS publish_state,
  r.published_count     AS published_count
ORDER BY r.triggered_at
LIMIT 50
"""

LATEST_COMPLETED_RUN = """
MATCH (r:ExtractionValidationRun)
WHERE r.status = 'completed'
RETURN
  r.run_id            AS run_id,
  r.triggered_by      AS triggered_by,
  r.overall_f1        AS overall_f1,
  r.overall_precision AS overall_precision,
  r.overall_recall    AS overall_recall,
  r.pass_threshold    AS pass_threshold,
  r.passed            AS passed,
  r.per_case_results  AS per_case_results,
  r.triggered_at      AS triggered_at,
  r.completed_at      AS completed_at,
  r.atlas_vt_recorded AS atlas_vt_recorded,
  r.atlas_val_recorded AS atlas_val_recorded
ORDER BY r.triggered_at DESC
LIMIT 1
"""

# -- Atlas recording ---------------------------------------------------------

MARK_ATLAS_RECORDED = """
MATCH (r:ExtractionValidationRun {run_id: $run_id})
SET
  r.atlas_vt_recorded  = $atlas_vt_recorded,
  r.atlas_val_recorded = $atlas_val_recorded
"""
