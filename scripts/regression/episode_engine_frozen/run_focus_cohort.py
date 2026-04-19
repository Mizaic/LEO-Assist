"""Run the Haiku Episode Engine focus-first pipeline across the full cohort.

Iterates over every patient that has at least one encounter, runs the
LangGraph engine via ``build_episode_engine_subgraph()`` so we can capture
the per-EoC ``eoc_traces`` that the focus-first pipeline records, and writes:

  - ``cohort-run-{ts}.json`` (full per-patient detail; safe to commit
    because it carries real Neo4j patient ids)
  - ``cohort-run-{ts}-summary.md`` (markdown table for human review)

By default runs in ``dry_run=True`` so no EpisodeOfCare nodes are written.

USAGE
=====

  Smoke (10 random patients, dry-run):
    python scripts/regression/episode_engine_frozen/run_focus_cohort.py --limit 10

  Full cohort, dry-run (default):
    python scripts/regression/episode_engine_frozen/run_focus_cohort.py

  Full cohort, real writes (DETACH DELETEs existing EoCs per patient first
  via the writer node; only run after a clean dry-run):
    python scripts/regression/episode_engine_frozen/run_focus_cohort.py \
        --no-dry-run

Cost
====
~$0.18/patient at SYN-EE-001 baseline. ~$19 / ~3.6 h sequential for ~103
patients. The runner prints a per-25-patient progress line so you can spot
cost blow-outs early.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=True)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
log = logging.getLogger("focus_cohort")


_Q_PATIENTS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(:Encounter)
WHERE p.id IS NOT NULL
RETURN DISTINCT toString(p.id) AS patient_id
ORDER BY patient_id
"""


def _list_patients(limit: int | None) -> list[str]:
    from libs.neo4j_client.client import PatientGraphClient

    client = PatientGraphClient()
    try:
        rows = client.run(_Q_PATIENTS) or []
    finally:
        client.close()
    ids = [str(r.get("patient_id") or "") for r in rows if r.get("patient_id")]
    if limit is not None:
        ids = ids[:limit]
    return ids


def _summarise_eoc_traces(traces: list[dict[str, Any]]) -> dict[str, Any]:
    if not traces:
        return {
            "windows": 0,
            "audit_input_total": 0,
            "audit_kept_by_guards_total": 0,
            "audit_kept_by_llm_total": 0,
            "audit_filter_failed_any": False,
            "audit_filter_overflow_any": False,
            "audit_parts_max": 1,
        }
    return {
        "windows": len(traces),
        "audit_input_total": sum(int(t.get("audit_input_encounters") or 0) for t in traces),
        "audit_kept_by_guards_total": sum(
            int(t.get("audit_kept_by_guards") or 0) for t in traces
        ),
        "audit_kept_by_llm_total": sum(
            int(t.get("audit_kept_by_llm") or 0) for t in traces
        ),
        "audit_filter_failed_any": any(bool(t.get("audit_filter_failed")) for t in traces),
        "audit_filter_overflow_any": any(
            bool(t.get("audit_filter_overflow")) for t in traces
        ),
        "audit_parts_max": max(int(t.get("audit_parts") or 1) for t in traces),
    }


def _summarise_episodes(written: list[dict[str, Any]]) -> dict[str, Any]:
    sites: Counter[str] = Counter()
    types: Counter[str] = Counter()
    milestone_counts: Counter[str] = Counter()
    needs_review = 0
    for raw in written:
        types[str(raw.get("episode_type") or "unknown")] += 1
        sites[str(raw.get("suspected_site") or "unknown").lower()] += 1
        if raw.get("needs_human_review"):
            needs_review += 1
        for m in raw.get("milestones") or []:
            milestone_counts[str(m.get("type") or "unknown")] += 1
    return {
        "episode_count": len(written),
        "by_type": dict(types),
        "by_site": dict(sites),
        "milestone_counts": dict(milestone_counts),
        "needs_human_review": needs_review,
    }


def _summarise_stages(stage_traces: list[dict[str, Any]]) -> dict[str, Any]:
    by_stage: dict[str, dict[str, float]] = {}
    for s in stage_traces:
        name = str(s.get("stage") or "unknown")
        bucket = by_stage.setdefault(
            name,
            {"calls": 0, "in": 0, "out": 0, "cost": 0.0, "latency_ms": 0, "errors": 0},
        )
        bucket["calls"] += 1
        bucket["in"] += int(s.get("input_tokens") or 0)
        bucket["out"] += int(s.get("output_tokens") or 0)
        bucket["cost"] += float(s.get("cost_usd") or 0.0)
        bucket["latency_ms"] += int(s.get("latency_ms") or 0)
        if s.get("ok") is False:
            bucket["errors"] += 1
    return {
        "by_stage": by_stage,
        "total_cost_usd": round(sum(b["cost"] for b in by_stage.values()), 4),
        "total_latency_ms": int(sum(b["latency_ms"] for b in by_stage.values())),
    }


