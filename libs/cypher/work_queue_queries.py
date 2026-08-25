"""Cypher queries for the unified /work task queue.

Atlas trace:
  DI: DI-6BD7B681
  DO: DO-E12EC9C0
  VT: VT-76C15B0E

All five patient-graph sources are returned in one Cypher UNION so the
per-source counts on the landing page and the page of rendered rows cannot
drift against each other.

Row shape:
    task_id      - str, unique across sources
    task_type    - one of the VALID_SOURCES values
    severity     - int 1..5 (5 = most urgent)
    summary      - plain-English one liner, FK grade <= 9
    age_days     - int, days since the task became actionable
    resolve_url  - app-relative URL that deep-links to the resolver UI
    patient_id   - str | null
    episode_id   - str | null
    failure_kind - short machine tag naming what went wrong (see below)

failure_kind values:
    no_code          - CodingReview: no SNOMED code could be found
    wrong_kind       - CodingReview: code found but type or tag mismatch
    assertion_check  - CodingReview: assertion is not 'present'
    safety_flag      - SafetyNetAlert: open safety alert
    needs_gold_label - TrainingCandidate: pending expert label
    unseen_form      - HITLTask: paused extraction (unknown form or OOD)
    new_phrase       - SurfaceFormTask: new phrase needs approval

Severity mapping:
    CodingReview.decision_tier 3 -> severity 4 (needs human review)
    CodingReview.decision_tier 2 -> severity 3
    CodingReview anything else   -> severity 2
    SafetyNetAlert.severity 'critical' -> 5
    SafetyNetAlert.severity 'warning'  -> 4
    SafetyNetAlert anything else       -> 3
    TrainingCandidate (pending)        -> 2
"""

GET_UNIFIED_WORK_TASKS = """
CALL {
    // -- CodingReview --
    MATCH (cr:CodingReview)-[:REVIEWS_CODING]->(t:TrainingLabel)
    WHERE cr.resolved = false
      AND t.include = true
    OPTIONAL MATCH (t)<-[:HAS_LABEL]-(doc:Document)<-[:HAS_DOCUMENT]-(p:Patient)
    OPTIONAL MATCH (doc)-[:FOR_EPISODE]->(ep:EpisodeOfCare)
    WITH cr, t, p, ep,
         CASE coalesce(cr.decision_tier, 0)
              WHEN 3 THEN 4
              WHEN 2 THEN 3
              ELSE 2
         END AS severity,
         duration.inDays(
             coalesce(cr.updated_at, cr.created_at, datetime()),
             datetime()
         ).days AS age_days,
         CASE
             WHEN coalesce(cr.coded, true) = false THEN 'no_code'
             WHEN cr.suggested_label IS NOT NULL
                  OR cr.tag_mismatch_delta IS NOT NULL THEN 'wrong_kind'
             WHEN coalesce(cr.assertion, 'present') <> 'present' THEN 'assertion_check'
             ELSE 'no_code'
         END AS failure_kind
    RETURN
        'coding_review:' + cr.review_id AS task_id,
        'coding_review'                 AS task_type,
        severity                        AS severity,
        CASE
            WHEN coalesce(cr.coded, true) = false
                THEN 'No safe code yet: ' + coalesce(cr.entity_text, '(empty)')
            WHEN cr.suggested_label IS NOT NULL
                 OR cr.tag_mismatch_delta IS NOT NULL
                THEN 'Wrong kind of code: ' + coalesce(cr.entity_text, '(empty)')
            WHEN coalesce(cr.assertion, 'present') <> 'present'
                THEN 'Check assertion: ' + coalesce(cr.entity_text, '(empty)')
            ELSE 'Code check: ' + coalesce(cr.entity_text, '(empty)')
        END AS summary,
        age_days                        AS age_days,
        '/admin/operations/reviews?review_id=' + cr.review_id AS resolve_url,
        p.id                            AS patient_id,
        ep.episode_id                   AS episode_id,
        failure_kind                    AS failure_kind

    UNION ALL

    // -- SafetyNetAlert --
    MATCH (a:SafetyNetAlert)
    WHERE a.status = 'open' AND coalesce(a.actioned, false) = false
    OPTIONAL MATCH (p:Patient)-[:HAS_SAFETY_NET_ALERT]->(a)
    OPTIONAL MATCH (a)-[:FOR_EPISODE]->(ep:EpisodeOfCare)
    WITH a, p, ep,
         CASE coalesce(a.severity, 'info')
              WHEN 'critical' THEN 5
              WHEN 'warning'  THEN 4
              ELSE 3
         END AS severity,
         duration.inDays(
             coalesce(a.created_at, datetime()),
             datetime()
         ).days AS age_days
    RETURN
        'safety_net_alert:' + a.alert_id AS task_id,
        'safety_net_alert'               AS task_type,
        severity                         AS severity,
        'Safety alert: ' + coalesce(
            a.description, a.alert_type, 'needs review'
        )                                AS summary,
        age_days                         AS age_days,
        '/safety-netting?alert_id=' + a.alert_id AS resolve_url,
        p.id                             AS patient_id,
        ep.episode_id                    AS episode_id,
        'safety_flag'                    AS failure_kind

    UNION ALL

    // -- TrainingCandidate (pending gold label) --
    MATCH (c:TrainingCandidate)
    WHERE c.status = 'pending'
    WITH c,
         2 AS severity,
         duration.inDays(
             coalesce(c.created_at, datetime()),
             datetime()
         ).days AS age_days
    RETURN
        'gold_label:' + c.candidate_id AS task_id,
        'gold_label'                   AS task_type,
        severity                       AS severity,
        'Label review: ' + coalesce(
            substring(c.text, 0, 80),
            '(no preview)'
        )                              AS summary,
        age_days                       AS age_days,
        '/admin/knowledge?tab=training-data&candidate_id='
            + c.candidate_id          AS resolve_url,
        NULL                           AS patient_id,
        NULL                           AS episode_id,
        'needs_gold_label'             AS failure_kind

    UNION ALL

    // -- HITLTask (paused LLM extraction awaiting human review) --
    MATCH (t:HITLTask)
    WHERE t.status = 'pending'
      AND t.task_type = 'extraction_quality_review'
    WITH t,
         3 AS severity,
         duration.inDays(
             coalesce(t.created_at, datetime()),
             datetime()
         ).days AS age_days
    RETURN
        'extraction_quality_pause:' + t.task_id AS task_id,
        'extraction_quality_pause'              AS task_type,
        severity                                AS severity,
        'Paused extraction: ' + coalesce(t.patient_id, '(unknown)') AS summary,
        age_days                                AS age_days,
        '/admin/knowledge?tab=validation-lab&hitl_task_id=' + t.task_id AS resolve_url,
        t.patient_id                            AS patient_id,
        NULL                                    AS episode_id,
        'unseen_form'                           AS failure_kind

    UNION ALL

    // -- SurfaceFormTask (new phrase mapping awaiting approval) --
    MATCH (t:SurfaceFormTask)
    WHERE t.status = 'pending'
    WITH t,
         2 AS severity,
         duration.inDays(
             coalesce(t.created_at, datetime()),
             datetime()
         ).days AS age_days
    RETURN
        'surface_form_approval:' + t.task_id AS task_id,
        'surface_form_approval'              AS task_type,
        severity                             AS severity,
        'New phrase to approve: ' + coalesce(t.entity_text, '(unknown)') AS summary,
        age_days                             AS age_days,
        '/admin/knowledge?tab=surface-forms' AS resolve_url,
        NULL                                 AS patient_id,
        NULL                                 AS episode_id,
        'new_phrase'                         AS failure_kind
}
WITH task_id, task_type, severity, summary, age_days, resolve_url,
     patient_id, episode_id, failure_kind
WHERE ($sources IS NULL OR task_type IN $sources)
RETURN task_id, task_type, severity, summary, age_days, resolve_url,
       patient_id, episode_id, failure_kind
ORDER BY severity DESC, age_days DESC, task_id
SKIP $offset
LIMIT $limit
"""


