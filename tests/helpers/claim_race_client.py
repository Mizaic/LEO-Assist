"""Thread-safe in-memory Neo4j stand-in for PipelineStageRun claim races.

Mirrors CLAIM_PIPELINE_STAGE_RUN outcomes (claimed / busy / already_completed
/ poisoned) under a process lock so CI can prove single-flight without a live
database.

Atlas: VT-E4457D16 / DI-36F80B95 / DO-CE65B1F2
"""

from __future__ import annotations

import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from libs.cypher.pipeline_stage_queries import (
    CLAIM_PIPELINE_STAGE_RUN,
    COMPLETE_PIPELINE_STAGE_RUN,
    ENSURE_OUTBOX_EVENT_CONSTRAINT,
    ENSURE_PIPELINE_RUN_ADMISSION_KEY_CONSTRAINT,
    ENSURE_PIPELINE_RUN_CONSTRAINT,
    ENSURE_PIPELINE_STAGE_CONSTRAINT,
    ENSURE_PIPELINE_STAGE_OUTBOX,
    GET_PENDING_OUTBOX_FOR_STAGE,
    GET_SUCCESSOR_STAGE_STATUSES,
    HAS_ANY_OUTBOX_FOR_STAGE,
    HAS_PENDING_OUTBOX_FOR_STAGE,
    MARK_OUTBOX_EVENT_SENT,
    MARK_STAGE_NEXT_PUBLISHED,
    RENEW_PIPELINE_STAGE_LEASE,
    UPSERT_PIPELINE_RUN,
)

_TERMINAL = ("completed", "failed", "cancelled", "poisoned")


