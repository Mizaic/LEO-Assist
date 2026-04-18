"""In-process background job runner for the AI first-pass.

DI-LEO-AI-209 / DO-LEO-AI-206.

Why in-process and not Redis/Service-Bus
----------------------------------------
This is admin tooling triggered manually (no SLA, no multi-replica
coordination required). An in-process job store is sufficient and
avoids dragging in the SBAR pipeline's Redis dependency.

Surface area
------------
  - create_job(...)         -- queue a new job; returns run_id.
  - get_job(run_id)         -- read final summary.
  - subscribe_events(run_id) -- generator yielding queued events.
  - shutdown()              -- best-effort drain (used in tests).

Each job has its own queue.Queue. Events emitted by the worker:
  - {"type": "started", "run_id", "params", "candidate_count", "started_at"}
  - {"type": "candidate_done", ...} per candidate
  - {"type": "completed", "run_id", "summary", "finished_at"}
  - {"type": "error", "run_id", "error"}
"""

from __future__ import annotations

import logging
import queue
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterator

from libs.terminology.client import TerminologyClient

from . import process_one, summarise
from ._gold_pool import get_few_shot_selector
from ._types import AIFirstPassParams, CandidateOutcome

logger = logging.getLogger(__name__)


_TERMINAL_EVENT_TYPES = frozenset({"completed", "error"})


@dataclass
class JobState:
    run_id: str
    status: str = "queued"  # queued | running | completed | error
    started_at: str | None = None
    finished_at: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    candidate_count: int = 0
    summary: dict[str, Any] = field(default_factory=dict)
    sample_outcomes: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "params": dict(self.params),
            "candidate_count": self.candidate_count,
            "summary": dict(self.summary),
            "sample_outcomes": list(self.sample_outcomes),
            "error": self.error,
        }


_JOBS_LOCK = threading.Lock()
_JOBS: dict[str, JobState] = {}
_QUEUES: dict[str, "queue.Queue[dict[str, Any] | None]"] = {}

# Test hook: tests inject a synchronous executor by overriding _spawn.
_RUNNER_EXECUTOR: ThreadPoolExecutor | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _publish(run_id: str, event: dict[str, Any]) -> None:
    q = _QUEUES.get(run_id)
    if q is None:
        return
    try:
        q.put_nowait(event)
    except queue.Full:
        logger.warning("AI first-pass event queue full for run_id=%s; dropping", run_id)


def get_job(run_id: str) -> JobState | None:
    with _JOBS_LOCK:
        return _JOBS.get(run_id)


def list_jobs(*, limit: int = 20) -> list[JobState]:
    with _JOBS_LOCK:
        items = sorted(
            _JOBS.values(),
            key=lambda j: j.started_at or "",
            reverse=True,
        )
        return items[: max(1, int(limit))]


def subscribe_events(
    run_id: str,
    *,
    timeout_s: float = 2.0,
    idle_timeout_s: float = 600.0,
) -> Iterator[dict[str, Any]]:
    """Yield queued events for ``run_id`` until terminal or idle timeout."""
    q = _QUEUES.get(run_id)
    if q is None:
        yield {
            "type": "error",
            "run_id": run_id,
            "error": "unknown_run_id",
        }
        return

    job = get_job(run_id)
    if job is not None and job.status in {"completed", "error"}:
        # Replay terminal payload so SSE consumers that connect late see the
        # final outcome rather than waiting forever for a fresh event.
        if job.status == "completed":
            yield {
                "type": "completed",
                "run_id": run_id,
                "summary": dict(job.summary),
                "finished_at": job.finished_at,
            }
        else:
            yield {
                "type": "error",
                "run_id": run_id,
                "error": job.error or "unknown",
            }
        return

    idle_acc = 0.0
    while True:
        try:
            event = q.get(timeout=timeout_s)
        except queue.Empty:
            idle_acc += timeout_s
            if idle_acc > idle_timeout_s:
                return
            yield {"type": "heartbeat", "run_id": run_id, "ts": time.time()}
            continue
        idle_acc = 0.0
        if event is None:
            return
        yield event
        if event.get("type") in _TERMINAL_EVENT_TYPES:
            return


