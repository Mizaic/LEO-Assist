#!/usr/bin/env python3
"""Find GP encounters that mention "fast track" in raw text and queue a coding run.

Uses the same path as ``POST /patients/{id}/encounters/{id}/reset-and-recode``:
``reset_encounter`` then a message to ``PIPELINE_QUEUE_NAME`` (default
``pipeline-jobs``) for ``pd-gp-encounter-coding``. With Azure Service Bus
configured, jobs are published there; otherwise the in-memory bus (local dev).

When ``AZURE_SERVICE_BUS_NAMESPACE`` is set, install deps are required
(``azure-servicebus``). Use the repo virtualenv, e.g.
``.venv/bin/python scripts/requeue_fast_track_encounters.py ...``.

Examples:

  # Count only (default)
  .venv/bin/python scripts/requeue_fast_track_encounters.py

  # Preview first 20 rows
  .venv/bin/python scripts/requeue_fast_track_encounters.py --limit 20

  # Reset + queue all matches (careful: production)
  .venv/bin/python scripts/requeue_fast_track_encounters.py --apply

  # Queue only (no graph reset) — e.g. after reset already ran
  .venv/bin/python scripts/requeue_fast_track_encounters.py --apply --no-reset
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "services" / "api"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_ROOT / "secrets" / ".env.config", override=True)
load_dotenv(_ROOT / "secrets" / ".env", override=False)
load_dotenv(_ROOT / "secrets" / ".env.secrets", override=False)

from app.services.reset_service import reset_encounter  # noqa: E402
from libs.message_bus.base import Message  # noqa: E402
from libs.message_bus.factory import create_message_bus  # noqa: E402
from libs.neo4j_client.client import PatientGraphClient  # noqa: E402

DEFAULT_ARTIFACTS = _ROOT / "artifacts" / "requeue_fast_track"

FAST_TRACK_MATCH = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE coalesce(e.classification_content_type, 'clinical') = 'clinical'
  AND trim(coalesce(e.text, '')) <> ''
  AND toLower(coalesce(e.text, '')) CONTAINS 'fast track'
RETURN toString(p.id) AS patient_id,
       toString(e.id) AS encounter_id,
       e.date AS date
ORDER BY patient_id, encounter_id
"""

PIPELINE_QUEUE = os.getenv("PIPELINE_QUEUE_NAME", "pipeline-jobs")
PLAN_ID = "pd-gp-encounter-coding"


def _encounter_created_payload(
    *,
    patient_id: str,
    encounter_id: str,
    dry_run: bool,
    trigger_analysis: bool,
) -> dict[str, Any]:
    """Match ``app.routers.patients._encounter_created_payload``."""
    return {
        "event_type": "encounter-created",
        "patient_id": patient_id,
        "encounter_id": encounter_id,
        "plan_definition_id": PLAN_ID,
        "mode": "extract_encounter",
        "dry_run": dry_run,
        "trigger_analysis": trigger_analysis,
        "context": {
            "encounter_id": encounter_id,
            "plan_definition_id": PLAN_ID,
            "mode": "extract_encounter",
            "dry_run": dry_run,
            "trigger_analysis": trigger_analysis,
        },
    }


def _load_rows(client: PatientGraphClient, limit: int) -> list[dict[str, Any]]:
    rows = [dict(r) for r in client.run(FAST_TRACK_MATCH)]
    if limit > 0:
        rows = rows[:limit]
    return rows


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--apply",
        action="store_true",
        help="Reset (unless --no-reset) and publish one job per row.",
    )
    p.add_argument(
        "--no-reset",
        action="store_true",
        help="Do not run reset_encounter; only publish pipeline jobs.",
    )
    p.add_argument(
        "--dry-run-pipeline",
        action="store_true",
        help="Set dry_run=True on published jobs (no graph writes in worker).",
    )
    p.add_argument(
        "--trigger-analysis",
        action="store_true",
        help="Set trigger_analysis=True (episode / downstream re-run in worker).",
    )
    p.add_argument(
        "--limit", type=int, default=0, help="Max rows (0 = all). Default: 0."
    )
    p.add_argument(
        "--report-dir",
        type=Path,
        default=DEFAULT_ARTIFACTS,
        help="Write JSON report here when using --apply.",
    )
    return p.parse_args()


async def _publish_jobs(
    rows: list[dict[str, Any]], *, dry_run: bool, trigger_analysis: bool
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    bus = create_message_bus()
    try:
        for row in rows:
            pid = str(row["patient_id"] or "")
            eid = str(row["encounter_id"] or "")
            if not pid or not eid:
                continue
            run_id = str(uuid.uuid4())
            body = _encounter_created_payload(
                patient_id=pid,
                encounter_id=eid,
                dry_run=dry_run,
                trigger_analysis=trigger_analysis,
            )
            await bus.send(
                PIPELINE_QUEUE,
                Message(
                    body=body,
                    correlation_id=run_id,
                    subject="encounter-created",
                ),
            )
            out.append(
                {
                    "patient_id": pid,
                    "encounter_id": eid,
                    "run_id": run_id,
                    "queued": True,
                }
            )
    finally:
        await bus.close()
    return out


def main() -> int:
    args = _parse_args()
    client = PatientGraphClient()
    try:
        rows = _load_rows(client, args.limit)
    finally:
        client.close()

    patients = {str(r["patient_id"]) for r in rows if r.get("patient_id")}
    summary = {
        "match": "fast track (case-insensitive substring on e.text)",
        "encounters": len(rows),
        "distinct_patients": len(patients),
        "apply": bool(args.apply),
        "reset": not args.no_reset,
        "pipeline_dry_run": bool(args.dry_run_pipeline),
        "trigger_analysis": bool(args.trigger_analysis),
        "queue": PIPELINE_QUEUE,
    }
    print(json.dumps(summary, indent=2))
    for i, r in enumerate(rows[:15]):
        print(
            f"  {r.get('patient_id')}\t{r.get('encounter_id')}\t{r.get('date', '')}"
        )
    if len(rows) > 15:
        print(f"  ... and {len(rows) - 15} more")

    if not args.apply:
        print(
            "\nDry run only. Re-run with --apply to reset (unless --no-reset) "
            "and publish jobs."
        )
        return 0

    reset_results: list[dict[str, Any]] = []
    rows_to_queue: list[dict[str, Any]] = list(rows)
    if not args.no_reset:
        rows_to_queue = []
        rc = PatientGraphClient()
        try:
            for row in rows:
                pid = str(row.get("patient_id") or "")
                eid = str(row.get("encounter_id") or "")
                if not pid or not eid:
                    continue
                with rc.session() as session:
                    rr = reset_encounter(pid, eid, session)
                reset_results.append(
                    {"patient_id": pid, "encounter_id": eid, "reset": rr}
                )
                if str(rr.get("error") or "") == "encounter_not_found":
                    continue
                rows_to_queue.append(row)
        finally:
            rc.close()

    queued = asyncio.run(
        _publish_jobs(
            rows_to_queue,
            dry_run=args.dry_run_pipeline,
            trigger_analysis=args.trigger_analysis,
        )
    )

    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "reset_by_encounter": reset_results
        if not args.no_reset
        else [],
        "queued": queued,
    }
    args.report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = args.report_dir / f"requeue_fast_track_{stamp}.json"
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {path} ({len(queued)} jobs).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
