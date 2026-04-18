"""Episode engine v1 spike runner.

Runs the Haiku-driven episode engine across a small cohort of synthetic
patients (default 10, including the canonical SYN-EE-001 breast-cancer
reference case) in DRY-RUN mode (no graph mutations) and writes a
markdown report capturing:

  - existing rule-based episodes (from the patient graph as-is)
  - engine output (windows, classifications, milestones, reconciled
    episodes, per-stage trace, total cost in tokens)
  - errors per stage

Usage::

    python scripts/investigations/episode_engine_spike/run_spike.py \
        --patients SYN-EE-001,SYN-EE-002,SYN-EE-003   # explicit list
    python scripts/investigations/episode_engine_spike/run_spike.py \
        --auto 10                                     # canonical 10
    python scripts/investigations/episode_engine_spike/run_spike.py \
        --apply                                       # write to graph

Synthetic ids are resolved to real Neo4j patient ids via the gitignored
``secrets/episode_engine_cohort_map.json`` mapping. Real ids never
appear in the committed source.

Output:
    scripts/investigations/episode_engine_spike/reports/
        spike-<UTC-timestamp>.md   (gitignored)
"""

from __future__ import annotations

import argparse
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
log = logging.getLogger("episode_engine_spike")


REQUIRED_SYNTHETIC = "SYN-EE-001"


_EXISTING_EPISODES_Q = """
MATCH (p:Patient {id: $patient_id})-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare)
RETURN ep.episode_id    AS episode_id,
       ep.condition_type AS condition_type,
       ep.cancer_type   AS cancer_type,
       ep.status        AS status,
       ep.start_date    AS start_date,
       ep.end_date      AS end_date,
       [(e:Encounter)-[r:IS_PART_OF]->(ep) | {milestone: r.milestone_type, date: e.date, encounter_id: e.id}] AS milestones
ORDER BY ep.start_date
"""


def _existing_episodes(client, patient_id: str) -> list[dict]:
    rows = client.run(_EXISTING_EPISODES_Q, patient_id=patient_id) or []
    out = []
    for r in rows:
        d = dict(r)
        d["start_date"] = str(d.get("start_date") or "")
        d["end_date"] = str(d.get("end_date") or "")
        out.append(d)
    return out


def _format_existing(eps: list[dict]) -> str:
    if not eps:
        return "_No existing episodes._"
    lines = []
    for ep in eps:
        lines.append(
            f"- **{ep.get('episode_id')}** ({ep.get('condition_type')}, "
            f"{ep.get('cancer_type') or 'site?'}, status={ep.get('status')}) "
            f"{ep.get('start_date')} -> {ep.get('end_date') or 'open'}"
        )
        for m in ep.get("milestones") or []:
            lines.append(
                f"  - {m.get('milestone')} on {m.get('date')} "
                f"(enc {str(m.get('encounter_id'))[:8]})"
            )
    return "\n".join(lines)


def _format_engine(result) -> str:
    lines = []
    lines.append(
        f"- trace_id `{result.trace_id}`, encounters={result.encounter_count}, "
        f"episodes={result.episode_count}, "
        f"in_tok={result.total_input_tokens}, out_tok={result.total_output_tokens}, "
        f"cached_in_tok={result.total_cached_input_tokens}, "
        f"cost_usd={result.total_cost_usd:.6f}, "
        f"latency_ms={result.total_latency_ms}, errors={len(result.errors)}"
    )
    for ep in result.episodes:
        lines.append(
            f"- **{ep.episode_id}** {ep.episode_type} site=`{ep.suspected_site}` "
            f"{ep.window_start} -> {ep.window_end or 'open'} "
            f"conf={ep.confidence:.2f} hitl={ep.needs_human_review}"
        )
        lines.append(f"  - reasoning: {ep.reasoning}")
        for m in ep.milestones:
            extras: list[str] = []
            if m.treatment_type:
                extras.append(f"treatment_type={m.treatment_type}")
            if m.presentation_place:
                extras.append(f"place={m.presentation_place}")
            extras_str = (", " + ", ".join(extras)) if extras else ""
            lines.append(
                f"  - {m.type} on {m.date} enc=`{m.encounter_id[:8]}` "
                f"conf={m.confidence:.2f}{extras_str}"
            )
            lines.append(f"    > {m.evidence_quote[:160]}")

    if result.errors:
        lines.append("")
        lines.append("**Errors:**")
        for e in result.errors:
            lines.append(f"  - {e}")

    lines.append("")
    lines.append("**Stage trace:**")
    for s in result.stage_traces:
        lines.append(
            f"  - {s.stage} ({s.prompt_version}, tier={s.tier or '?'}, "
            f"model `{s.model_id}`) "
            f"in={s.input_tokens} (cached {s.cached_input_tokens}) "
            f"out={s.output_tokens} cost_usd={s.cost_usd:.6f} "
            f"latency_ms={s.latency_ms} ok={s.ok} "
            f"{('-- ' + s.error) if s.error else ''}"
        )

    return "\n".join(lines)


def _resolve_cohort(synthetic_ids: list[str]) -> list[tuple[str, str]]:
    """Resolve a list of synthetic ids -> (synthetic_id, real_id) pairs."""

    from scripts.regression.episode_engine_frozen.cohort_ids import (
        CohortMappingError,
        resolve_real_id,
    )

    pairs: list[tuple[str, str]] = []
    for sid in synthetic_ids:
        try:
            pairs.append((sid, resolve_real_id(sid)))
        except CohortMappingError as exc:
            raise SystemExit(f"Cannot resolve {sid}: {exc}") from exc
    return pairs


