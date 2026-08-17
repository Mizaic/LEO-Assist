"""Digest queries for gated LEO phone-home tickets.

Atlas: DI-C7DEF132
"""

LIST_PHONE_HOME_UNCODED = """
MATCH (u:UncodedPhrase)
WHERE u.status = 'inbox' AND coalesce(u.note_count, 0) >= $threshold
RETURN u.phrase_key AS key,
       u.extracted_tag AS tag,
       u.note_count AS count
ORDER BY u.note_count DESC
LIMIT 50
"""

LIST_PHONE_HOME_CANDIDATES = """
MATCH (c:TrainingCandidate)
WHERE c.status = 'pending'
  AND c.source IN ['pipeline_hitl_ner', 'pipeline_hitl_coding']
WITH c.source AS source,
     coalesce(c.hitl_reason, 'unknown') AS reason,
     count(*) AS count
WHERE count >= $threshold
RETURN source AS source, reason AS key, count AS count
ORDER BY count DESC
LIMIT 50
"""
