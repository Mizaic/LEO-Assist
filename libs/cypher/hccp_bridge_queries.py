"""Cypher helpers for the HCCP chunks-ready bridge.

Atlas trace:
  DI: DI-6B52E28E
  DO: DO-4B8D8AEB
  VT: VT-66810B48
"""

from __future__ import annotations

import json
from typing import Any

from libs.hccp.events import HCCPChunkRef


RESOLVE_HCCP_CHUNK_REF = """
MATCH (dr:DocumentReference {id: $document_reference_id})-[:HAS_CHUNK]->(c:Chunk)
WHERE c.id = $chunk_id
   OR toString(c.chunk_idx) = $chunk_id
   OR ($chunk_idx IS NOT NULL AND c.chunk_idx = $chunk_idx)
   OR toString(c.ordinal) = $chunk_id
   OR ($chunk_idx IS NOT NULL AND c.ordinal = $chunk_idx)
RETURN coalesce(c.id, toString(c.chunk_idx)) AS chunk_id,
       dr.id AS document_reference_id,
       coalesce(c.chunk_idx, c.ordinal) AS chunk_idx,
       coalesce(c.text, '') AS text,
       c.category_key AS category_key
LIMIT 1
"""


UPDATE_HCCP_DATA_REQUEST_STATUS = """
MATCH (dr:DataRequest {id: $data_request_id})
SET dr.status = $status,
    dr.updated = datetime(),
    dr.updated_at = datetime(),
    dr.core_ai_summary_json = $summary_json,
    dr.error = $error
RETURN dr.status AS status
"""


def _record_to_dict(record: Any) -> dict[str, Any] | None:
    if record is None:
        return None
    if isinstance(record, dict):
        return dict(record)
    return dict(record)


def resolve_hccp_chunk_ref(session: Any, ref: HCCPChunkRef) -> dict[str, Any] | None:
    """Resolve a Core or HCCP chunk reference to the graph Chunk row."""
    result = session.run(
        RESOLVE_HCCP_CHUNK_REF,
        document_reference_id=ref.document_reference_id,
        chunk_id=ref.chunk_id,
        chunk_idx=ref.chunk_idx,
    )
    return _record_to_dict(result.single())


def update_hccp_data_request_status(
    session: Any,
    *,
    data_request_id: str,
    status: str,
    summary: dict[str, Any],
    error: str | None,
) -> None:
    """Write the HCCP-visible terminal DataRequest status."""
    session.run(
        UPDATE_HCCP_DATA_REQUEST_STATUS,
        data_request_id=data_request_id,
        status=status,
        summary_json=json.dumps(summary, sort_keys=True),
        error=error,
    )