def _run_one(patient_id: str, dry_run: bool) -> dict[str, Any]:
    from services.analysis_worker.app.episode_engine.chain import (
        build_episode_engine_subgraph,
    )
    from services.analysis_worker.app.episode_engine.tracing import new_trace_id

    started = time.monotonic()
    graph = build_episode_engine_subgraph()
    initial = {
        "patient_id": str(patient_id),
        "domain_id": "",
        "dry_run": dry_run,
        "stage_traces": [],
        "errors": [],
        "trace_id": new_trace_id(),
    }
    final = graph.invoke(initial)
    elapsed_s = time.monotonic() - started

    eoc_traces = list(final.get("eoc_traces") or [])
    written = list(final.get("written_episodes") or [])
    stage_traces = list(final.get("stage_traces") or [])
    return {
        "patient_id": patient_id,
        "trace_id": str(final.get("trace_id") or ""),
        "encounter_count": int(final.get("encounter_count") or 0),
        "errors": list(final.get("errors") or []),
        "wall_clock_s": round(elapsed_s, 2),
        "eoc_summary": _summarise_eoc_traces(eoc_traces),
        "episode_summary": _summarise_episodes(written),
        "stage_summary": _summarise_stages(stage_traces),
        "eoc_traces": eoc_traces,
        "episodes": written,
    }


def _safe_run(patient_id: str, dry_run: bool) -> dict[str, Any]:
    try:
        return _run_one(patient_id, dry_run=dry_run)
    except Exception as exc:
        log.exception("Engine failed for patient %s", patient_id)
        return {
            "patient_id": patient_id,
            "trace_id": "",
            "encounter_count": 0,
            "errors": [f"{type(exc).__name__}: {exc}"],
            "wall_clock_s": 0.0,
            "eoc_summary": _summarise_eoc_traces([]),
            "episode_summary": _summarise_episodes([]),
            "stage_summary": _summarise_stages([]),
            "eoc_traces": [],
            "episodes": [],
            "traceback": traceback.format_exc(),
        }


