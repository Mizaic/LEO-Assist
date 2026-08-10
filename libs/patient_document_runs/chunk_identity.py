"""Normalize legacy :Chunk nodes that lack c.id for pipeline re-runs."""

from __future__ import annotations

from typing import Any

from libs.cypher.chunk_queries import chunk_sha256, make_chunk_id

_LIST_RAW_CHUNKS = """
MATCH (dr:DocumentReference {id: $document_reference_id})-[r:HAS_CHUNK]->(c:Chunk)
RETURN coalesce(toString(c.id), '') AS id,
       r.ordinal AS r_ordinal,
       c.ordinal AS c_ordinal,
       c.chunk_idx AS chunk_idx,
       coalesce(c.text, '') AS text
ORDER BY coalesce(r.ordinal, c.chunk_idx, c.ordinal, 0) ASC
LIMIT $limit
"""

_BACKFILL_CHUNK_ID = """
MATCH (dr:DocumentReference {id: $document_reference_id})-[r:HAS_CHUNK]->(c:Chunk)
WHERE coalesce(c.text, '') = $text
  AND coalesce(r.ordinal, c.chunk_idx, c.ordinal, -1) = $ordinal
SET c.id = $chunk_id,
    c.ordinal = $ordinal,
    c.document_reference_id = $document_reference_id,
    c.updated_at = datetime(),
    c.created_at = coalesce(c.created_at, datetime())
RETURN c.id AS id
LIMIT 1
"""


def chunk_ordinal(row: dict[str, Any]) -> int:
    """Resolve display/processing ordinal for legacy and canonical chunks."""
    if row.get("r_ordinal") is not None:
        return int(row["r_ordinal"])
    if row.get("chunk_idx") is not None:
        return int(row["chunk_idx"])
    if row.get("c_ordinal") is not None:
        return int(row["c_ordinal"])
    return int(row.get("ordinal") or 0)


def expected_chunk_id(document_reference_id: str, row: dict[str, Any]) -> str:
    text = str(row.get("text") or "")
    ordinal = chunk_ordinal(row)
    return make_chunk_id(document_reference_id, ordinal, chunk_sha256(text))


def resolve_chunk_id(document_reference_id: str, row: dict[str, Any]) -> str:
    """Return persisted or deterministic chunk id for a graph row."""
    existing = str(row.get("id") or "").strip()
    expected = expected_chunk_id(document_reference_id, row)
    if existing and existing != expected:
        return expected
    if existing:
        return existing
    return expected


def normalize_chunk_row(
    document_reference_id: str,
    row: dict[str, Any],
) -> dict[str, Any]:
    chunk_id = resolve_chunk_id(document_reference_id, row)
    stored_id = str(row.get("id") or "").strip()
    return {
        "id": chunk_id,
        "ordinal": chunk_ordinal(row),
        "text": str(row.get("text") or ""),
        "legacy_missing_id": not stored_id,
        "legacy_mismatched_id": bool(stored_id and stored_id != chunk_id),
    }


def list_document_chunks_normalized(
    client: Any,
    *,
    document_reference_id: str,
    limit: int = 500,
    backfill_legacy_ids: bool = True,
) -> list[dict[str, Any]]:
    """List chunks under a DocumentReference with stable ids."""
    rows = client.run(
        _LIST_RAW_CHUNKS,
        document_reference_id=document_reference_id,
        limit=limit,
    )
    out: list[dict[str, Any]] = []
    for raw in rows or []:
        row = dict(raw)
        normalized = normalize_chunk_row(document_reference_id, row)
        if not normalized["text"].strip() and normalized["legacy_missing_id"]:
            continue
        if backfill_legacy_ids and (
            normalized["legacy_missing_id"] or normalized["legacy_mismatched_id"]
        ):
            client.run(
                _BACKFILL_CHUNK_ID,
                document_reference_id=document_reference_id,
                chunk_id=normalized["id"],
                ordinal=normalized["ordinal"],
                text=normalized["text"],
            )
        out.append(
            {
                "id": normalized["id"],
                "ordinal": normalized["ordinal"],
                "text": normalized["text"],
            }
        )
    return out
