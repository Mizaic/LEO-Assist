"""Materialise Validation Lab A&G cases into production-shaped Neo4j graphs.

Atlas trace:
  DO: DO-E981C7B1
  DI: DI-D6E5F94E
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-E981C7B1")
"""

from __future__ import annotations

from typing import Any

from libs.cypher.chunk_queries import UPSERT_CHUNK
from libs.referral_simulator.scaffold import _birth_date_from_age, split_into_chunks
from libs.validation_lab.models import AgConversationTurn, ValidationCaseSpec

SOURCE_VALIDATION_LAB = "validation-lab"

_UPSERT_AG_PATIENT = """
MERGE (p:Patient {id: $patient_id})
SET p.source = $source,
    p.synthetic = true,
    p.gender = coalesce($gender, 'unknown'),
    p.birthDate = CASE WHEN $birth_date <> '' THEN $birth_date ELSE p.birthDate END,
    p.name = CASE WHEN $patient_name <> '' THEN $patient_name ELSE p.name END,
    p.case_id = CASE WHEN $case_id <> '' THEN $case_id ELSE p.case_id END
MERGE (cr:CommunicationRequest {id: $communication_request_id})
SET cr.ubrn = $ubrn,
    cr.source = $source,
    cr.status = 'active',
    cr.case_id = $case_id
MERGE (cr)-[:FOR_PATIENT]->(p)
"""

_UPSERT_COMMUNICATION = """
MATCH (cr:CommunicationRequest {id: $communication_request_id})
MERGE (c:Communication {id: $communication_id})
SET c.note = $note,
    c.category = $category,
    c.sent_datetime = datetime($sent_datetime),
    c.source = $source,
    c.case_id = $case_id
MERGE (cr)-[:HAS_CONVERSATION]->(c)
"""

_UPSERT_AGR = """
MATCH (cr:CommunicationRequest {id: $communication_request_id})
MERGE (agr:AdviceAndGuidanceResponse {id: $agr_id})
SET agr.responseText = $response_text,
    agr.source = $source,
    agr.case_id = $case_id,
    agr.updated_at = datetime()
MERGE (cr)-[:HAS_RESPONSE]->(agr)
"""

_UPSERT_ATTACHMENT_DR = """
MATCH (cr:CommunicationRequest {id: $communication_request_id})
MERGE (dr:DocumentReference {id: $dr_id})
SET dr.source = $source,
    dr.title = $title,
    dr.case_id = $case_id
MERGE (cr)-[:HAS_DOCUMENT]->(dr)
"""

_UPSERT_MESSAGE_ATTACHMENT_DR = """
MATCH (c:Communication {id: $communication_id})
MERGE (dr:DocumentReference {id: $dr_id})
SET dr.source = $source,
    dr.title = $title,
    dr.case_id = $case_id
MERGE (c)-[:HAS_DOCUMENT]->(dr)
"""

_UPSERT_CORRELATION_ENCOUNTER = """
MATCH (p:Patient {id: $patient_id})
MERGE (e:Encounter {id: $encounter_id})
SET e.source = $source,
    e.case_id = $case_id,
    e.communication_request_id = $communication_request_id
MERGE (p)-[:HAS_ENCOUNTER]->(e)
"""


def _ids_for_ag_case(case_id: str, ubrn: str) -> dict[str, str]:
    base = f"lab-{case_id}"
    ubrn_val = ubrn or f"{case_id}-ag"
    return {
        "patient_id": f"{base}:patient",
        "encounter_id": f"{ubrn_val}:ag-assessment",
        "communication_request_id": f"{base}:communication-request",
        "ubrn": ubrn_val,
    }


def _write_attachment_chunks(
    session: Any,
    *,
    dr_id: str,
    attachment_text: str,
    source: str,
) -> list[str]:
    chunks = split_into_chunks(attachment_text, dr_id)
    chunk_ids: list[str] = []
    for chunk in chunks:
        session.run(
            UPSERT_CHUNK,
            document_reference_id=dr_id,
            chunk_id=chunk["id"],
            text=chunk["text"],
            sha256=chunk["sha256"],
            char_start=chunk["char_start"],
            char_end=chunk["char_end"],
            ordinal=chunk["ordinal"],
            tenant_id="validation-lab" if source == SOURCE_VALIDATION_LAB else "",
        )
        chunk_ids.append(chunk["id"])
    return chunk_ids


