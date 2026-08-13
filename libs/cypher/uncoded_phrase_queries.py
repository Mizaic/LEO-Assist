"""Cypher for grouped pipeline-rejected phrases (Phrase mappings inbox).

Atlas trace:
  DI: DI-D90542E5
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-D90542E5")
"""

UPSERT_UNCODED_PHRASE = """
MERGE (u:UncodedPhrase {phrase_key: $phrase_key})
ON CREATE SET
    u.normalized = $normalized,
    u.note_count = 1,
    u.status = 'inbox',
    u.created_at = datetime()
ON MATCH SET
    u.note_count = coalesce(u.note_count, 0) + 1
SET u.extracted_tag = $extracted_tag,
    u.last_score = $last_score,
    u.last_best_term = $last_best_term,
    u.last_best_concept = $last_best_concept,
    u.last_best_tag = $last_best_tag,
    u.sample_span = $sample_span,
    u.sample_sentence = $sample_sentence,
    u.last_seen_at = datetime(),
    u.status = CASE
        WHEN u.status IN ['draft', 'review', 'closed'] THEN u.status
        ELSE 'inbox'
    END
RETURN u.phrase_key AS phrase_key, u.note_count AS note_count, u.status AS status
"""

COUNT_UNCODED_BY_STATUS = """
MATCH (u:UncodedPhrase)
RETURN u.status AS status, count(u) AS total
"""

COUNT_MY_DRAFTS = """
MATCH (u:UncodedPhrase)
WHERE u.status = 'draft' AND u.draft_author = $author
RETURN count(u) AS total
"""

LIST_UNCODED_PHRASES = """
MATCH (u:UncodedPhrase)
WHERE u.status = $status
  AND ($author = '' OR u.draft_author = $author)
RETURN
    u.phrase_key AS phrase_key,
    u.normalized AS normalized,
    u.extracted_tag AS extracted_tag,
    u.note_count AS note_count,
    u.last_score AS last_score,
    u.last_best_term AS last_best_term,
    u.last_best_concept AS last_best_concept,
    u.last_best_tag AS last_best_tag,
    u.sample_span AS sample_span,
    u.sample_sentence AS sample_sentence,
    u.status AS status,
    u.draft_action AS draft_action,
    u.draft_concept_id AS draft_concept_id,
    u.draft_concept_term AS draft_concept_term,
    u.draft_reason AS draft_reason,
    u.draft_author AS draft_author,
    toString(u.last_seen_at) AS last_seen_at
ORDER BY coalesce(u.note_count, 0) DESC, u.normalized
SKIP $skip
LIMIT $limit
"""

COUNT_UNCODED_PHRASES = """
MATCH (u:UncodedPhrase)
WHERE u.status = $status
RETURN count(u) AS total
"""

GET_UNCODED_PHRASE = """
MATCH (u:UncodedPhrase {phrase_key: $phrase_key})
RETURN
    u.phrase_key AS phrase_key,
    u.normalized AS normalized,
    u.extracted_tag AS extracted_tag,
    u.note_count AS note_count,
    u.last_score AS last_score,
    u.last_best_term AS last_best_term,
    u.last_best_concept AS last_best_concept,
    u.last_best_tag AS last_best_tag,
    u.sample_span AS sample_span,
    u.sample_sentence AS sample_sentence,
    u.status AS status,
    u.draft_action AS draft_action,
    u.draft_concept_id AS draft_concept_id,
    u.draft_concept_term AS draft_concept_term,
    u.draft_reason AS draft_reason,
    u.draft_author AS draft_author,
    toString(u.last_seen_at) AS last_seen_at
"""

SAVE_UNCODED_DRAFT = """
MATCH (u:UncodedPhrase {phrase_key: $phrase_key})
WHERE u.status IN ['inbox', 'draft']
SET u.status = 'draft',
    u.draft_action = $draft_action,
    u.draft_concept_id = $draft_concept_id,
    u.draft_concept_term = $draft_concept_term,
    u.draft_reason = $draft_reason,
    u.draft_author = $draft_author,
    u.updated_at = datetime()
RETURN u.phrase_key AS phrase_key, u.status AS status
"""

SUBMIT_UNCODED_DRAFTS = """
MATCH (u:UncodedPhrase)
WHERE u.status = 'draft' AND u.draft_author = $author
SET u.status = 'review',
    u.updated_at = datetime()
RETURN count(u) AS submitted
"""

SEND_BACK_UNCODED_PHRASE = """
MATCH (u:UncodedPhrase {phrase_key: $phrase_key})
WHERE u.status = 'review'
SET u.status = 'draft',
    u.updated_at = datetime()
RETURN u.phrase_key AS phrase_key, u.status AS status
"""

CLOSE_UNCODED_PHRASE = """
MATCH (u:UncodedPhrase {phrase_key: $phrase_key})
WHERE u.status = 'review'
SET u.status = 'closed',
    u.published_by = $published_by,
    u.published_at = datetime(),
    u.updated_at = datetime()
RETURN u.phrase_key AS phrase_key, u.status AS status,
       u.draft_action AS draft_action,
       u.draft_author AS draft_author,
       u.normalized AS normalized,
       u.extracted_tag AS extracted_tag,
       u.draft_concept_id AS draft_concept_id,
       u.draft_concept_term AS draft_concept_term,
       u.draft_reason AS draft_reason
"""
