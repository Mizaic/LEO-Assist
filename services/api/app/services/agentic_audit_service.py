"""Background Agentic Auditor runner for the API.

Model-agnostic audit service — the model and provider are configurable
via environment variables, defaulting to AWS max-tier.

Mirrors the threading / job-state pattern used by label_verifier.py.
Exposes begin_audit_job(), get_audit_state(), request_stop_audit(), and
run_audit() — all of which are called by the training router endpoints.

Job state is kept in a single in-process dict (protected by a lock) so
the status endpoint can return live progress without touching the DB.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from libs.audit.auditor import (
    AuditVerdict,
    AutoFixCapMonitor,
    CostGuardrail,
    FETCH_AUDIT_LABELS,
    FETCH_HITL_PENDING_LABEL_IDS,
    MAX_WORKERS,
    SecondOpinionProvider,
    SET_AUDITED_AT,
    ToolExecutor,
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

logger = logging.getLogger(__name__)

# ── Job state ─────────────────────────────────────────────────────────────────

_audit_state_lock = threading.Lock()
_audit_state: dict[str, Any] = {
    "status":             "idle",   # idle | running | stopping | done | failed | cancelled
    "mode":               "all",
    "apply":              False,
    "no_agentic":         False,
    "started_at":         None,
    "finished_at":        None,
    "total":              0,
    "done":               0,
    "passed":             0,
    "has_issues":         0,
    "errors":             0,
    "auto_fixed":         0,
    "proposals":          0,
    "needs_review":       0,
    "second_opinions":    0,
    "total_tokens":       0,
    "estimated_cost_usd": 0.0,
    "stop_requested":     False,
    "last_error":         None,
}


def _patch_state(**kwargs: Any) -> None:
    with _audit_state_lock:
        _audit_state.update(kwargs)


def _increment_state(**kwargs: int) -> None:
    with _audit_state_lock:
        for k, v in kwargs.items():
            _audit_state[k] = _audit_state.get(k, 0) + v


def get_audit_state() -> dict[str, Any]:
    with _audit_state_lock:
        return dict(_audit_state)


def _stop_requested() -> bool:
    with _audit_state_lock:
        return bool(_audit_state.get("stop_requested"))


def begin_audit_job(
    mode: str = "all",
    apply: bool = False,
    no_agentic: bool = False,
    limit: int = 0,
) -> bool:
    """Atomically claim the running slot.  Returns False if a job is active."""
    with _audit_state_lock:
        if _audit_state["status"] in ("running", "stopping"):
            return False
        _audit_state.update({
            "status":             "running",
            "mode":               mode,
            "apply":              apply,
            "no_agentic":         no_agentic,
            "started_at":         time.time(),
            "finished_at":        None,
            "total":              0,
            "done":               0,
            "passed":             0,
            "has_issues":         0,
            "errors":             0,
            "auto_fixed":         0,
            "proposals":          0,
            "needs_review":       0,
            "second_opinions":    0,
            "total_tokens":       0,
            "estimated_cost_usd": 0.0,
            "stop_requested":     False,
            "last_error":         None,
        })
        return True


def request_stop_audit() -> bool:
    """Request graceful stop.  Returns False if no job is running."""
    with _audit_state_lock:
        if _audit_state["status"] not in ("running", "stopping"):
            return False
        _audit_state["stop_requested"] = True
        _audit_state["status"]         = "stopping"
        return True


# ── Trail writer ──────────────────────────────────────────────────────────────

_TRAIL_DIR = Path(__file__).resolve().parents[4] / "data" / "audit_trails"


def _write_trail_entry(trail_path: Path, verdict: AuditVerdict, applied: bool) -> None:
    entry = {
        "label_id":         verdict.label_id,
        "record_verdict":   verdict.record_verdict,
        "timestamp":        datetime.now(timezone.utc).isoformat(),
        "applied":          applied,
        "auto_fixes":       verdict.auto_fixes_applied,
        "proposals":        verdict.proposals,
        "missing_entities": verdict.missing_entities,
        "entity_verdicts":  verdict.entity_verdicts,
        "tool_calls":       verdict.tool_calls,
        "input_tokens":     verdict.input_tokens,
        "output_tokens":    verdict.output_tokens,
        "cached_tokens":    verdict.cached_tokens,
        "error":            verdict.error,
    }
    try:
        trail_path.parent.mkdir(parents=True, exist_ok=True)
        with open(trail_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except Exception as exc:
        logger.warning("Failed to write trail entry: %s", exc)


# ── Background worker ─────────────────────────────────────────────────────────

def run_audit() -> None:
    """Background daemon thread — runs the full two-pass audit."""
    state     = get_audit_state()
    mode      = state.get("mode", "all")
    apply     = state.get("apply", False)
    no_agentic = state.get("no_agentic", False)

    ts         = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    trail_path = _TRAIL_DIR / f"agentic_audit_trail_{ts}.jsonl"

    try:
        _run_audit_inner(mode, apply, no_agentic, trail_path)
    except Exception as exc:
        logger.error("Audit job failed: %s", exc, exc_info=True)
        _patch_state(
            status="failed",
            finished_at=time.time(),
            last_error=str(exc),
        )


def _run_audit_inner(
    mode: str,
    apply: bool,
    no_agentic: bool,
    trail_path: Path,
) -> None:
    neo4j = PatientGraphClient()
    try:
        _fetch_and_run(neo4j, mode, apply, no_agentic, trail_path)
    finally:
        neo4j.close()


def _fetch_and_run(
    neo4j: PatientGraphClient,
    mode: str,
    apply: bool,
    no_agentic: bool,
    trail_path: Path,
) -> None:
    # Build the WHERE clause addendum for hitl_only mode
    hitl_ids_clause = ""
    if mode == "hitl_only":
        try:
            hitl_ids = {r["label_id"] for r in neo4j.run(FETCH_HITL_PENDING_LABEL_IDS)}
            if not hitl_ids:
                logger.info("Agentic audit (hitl_only): no pending HITL labels — nothing to do.")
                _patch_state(status="done", finished_at=time.time(), total=0)
                return
            ids_str = ", ".join(f"'{lid}'" for lid in hitl_ids)
            hitl_ids_clause = f"AND t.label_id IN [{ids_str}]"
        except Exception as exc:
            logger.warning("Could not fetch HITL label IDs: %s — auditing all", exc)

    query = FETCH_AUDIT_LABELS.format(
        skip_audited_clause="",
        hitl_ids_clause=hitl_ids_clause,
        limit_clause="",
        offset_clause="",
    )

    rows = neo4j.run(query)
    total = len(rows)
    _patch_state(total=total)
    logger.info("Agentic audit: fetched %d labels (mode=%s)", total, mode)

    if total == 0:
        _patch_state(status="done", finished_at=time.time())
        return

    # Preload sentence splitter on this thread (lazy-loads once)
    _get_splitter()

    _audit_provider = "aws"
    opus            = create_llm(provider=_audit_provider, tier="max")
    system_prompt   = INJECTION_GUARD + get_prompt("agentic_audit", version=1)

    guardrail     = CostGuardrail()
    so_provider   = SecondOpinionProvider(guardrail=guardrail)
    tool_executor = ToolExecutor(second_opinion=so_provider)
    cap_monitor   = AutoFixCapMonitor()

    logger.info(
        "Agentic audit started: model=%s token_budget=%d cost_cap=$%.2f agentic=%s",
        opus.model_id,
        guardrail._token_budget,
        guardrail._cost_cap,
        not no_agentic,
    )

    def _process_one(row: dict[str, Any]) -> AuditVerdict:
        return audit_record(opus, system_prompt, row)

    workers = int(__import__("os").getenv("AUDIT_WORKERS", str(MAX_WORKERS)))

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="agentic-audit") as pool:
        future_to_row = {pool.submit(_process_one, row): row for row in rows}

        for future in as_completed(future_to_row):
            if _stop_requested():
                break

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

            if not no_agentic and not verdict.error and not _stop_requested():
                try:
                    entities = _parse_entities(row["entities_json"])
                except Exception:
                    entities = []
                verdict = _pass_two(
                    pass_one_verdict=verdict,
                    row=row,
                    entities=entities,
                    audit_client=opus,
                    system_prompt=system_prompt,
                    tool_executor=tool_executor,
                    guardrail=guardrail,
                )

            _classify_fixes(verdict, agentic=not no_agentic)

            # Collect per-record stats before Neo4j write
            second_opinions_this = sum(
                1 for tc in verdict.tool_calls
                if tc.get("tool_name") == "get_second_opinion"
            )

            # Neo4j write (apply fixes or just mark audited_at)
            applied_this_record = False
            try:
                entities = _parse_entities(row["entities_json"])
            except Exception:
                entities = []

            entity_count = len(entities)
            fix_count    = len(verdict.auto_fixes_applied)
            cap_triggered = cap_monitor.record(entity_count, fix_count)

            if apply and not cap_triggered:
                try:
                    fixed, prog_repairs = _apply_fixes(
                        entities, verdict.auto_fixes_applied, row["text"]
                    )
                    changed = verdict.auto_fixes_applied or prog_repairs
                    if changed:
                        audit_actions = json.dumps({
                            "model":        opus.model_id,
                            "provider":     _audit_provider,
                            "applied_at":   datetime.now(timezone.utc).isoformat(),
                            "fixes":        verdict.auto_fixes_applied,
                            "prog_repairs": prog_repairs,
                        })
                        neo4j.run(
                            UPDATE_ENTITIES,
                            label_id=label_id,
                            entities_json=json.dumps(fixed),
                            audit_actions=audit_actions,
                            audit_model=opus.model_id,
                        )
                        applied_this_record = True
                    else:
                        neo4j.run(SET_AUDITED_AT, label_id=label_id)
                except Exception as exc:
                    logger.error("Failed to write fixes for %s: %s", label_id, exc)
            else:
                try:
                    neo4j.run(SET_AUDITED_AT, label_id=label_id)
                except Exception as exc:
                    logger.warning("Failed to set audited_at for %s: %s", label_id, exc)

            _write_trail_entry(trail_path, verdict, applied=applied_this_record)

            # Update job state counters
            _increment_state(
                done=1,
                passed=(1 if verdict.record_verdict == "pass" else 0),
                has_issues=(1 if verdict.record_verdict == "has_issues" else 0),
                errors=(1 if verdict.error else 0),
                auto_fixed=len(verdict.auto_fixes_applied) if applied_this_record else 0,
                proposals=len(verdict.proposals),
                needs_review=sum(
                    1 for ev in verdict.entity_verdicts
                    if ev.get("verdict") == "needs_review"
                ),
                second_opinions=second_opinions_this,
                total_tokens=verdict.input_tokens + verdict.output_tokens,
            )
            with _audit_state_lock:
                _audit_state["estimated_cost_usd"] = guardrail.estimated_cost

    final_status = "cancelled" if _stop_requested() else "done"
    _patch_state(status=final_status, finished_at=time.time())
    logger.info(
        "Agentic audit %s. cost=$%.2f tokens=%d",
        final_status,
        guardrail.estimated_cost,
        guardrail.total_tokens,
    )
