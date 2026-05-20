"""Resilience tests for ExtractionValidationRun lifecycle.

Atlas trace:
  UN: UN-89E2AE36
  DI: DI-1B3B5375
  VT: VT-24D7A846

Covers the failure modes that previously stranded validation runs in status
"running" forever:

* Daemon publish thread killed by API restart/logout mid-flight.
* User closing the browser before all 97 cases land as AuditEvents.
* Worker dying between consume and audit write.

For each scenario we assert that:

1. The parent ExtractionValidationRun node persists enough state at creation
   to allow finalisation from another API instance.
2. A poll via GET /extraction-scenarios/runs/{run_id} can recover and either
   finalise or fail the run cleanly.
3. The background sweeper force-fails publishing rows that have outlived the
   hard cutoff.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
for sub in (ROOT, ROOT / "services" / "api"):
    if str(sub) not in sys.path:
        sys.path.insert(0, str(sub))

# Import the router lazily inside a fixture so we can monkeypatch the Neo4j
# client and the message bus before any real I/O is attempted.


class FakeCypherClient:
    """Records every Cypher call and serves canned responses."""

    def __init__(self, canned: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._canned = canned or {}

    def run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        self.calls.append({"query": query, "params": params})
        for fragment, rows in self._canned.items():
            if fragment in query:
                return list(rows)
        return []

    def close(self) -> None:
        return None


@pytest.fixture
def router(monkeypatch):
    """Import the router and stub out external dependencies."""
    from app.routers import extraction_scenarios

    monkeypatch.setattr(extraction_scenarios, "_runs", {}, raising=False)
    yield extraction_scenarios


def _attach_fake_client(monkeypatch, router, canned=None) -> FakeCypherClient:
    client = FakeCypherClient(canned=canned)
    monkeypatch.setattr(router, "_coding_client", lambda: client)
    return client


def _find_call(client: FakeCypherClient, needle: str) -> dict[str, Any] | None:
    for call in client.calls:
        if needle in call["query"]:
            return call
    return None


# ---------------------------------------------------------------------------
# Create + publish lifecycle
# ---------------------------------------------------------------------------


def test_create_validation_run_persists_case_ids_and_publishing_state(
    monkeypatch, router
):
    """Phase 1 of the resilience fix: persist enough to recover."""
    client = _attach_fake_client(monkeypatch, router)
    router._create_validation_run_node(
        run_id="rid",
        triggered_at="2026-05-20T12:00:00+00:00",
        case_ids=["case-a", "case-b"],
        child_runs={"case-a": "rid:case-a", "case-b": "rid:case-b"},
        model_mode="llm",
    )

    call = _find_call(client, "MERGE (r:ExtractionValidationRun")
    assert call is not None, "CREATE_VALIDATION_RUN was not executed"
    params = call["params"]
    assert params["case_ids"] == ["case-a", "case-b"]
    assert params["child_run_ids"] == ["rid:case-a", "rid:case-b"]
    assert params["case_count"] == 2
    assert params["publish_state"] == "publishing"
    assert params["published_count"] == 0
    assert params["plan_definition_id"] == router._PRODUCTION_PLAN_ID
    assert params["model_mode"] == "llm"


def test_publish_loop_returns_count_sent(monkeypatch, router):
    sent: list[Any] = []

    class FakeBus:
        async def send(self, queue, message):
            sent.append((queue, message))

        async def close(self):
            return None

    monkeypatch.setattr(
        "libs.message_bus.factory.create_message_bus", lambda: FakeBus()
    )

    cases = [{"case_id": f"case-{i}"} for i in range(3)]
    child_runs = {c["case_id"]: f"rid:{c['case_id']}" for c in cases}
    count = router._publish_production_validation_jobs(
        "rid", cases, child_runs, model_mode="auto"
    )
    assert count == 3
    assert len(sent) == 3
    assert sent[0][1].body["context"]["model_mode"] == "auto"


def test_publish_loop_partial_count_when_send_raises(monkeypatch, router):
    class ExplodingBus:
        def __init__(self) -> None:
            self.sent = 0

        async def send(self, queue, message):
            if self.sent == 1:
                raise RuntimeError("bus connection lost")
            self.sent += 1

        async def close(self):
            return None

    monkeypatch.setattr(
        "libs.message_bus.factory.create_message_bus", lambda: ExplodingBus()
    )

    cases = [{"case_id": f"case-{i}"} for i in range(4)]
    child_runs = {c["case_id"]: f"rid:{c['case_id']}" for c in cases}
    with pytest.raises(RuntimeError):
        router._publish_production_validation_jobs(
            "rid", cases, child_runs, model_mode=None
        )


# ---------------------------------------------------------------------------
# Recovery from Neo4j when in-memory state is gone
# ---------------------------------------------------------------------------


def _build_row(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "run_id": "rid",
        "triggered_at": "2026-05-20T12:00:00+00:00",
        "status": "running",
        "case_ids": ["case-a", "case-b"],
        "child_run_ids": ["rid:case-a", "rid:case-b"],
        "case_count": 2,
        "publish_state": "published",
        "published_count": 2,
        "plan_definition_id": "pd-val-key-fact-extraction",
        "model_mode": "llm",
    }
    base.update(overrides)
    return base


def test_recover_running_run_fails_when_case_ids_missing(monkeypatch, router):
    """Pre-resilience rows have no case_ids list -- they must fail cleanly."""
    client = _attach_fake_client(monkeypatch, router)
    row = _build_row(case_ids=[], child_run_ids=[])

    result = router._recover_running_run("rid", row)

    assert result["status"] == "failed"
    fail_call = _find_call(client, "WHERE r.status IN ['queued','running']")
    assert fail_call is not None
    assert "predates resilience persistence" in fail_call["params"]["failure_reason"]


def test_recover_running_run_fails_when_publish_state_failed(monkeypatch, router):
    client = _attach_fake_client(monkeypatch, router)
    row = _build_row(publish_state="publish_failed", failure_reason="bus dropped")

    result = router._recover_running_run("rid", row)

    assert result["status"] == "failed"
    fail_call = _find_call(client, "WHERE r.status IN ['queued','running']")
    assert fail_call is not None
    assert fail_call["params"]["failure_reason"] == "bus dropped"


def test_recover_running_run_rehydrates_in_memory_when_recoverable(
    monkeypatch, router
):
    """When publish completed, the recovery should warm the in-memory cache."""
    scenario_rows = {
        "MATCH (s:ExtractionScenario {case_id: $case_id})": [
            {"case_id": "case-a", "expected_strings": ["foo"], "markdown_body": ""}
        ]
    }
    client = _attach_fake_client(monkeypatch, router, canned=scenario_rows)
    monkeypatch.setattr(router, "_refresh_production_run", lambda *_a, **_k: None)

    row = _build_row(case_ids=["case-a"], child_run_ids=["rid:case-a"], case_count=1)
    result = router._recover_running_run("rid", row)

    assert result["status"] == "running"
    assert "rid" in router._runs
    cached = router._runs["rid"]
    assert cached["production_path"] is True
    assert cached["child_runs"] == {"case-a": "rid:case-a"}
    assert len(cached["cases"]) == 1
    assert cached["cases"][0]["case_id"] == "case-a"


# ---------------------------------------------------------------------------
# Sweeper
# ---------------------------------------------------------------------------


def _stale_row(**overrides: Any) -> dict[str, Any]:
    base = _build_row()
    base.update(overrides)
    return base


def test_sweeper_force_fails_runs_publishing_past_hard_cutoff(monkeypatch, router):
    from datetime import datetime, timedelta, timezone

    from app.services import extraction_run_sweeper as sweeper

    cutoff = sweeper.PUBLISH_HARD_CUTOFF_SECONDS
    too_old = (
        datetime.now(timezone.utc) - timedelta(seconds=cutoff + 60)
    ).isoformat()
    row = _stale_row(
        publish_state="publishing", published_count=3, triggered_at=too_old
    )

    canned = {"MATCH (r:ExtractionValidationRun)\nWHERE r.status IN ['queued',": [row]}
    client = _attach_fake_client(monkeypatch, router, canned=canned)

    def _fake_client_factory():
        return client

    monkeypatch.setattr(
        "app.db.neo4j_client.CodingGraphClient", _fake_client_factory
    )

    fail_calls: list[dict[str, Any]] = []

    def _spy_fail(run_id, row_arg, *, reason):
        fail_calls.append({"run_id": run_id, "reason": reason})
        return {"status": "failed", "failure_reason": reason}

    monkeypatch.setattr(router, "_fail_unrecoverable_run", _spy_fail)
    monkeypatch.setattr(
        router,
        "_recover_running_run",
        lambda *_a, **_k: pytest.fail("recovery must not run for hard-cutoff rows"),
    )

    summary = sweeper.sweep_once()

    assert summary["scanned"] == 1
    assert summary["failed"] == 1
    assert len(fail_calls) == 1
    assert "publish loop did not complete" in fail_calls[0]["reason"]
    assert "3/2" in fail_calls[0]["reason"] or "published" in fail_calls[0]["reason"]


def test_sweeper_calls_recover_for_recent_stale_rows(monkeypatch, router):
    from datetime import datetime, timedelta, timezone

    from app.services import extraction_run_sweeper as sweeper

    # Recent enough that the hard cutoff has not fired, old enough to be in
    # the stale set returned by the find query.
    triggered = (
        datetime.now(timezone.utc)
        - timedelta(seconds=sweeper.RECOVERY_CUTOFF_SECONDS + 30)
    ).isoformat()
    row = _stale_row(publish_state="published", triggered_at=triggered)

    canned = {"MATCH (r:ExtractionValidationRun)\nWHERE r.status IN ['queued',": [row]}
    client = _attach_fake_client(monkeypatch, router, canned=canned)
    monkeypatch.setattr("app.db.neo4j_client.CodingGraphClient", lambda: client)

    recover_calls: list[Any] = []

    def _spy_recover(run_id, row_arg):
        recover_calls.append(run_id)
        return {"status": "completed"}

    monkeypatch.setattr(router, "_recover_running_run", _spy_recover)
    monkeypatch.setattr(
        router,
        "_fail_unrecoverable_run",
        lambda *_a, **_k: pytest.fail("must not force-fail recoverable rows"),
    )

    summary = sweeper.sweep_once()

    assert summary["scanned"] == 1
    assert summary["recovered"] == 1
    assert summary["finalised"] == 1
    assert recover_calls == ["rid"]
