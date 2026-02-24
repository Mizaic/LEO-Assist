"""Patient and encounter endpoints reading from patient Neo4j graph."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.db.neo4j_client import PatientGraphClient
from app.models.neo4j_schema import (
    DELETE_CODED_LINK,
    GET_ENCOUNTER,
    GET_PATIENT,
    LIST_ENCOUNTER_CODED_LINKS,
    LIST_PATIENT_ENCOUNTERS,
    LIST_PATIENTS,
)
from app.services.reset_service import reset_patient
from app.services.v3.patient_graph_writer import PatientGraphWriter, SemanticLinkPayload


router = APIRouter(prefix="/patients", tags=["patients"])


class RecodeCodedLinkRequest(BaseModel):
    new_concept_id: str
    term: str | None = None
    read_code: str | None = None
    semantic_tag: str = "SnomedConcept"
    modifiers: dict[str, Any] | None = None


class AddCodedLinkRequest(BaseModel):
    concept_id: str
    term: str | None = None
    read_code: str | None = None
    semantic_tag: str = "SnomedConcept"
    evidence: str = ""
    modifiers: dict[str, Any] | None = None


@router.get("")
def list_patients():
    client = PatientGraphClient()
    try:
        return client.run(LIST_PATIENTS)
    finally:
        client.close()


@router.post("/{patient_id}/reset")
def reset_patient_documents(patient_id: str):
    """Remove all DOCUMENTS for a patient's encounters. Keeps Patient, Encounters, text."""
    client = PatientGraphClient()
    try:
        with client.session() as session:
            result = reset_patient(patient_id, session)
        if result.get("error") == "patient_not_found":
            raise HTTPException(status_code=404, detail="Patient not found")
        return {
            "patient_id": result["patient_id"],
            "links_deleted": result["links_deleted"],
        }
    finally:
        client.close()


@router.get("/{patient_id}")
def get_patient(patient_id: str):
    client = PatientGraphClient()
    try:
        rows = client.run(GET_PATIENT, patient_id=patient_id)
        if not rows:
            raise HTTPException(status_code=404, detail="Patient not found")
        return rows[0]
    finally:
        client.close()


@router.get("/{patient_id}/encounters")
def list_encounters(patient_id: str, limit: int = Query(default=500, ge=1, le=2000)):
    client = PatientGraphClient()
    try:
        return client.run(LIST_PATIENT_ENCOUNTERS, patient_id=patient_id, limit=limit)
    finally:
        client.close()


@router.get("/{patient_id}/encounters/{encounter_id}")
def get_encounter(patient_id: str, encounter_id: str):
    client = PatientGraphClient()
    try:
        rows = client.run(GET_ENCOUNTER, patient_id=patient_id, encounter_id=encounter_id)
        if not rows:
            raise HTTPException(status_code=404, detail="Encounter not found")
        return rows[0]
    finally:
        client.close()


@router.post("/{patient_id}/encounters/{encounter_id}/coded-links")
def add_coded_link(
    patient_id: str,
    encounter_id: str,
    body: AddCodedLinkRequest,
):
    writer = PatientGraphWriter()
    client = PatientGraphClient()
    try:
        with client.session() as session:
            payload = SemanticLinkPayload(
                encounter_id=encounter_id,
                semantic_tag=body.semantic_tag,
                concept_id=body.concept_id,
                term=body.term,
                read_code=body.read_code,
                evidence=body.evidence,
                confidence=0.95,
                domain="clinical",
                context={},
                modifiers=body.modifiers or {},
                source="manual",
            )
            writer.upsert_documents_link(payload, session=session)
        return {"added": True, "concept_id": body.concept_id}
    finally:
        client.close()


@router.get("/{patient_id}/encounters/{encounter_id}/coded-links")
def get_encounter_coded_links(patient_id: str, encounter_id: str):
    client = PatientGraphClient()
    try:
        rows = client.run(
            LIST_ENCOUNTER_CODED_LINKS,
            patient_id=patient_id,
            encounter_id=encounter_id,
        )
        # Filter out placeholder row when no DOCUMENTS exist (concept_id is null)
        result = []
        for r in rows:
            if not r.get("concept_id"):
                continue
            row = dict(r)
            # Parse context/modifiers from JSON strings (Neo4j stores primitives only)
            ctx = row.get("context")
            mod = row.get("modifiers")
            if isinstance(ctx, str):
                try:
                    row["context"] = json.loads(ctx) if ctx else {}
                except json.JSONDecodeError:
                    row["context"] = {}
            elif ctx is None:
                row["context"] = {}
            if isinstance(mod, str):
                try:
                    row["modifiers"] = json.loads(mod) if mod else {}
                except json.JSONDecodeError:
                    row["modifiers"] = {}
            elif mod is None:
                row["modifiers"] = {}
            result.append(row)
        return result
    finally:
        client.close()


@router.delete("/{patient_id}/encounters/{encounter_id}/coded-links/{concept_id}")
def delete_coded_link(patient_id: str, encounter_id: str, concept_id: str):
    client = PatientGraphClient()
    try:
        rows = client.run(
            DELETE_CODED_LINK,
            patient_id=patient_id,
            encounter_id=encounter_id,
            concept_id=concept_id,
        )
        return {"deleted": True}
    finally:
        client.close()


@router.patch("/{patient_id}/encounters/{encounter_id}/coded-links/{concept_id}")
def recode_coded_link(
    patient_id: str,
    encounter_id: str,
    concept_id: str,
    body: RecodeCodedLinkRequest,
):
    writer = PatientGraphWriter()
    client = PatientGraphClient()
    try:
        with client.session() as session:
            payload = SemanticLinkPayload(
                encounter_id=encounter_id,
                semantic_tag=body.semantic_tag,
                concept_id=body.new_concept_id,
                term=body.term,
                read_code=body.read_code,
                evidence="",
                confidence=0.9,
                domain="clinical",
                context={},
                modifiers=body.modifiers or {},
                source="manual_recode",
            )
            writer.recode_documents_link(
                patient_id=patient_id,
                old_concept_id=concept_id,
                new_payload=payload,
                session=session,
            )
        return {"recode": True, "new_concept_id": body.new_concept_id}
    finally:
        client.close()
