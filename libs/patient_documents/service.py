"""Create, update, and delete manual journey patient documents."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from libs.cypher.chunk_queries import UPSERT_CHUNK
from libs.llm_client.prompt_safety import sanitise_for_prompt
from libs.patient_document_runs.service import DocumentRunError, start_document_run
from libs.patient_documents.queries import (
    ATTACH_ENCOUNTER_TO_EPISODE,
    CREATE_DOCUMENT_GRAPH,
    DELETE_DOCUMENT_CHUNKS,
    DELETE_DOCUMENT_NODE,
    DELETE_MILESTONE_ENCOUNTER,
    DELETE_ORPHAN_REFERRAL,
    GET_DOCUMENT_FOR_PATIENT,
    SOURCE_MANUAL_JOURNEY,
    UPDATE_DOCUMENT_BODY,
    UPDATE_DOCUMENT_META,
    UPSERT_MILESTONE_ENCOUNTER,
)
from libs.referral_simulator.scaffold import split_into_chunks

logger = logging.getLogger(__name__)

MAX_BODY_CHARS = 200_000


class PatientDocumentError(Exception):
    """Raised when a patient document mutation cannot be completed."""


@dataclass(frozen=True)
class PatientDocumentResult:
    document_id: str
    referral_id: str
    encounter_id: str
    chunk_ids: tuple[str, ...]
    run_id: str | None = None


def _normalise_body(text: str) -> str:
    body = str(text or "").strip()
    if not body:
        raise PatientDocumentError("Document body is required.")
    if len(body) > MAX_BODY_CHARS:
        raise PatientDocumentError(
            f"Document body exceeds {MAX_BODY_CHARS} characters."
        )
    return sanitise_for_prompt(body, max_chars=MAX_BODY_CHARS)


def _write_chunks(
    session: Any,
    *,
    document_id: str,
    markdown_body: str,
    tenant_id: str,
) -> list[str]:
    chunks = split_into_chunks(markdown_body, document_id)
    chunk_ids: list[str] = []
    for chunk in chunks:
        session.run(
            UPSERT_CHUNK,
            document_reference_id=document_id,
            chunk_id=chunk["id"],
            text=chunk["text"],
            sha256=chunk["sha256"],
            char_start=chunk["char_start"],
            char_end=chunk["char_end"],
            ordinal=chunk["ordinal"],
            tenant_id=tenant_id,
        )
        chunk_ids.append(chunk["id"])
    return chunk_ids


def _link_milestone(
    session: Any,
    *,
    patient_id: str,
    document_id: str,
    referral_id: str,
    episode_id: str,
    milestone_type: str,
) -> str:
    encounter_id = f"{document_id}:milestone"
    session.run(
        UPSERT_MILESTONE_ENCOUNTER,
        patient_id=patient_id,
        encounter_id=encounter_id,
        referral_id=referral_id,
        document_id=document_id,
        milestone_type=milestone_type,
        source=SOURCE_MANUAL_JOURNEY,
    )
    session.run(
        ATTACH_ENCOUNTER_TO_EPISODE,
        encounter_id=encounter_id,
        episode_id=episode_id,
        milestone_type=milestone_type,
    )
    return encounter_id


def create_patient_document(
    client: Any,
    *,
    patient_id: str,
    title: str,
    markdown_body: str,
    category: str = "referral",
    document_date: str = "",
    episode_id: str = "",
    milestone_type: str = "",
    referral_id: str = "",
    run_pipeline: bool = False,
    requested_by: str = "",
    tenant_fallback: str | None = None,
) -> PatientDocumentResult:
    """Create a manual journey DocumentReference with chunks."""
    pid = str(patient_id or "").strip()
    if not pid:
        raise PatientDocumentError("patient_id is required.")
    body = _normalise_body(markdown_body)
    doc_title = str(title or "Untitled document").strip() or "Untitled document"
    document_id = uuid.uuid4().hex
    resolved_referral = str(referral_id or "").strip() or f"{document_id}:referral"
    encounter_id = ""

    with client.session() as session:
        rows = session.run(
            CREATE_DOCUMENT_GRAPH,
            patient_id=pid,
            document_id=document_id,
            referral_id=resolved_referral,
            source=SOURCE_MANUAL_JOURNEY,
            title=doc_title,
            category=str(category or "referral"),
            document_date=str(document_date or ""),
            markdown_body=body,
            episode_id=str(episode_id or ""),
            milestone_type=str(milestone_type or ""),
        ).data()
        if not rows:
            raise PatientDocumentError("Failed to create document.")
        chunk_ids = _write_chunks(
            session,
            document_id=document_id,
            markdown_body=body,
            tenant_id=str(tenant_fallback or ""),
        )
        if episode_id and milestone_type:
            encounter_id = _link_milestone(
                session,
                patient_id=pid,
                document_id=document_id,
                referral_id=resolved_referral,
                episode_id=episode_id,
                milestone_type=milestone_type,
            )

    run_id = None
    if run_pipeline and chunk_ids:
        try:
            run = start_document_run(
                client,
                patient_id=pid,
                document_reference_id=document_id,
                chunk_ids=chunk_ids,
                requested_by=requested_by,
                tenant_fallback=tenant_fallback,
            )
            run_id = run.run_id
        except DocumentRunError as exc:
            raise PatientDocumentError(str(exc)) from exc

    return PatientDocumentResult(
        document_id=document_id,
        referral_id=resolved_referral,
        encounter_id=encounter_id,
        chunk_ids=tuple(chunk_ids),
        run_id=run_id,
    )


def update_patient_document(
    client: Any,
    *,
    patient_id: str,
    document_id: str,
    title: str | None = None,
    markdown_body: str | None = None,
    category: str | None = None,
    document_date: str | None = None,
    episode_id: str | None = None,
    milestone_type: str | None = None,
    tenant_fallback: str | None = None,
) -> PatientDocumentResult:
    """Update metadata and optionally re-chunk a manual journey document."""
    pid = str(patient_id or "").strip()
    did = str(document_id or "").strip()
    rows = client.run(
        GET_DOCUMENT_FOR_PATIENT,
        patient_id=pid,
        document_id=did,
        source=SOURCE_MANUAL_JOURNEY,
    )
    if not rows:
        raise PatientDocumentError("Document not found or not editable.")

    referral_id = f"{did}:referral"
    encounter_id = f"{did}:milestone"
    chunk_ids: list[str] = list(rows[0].get("chunk_ids") or [])

    with client.session() as session:
        session.run(
            UPDATE_DOCUMENT_META,
            document_id=did,
            source=SOURCE_MANUAL_JOURNEY,
            title=title,
            category=category,
            document_date=document_date,
            episode_id=episode_id,
            milestone_type=milestone_type,
        )
        if markdown_body is not None:
            body = _normalise_body(markdown_body)
            session.run(
                UPDATE_DOCUMENT_BODY,
                document_id=did,
                source=SOURCE_MANUAL_JOURNEY,
                markdown_body=body,
            )
            session.run(
                DELETE_DOCUMENT_CHUNKS,
                document_id=did,
                source=SOURCE_MANUAL_JOURNEY,
            )
            chunk_ids = _write_chunks(
                session,
                document_id=did,
                markdown_body=body,
                tenant_id=str(tenant_fallback or ""),
            )
        resolved_episode = (
            episode_id if episode_id is not None else rows[0].get("episode_id")
        )
        resolved_milestone = (
            milestone_type
            if milestone_type is not None
            else rows[0].get("milestone_type")
        )
        if resolved_episode and resolved_milestone:
            encounter_id = _link_milestone(
                session,
                patient_id=pid,
                document_id=did,
                referral_id=referral_id,
                episode_id=str(resolved_episode),
                milestone_type=str(resolved_milestone),
            )

    return PatientDocumentResult(
        document_id=did,
        referral_id=referral_id,
        encounter_id=encounter_id,
        chunk_ids=tuple(chunk_ids),
    )


def delete_patient_document(
    client: Any,
    *,
    patient_id: str,
    document_id: str,
) -> str:
    """Delete a manual journey document and its chunks."""
    pid = str(patient_id or "").strip()
    did = str(document_id or "").strip()
    rows = client.run(
        GET_DOCUMENT_FOR_PATIENT,
        patient_id=pid,
        document_id=did,
        source=SOURCE_MANUAL_JOURNEY,
    )
    if not rows:
        raise PatientDocumentError("Document not found or not deletable.")
    encounter_id = f"{did}:milestone"
    referral_id = f"{did}:referral"
    with client.session() as session:
        session.run(
            DELETE_DOCUMENT_CHUNKS,
            document_id=did,
            source=SOURCE_MANUAL_JOURNEY,
        )
        session.run(
            DELETE_DOCUMENT_NODE,
            document_id=did,
            source=SOURCE_MANUAL_JOURNEY,
        )
        session.run(
            DELETE_ORPHAN_REFERRAL,
            referral_id=referral_id,
            source=SOURCE_MANUAL_JOURNEY,
        )
        session.run(
            DELETE_MILESTONE_ENCOUNTER,
            encounter_id=encounter_id,
            source=SOURCE_MANUAL_JOURNEY,
        )
    return did