def _run_job(
    run_id: str,
    *,
    client_factory: Callable[[], Any],
    terminology_factory: Callable[[], TerminologyClient],
    params: AIFirstPassParams,
) -> None:
    """Worker body: fetch + process + persist + publish events."""
    state = get_job(run_id)
    if state is None:
        return
    state.status = "running"
    state.started_at = _now_iso()

    client = client_factory()
    try:
        terminology = terminology_factory()
        from . import fetch_candidates

        rows = fetch_candidates(client, params)
        state.candidate_count = len(rows)
        _publish(
            run_id,
            {
                "type": "started",
                "run_id": run_id,
                "candidate_count": state.candidate_count,
                "params": dict(state.params),
                "started_at": state.started_at,
            },
        )

        if not rows:
            state.status = "completed"
            state.finished_at = _now_iso()
            state.summary = summarise([])
            _publish(
                run_id,
                {
                    "type": "completed",
                    "run_id": run_id,
                    "summary": state.summary,
                    "finished_at": state.finished_at,
                },
            )
            _publish(run_id, None)
            return

        selector = get_few_shot_selector(client, limit=params.few_shot_pool_limit)

        outcomes: list[CandidateOutcome] = []
        workers = max(1, min(int(params.max_workers), 8))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [
                pool.submit(
                    process_one,
                    row,
                    client=client,
                    terminology=terminology,
                    selector=selector,
                    params=params,
                    run_id=run_id,
                )
                for row in rows
            ]
            for fut in futures:
                outcome = fut.result()
                outcomes.append(outcome)
                _publish(run_id, outcome.to_event())

        state.summary = summarise(outcomes)
        state.sample_outcomes = [o.to_dict() for o in outcomes[-20:]]
        state.status = "completed"
        state.finished_at = _now_iso()
        _publish(
            run_id,
            {
                "type": "completed",
                "run_id": run_id,
                "summary": state.summary,
                "finished_at": state.finished_at,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("AI first-pass job failed: run_id=%s", run_id)
        state.status = "error"
        state.error = f"{type(exc).__name__}: {exc}"
        state.finished_at = _now_iso()
        _publish(
            run_id,
            {"type": "error", "run_id": run_id, "error": state.error},
        )
    finally:
        try:
            client.close()
        except Exception:  # noqa: BLE001
            pass
        _publish(run_id, None)


def create_job(
    *,
    client_factory: Callable[[], Any],
    terminology_factory: Callable[[], TerminologyClient],
    params: AIFirstPassParams,
    run_in_background: bool = True,
) -> JobState:
    """Register and (optionally) spawn a new AI first-pass job."""
    run_id = uuid.uuid4().hex
    state = JobState(
        run_id=run_id,
        status="queued",
        params={
            "min_surface_match": params.min_surface_match,
            "semantic_vector_floor": params.semantic_vector_floor,
            "semantic_min_surface": params.semantic_min_surface,
            "statuses": list(params.statuses),
            "limit": params.limit,
            "max_workers": params.max_workers,
            "few_shot_k": params.few_shot_k,
            "coder_max_retries": params.coder_max_retries,
            "haiku_tier": params.haiku_tier,
            "dry_run": bool(params.dry_run),
        },
    )
    with _JOBS_LOCK:
        _JOBS[run_id] = state
        _QUEUES[run_id] = queue.Queue(maxsize=10_000)

    if run_in_background:
        t = threading.Thread(
            target=_run_job,
            kwargs={
                "run_id": run_id,
                "client_factory": client_factory,
                "terminology_factory": terminology_factory,
                "params": params,
            },
            daemon=True,
            name=f"ai-first-pass-{run_id[:8]}",
        )
        t.start()
    else:
        _run_job(
            run_id,
            client_factory=client_factory,
            terminology_factory=terminology_factory,
            params=params,
        )

    return get_job(run_id) or state


def reset_for_tests() -> None:
    """Clear the global job store (test fixture only)."""
    with _JOBS_LOCK:
        _JOBS.clear()
        for q in _QUEUES.values():
            try:
                q.put_nowait(None)
            except Exception:  # noqa: BLE001
                pass
        _QUEUES.clear()