def _auto_cohort(limit: int) -> list[str]:
    from scripts.regression.episode_engine_frozen.cohort_ids import FROZEN_COHORT

    take = max(1, min(limit, len(FROZEN_COHORT)))
    cohort = list(FROZEN_COHORT[:take])
    if REQUIRED_SYNTHETIC not in cohort:
        cohort = [REQUIRED_SYNTHETIC] + cohort[: take - 1]
    return cohort


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--patients",
        type=str,
        default="",
        help=(
            "Comma-separated SYNTHETIC patient ids (e.g. "
            "SYN-EE-001,SYN-EE-002). SYN-EE-001 is always included."
        ),
    )
    parser.add_argument(
        "--auto",
        type=int,
        default=10,
        help=(
            "If --patients omitted, take the first N from FROZEN_COHORT "
            "(SYN-EE-001..SYN-EE-N)."
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write episodes to the graph. Default: dry_run (no writes).",
    )
    parser.add_argument(
        "--out",
        type=str,
        default="",
        help="Override output report path.",
    )
    args = parser.parse_args()

    from libs.neo4j_client.client import PatientGraphClient
    from services.analysis_worker.app.episode_engine import run_episode_engine

    if args.patients.strip():
        synthetic_ids = [
            p.strip() for p in args.patients.split(",") if p.strip()
        ]
        if REQUIRED_SYNTHETIC not in synthetic_ids:
            synthetic_ids = [REQUIRED_SYNTHETIC] + synthetic_ids
    else:
        synthetic_ids = _auto_cohort(args.auto)

    pairs = _resolve_cohort(synthetic_ids)
    log.info(
        "Spike cohort (%d synthetic ids): %s",
        len(pairs),
        [s for s, _ in pairs],
    )

    client = PatientGraphClient()
    try:
        report_dir = (
            ROOT / "scripts" / "investigations" / "episode_engine_spike" / "reports"
        )
        report_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        report_path = (
            Path(args.out) if args.out else report_dir / f"spike-{ts}.md"
        )

        sections: list[str] = []
        sections.append(
            f"# Episode Engine v1 Spike\n\n_{ts}, dry_run={not args.apply}_\n"
        )
        summary_rows: list[dict] = []

        for synthetic_id, real_id in pairs:
            log.info("--- patient %s", synthetic_id)
            existing = _existing_episodes(client, real_id)
            try:
                result = run_episode_engine(real_id, dry_run=not args.apply)
            except Exception as exc:
                log.exception("Engine crashed for %s", synthetic_id)
                sections.append(
                    f"\n## {synthetic_id}\n\n"
                    f"**ENGINE CRASHED**: `{type(exc).__name__}: {exc}`\n"
                )
                summary_rows.append(
                    {
                        "patient": synthetic_id,
                        "episodes": "ERR",
                        "errors": str(exc)[:80],
                    }
                )
                continue

            sections.append(f"\n## {synthetic_id}\n")
            sections.append(
                f"### Existing rule-based episodes ({len(existing)})\n"
            )
            sections.append(_format_existing(existing))
            sections.append("\n### Engine output\n")
            sections.append(_format_engine(result))
            summary_rows.append(
                {
                    "patient": synthetic_id,
                    "existing": len(existing),
                    "engine": result.episode_count,
                    "in_tok": result.total_input_tokens,
                    "out_tok": result.total_output_tokens,
                    "cached_tok": result.total_cached_input_tokens,
                    "cost_usd": result.total_cost_usd,
                    "errors": len(result.errors),
                }
            )

        # Cohort totals
        total_cost = sum(float(r.get("cost_usd", 0) or 0) for r in summary_rows)
        total_in = sum(int(r.get("in_tok", 0) or 0) for r in summary_rows)
        total_out = sum(int(r.get("out_tok", 0) or 0) for r in summary_rows)
        n_pat = max(1, len(summary_rows))

        sections.append("\n## Summary\n")
        sections.append(
            "| patient | existing | engine | in_tok | out_tok | cached_tok | "
            "cost_usd | errors |"
        )
        sections.append("|---|---|---|---|---|---|---|---|")
        for r in summary_rows:
            cost_val = r.get("cost_usd")
            cost_str = (
                f"{cost_val:.6f}" if isinstance(cost_val, (int, float)) else "-"
            )
            sections.append(
                f"| {r.get('patient')} | {r.get('existing','-')} | "
                f"{r.get('engine','-')} | {r.get('in_tok','-')} | "
                f"{r.get('out_tok','-')} | {r.get('cached_tok','-')} | "
                f"{cost_str} | {r.get('errors','-')} |"
            )

        sections.append("")
        sections.append(
            f"**Cohort totals:** patients={len(summary_rows)}, "
            f"in_tok={total_in}, out_tok={total_out}, "
            f"cost_usd={total_cost:.6f}, "
            f"avg_cost_per_patient_usd={total_cost / n_pat:.6f}"
        )

        report_path.write_text("\n".join(sections))
        log.info("Wrote report -> %s", report_path)

        json_path = report_path.with_suffix(".json")
        json_path.write_text(json.dumps(summary_rows, indent=2))
        log.info("Wrote summary JSON -> %s", json_path)

    finally:
        client.close()


if __name__ == "__main__":
    main()
