"""Cypher queries for the unified /work task queue (DI-LEO-AI-138).

All three sources (CodingReview, SafetyNetAlert, TrainingCandidate pending)
are returned in one Cypher UNION so the per-source counts on the landing
page and the page of rendered rows cannot drift against each other.

Row shape:
    task_id     - str, unique across sources
    task_type   - one of 'coding_review' | 'safety_net_alert' | 'gold_label'
    severity    - int 1..5 (5 = most urgent)
    summary     - plain-English one liner, FK grade <= 9
    age_days    - int, days since the task became actionable
    resolve_url - app-relative URL that deep-links to the resolver UI
    patient_id  - str | null
    episode_id  - str | null

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
         ).days AS age_days
    RETURN
        'coding_review:' + cr.review_id AS task_id,
        'coding_review'                 AS task_type,
        severity                        AS severity,
        'Code check: ' + coalesce(cr.entity_text, '(empty)') AS summary,
        age_days                        AS age_days,
        '/admin/operations/reviews?review_id=' + cr.review_id AS resolve_url,
        p.id                            AS patient_id,
        ep.episode_id                   AS episode_id

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
        ep.episode_id                    AS episode_id

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
        NULL                           AS episode_id
}
WITH task_id, task_type, severity, summary, age_days, resolve_url,
     patient_id, episode_id
WHERE ($sources IS NULL OR task_type IN $sources)
RETURN task_id, task_type, severity, summary, age_days, resolve_url,
       patient_id, episode_id
ORDER BY severity DESC, age_days DESC, task_id
SKIP $offset
LIMIT $limit
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
}
RETURN task_type, total
"""
