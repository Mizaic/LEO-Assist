"""Persistence operations for review queue and audit artifacts."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from app.models.neo4j_schema import (
    APPEND_APPROVAL,
    APPEND_CHANGE,
    CREATE_REVIEW_TASK,
    GET_AUDIT_TIMELINE,
    GET_TASK_DETAIL,
    LIST_APPROVED_CANDIDATES,
    LIST_APPROVED_CANDIDATES_FOR_PATIENT,
    LIST_TASKS,
    UPSERT_CANDIDATE,
)


def _to_iso() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_temporal(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:  # pragma: no cover
            return str(value)
    return value


def _normalize_record(payload: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in payload.items():
        normalized[key] = _normalize_temporal(value)
    return normalized


def upsert_candidate(candidate: dict[str, Any], session) -> None:
    llm_usage = candidate.get("llm_usage")
    payload = {
        "candidate_id": candidate["candidate_id"],
        "patient_id": candidate["patient_id"],
        "encounter_id": candidate["encounter_id"],
        "date": candidate["date"],
        "source_hash": candidate["source_hash"],
        "deidentified_hash": candidate["deidentified_hash"],
        "deidentified_text": candidate["deidentified_text"],
        "approval_status": candidate["approval_status"],
        "hard_fail_reasons": candidate["hard_fail_reasons"],
        "warning_reasons": candidate["warning_reasons"],
        "sentences_json": json.dumps(candidate["sentences"], ensure_ascii=False),
        "llm_usage_json": json.dumps(llm_usage, ensure_ascii=False) if llm_usage else None,
    }
    session.run(UPSERT_CANDIDATE, **payload)

    for event in candidate.get("audit_events", []):
        session.run(
            APPEND_CHANGE,
            candidate_id=candidate["candidate_id"],
            change_id=str(uuid.uuid4()),
            event_type=event["event_type"],
            actor=event["actor"],
            reason=event["reason"],
            timestamp=event["timestamp"],
            before_hash=event["before_hash"],
            after_hash=event["after_hash"],
            version_bundle_json=json.dumps(event["version_bundle"], ensure_ascii=False),
        )


def create_review_task(candidate_id: str, session, priority: int = 50, warning_count: int = 0) -> str:
    # Keep one mutable task per candidate (candidate is now per encounter).
    task_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"review-task:{candidate_id}"))
    session.run(
        CREATE_REVIEW_TASK,
        candidate_id=candidate_id,
        task_id=task_id,
        priority=priority,
        status="pending",
        assigned_reviewer=None,
        warning_count=warning_count,
    )
    return task_id


def list_review_tasks(session, status: str | None, patient_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    records = session.run(LIST_TASKS, status=status, patient_id=patient_id, limit=limit)
    return [_normalize_record(dict(r)) for r in records]


def get_review_task_detail(task_id: str, session) -> dict[str, Any] | None:
    record = session.run(GET_TASK_DETAIL, task_id=task_id).single()
    if not record:
        return None
    payload = dict(record)
    payload = _normalize_record(payload)
    candidate = dict(payload.pop("candidate"))
    try:
        candidate["sentences"] = json.loads(candidate.get("sentences_json", "[]"))
    except json.JSONDecodeError:
        candidate["sentences"] = []
    payload["candidate"] = candidate
    return payload


def append_approval(
    *,
    task_id: str,
    candidate_id: str,
    reviewer: str,
    action: str,
    reason: str,
    status_after: str,
    before_hash: str,
    after_hash: str,
    session,
) -> str:
    approval_id = str(uuid.uuid4())
    session.run(
        APPEND_APPROVAL,
        task_id=task_id,
        candidate_id=candidate_id,
        approval_id=approval_id,
        action=action,
        reviewer=reviewer,
        reason=reason,
        status_after=status_after,
        timestamp=_to_iso(),
        before_hash=before_hash,
        after_hash=after_hash,
    )
    return approval_id


def get_audit_timeline(candidate_id: str, session) -> dict[str, Any]:
    record = session.run(GET_AUDIT_TIMELINE, candidate_id=candidate_id).single()
    if not record:
        return {"candidate_id": candidate_id, "changes": [], "approvals": []}
    payload = dict(record)
    payload["changes"] = [_normalize_record(dict(row)) for row in payload.get("changes", []) if row]
    payload["approvals"] = [_normalize_record(dict(row)) for row in payload.get("approvals", []) if row]
    return payload


def list_approved_candidates(session) -> list[dict[str, Any]]:
    records = session.run(LIST_APPROVED_CANDIDATES)
    payload: list[dict[str, Any]] = []
    for record in records:
        candidate = dict(record["c"])
        try:
            candidate["sentences"] = json.loads(candidate.get("sentences_json", "[]"))
        except json.JSONDecodeError:
            candidate["sentences"] = []
        payload.append(candidate)
    return payload


def list_approved_candidates_for_patient(patient_id: str, session) -> list[dict[str, Any]]:
    """Return approved EncounterCandidates for a patient."""
    records = session.run(LIST_APPROVED_CANDIDATES_FOR_PATIENT, patient_id=patient_id)
    payload: list[dict[str, Any]] = []
    for record in records:
        candidate = dict(record["c"])
        try:
            candidate["sentences"] = json.loads(candidate.get("sentences_json", "[]"))
        except json.JSONDecodeError:
            candidate["sentences"] = []
        payload.append(candidate)
    return payload
