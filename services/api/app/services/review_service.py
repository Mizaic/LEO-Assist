"""Review queue operations for HITL workflow."""

from __future__ import annotations

import random

from app.db.neo4j_client import CodingGraphClient
from app.models.contracts import ReviewAction, ReviewDecisionRequest, ReviewStatus
from app.services.neo4j_store import (
    append_approval,
    get_audit_timeline,
    get_review_task_detail,
    list_review_tasks,
    upsert_candidate,
)


class ReviewService:
    def __init__(self, neo4j_client: CodingGraphClient) -> None:
        self.neo4j = neo4j_client

    def list_tasks(self, status: ReviewStatus | None, patient_id: str | None = None, limit: int = 100):
        with self.neo4j.session() as session:
            return list_review_tasks(session=session, status=status.value if status else None, patient_id=patient_id, limit=limit)

    def get_task(self, task_id: str):
        with self.neo4j.session() as session:
            return get_review_task_detail(task_id, session=session)

    def decide(self, task_id: str, decision: ReviewDecisionRequest):
        with self.neo4j.session() as session:
            task = get_review_task_detail(task_id, session=session)
            if not task:
                return None
            candidate = task["candidate"]
            before_hash = candidate["deidentified_hash"]
            after_hash = before_hash

            status_after = {
                ReviewAction.approve: ReviewStatus.approved.value,
                ReviewAction.edit: ReviewStatus.approved.value,
                ReviewAction.reject: ReviewStatus.rejected.value,
                ReviewAction.escalate: ReviewStatus.escalated.value,
            }[decision.action]

            if decision.action == ReviewAction.edit and decision.edited_candidate:
                edited = decision.edited_candidate
                edited["candidate_id"] = candidate["candidate_id"]
                edited["patient_id"] = candidate["patient_id"]
                edited["encounter_id"] = candidate["encounter_id"]
                edited["date"] = candidate["date"]
                edited["source_hash"] = candidate["source_hash"]
                edited["deidentified_hash"] = candidate["deidentified_hash"]
                edited["approval_status"] = "pending"
                upsert_candidate(edited, session=session)
                after_hash = edited["deidentified_hash"]

            approval_id = append_approval(
                task_id=task_id,
                candidate_id=candidate["candidate_id"],
                reviewer=decision.reviewer,
                action=decision.action.value,
                reason=decision.reason,
                status_after=status_after,
                before_hash=before_hash,
                after_hash=after_hash,
                session=session,
            )
            return {
                "task_id": task_id,
                "candidate_id": candidate["candidate_id"],
                "status": status_after,
                "approval_event_id": approval_id,
            }

    def audit_timeline(self, candidate_id: str):
        with self.neo4j.session() as session:
            return get_audit_timeline(candidate_id, session=session)

    @staticmethod
    def split_train_validation(candidates: list[dict], train_ratio: float, seed: int):
        rows = list(candidates)
        random.Random(seed).shuffle(rows)
        cutoff = int(len(rows) * train_ratio)
        return rows[:cutoff], rows[cutoff:]