def _spo_ag_thread(spec: ValidationCaseSpec, knowledge_client: Any | None) -> list:
    """Build A&G turns for spo_ag with reason + verbalised PMH in first REQUESTER."""
    from libs.validation_lab.models import AgConversationTurn
    from libs.validation_lab.pmh_verbalisation import compose_submission_text

    seed = str(spec.verbalisation_seed or spec.case_id)
    reason = str(spec.reason_for_submission or "").strip()
    first_note = ""
    if spec.ag_thread:
        first_note = str(spec.ag_thread[0].note or "").strip()
    if not reason and not first_note and not spec.ag_response_text.strip():
        raise ValueError(
            "reason_for_submission or first REQUESTER note is required for spo_ag"
        )
    close_kg = False
    kg = knowledge_client
    if kg is None and spec.pmh:
        from libs.neo4j_client.client import KnowledgeGraphClient

        kg = KnowledgeGraphClient()
        close_kg = True
    try:
        requester_note = compose_submission_text(
            reason=reason or first_note,
            pmh=spec.pmh,
            seed=seed,
            client=kg,
        )
    finally:
        if close_kg and kg is not None:
            kg.close()
    turns: list[AgConversationTurn] = [
        AgConversationTurn(
            category="REQUESTER",
            note=requester_note,
            sent_datetime=(spec.ag_thread[0].sent_datetime if spec.ag_thread else ""),
            attachment_text=(
                spec.ag_thread[0].attachment_text if spec.ag_thread else ""
            ),
        )
    ]
    for turn in (spec.ag_thread or [])[1:]:
        turns.append(turn)
    return turns


def scaffold_ag_case(
    client: Any,
    spec: ValidationCaseSpec,
    *,
    knowledge_client: Any | None = None,
) -> dict[str, Any]:
    """Write CommunicationRequest thread graph for an A&G Lab case."""
    thread = list(spec.ag_thread or [])
    if spec.scenario_type == "spo_ag":
        thread = _spo_ag_thread(spec, knowledge_client)
    if not thread and not spec.ag_response_text.strip():
        raise ValueError("ag_thread or ag_response_text is required for ag cases")
    ids = _ids_for_ag_case(spec.case_id, spec.ag_ubrn or spec.case_id)
    birth_date = _birth_date_from_age(spec.patient_age)
    all_chunk_ids: list[str] = []

    with client.session() as session:
        session.run(
            _UPSERT_AG_PATIENT,
            patient_id=ids["patient_id"],
            communication_request_id=ids["communication_request_id"],
            ubrn=ids["ubrn"],
            source=SOURCE_VALIDATION_LAB,
            gender=spec.patient_sex or "unknown",
            birth_date=birth_date,
            patient_name=spec.patient_name or spec.title or "",
            case_id=spec.case_id,
        )
        session.run(
            _UPSERT_CORRELATION_ENCOUNTER,
            patient_id=ids["patient_id"],
            encounter_id=ids["encounter_id"],
            communication_request_id=ids["communication_request_id"],
            source=SOURCE_VALIDATION_LAB,
            case_id=spec.case_id,
        )
        for index, turn in enumerate(thread):
            comm_id = f"{ids['communication_request_id']}:comm:{index}"
            sent = turn.sent_datetime or f"2026-01-{index + 1:02d}T09:00:00"
            session.run(
                _UPSERT_COMMUNICATION,
                communication_request_id=ids["communication_request_id"],
                communication_id=comm_id,
                note=turn.note,
                category=turn.category,
                sent_datetime=sent,
                source=SOURCE_VALIDATION_LAB,
                case_id=spec.case_id,
            )
            if turn.attachment_text.strip():
                dr_id = f"{comm_id}:attachment"
                session.run(
                    _UPSERT_MESSAGE_ATTACHMENT_DR,
                    communication_id=comm_id,
                    dr_id=dr_id,
                    source=SOURCE_VALIDATION_LAB,
                    title=f"A&G attachment {index + 1}",
                    case_id=spec.case_id,
                )
                all_chunk_ids.extend(
                    _write_attachment_chunks(
                        session,
                        dr_id=dr_id,
                        attachment_text=turn.attachment_text,
                        source=SOURCE_VALIDATION_LAB,
                    )
                )
        for index, attachment_text in enumerate(spec.ag_request_attachments):
            text = str(attachment_text or "").strip()
            if not text:
                continue
            dr_id = f"{ids['communication_request_id']}:request-attachment:{index}"
            session.run(
                _UPSERT_ATTACHMENT_DR,
                communication_request_id=ids["communication_request_id"],
                dr_id=dr_id,
                source=SOURCE_VALIDATION_LAB,
                title=f"A&G request attachment {index + 1}",
                case_id=spec.case_id,
            )
            all_chunk_ids.extend(
                _write_attachment_chunks(
                    session,
                    dr_id=dr_id,
                    attachment_text=text,
                    source=SOURCE_VALIDATION_LAB,
                )
            )
        if spec.ag_response_text.strip():
            session.run(
                _UPSERT_AGR,
                communication_request_id=ids["communication_request_id"],
                agr_id=f"{ids['communication_request_id']}:response",
                response_text=spec.ag_response_text.strip(),
                source=SOURCE_VALIDATION_LAB,
                case_id=spec.case_id,
            )

    return {
        "patient_id": ids["patient_id"],
        "encounter_id": ids["encounter_id"],
        "communication_request_id": ids["communication_request_id"],
        "ubrn": ids["ubrn"],
        "chunk_ids": all_chunk_ids,
        "background_encounter_ids": [],
    }
