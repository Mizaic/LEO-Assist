"""Run one referral through the whole pipeline inside this one process.

Atlas trace:
  DO: DO-AA3B7FCC  (production-shaped referral-received bus messages)
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")

Why this exists
---------------
The production path is DurableStepRunner publishing one message per step,
so a run needs a consumer. Locally that leaves two bad options. An
in-memory bus is per-process, so a separate worker process gets its own
empty queue and never sees the job. The configured Service Bus is the
dev namespace, so publishing a job that names a production patient
invites a deployed dev worker to consume it and write to the wrong graph.

This script takes the third option: it owns the bus, the consumer and the
trigger in a single event loop. The transport is swapped; nothing else
is. Context resolution, chunk-scope validation, message building,
DurableStepRunner and every subgraph are the production code.

Safety
------
Service Bus environment variables are removed from this process before a
bus is built, so a job naming a production patient cannot reach a shared
queue. The script refuses to run if either variable survives.

Without --dry-run this writes to whichever graph NEO4J_URI points at.

--dry-run loads existing :Chunk nodes only (no pull, convert, or re-chunk)
and runs the plan in memory. Persist, SBAR, assessments, referral reason,
HITL, and staging writes are skipped. A local quality report is dumped.

Usage
-----
    python scripts/run_referral_inprocess.py --referral-id 000481914514
    python scripts/run_referral_inprocess.py --referral-id X --reset
    python scripts/run_referral_inprocess.py --referral-id X --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import os
import pathlib
import sys
import time
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_BUS_VARS = (
    "AZURE_SERVICE_BUS_NAMESPACE",
    "AZURE_SERVICE_BUS_CONNECTION_STRING",
)
_QUEUE = "pipeline-jobs"
_TERMINAL = ("completed", "failed", "cancelled", "degraded")


def _load_env() -> None:
    """Load local env files, secrets first so they win."""
    from dotenv import load_dotenv

    for name in ("secrets/.env", "secrets/.env.secrets", ".env"):
        load_dotenv(ROOT / name, override=False)


def _force_local_bus() -> list[str]:
    """Remove Service Bus config so create_message_bus cannot reach Azure."""
    removed = [name for name in _BUS_VARS if os.environ.pop(name, None)]
    survivors = [name for name in _BUS_VARS if os.getenv(name)]
    if survivors:
        raise SystemExit(f"Refusing to run: {survivors} still set.")
    return removed


def _make_handler(bus: Any) -> Any:
    """Return a consumer that dispatches one message the way the worker does.

    The in-memory adapter logs and swallows handler exceptions, which
    would turn a broken step into a silent hang, so failures are printed
    here as well.
    """
    from services.pipeline_worker.app.services.durable_dispatcher import (
        handle_durable_message,
    )

    async def handler(message: Any) -> None:
        body = message.body
        label = body.get("action_id") or body.get("event_type") or "?"
        print(f"    -> step {label}")
        try:
            handled = await handle_durable_message(body, bus=bus, queue_name=_QUEUE)
        except Exception as exc:  # noqa: BLE001 - surface, do not swallow
            print(f"    !! step {label} raised {type(exc).__name__}: {exc}")
            raise
        if not handled:
            print(f"    ?? step {label} not handled by the durable dispatcher")

    return handler


def _describe(client: Any, referral_id: str) -> dict[str, Any]:
    """Resolve the replay target and its chunks, reusing production code."""
    from libs.patient_document_runs.chunk_resolver import resolve_pipeline_chunks
    from scripts.replay_referral import _resolve_referral_target

    target = _resolve_referral_target(client, referral_id)
    resolved = resolve_pipeline_chunks(
        client,
        document_reference_id=target.document_reference_id,
        referral_id=referral_id,
        backfill_legacy_ids=True,
    )
    return {
        "target": target,
        "chunk_ids": [str(c["id"]) for c in resolved.chunks],
    }


def _poll(client: Any, run_id: str, timeout_s: int) -> dict[str, Any]:
    """Print stage progress until the run reaches a terminal status."""
    from libs.validation_lab.pipeline import list_stage_progress, poll_run_status

    started = time.time()
    seen: set[tuple[str, str]] = set()
    row: dict[str, str] = {"status": "queued", "assessment_id": ""}
    while time.time() - started < timeout_s:
        row = poll_run_status(client, run_id)
        for stage in list_stage_progress(client, run_id):
            key = (stage["step_id"], stage["status"])
            if key not in seen:
                seen.add(key)
                print(f"  [{int(time.time() - started):>4}s] {key[0]} -> {key[1]}")
        if row["status"] in _TERMINAL:
            break
        time.sleep(2)
    return {
        "status": row["status"],
        "assessment_id": row.get("assessment_id") or "",
        "stages": list_stage_progress(client, run_id),
    }


async def _drive(client: Any, referral_id: str, reset: bool, timeout_s: int) -> int:
    """Own the bus, the consumer and the trigger in one event loop."""
    from libs.message_bus.base import Message
    from libs.message_bus.in_memory_adapter import InMemoryQueueAdapter
    from libs.patient_document_runs.service import start_document_run

    info = _describe(client, referral_id)
    target = info["target"]
    chunk_ids = info["chunk_ids"]
    print(f"patient       : {target.patient_id}")
    print(f"document      : {target.document_reference_id}")
    print(f"chunks        : {len(chunk_ids)}")
    if not chunk_ids:
        print("No chunks resolved; nothing to run.")
        return 1

    if reset:
        from scripts.replay_referral import _reset_for_replay

        print(f"reset         : {_reset_for_replay(client, target)}")

    bus = InMemoryQueueAdapter()
    await bus.subscribe(_QUEUE, _make_handler(bus))

    trigger: list[dict[str, Any]] = []
    result = start_document_run(
        client,
        patient_id=target.patient_id,
        document_reference_id=target.document_reference_id,
        chunk_ids=chunk_ids,
        requested_by="run_referral_inprocess.py",
        publish=lambda body, _run_id: trigger.append(body),
        eager_durable_bootstrap=False,
    )
    if result.status == "failed":
        print(f"start_document_run failed: {result.error_message}")
        return 1

    print(f"run_id        : {result.run_id}")
    print("\nstages:")
    for body in trigger:
        await bus.send(_QUEUE, Message(body=body))

    outcome = await asyncio.to_thread(_poll, client, result.run_id, timeout_s)
    await bus.close()

    print(f"\nfinal status  : {outcome['status']}")
    print(f"assessment    : {outcome['assessment_id'] or '(none)'}")
    if outcome["status"] not in ("completed", "degraded"):
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--referral-id", required=True)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Clear prior facts and draft assessments before running.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the plan in memory. Load existing chunks only. No writeback.",
    )
    parser.add_argument(
        "--report-dir",
        default="tmp/referral-quality-dry-run",
        help="Directory for dry-run quality JSON reports.",
    )
    parser.add_argument("--timeout", type=int, default=900)
    return parser


async def _drive_dry_run(
    client: Any, referral_id: str, report_dir: str, timeout_s: int
) -> int:
    """Load existing chunks and run the plan with dry_run=True."""
    from libs.referral_quality.inprocess_dry_run import run_dry_pipeline
    from pathlib import Path

    outcome = await run_dry_pipeline(
        client,
        referral_id,
        report_dir=Path(report_dir),
        timeout_s=timeout_s,
    )
    print(f"chunks        : {outcome['chunk_count']}")
    print(f"final status  : {outcome['status']}")
    print(f"report        : {outcome['report_path']}")
    if outcome["status"] == "skipped":
        return 2
    if outcome["status"] not in ("completed", "degraded"):
        return 1
    return 0


def main() -> int:
    args = build_parser().parse_args()
    if args.dry_run and args.reset:
        raise SystemExit("Refusing --reset with --dry-run: reset writes to Neo4j.")

    _load_env()
    removed = _force_local_bus()
    mode = (
        "dry-run (no writeback, existing chunks only)"
        if args.dry_run
        else ("in-process referral run (no Service Bus, no separate worker)")
    )
    print("=" * 68)
    print(mode)
    print("=" * 68)
    print(f"neo4j         : {os.getenv('NEO4J_URI')}")
    print(f"bus           : in-memory (unset {removed or 'nothing'})")
    print(f"referral      : {args.referral_id}")
    print(f"dry_run       : {args.dry_run}")

    from libs.neo4j_client.client import PatientGraphClient

    client = PatientGraphClient()
    try:
        if args.dry_run:
            return asyncio.run(
                _drive_dry_run(client, args.referral_id, args.report_dir, args.timeout)
            )
        return asyncio.run(_drive(client, args.referral_id, args.reset, args.timeout))
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
