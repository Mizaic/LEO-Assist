"""Read-only Cypher for A&G communication_thread pipeline loading."""

from __future__ import annotations

LIST_THREAD_WITH_MESSAGE_ATTACHMENTS = """
MATCH (cr:CommunicationRequest {id: $communication_request_id})
      -[:HAS_CONVERSATION]->(c:Communication)
OPTIONAL MATCH (c)-[:HAS_DOCUMENT]->(dr:DocumentReference)
      -[:HAS_CHUNK]->(ch:Chunk)
WHERE ch.id IS NOT NULL AND trim(coalesce(ch.text, '')) <> ''
WITH c,
     collect(DISTINCT {
       chunk_id: ch.id,
       text: ch.text,
       ordinal: coalesce(ch.ordinal, 0)
     }) AS attachment_chunks
RETURN c.id AS communication_id,
       c.note AS note,
       c.category AS category,
       toString(c.sent_datetime) AS sent_datetime,
       attachment_chunks
ORDER BY c.sent_datetime ASC
"""

LIST_CR_LEVEL_ATTACHMENTS = """
MATCH (cr:CommunicationRequest {id: $communication_request_id})
      -[:HAS_DOCUMENT]->(dr:DocumentReference)
      -[:HAS_CHUNK]->(ch:Chunk)
WHERE trim(coalesce(ch.text, '')) <> ''
  AND NOT EXISTS {
    MATCH (:Communication)-[:HAS_DOCUMENT]->(dr)
  }
RETURN dr.id AS document_reference_id,
       ch.id AS chunk_id,
       ch.text AS text,
       coalesce(ch.ordinal, 0) AS ordinal
ORDER BY ordinal ASC, chunk_id ASC
"""

READ_FORMAL_AGR_RESPONSE = """
MATCH (cr:CommunicationRequest {id: $communication_request_id})
      -[:HAS_RESPONSE]->(agr:AdviceAndGuidanceResponse)
RETURN agr.responseText AS response_text
ORDER BY agr.updated_at DESC
LIMIT 1
"""

RESOLVE_COMMUNICATION_REQUEST_BY_UBRN = """
MATCH (cr:CommunicationRequest {ubrn: $ubrn})-[:FOR_PATIENT]->(p:Patient)
RETURN cr.id AS communication_request_id,
       cr.ubrn AS ubrn,
       p.id AS patient_id
LIMIT 1
"""