class InMemoryClaimClient:
    """Minimal client.run() surface for durable stage claim concurrency tests."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.runs: dict[str, dict[str, Any]] = {}
        self.stages: dict[str, dict[str, Any]] = {}
        self.outbox: dict[str, dict[str, Any]] = {}
        self.stage_outbox: dict[str, list[str]] = {}

    def close(self) -> None:
        return None

    def run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        with self._lock:
            if query in (
                ENSURE_PIPELINE_RUN_CONSTRAINT,
                ENSURE_PIPELINE_RUN_ADMISSION_KEY_CONSTRAINT,
                ENSURE_PIPELINE_STAGE_CONSTRAINT,
                ENSURE_OUTBOX_EVENT_CONSTRAINT,
            ):
                return []
            if query == UPSERT_PIPELINE_RUN:
                return [self._upsert_run(params)]
            if query == CLAIM_PIPELINE_STAGE_RUN:
                return [self._claim(params)]
            if query == RENEW_PIPELINE_STAGE_LEASE:
                return [self._renew(params)]
            if query == COMPLETE_PIPELINE_STAGE_RUN:
                return [self._complete(params)]
            if query == MARK_STAGE_NEXT_PUBLISHED:
                stage = self.stages.get(params["stage_run_id"])
                if stage is not None:
                    stage["next_published"] = True
                return [{"id": params["stage_run_id"]}]
            if query == GET_PENDING_OUTBOX_FOR_STAGE:
                return self._pending_outbox(params["stage_run_id"])
            if query == MARK_OUTBOX_EVENT_SENT:
                return [self._mark_outbox_sent(params["outbox_id"])]
            if query == HAS_PENDING_OUTBOX_FOR_STAGE:
                pending = self._pending_outbox(params["stage_run_id"])
                return [{"has_pending": bool(pending)}]
            if query == GET_SUCCESSOR_STAGE_STATUSES:
                return self._successor_statuses(params["run_id"], params["step_ids"])
            if query == HAS_ANY_OUTBOX_FOR_STAGE:
                links = self.stage_outbox.get(params["stage_run_id"], [])
                return [{"has_outbox": bool(links)}]
            if query == ENSURE_PIPELINE_STAGE_OUTBOX:
                return [self._ensure_outbox(params)]
            raise ValueError(f"Unsupported query in InMemoryClaimClient: {query[:60]}")

    def expire_lease(self, stage_run_id: str) -> None:
        """Force lease expiry for reclaim tests."""
        with self._lock:
            stage = self.stages[stage_run_id]
            stage["lease_until"] = datetime.now(timezone.utc) - timedelta(seconds=1)

    def _upsert_run(self, params: dict[str, Any]) -> dict[str, Any]:
        run_id = params["run_id"]
        existing = self.runs.get(run_id, {})
        current = str(existing.get("status") or "running")
        requested = str(params["status"])
        if current in _TERMINAL and requested == "running":
            status = current
        else:
            status = requested
        row = {**params, "status": status}
        self.runs[run_id] = row
        return {"id": run_id, "status": status}

    def _max_attempts(self, params: dict[str, Any]) -> int:
        return max(
            1,
            int(
                params.get("max_attempts")
                or os.getenv("PIPELINE_STAGE_MAX_ATTEMPTS", "5")
            ),
        )

    def _claim(self, params: dict[str, Any]) -> dict[str, Any]:
        run_id = params["run_id"]
        if run_id not in self.runs:
            raise RuntimeError(f"PipelineRun {run_id} missing -- upsert_run first")
        stage_id = params["stage_run_id"]
        owner = params["lease_owner"]
        lease_seconds = int(params["lease_seconds"])
        max_attempts = self._max_attempts(params)
        now = datetime.now(timezone.utc)
        stage = self.stages.setdefault(
            stage_id,
            {
                "status": "pending",
                "lease_owner": None,
                "lease_until": None,
                "lease_generation": 0,
                "attempt": 0,
                "output_json": None,
                "next_action_ids_json": None,
                "next_published": False,
            },
        )
        if stage["status"] == "completed":
            return self._claim_row("already_completed", stage)
        if stage["status"] == "poisoned":
            return self._claim_row("poisoned", stage)
        if self._can_claim(stage, owner, now):
            same_owner_live = (
                stage.get("status") == "running"
                and (stage.get("lease_owner") or "") == owner
                and stage.get("lease_until") is not None
                and stage["lease_until"] >= now
            )
            if same_owner_live:
                generation = int(stage.get("lease_generation") or 1)
                next_attempt = int(stage.get("attempt") or 1)
            else:
                generation = int(stage.get("lease_generation") or 0) + 1
                next_attempt = int(stage.get("attempt") or 0) + 1
            if next_attempt > max_attempts:
                stage["status"] = "poisoned"
                self.runs[run_id]["status"] = "poisoned"
                return self._claim_row("poisoned", stage)
            stage["status"] = "running"
            stage["lease_owner"] = owner
            stage["lease_generation"] = generation
            stage["lease_until"] = now + timedelta(seconds=lease_seconds)
            stage["attempt"] = next_attempt
            stage["step_id"] = params.get("step_id")
            stage["event_type"] = params.get("event_type")
            stage["input_json"] = params.get("input_json")
            stage["run_id"] = run_id
            stage["next_published"] = False
            return {
                "outcome": "claimed",
                "output_json": None,
                "next_action_ids_json": None,
                "next_published": False,
                "lease_owner": owner,
                "lease_generation": generation,
            }
        if (
            stage["status"] == "running"
            and stage.get("lease_until") is not None
            and stage["lease_until"] >= now
            and stage.get("lease_owner") != owner
        ):
            return self._claim_row("busy", stage)
        return self._claim_row("busy", stage)

    @staticmethod
    def _claim_row(outcome: str, stage: dict[str, Any]) -> dict[str, Any]:
        return {
            "outcome": outcome,
            "output_json": stage.get("output_json"),
            "next_action_ids_json": stage.get("next_action_ids_json"),
            "next_published": bool(stage.get("next_published")),
            "lease_owner": stage.get("lease_owner") or "",
            "lease_generation": int(stage.get("lease_generation") or 0),
        }

    @staticmethod
    def _can_claim(stage: dict[str, Any], owner: str, now: datetime) -> bool:
        status = stage.get("status") or "pending"
        if status in {"pending", "failed", "paused"}:
            return True
        if status != "running":
            return False
        lease_until = stage.get("lease_until")
        return (
            lease_until is None
            or lease_until < now
            or (stage.get("lease_owner") or "") == owner
        )

    def _renew(self, params: dict[str, Any]) -> dict[str, Any]:
        stage = self.stages.get(params["stage_run_id"])
        if stage is None:
            return {}
        if (
            stage.get("status") != "running"
            or (stage.get("lease_owner") or "") != params["lease_owner"]
            or int(stage.get("lease_generation") or 0)
            != int(params["lease_generation"])
        ):
            return {}
        stage["lease_until"] = datetime.now(timezone.utc) + timedelta(
            seconds=int(params["lease_seconds"])
        )
        return {"id": params["stage_run_id"]}

    def _complete(self, params: dict[str, Any]) -> dict[str, Any]:
        stage = self.stages.setdefault(params["stage_run_id"], {})
        if (
            stage.get("status") == "running"
            and (stage.get("lease_owner") or "") == params.get("lease_owner", "")
            and int(stage.get("lease_generation") or 0)
            == int(params.get("lease_generation") or 0)
        ):
            stage["status"] = params["status"]
            stage["output_json"] = params.get("output_json")
            stage["next_action_ids_json"] = params.get("next_action_ids_json")
            stage["next_published"] = bool(params.get("next_published"))
            stage["lease_owner"] = None
            stage["lease_until"] = None
            run = self.runs.get(params["run_id"])
            if run is not None and params.get("run_status"):
                run["status"] = params["run_status"]
            created = 0
            for evt in params.get("outbox_events") or []:
                event_id = str(evt["id"])
                row = {
                    "id": event_id,
                    "message_id": evt.get("message_id"),
                    "queue_name": evt.get("queue_name"),
                    "body_json": evt.get("body_json"),
                    "status": evt.get("status") or "pending",
                }
                self.outbox[event_id] = row
                links = self.stage_outbox.setdefault(params["stage_run_id"], [])
                if event_id not in links:
                    links.append(event_id)
                created += 1
            return {"outcome": "completed", "outbox_created": created}
        return {"outcome": "stale_lease", "outbox_created": 0}

    def _pending_outbox(self, stage_run_id: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for event_id in self.stage_outbox.get(stage_run_id, []):
            row = self.outbox.get(event_id)
            if row and row.get("status") == "pending":
                rows.append(dict(row))
        return rows

    def _mark_outbox_sent(self, outbox_id: str) -> dict[str, Any]:
        row = self.outbox.get(outbox_id)
        if row is not None:
            row["status"] = "sent"
        return {"id": outbox_id}

    def _successor_statuses(
        self, run_id: str, step_ids: list[str]
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for stage in self.stages.values():
            if stage.get("run_id") != run_id:
                continue
            step_id = str(stage.get("step_id") or "")
            if step_id in step_ids:
                rows.append({"step_id": step_id, "status": stage.get("status")})
        return rows

    def _ensure_outbox(self, params: dict[str, Any]) -> dict[str, Any]:
        created = 0
        for evt in params.get("outbox_events") or []:
            event_id = str(evt["id"])
            if event_id in self.outbox:
                continue
            row = {
                "id": event_id,
                "message_id": evt.get("message_id"),
                "queue_name": evt.get("queue_name"),
                "body_json": evt.get("body_json"),
                "status": "pending",
            }
            self.outbox[event_id] = row
            links = self.stage_outbox.setdefault(params["stage_run_id"], [])
            if event_id not in links:
                links.append(event_id)
            created += 1
        return {"outbox_ensured": created}
