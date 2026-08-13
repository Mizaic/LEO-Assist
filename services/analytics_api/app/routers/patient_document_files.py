"""Inline patient document file streaming for the Care document viewer."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import httpx

from libs.auth.org_scope import CallerScope, get_caller_scope
from libs.neo4j_client.client import PatientGraphClient
from libs.patient_documents.chunk_preview import build_chunk_fallback_preview
from libs.patient_documents.docx_preview import build_word_preview_html
from libs.patient_documents.file_stream import (
    resolve_document_file_target,
    stream_remote_file,
)

from .patients_epr_queries import GET_DOCUMENT_FILE_ADMIN, GET_DOCUMENT_FILE_SCOPED

router = APIRouter()


class DocumentPreviewResponse(BaseModel):
    html: str = ""
    warnings: list[str] = Field(default_factory=list)


def _cypher_params(scope: CallerScope, patient_id: str, **extra: Any) -> dict[str, Any]:
    params: dict[str, Any] = {"patient_id": patient_id, **extra}
    if not scope.is_admin:
        params["scope_org_ids"] = list(scope.org_ids)
    return params


def _pick_query(scope: CallerScope, admin_q: str, scoped_q: str) -> str:
    return admin_q if scope.is_admin else scoped_q


def _load_document_file_row(
    scope: CallerScope,
    patient_id: str,
    document_id: str,
) -> dict[str, Any] | None:
    query = _pick_query(scope, GET_DOCUMENT_FILE_ADMIN, GET_DOCUMENT_FILE_SCOPED)
    client = PatientGraphClient()
    try:
        rows = client.run(
            query,
            **_cypher_params(scope, patient_id, document_id=document_id),
        )
    finally:
        client.close()
    if not rows:
        return None
    return rows[0]


@router.get("/patients/{patient_id}/documents/{document_id}/file")
async def get_patient_document_file(
    patient_id: str,
    document_id: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> StreamingResponse:
    """Stream a patient document file for same-origin iframe embedding."""
    row = _load_document_file_row(scope, patient_id, document_id)
    if not row:
        raise HTTPException(status_code=404, detail="Document not found.")

    target = resolve_document_file_target(
        original_url=row.get("original_url") or None,
        markdown_url=row.get("markdown_url") or None,
        content_type=row.get("content_type") or None,
        title=row.get("title") or None,
    )
    if not target:
        raise HTTPException(status_code=404, detail="Document file URL not available.")

    signed_url, media_type, filename = target
    headers = {"Content-Disposition": f'inline; filename="{filename}"'}
    return StreamingResponse(
        stream_remote_file(signed_url),
        media_type=media_type,
        headers=headers,
    )


@router.get(
    "/patients/{patient_id}/documents/{document_id}/preview",
    response_model=DocumentPreviewResponse,
)
async def get_patient_document_preview(
    patient_id: str,
    document_id: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> DocumentPreviewResponse:
    """Convert a Word document to HTML for inline viewing in Care."""
    row = _load_document_file_row(scope, patient_id, document_id)
    if not row:
        raise HTTPException(status_code=404, detail="Document not found.")

    try:
        html, warnings = await build_word_preview_html(
            original_url=row.get("original_url") or None,
            markdown_url=row.get("markdown_url") or None,
            content_type=row.get("content_type") or None,
            title=row.get("title") or None,
        )
    except ValueError as exc:
        detail = str(exc)
        status = 415 if "Legacy .doc" in detail or "Word documents" in detail else 404
        raise HTTPException(status_code=status, detail=detail) from exc
    except httpx.HTTPError as exc:
        fallback_html, fallback_warnings = build_chunk_fallback_preview(
            str(row.get("full_text") or "")
        )
        if fallback_html.strip():
            return DocumentPreviewResponse(
                html=fallback_html,
                warnings=fallback_warnings,
            )
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch the document file for preview.",
        ) from exc
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail="Word preview is unavailable. Install mammoth on analytics-api.",
        ) from exc

    if not html.strip():
        raise HTTPException(status_code=422, detail="Document preview was empty.")

    return DocumentPreviewResponse(html=html, warnings=warnings)
