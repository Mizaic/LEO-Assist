"""Cypher queries for the :Chunk node and :HAS_CHUNK relationship.

Atlas trace:
  DO: DO-F8EFEF89
  DI: DI-E47C3FC2
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-F8EFEF89")

A :Chunk represents a sub-segment of a DocumentReference text body
(typically a sentence or short paragraph) that can independently carry
SNOMED concept evidence via :DOCUMENTS relationships:

    (DocumentReference)-[:HAS_CHUNK {ordinal, char_start, char_end}]->(Chunk)
    (Chunk)-[:DOCUMENTS]->(Concept)

This is required for long referral letters where the whole document is
too coarse to attach codes to. See DI-LEO-AI-185.

All write/upsert queries are idempotent: chunks are uniquely identified
by their ``id`` (a hash of (document_reference_id, ordinal, sha256)),
so re-ingesting the same document does not duplicate chunks.
"""

from __future__ import annotations

import hashlib
from typing import Any

# -- Constraint / index DDL -------------------------------------------------

CHUNK_CONSTRAINTS: list[str] = [
    "CREATE CONSTRAINT chunk_id IF NOT EXISTS " "FOR (c:Chunk) REQUIRE c.id IS UNIQUE",
    "CREATE INDEX chunk_document_reference IF NOT EXISTS "
    "FOR (c:Chunk) ON (c.document_reference_id)",
    "CREATE INDEX chunk_sha256 IF NOT EXISTS " "FOR (c:Chunk) ON (c.sha256)",
]


# -- Helpers ----------------------------------------------------------------


def make_chunk_id(document_reference_id: str, ordinal: int, sha256: str) -> str:
    """Deterministic chunk ID. Re-running ingestion is a no-op."""
    raw = f"{document_reference_id}:{ordinal}:{sha256}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def chunk_sha256(text: str) -> str:
    """SHA-256 of the de-identified chunk text."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


# -- Queries ----------------------------------------------------------------

UPSERT_CHUNK = """
MATCH (dr:DocumentReference {id: $document_reference_id})
MERGE (c:Chunk {id: $chunk_id})
SET c.document_reference_id = $document_reference_id,
    c.text                  = $text,
    c.sha256                = $sha256,
    c.char_start            = $char_start,
    c.char_end              = $char_end,
    c.ordinal               = $ordinal,
    c.tenantId              = CASE
        WHEN $tenant_id <> '' THEN $tenant_id
        ELSE c.tenantId END,
    c.updated_at            = datetime(),
    c.created_at            = coalesce(c.created_at, datetime())
MERGE (dr)-[r:HAS_CHUNK]->(c)
SET r.ordinal     = $ordinal,
    r.char_start  = $char_start,
    r.char_end    = $char_end
RETURN c.id AS chunk_id
"""


GET_CHUNKS_FOR_DOCUMENT_REFERENCE = """
MATCH (dr:DocumentReference {id: $document_reference_id})-[r:HAS_CHUNK]->(c:Chunk)
RETURN c.id          AS chunk_id,
       c.text        AS text,
       c.sha256      AS sha256,
       r.ordinal     AS ordinal,
       r.char_start  AS char_start,
       r.char_end    AS char_end
ORDER BY r.ordinal ASC
"""


GET_CHUNKS_BY_IDS = """
UNWIND $chunk_ids AS cid
MATCH (c:Chunk {id: cid})
RETURN c.id          AS chunk_id,
       c.text        AS text,
       c.sha256      AS sha256,
       c.ordinal     AS ordinal,
       c.char_start  AS char_start,
       c.char_end    AS char_end
ORDER BY c.ordinal ASC
"""


GET_CHUNK_WITH_CODES = """
MATCH (c:Chunk {id: $chunk_id})
OPTIONAL MATCH (c)-[d:DOCUMENTS]->(s)
RETURN c.id          AS chunk_id,
       c.text        AS text,
       c.sha256      AS sha256,
       c.ordinal     AS ordinal,
       collect({
         concept_id:    toString(s.conceptId),
         term:          s.name,
         semantic_tag:  s.semanticTag,
         evidence:      d.evidence,
         confidence:    d.confidence,
         assertion:     d.context
       }) AS codes
"""


GET_REASON_CHUNKS_BY_IDS = """
UNWIND $chunk_ids AS cid
MATCH (c:Chunk {id: cid})
WHERE any(pat IN $patterns WHERE toLower(c.text) CONTAINS pat)
RETURN c.id AS chunk_id, c.text AS text, c.ordinal AS ordinal
ORDER BY ordinal ASC
LIMIT 3
"""


SET_REFERRAL_REASON = """
MATCH (rr:ReferralRequest {id: $referral_id})
SET rr.reason               = $reason,
    rr.reason_extracted_at  = datetime()
"""


def upsert_chunk_payload(
    *,
    document_reference_id: str,
    ordinal: int,
    text: str,
    char_start: int,
    char_end: int,
    session: Any,
    tenant_id: str = "",
) -> str:
    """Idempotently upsert a :Chunk under the given DocumentReference.

    Returns the chunk_id.
    """
    sha = chunk_sha256(text)
    chunk_id = make_chunk_id(document_reference_id, ordinal, sha)
    session.run(
        UPSERT_CHUNK,
        document_reference_id=document_reference_id,
        chunk_id=chunk_id,
        text=text,
        sha256=sha,
        char_start=char_start,
        char_end=char_end,
        ordinal=ordinal,
        tenant_id=tenant_id,
    )
    return chunk_id