# -- Knowledge-graph queries (run against KnowledgeGraphClient) ---------------
# UncodedPhrase lives in the knowledge graph, so these cannot be UNION'd
# into GET_UNIFIED_WORK_TASKS which runs on the patient graph session.
# libs/work/queue.py merges the results in Python.

GET_PHRASE_PUBLISH_TASKS = """
MATCH (u:UncodedPhrase)
WHERE u.status = 'review'
WITH u,
     3 AS severity,
     duration.inDays(
         coalesce(u.updated_at, u.created_at, datetime()),
         datetime()
     ).days AS age_days
RETURN
    'phrase_publish:' + u.phrase_key  AS task_id,
    'phrase_publish'                  AS task_type,
    severity                          AS severity,
    'Change to publish: ' + coalesce(u.normalized, u.phrase_key) AS summary,
    age_days                          AS age_days,
    '/work'                           AS resolve_url,
    NULL                              AS patient_id,
    NULL                              AS episode_id,
    'change_to_publish'               AS failure_kind,
    coalesce(u.draft_author, '')      AS draft_author,
    coalesce(u.draft_action, '')      AS draft_action
ORDER BY age_days DESC, task_id
SKIP $offset
LIMIT $limit
"""

COUNT_PHRASE_PUBLISH_TASKS = """
MATCH (u:UncodedPhrase)
WHERE u.status = 'review'
RETURN count(u) AS total
"""

COUNT_WORK_TASKS_BY_SOURCE = """
CALL {
    MATCH (cr:CodingReview)-[:REVIEWS_CODING]->(t:TrainingLabel)
    WHERE cr.resolved = false AND t.include = true
    RETURN 'coding_review' AS task_type, count(cr) AS total

    UNION ALL

    MATCH (a:SafetyNetAlert)
    WHERE a.status = 'open' AND coalesce(a.actioned, false) = false
    RETURN 'safety_net_alert' AS task_type, count(a) AS total

    UNION ALL

    MATCH (c:TrainingCandidate)
    WHERE c.status = 'pending'
    RETURN 'gold_label' AS task_type, count(c) AS total

    UNION ALL

    MATCH (t:HITLTask)
    WHERE t.status = 'pending' AND t.task_type = 'extraction_quality_review'
    RETURN 'extraction_quality_pause' AS task_type, count(t) AS total

    UNION ALL

    MATCH (t:SurfaceFormTask)
    WHERE t.status = 'pending'
    RETURN 'surface_form_approval' AS task_type, count(t) AS total
}
RETURN task_type, total
"""
