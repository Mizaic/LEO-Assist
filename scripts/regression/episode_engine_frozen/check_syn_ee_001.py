"""SYN-EE-001 single-patient regression check (focus-first pipeline).

Invokes the LangGraph engine directly (bypassing run_episode_engine) so we can
inspect the audit trace fields the new focus-first pipeline records on engine
state (`eoc_traces`, `focused_sets`). Prints:

  - encounter_count for the timeline
  - per-EoC audit summary: input encounters, kept-by-guards, kept-by-LLM,
    dropped-by-LLM (with reasons), filter_failed/overflow flags, audit_parts
  - per-part trace items
  - episode summary: episode_type, suspected_site, milestone types/dates,
    treatment_types, needs_human_review
  - stage_traces totals: cost, latency, token counts (so we can sanity-check
    Bedrock spend)

Always runs in dry_run=True so no EpisodeOfCare nodes are written.

USAGE
=====

    python scripts/regression/episode_engine_frozen/check_syn_ee_001.py
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=True)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
log = logging.getLogger("syn_ee_001_check")

SYNTHETIC_ID = "SYN-EE-001"


def _format_date(value) -> str:
    if value is None:
        return "----"
    return str(value)


def _print_eoc_trace(trace: dict) -> None:
    window_id = trace.get("window_id", "?")
    print(f"  Window {window_id}")
    print(f"    audit_input_encounters : {trace.get('audit_input_encounters')}")
    print(f"    audit_kept_by_guards   : {trace.get('audit_kept_by_guards')}")
    print(f"    audit_kept_by_llm      : {trace.get('audit_kept_by_llm')}")
    dropped = trace.get("audit_dropped_by_llm") or []
    print(f"    audit_dropped_by_llm   : {len(dropped)}")
    for d in dropped[:5]:
        print(
            f"      - {d.get('encounter_id', '')[:8]} : "
            f"{d.get('reason', '')[:120]}"
        )
    if len(dropped) > 5:
        print(f"      ... +{len(dropped) - 5} more")
    print(f"    audit_filter_failed    : {trace.get('audit_filter_failed')}")
    print(f"    audit_filter_overflow  : {trace.get('audit_filter_overflow')}")
    print(f"    audit_parts            : {trace.get('audit_parts')}")
    parts = trace.get("parts") or []
    if parts:
        print("    parts:")
        for p in parts:
            err = f" ERROR: {p.get('error')}" if p.get("error") else ""
            print(
                f"      - part {p.get('part_index')}: "
                f"{p.get('encounter_count')} encounters, "
                f"{p.get('milestones_count')} milestones{err}"
            )


def _print_episode(idx: int, ep) -> None:
    print(f"  Episode {idx}: {ep.episode_id}")
    print(f"    episode_type      : {ep.episode_type}")
    print(f"    suspected_site    : {ep.suspected_site}")
    print(f"    needs_human_review: {ep.needs_human_review}")
    if ep.milestones:
        print("    milestones:")
        for m in ep.milestones:
            extra = ""
            if m.treatment_type:
                extra = f" [{m.treatment_type}]"
            print(
                f"      - {_format_date(m.date)}  {m.type}{extra}  "
                f"(conf={m.confidence:.2f})"
            )
    sn = getattr(ep, "safety_netting", None)
    if sn is not None and getattr(sn, "present", False):
        evidence_n = len(getattr(sn, "evidence", []) or [])
        print(f"    safety_netting    : YES ({evidence_n} evidence items)")
    if ep.disruptions:
        print(f"    disruptions       : {len(ep.disruptions)}")
        for d in ep.disruptions[:3]:
            print(f"      - {_format_date(d.date)}  {d.type}")


def _print_stage_totals(stages: list) -> None:
    by_stage: dict[str, dict[str, float]] = {}
    for s in stages:
        bucket = by_stage.setdefault(
            s.stage,
            {"calls": 0, "in": 0, "out": 0, "cost": 0.0, "latency_ms": 0},
        )
        bucket["calls"] += 1
        bucket["in"] += s.input_tokens
        bucket["out"] += s.output_tokens
        bucket["cost"] += s.cost_usd
        bucket["latency_ms"] += s.latency_ms
    print("Stage totals:")
    for name, b in sorted(by_stage.items()):
        print(
            f"  {name:30s} calls={b['calls']:>3}  "
            f"in={int(b['in']):>6}  out={int(b['out']):>5}  "
            f"cost=${b['cost']:.4f}  lat={int(b['latency_ms'])}ms"
        )
    total_cost = sum(s.cost_usd for s in stages)
    total_lat = sum(s.latency_ms for s in stages)
    print(f"  TOTAL                          cost=${total_cost:.4f}  lat={total_lat}ms")


def main() -> int:
    from scripts.regression.episode_engine_frozen.cohort_ids import resolve_real_id
    from services.analysis_worker.app.episode_engine.chain import (
        build_episode_engine_subgraph,
    )
    from services.analysis_worker.app.episode_engine.schemas import (
        Episode,
        StageTrace,
    )
    from services.analysis_worker.app.episode_engine.tracing import new_trace_id

    real_id = resolve_real_id(SYNTHETIC_ID)
    log.info("Resolved %s -> %s", SYNTHETIC_ID, real_id)

    started = datetime.now(timezone.utc)
    graph = build_episode_engine_subgraph()
    initial = {
        "patient_id": real_id,
        "domain_id": "",
        "dry_run": True,
        "stage_traces": [],
        "errors": [],
        "trace_id": new_trace_id(),
    }
    final = graph.invoke(initial)
    elapsed = (datetime.now(timezone.utc) - started).total_seconds()

    print()
    print("=" * 72)
    print(f"SYN-EE-001 focus-first regression check")
    print(f"trace_id        : {final.get('trace_id')}")
    print(f"encounter_count : {final.get('encounter_count')}")
    print(f"wall_clock      : {elapsed:.1f}s")
    print(f"errors          : {final.get('errors') or '(none)'}")
    print("=" * 72)

    eoc_traces = final.get("eoc_traces") or []
    print()
    print(f"EoC audit traces ({len(eoc_traces)}):")
    if not eoc_traces:
        print("  (none -- segmenter found no candidate windows)")
    for t in eoc_traces:
        _print_eoc_trace(t)

    written = final.get("written_episodes") or []
    print()
    print(f"Episodes ({len(written)}):")
    for i, raw in enumerate(written, start=1):
        try:
            ep = Episode.model_validate(raw)
            _print_episode(i, ep)
        except Exception as exc:
            log.warning("Could not validate episode %d: %s", i, exc)

    print()
    stages = [StageTrace.model_validate(d) for d in (final.get("stage_traces") or [])]
    _print_stage_totals(stages)

    out_path = Path(__file__).with_name(
        f"check-syn-ee-001-{started.strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    out_path.write_text(
        json.dumps(
            {
                "synthetic_id": SYNTHETIC_ID,
                "trace_id": final.get("trace_id"),
                "encounter_count": final.get("encounter_count"),
                "wall_clock_s": elapsed,
                "errors": list(final.get("errors") or []),
                "eoc_traces": eoc_traces,
                "episodes": written,
                "stage_traces": [s.model_dump(mode="json") for s in stages],
            },
            indent=2,
            default=str,
        )
        + "\n"
    )
    print(f"\nFull JSON dump -> {out_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