def _format_md_summary(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    started = payload.get("started_at")
    finished = payload.get("finished_at")
    lines.append(f"# Episode Engine focus-first cohort run")
    lines.append("")
    lines.append(f"- Started:  {started}")
    lines.append(f"- Finished: {finished}")
    lines.append(f"- Cohort size: {payload.get('cohort_size')}")
    lines.append(f"- dry_run: {payload.get('dry_run')}")
    lines.append(f"- Total cost (USD): ${payload.get('total_cost_usd', 0.0):.2f}")
    lines.append(
        f"- Total wall clock (s): {payload.get('total_wall_clock_s', 0.0):.0f}"
    )
    lines.append("")

    rolled = payload.get("rollup", {})
    lines.append("## Roll-up")
    lines.append("")
    for k, v in rolled.items():
        lines.append(f"- {k}: {v}")
    lines.append("")

    lines.append("## Per-patient")
    lines.append("")
    lines.append(
        "| patient_id | enc | windows | audit_in | guards | llm_keep | parts_max | "
        "fail | over | episodes | review | cost | wall_s | errors |"
    )
    lines.append(
        "|---|---:|---:|---:|---:|---:|---:|:---:|:---:|---:|---:|---:|---:|---|"
    )
    for r in payload.get("patients", []):
        eoc = r.get("eoc_summary", {})
        ep = r.get("episode_summary", {})
        st = r.get("stage_summary", {})
        errors = "; ".join(r.get("errors") or [])[:80]
        lines.append(
            f"| {r['patient_id']} | {r['encounter_count']} | {eoc['windows']} "
            f"| {eoc['audit_input_total']} | {eoc['audit_kept_by_guards_total']} "
            f"| {eoc['audit_kept_by_llm_total']} | {eoc['audit_parts_max']} "
            f"| {'Y' if eoc['audit_filter_failed_any'] else '-'} "
            f"| {'Y' if eoc['audit_filter_overflow_any'] else '-'} "
            f"| {ep['episode_count']} | {ep['needs_human_review']} "
            f"| ${st.get('total_cost_usd', 0.0):.3f} | {r['wall_clock_s']:.0f} "
            f"| {errors} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional cap on number of patients (for smoke runs).",
    )
    parser.add_argument(
        "--no-dry-run",
        action="store_true",
        help=(
            "Default is dry_run=True (no writes). Pass this flag to actually "
            "DETACH DELETE existing EpisodeOfCare nodes per patient and write "
            "fresh ones. Only run after a clean dry-run."
        ),
    )
    parser.add_argument(
        "--out-dir",
        default=str(Path(__file__).parent),
        help="Where to write the cohort-run-{ts}.json and .md outputs.",
    )
    args = parser.parse_args()

    dry_run = not args.no_dry_run
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info("Loading cohort from Neo4j (limit=%s) ...", args.limit)
    patient_ids = _list_patients(args.limit)
    log.info("Cohort size: %d patients (dry_run=%s)", len(patient_ids), dry_run)
    if not patient_ids:
        log.error("No patients found. Exiting.")
        return 1

    started = datetime.now(timezone.utc)
    started_mono = time.monotonic()
    rows: list[dict[str, Any]] = []
    total_cost = 0.0
    failed_patients = 0

    for i, pid in enumerate(patient_ids, start=1):
        result = _safe_run(pid, dry_run=dry_run)
        rows.append(result)
        cost = float(result.get("stage_summary", {}).get("total_cost_usd") or 0.0)
        total_cost += cost
        if result.get("errors"):
            failed_patients += 1
        if i % 5 == 0 or i == len(patient_ids):
            elapsed = time.monotonic() - started_mono
            avg = elapsed / i
            remaining_s = avg * (len(patient_ids) - i)
            log.info(
                "  %d/%d done | cost=$%.2f | failed=%d | avg=%.1fs/pt | ETA=%.0fmin",
                i,
                len(patient_ids),
                total_cost,
                failed_patients,
                avg,
                remaining_s / 60.0,
            )

    finished = datetime.now(timezone.utc)
    total_elapsed_s = time.monotonic() - started_mono

    overflow_patients = sum(
        1 for r in rows if r.get("eoc_summary", {}).get("audit_filter_overflow_any")
    )
    fail_open_patients = sum(
        1 for r in rows if r.get("eoc_summary", {}).get("audit_filter_failed_any")
    )
    multi_part_patients = sum(
        1
        for r in rows
        if int(r.get("eoc_summary", {}).get("audit_parts_max") or 1) > 1
    )
    total_episodes = sum(
        int(r.get("episode_summary", {}).get("episode_count") or 0) for r in rows
    )
    needs_review = sum(
        int(r.get("episode_summary", {}).get("needs_human_review") or 0) for r in rows
    )
    site_counter: Counter[str] = Counter()
    type_counter: Counter[str] = Counter()
    for r in rows:
        site_counter.update(r.get("episode_summary", {}).get("by_site", {}))
        type_counter.update(r.get("episode_summary", {}).get("by_type", {}))

    rollup = {
        "patients_processed": len(rows),
        "patients_failed": failed_patients,
        "patients_with_audit_filter_failure_open": fail_open_patients,
        "patients_with_partitioner_overflow": overflow_patients,
        "patients_with_multi_part_extraction": multi_part_patients,
        "total_episodes": total_episodes,
        "episodes_needs_human_review": needs_review,
        "episodes_by_type": dict(type_counter),
        "episodes_by_site": dict(site_counter),
    }

    payload: dict[str, Any] = {
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "cohort_size": len(patient_ids),
        "dry_run": dry_run,
        "total_cost_usd": round(total_cost, 4),
        "total_wall_clock_s": round(total_elapsed_s, 2),
        "rollup": rollup,
        "patients": rows,
    }

    ts = started.strftime("%Y%m%dT%H%M%SZ")
    json_path = out_dir / f"cohort-run-{ts}.json"
    md_path = out_dir / f"cohort-run-{ts}-summary.md"
    json_path.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    md_path.write_text(_format_md_summary(payload) + "\n")
    log.info("JSON dump  -> %s", json_path.relative_to(ROOT))
    log.info("MD summary -> %s", md_path.relative_to(ROOT))
    log.info(
        "DONE: %d patients, %d episodes, %d failed, $%.2f total, %.0fs wall",
        len(rows),
        total_episodes,
        failed_patients,
        total_cost,
        total_elapsed_s,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
