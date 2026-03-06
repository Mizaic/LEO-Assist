"""Opus-in-the-Loop TrainingLabel auditor — CLI entry point.

Uses Claude Opus 4.6 (AWS_MAX_MODEL) to review every included
TrainingLabel record, validating entities, assertions, values, SNOMED
codes, and span boundaries.  Applies safe auto-fixes and escalates
ambiguous issues for human review.

For entities flagged "needs_review" with SNOMED coding concerns a
second pass invokes Opus with Bedrock tool-use, delegating terminology
lookups to Haiku (AWS_SMALL_MODEL) via the internal Terminology API.
Opus may also call get_second_opinion to get a blind Haiku assessment
without anchoring bias.  Cost guardrails (token budget + dollar cap)
and a hard iteration cap prevent runaway spending.  SNOMED fields are
never auto-fixed.

Usage
-----
    # Dry-run (default) — audit only, no writes:
    python -m scripts.opus_training_auditor --limit 50

    # Apply safe auto-fixes:
    python -m scripts.opus_training_auditor --apply

    # Skip already-audited records on re-run:
    python -m scripts.opus_training_auditor --skip-audited --apply

    # Full options:
    python -m scripts.opus_training_auditor \\
        --limit 500 --offset 0 --apply --skip-audited

Environment variables
---------------------
    OPUS_AUDIT_WORKERS         Thread pool size (default: 5).
    OPUS_AUDIT_TOKEN_BUDGET    Max cumulative tokens for the run (default: 2_000_000).
    OPUS_AUDIT_COST_CAP        Max USD cost for the run (default: 50.0).
    TERMINOLOGY_API_URL        Terminology service base URL (default: http://localhost:8001).
    NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD
    AWS_DEFAULT_REGION         Bedrock region.
    AWS_MAX_MODEL              Override Opus model ID.
    AWS_SMALL_MODEL            Override Haiku model ID.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

_SECRETS = _REPO_ROOT / "secrets"
load_dotenv(_SECRETS / ".env.config", override=True)
load_dotenv(_SECRETS / ".env", override=False)

# All core logic lives in the shared lib — import from there
from libs.audit.auditor import (  # noqa: E402
    AuditVerdict,
    AutoFixCapMonitor,
    CostGuardrail,
    MAX_WORKERS,
    SecondOpinionProvider,
    ToolExecutor,
    FETCH_AUDIT_LABELS,
    SET_AUDITED_AT,
    UPDATE_ENTITIES,
    _apply_fixes,
    _classify_fixes,
    _get_splitter,
    _parse_entities,
    _pass_two,
    audit_record,
)
from libs.llm_client.factory import create_llm
from libs.llm_client.prompt_safety import INJECTION_GUARD
from libs.neo4j_client.client import PatientGraphClient
from libs.prompts.registry import get_prompt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("opus_training_auditor")


# ── Audit trail (JSONL) ───────────────────────────────────────────────────────

def _write_trail_entry(
    trail_path: Path,
    verdict: AuditVerdict,
    applied: bool,
) -> None:
    entry = {
        "label_id":        verdict.label_id,
        "record_verdict":  verdict.record_verdict,
        "timestamp":       datetime.now(timezone.utc).isoformat(),
        "applied":         applied,
        "auto_fixes":      verdict.auto_fixes_applied,
        "proposals":       verdict.proposals,
        "missing_entities": verdict.missing_entities,
        "entity_verdicts": verdict.entity_verdicts,
        "tool_calls":      verdict.tool_calls,
        "input_tokens":    verdict.input_tokens,
        "output_tokens":   verdict.output_tokens,
        "cached_tokens":   verdict.cached_tokens,
        "error":           verdict.error,
    }
    with open(trail_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")


# ── Report generation ─────────────────────────────────────────────────────────

def _generate_report(
    verdicts: list[AuditVerdict],
    report_path: Path,
    applied: bool,
    elapsed_s: float,
    guardrail: CostGuardrail,
) -> None:
    total      = len(verdicts)
    errors     = sum(1 for v in verdicts if v.error)
    passed     = sum(1 for v in verdicts if v.record_verdict == "pass")
    has_issues = sum(1 for v in verdicts if v.record_verdict == "has_issues")

    verdict_counts: Counter[str] = Counter()
    for v in verdicts:
        for ev in v.entity_verdicts:
            verdict_counts[ev["verdict"]] += 1

    total_auto_fixes  = sum(len(v.auto_fixes_applied) for v in verdicts)
    total_proposals   = sum(len(v.proposals) for v in verdicts)
    total_tool_calls  = sum(len(v.tool_calls) for v in verdicts)
    second_opinions   = sum(
        1 for v in verdicts for tc in v.tool_calls
        if tc.get("tool_name") == "get_second_opinion"
    )

    total_input  = sum(v.input_tokens for v in verdicts)
    total_output = sum(v.output_tokens for v in verdicts)
    total_cached = sum(v.cached_tokens for v in verdicts)

    fix_field_counts: Counter[str] = Counter()
    for v in verdicts:
        for fix in v.auto_fixes_applied:
            fix_field_counts[fix.get("field", "unknown")] += 1

    proposal_type_counts: Counter[str] = Counter()
    for v in verdicts:
        for p in v.proposals:
            proposal_type_counts[p.get("verdict", "unknown")] += 1

    sample_fixes: list[dict] = []
    sample_proposals: list[dict] = []
    sample_reviews: list[dict] = []
    sample_tool_calls: list[dict] = []
    for v in verdicts:
        if len(sample_fixes) < 10:
            for fix in v.auto_fixes_applied:
                sample_fixes.append({"label_id": v.label_id, **fix})
                if len(sample_fixes) >= 10:
                    break
        if len(sample_proposals) < 10:
            for p in v.proposals:
                sample_proposals.append({"label_id": v.label_id, **p})
                if len(sample_proposals) >= 10:
                    break
        if len(sample_reviews) < 10:
            for ev in v.entity_verdicts:
                if ev["verdict"] == "needs_review":
                    sample_reviews.append({"label_id": v.label_id, **ev})
                    if len(sample_reviews) >= 10:
                        break
        if len(sample_tool_calls) < 5:
            for tc in v.tool_calls:
                sample_tool_calls.append({"label_id": v.label_id, **tc})
                if len(sample_tool_calls) >= 5:
                    break

    lines = [
        "# Opus Training Label Audit Report",
        "",
        f"**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}  ",
        f"**Mode:** {'APPLY' if applied else 'DRY-RUN'}  ",
        f"**Records audited:** {total}  ",
        f"**Elapsed:** {elapsed_s:.0f}s ({elapsed_s / max(total, 1):.1f}s/record)  ",
        "",
        "## Summary",
        "",
        "| Metric | Count |",
        "|--------|-------|",
        f"| Records passed | {passed} |",
        f"| Records with issues | {has_issues} |",
        f"| Errors (parse/LLM) | {errors} |",
        f"| Total auto-fixes | {total_auto_fixes} |",
        f"| Total proposals (human review) | {total_proposals} |",
        f"| Total agentic tool calls | {total_tool_calls} |",
        f"| Second opinions requested | {second_opinions} |",
        "",
        "## Entity Verdict Breakdown",
        "",
        "| Verdict | Count |",
        "|---------|-------|",
    ]
    for verdict_type in ("correct", "fixable", "needs_review", "remove"):
        lines.append(f"| {verdict_type} | {verdict_counts.get(verdict_type, 0)} |")
    lines.append("")

    if fix_field_counts:
        lines.extend([
            "## Auto-Fix Field Breakdown",
            "",
            "| Field | Count |",
            "|-------|-------|",
        ])
        for fld, cnt in fix_field_counts.most_common():
            lines.append(f"| {fld} | {cnt} |")
        lines.append("")

    if proposal_type_counts:
        lines.extend([
            "## Proposal Type Breakdown",
            "",
            "| Type | Count |",
            "|------|-------|",
        ])
        for ptype, cnt in proposal_type_counts.most_common():
            lines.append(f"| {ptype} | {cnt} |")
        lines.append("")

    lines.extend([
        "## Token Usage & Cost",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total input tokens | {total_input:,} |",
        f"| Total output tokens | {total_output:,} |",
        f"| Cached input tokens | {total_cached:,} |",
        f"| Guardrail total tokens | {guardrail.total_tokens:,} |",
        f"| Estimated cost | ${guardrail.estimated_cost:.2f} |",
        "",
    ])

    if sample_fixes:
        lines.extend(["## Sample Auto-Fixes (up to 10)", ""])
        for sf in sample_fixes:
            lines.append(
                f"- **{sf['label_id'][:12]}...** entity[{sf.get('entity_index')}] "
                f"`{sf.get('field')}`: `{sf.get('current')}` -> `{sf.get('suggested')}` "
                f"(conf={sf.get('confidence', 0):.2f}) -- {sf.get('rationale', '')}"
            )
        lines.append("")

    if sample_proposals:
        lines.extend(["## Sample Proposals for Human Review (up to 10)", ""])
        for sp in sample_proposals:
            if sp.get("verdict") == "missing":
                lines.append(
                    f"- **{sp['label_id'][:12]}...** MISSING: `{sp.get('text')}` "
                    f"({sp.get('label')}, {sp.get('assertion')}) "
                    f"conf={sp.get('confidence', 0):.2f} -- {sp.get('rationale', '')}"
                )
            else:
                lines.append(
                    f"- **{sp['label_id'][:12]}...** entity[{sp.get('entity_index')}] "
                    f"`{sp.get('field')}`: `{sp.get('current')}` -> `{sp.get('suggested')}` "
                    f"(conf={sp.get('confidence', 0):.2f}) -- {sp.get('rationale', '')}"
                )
        lines.append("")

    if sample_reviews:
        lines.extend(["## Sample Needs-Review (up to 10)", ""])
        for sr in sample_reviews:
            issues_str = "; ".join(
                f"{i.get('field')}: {i.get('rationale', '')}"
                for i in sr.get("issues", [])
            )
            lines.append(
                f"- **{sr['label_id'][:12]}...** entity[{sr.get('entity_index')}] "
                f"-- {issues_str}"
            )
        lines.append("")

    if sample_tool_calls:
        lines.extend(["## Sample Agentic Tool Calls (up to 5)", ""])
        for tc in sample_tool_calls:
            lines.append(
                f"- **{tc['label_id'][:12]}...** `{tc.get('tool_name')}` "
                f"input={json.dumps(tc.get('tool_input', {}))}"
            )
        lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Report written to %s", report_path)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Opus-in-the-Loop TrainingLabel auditor"
    )
    parser.add_argument("--limit",        type=int,  default=0,          help="Max records (0=all)")
    parser.add_argument("--offset",       type=int,  default=0,          help="Skip first N records")
    parser.add_argument("--apply",        action="store_true",           help="Write fixes to Neo4j")
    parser.add_argument("--skip-audited", action="store_true",           help="Skip audited records")
    parser.add_argument("--workers",      type=int,  default=MAX_WORKERS, help="Thread pool size")
    parser.add_argument(
        "--no-agentic", action="store_true",
        help="Skip pass 2 (no tool-use); useful for cost-constrained runs",
    )
    args = parser.parse_args()

    mode_label = "APPLY" if args.apply else "DRY-RUN"
    logger.info("=== Opus Training Label Auditor [%s] ===", mode_label)

    skip_clause   = "AND t.audited_at IS NULL" if args.skip_audited else ""
    limit_clause  = f"LIMIT {args.limit}"  if args.limit  else ""
    offset_clause = f"SKIP {args.offset}"  if args.offset else ""
    query = FETCH_AUDIT_LABELS.format(
        skip_audited_clause=skip_clause,
        hitl_ids_clause="",
        limit_clause=limit_clause,
        offset_clause=offset_clause,
    )

    neo4j = PatientGraphClient()
    try:
        rows = neo4j.run(query)
    except Exception as exc:
        logger.error("Failed to fetch TrainingLabels: %s", exc)
        sys.exit(1)

    total = len(rows)
    logger.info("Fetched %d records to audit", total)
    if total == 0:
        logger.info("Nothing to audit -- exiting.")
        neo4j.close()
        return

    logger.info("Initialising sentence splitter...")
    _get_splitter()
    logger.info("Sentence splitter ready")

    opus          = create_llm(provider="aws", tier="max")
    system_prompt = INJECTION_GUARD + get_prompt("opus_audit", version=1)
    logger.info("Using Opus model: %s", opus.model_id)

    so_provider  = SecondOpinionProvider(guardrail=CostGuardrail())  # temp guardrail for SO
    guardrail    = CostGuardrail()
    # Wire SO provider to share the run's guardrail
    so_provider._guardrail = guardrail

    tool_executor = ToolExecutor(second_opinion=so_provider)
    logger.info(
        "Cost guardrail: token_budget=%d, cost_cap=$%.2f",
        guardrail._token_budget,
        guardrail._cost_cap,
    )

    ts          = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    scripts_dir = Path(__file__).resolve().parent
    trail_path  = scripts_dir / f"opus_audit_trail_{ts}.jsonl"
    report_path = scripts_dir / f"opus_audit_report_{ts}.md"

    verdicts: list[AuditVerdict] = []
    cap_monitor        = AutoFixCapMonitor()
    cap_triggered_at: int | None = None
    t_start = time.monotonic()

    def _process_one(row: dict) -> AuditVerdict:
        return audit_record(opus, system_prompt, row)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        future_to_row = {pool.submit(_process_one, row): row for row in rows}
        for i, future in enumerate(as_completed(future_to_row), 1):
            row      = future_to_row[future]
            label_id = row["label_id"]

            try:
                verdict = future.result()
            except Exception as exc:
                verdict = AuditVerdict(
                    label_id=label_id,
                    record_verdict="error",
                    entity_verdicts=[],
                    missing_entities=[],
                    error=str(exc),
                )

            guardrail.record(verdict.input_tokens, verdict.output_tokens, is_haiku=False)

            if not args.no_agentic and not verdict.error:
                try:
                    entities = _parse_entities(row["entities_json"])
                except Exception:
                    entities = []
                verdict = _pass_two(
                    pass_one_verdict=verdict,
                    row=row,
                    entities=entities,
                    opus_client=opus,
                    system_prompt=system_prompt,
                    tool_executor=tool_executor,
                    guardrail=guardrail,
                )

            _classify_fixes(verdict)

            try:
                entities   = _parse_entities(row["entities_json"])
                entity_count = len(entities)
            except Exception:
                entity_count = 0
            fix_count = len(verdict.auto_fixes_applied)

            if cap_monitor.record(entity_count, fix_count) and cap_triggered_at is None:
                cap_triggered_at = i
                logger.warning(
                    "AUTO-FIX CAP TRIGGERED at record %d/%d -- "
                    ">%.0f%% of entities in last %d records received auto-fixes. "
                    "Continuing audit but SUSPENDING auto-fix writes.",
                    i, total, cap_monitor._ratio * 100, cap_monitor._window,
                )

            applied_this_record = False
            if args.apply and verdict.auto_fixes_applied and cap_triggered_at is None:
                try:
                    fixed_entities = _apply_fixes(entities, verdict.auto_fixes_applied, row["text"])
                    neo4j.run(
                        UPDATE_ENTITIES,
                        label_id=label_id,
                        entities_json=json.dumps(fixed_entities),
                    )
                    applied_this_record = True
                except Exception as exc:
                    logger.error("Failed to write fixes for %s: %s", label_id, exc)
            else:
                try:
                    neo4j.run(SET_AUDITED_AT, label_id=label_id)
                except Exception as exc:
                    logger.warning("Failed to set audited_at for %s: %s", label_id, exc)

            _write_trail_entry(trail_path, verdict, applied=applied_this_record)
            verdicts.append(verdict)

            if i % 50 == 0 or i == total:
                elapsed    = time.monotonic() - t_start
                rate       = i / elapsed if elapsed > 0 else 0
                tool_total = sum(len(v.tool_calls) for v in verdicts)
                logger.info(
                    "Progress: %d/%d (%.1f rec/s) | pass=%d issues=%d errors=%d "
                    "fixes=%d proposals=%d tools=%d cost=$%.2f",
                    i, total, rate,
                    sum(1 for v in verdicts if v.record_verdict == "pass"),
                    sum(1 for v in verdicts if v.record_verdict == "has_issues"),
                    sum(1 for v in verdicts if v.error),
                    sum(len(v.auto_fixes_applied) for v in verdicts),
                    sum(len(v.proposals) for v in verdicts),
                    tool_total,
                    guardrail.estimated_cost,
                )

    elapsed_s = time.monotonic() - t_start
    logger.info("Audit complete in %.0fs", elapsed_s)

    _generate_report(
        verdicts, report_path,
        applied=args.apply,
        elapsed_s=elapsed_s,
        guardrail=guardrail,
    )
    logger.info("Audit trail: %s", trail_path)

    if cap_triggered_at is not None:
        logger.warning(
            "AUTO-FIX CAP was triggered at record %d. Review the audit trail "
            "for systemic issues before re-running with --apply.",
            cap_triggered_at,
        )

    neo4j.close()


if __name__ == "__main__":
    main()
