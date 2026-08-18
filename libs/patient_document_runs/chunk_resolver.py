"""Resolve pipeline chunks for referral-linked documents.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")

Clinical Information PDFs often have no :Chunk nodes. Chunks usually
live on the referral bundle ({referral_id}:leo-referral-bundle) or on
a sibling Word or form DocumentReference under the same ReferralRequest.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from libs.patient_document_runs.chunk_identity import list_document_chunks_normalized

_SIBLING_SOURCE = """
MATCH (rr:ReferralRequest {id: $referral_id})-[:HAS_DOCUMENT]->(sibling:DocumentReference)
WHERE sibling.id <> $document_reference_id
MATCH (sibling)-[:HAS_CHUNK]->(:Chunk)
RETURN toString(sibling.id) AS source_document_id, count(*) AS chunk_count
ORDER BY chunk_count DESC
LIMIT 1
"""


@dataclass(frozen=True)
class ResolvedPipelineChunks:
    chunks: list[dict[str, Any]]
    source_document_id: str
    resolution: str


def resolve_pipeline_chunks(
    client: Any,
    *,
    document_reference_id: str,
    referral_id: str | None,
    limit: int = 500,
    backfill_legacy_ids: bool = True,
) -> ResolvedPipelineChunks:
    direct = list_document_chunks_normalized(
        client,
        document_reference_id=document_reference_id,
        limit=limit,
        backfill_legacy_ids=backfill_legacy_ids,
    )
    if direct:
        return ResolvedPipelineChunks(
            chunks=direct,
            source_document_id=document_reference_id,
            resolution="direct",
        )

    rid = str(referral_id or "").strip()
    if not rid:
        return ResolvedPipelineChunks(
            chunks=[],
            source_document_id=document_reference_id,
            resolution="none",
        )

    bundle_id = f"{rid}:leo-referral-bundle"
    bundle = list_document_chunks_normalized(
        client,
        document_reference_id=bundle_id,
        limit=limit,
    )
    if bundle:
        return ResolvedPipelineChunks(
            chunks=bundle,
            source_document_id=bundle_id,
            resolution="referral_bundle",
        )

    sibling_rows = client.run(
        _SIBLING_SOURCE,
        referral_id=rid,
        document_reference_id=document_reference_id,
    )
    first_sibling = sibling_rows[0] if sibling_rows else {}
    source_id = str((first_sibling or {}).get("source_document_id") or "").strip()
    if source_id:
        sibling = list_document_chunks_normalized(
            client,
            document_reference_id=source_id,
            limit=limit,
            backfill_legacy_ids=backfill_legacy_ids,
        )
        if sibling:
            return ResolvedPipelineChunks(
                chunks=sibling,
                source_document_id=source_id,
                resolution="referral_sibling",
            )

    return ResolvedPipelineChunks(
        chunks=[],
        source_document_id=document_reference_id,
        resolution="none",
    )
