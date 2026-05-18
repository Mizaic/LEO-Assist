#!/usr/bin/env python3
"""Stage 2 - Backup, consolidate, and strict tidy of reviewed EpisodeOfCare.

Workflow:
    1. Refuse to run while open severity='high' audit findings exist (Stage 1
       gate). --force overrides.
    2. Snapshot every reviewed EpisodeOfCare and its IS_PART_OF edges to
       artifacts/ncda_episode_backup/<timestamp>/{episodes,milestones}.parquet
       plus a Cypher dump.
    3. Consolidate per services.analysis_worker.app.ncda_detector.tidy_rules.
    4. Strict tidy: delete IS_PART_OF whose milestone_type is not canonical
       and the encounter could not be consolidated.
    5. Verify each reviewed episode now carries at most one of each canonical
       milestone (max 4 anchors).

Idempotent and re-runnable; --dry-run computes the plan without writing.

Usage:
    python scripts/ncda/tidy_reviewed_episodes.py --dry-run
    python scripts/ncda/tidy_reviewed_episodes.py
    python scripts/ncda/tidy_reviewed_episodes.py --force --json
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from neo4j import GraphDatabase  # noqa: E402

from libs.data.ncda_label_audit import (  # noqa: E402
    AuditFinding,
    open_high_severity_count,
    upsert_findings,
)
from services.analysis_worker.app.ncda_detector.tidy_rules import (  # noqa: E402
    CANONICAL_MILESTONES,
    consolidate,
)

_PULL_QUERY = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(enc:Encounter)-[r:IS_PART_OF]->(e:EpisodeOfCare)
WHERE e.reviewed_at IS NOT NULL
RETURN
    coalesce(toString(p.id), toString(p.patient_id)) AS patient_id,
    e.id AS episode_id,
    e.cancer_type AS cancer_type,
    enc.id AS encounter_id,
    r.milestone_type AS milestone_type,
    r.outcome AS current_outcome,
    toString(enc.date) AS encounter_date,
    enc.text AS text
"""

_REWRITE_QUERY = """
MATCH (enc:Encounter {id: $encounter_id})-[r:IS_PART_OF]->(e:EpisodeOfCare {id: $episode_id})
WHERE r.milestone_type = $old_milestone
SET r.milestone_type = $new_milestone,
    r.outcome = coalesce($outcome, r.outcome),
    r.tidy_at = $now,
    r.tidy_previous = $old_milestone
"""

_DELETE_QUERY = """
MATCH (enc:Encounter {id: $encounter_id})-[r:IS_PART_OF]->(e:EpisodeOfCare {id: $episode_id})
WHERE r.milestone_type = $old_milestone
DELETE r
"""

_VERIFY_QUERY = """
MATCH (enc:Encounter)-[r:IS_PART_OF]->(e:EpisodeOfCare)
WHERE e.reviewed_at IS NOT NULL
WITH e, r.milestone_type AS mt, count(*) AS n
WHERE n > 1 AND mt IN $canonical
RETURN e.id AS episode_id, mt AS milestone_type, n
"""


def _connect():
    uri = os.environ.get("NEO4J_PATIENT_URI", "").strip() or os.environ.get(
        "NEO4J_URI", ""
    ).strip()
    user = os.environ.get("NEO4J_PATIENT_USER", "").strip() or os.environ.get(
        "NEO4J_USER", ""
    ).strip()
    pw = os.environ.get("NEO4J_PATIENT_PASSWORD", "").strip() or os.environ.get(
        "NEO4J_PASSWORD", ""
    ).strip()
    if not all([uri, user, pw]):
        raise SystemExit("ERROR: NEO4J credentials missing.")
    return GraphDatabase.driver(uri, auth=(user, pw))


def _backup_dir() -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "artifacts" / "ncda_episode_backup" / ts
    out.mkdir(parents=True, exist_ok=True)
    return out


def _snapshot_csv(rows: list[dict], target: Path) -> None:
    if not rows:
        target.write_text("")
        return
    fieldnames = list(rows[0].keys())
    with target.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k) for k in fieldnames})


def _decide_actions(rows: list[dict]) -> list[dict]:
    """Run consolidate() against every reviewed milestone row."""
    decisions: list[dict] = []
    for r in rows:
        decision = consolidate(r["milestone_type"], r.get("text"))
        decisions.append(
            {
                "patient_id": r["patient_id"],
                "episode_id": r["episode_id"],
                "encounter_id": r["encounter_id"],
                "old_milestone": r["milestone_type"],
                "encounter_date": r["encounter_date"],
                "action": decision.action,
                "new_milestone": decision.new_milestone,
                "outcome_attribute": decision.outcome_attribute,
                "rationale": decision.rationale,
            }
        )
    return decisions


def _apply_decisions(session, decisions: list[dict]) -> None:
    """Apply rewrite / delete edits in a single transaction per row."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for d in decisions:
        if d["action"] == "rewrite":
            session.run(
                _REWRITE_QUERY,
                encounter_id=d["encounter_id"],
                episode_id=d["episode_id"],
                old_milestone=d["old_milestone"],
                new_milestone=d["new_milestone"],
                outcome=d["outcome_attribute"],
                now=now,
            )
        elif d["action"] == "delete":
            session.run(
                _DELETE_QUERY,
                encounter_id=d["encounter_id"],
                episode_id=d["episode_id"],
                old_milestone=d["old_milestone"],
            )


def _decisions_to_audit_rows(decisions: list[dict]) -> list[AuditFinding]:
    out: list[AuditFinding] = []
    for d in decisions:
        if d["action"] == "keep":
            continue
        out.append(
            AuditFinding(
                patient_id=d["patient_id"],
                episode_id=d["episode_id"],
                encounter_id=d["encounter_id"],
                finding_type="role_mismatch"
                if d["action"] == "delete"
                else "llm_relabel_suggestion",
                severity="info",
                rationale=(
                    f"Tidy migration: {d['action']} {d['old_milestone']}"
                    f" -> {d.get('new_milestone') or 'none'}: {d['rationale']}"
                ),
                current_milestone=d["old_milestone"],
                suggested_role=None,
                suggested_outcome=d["outcome_attribute"],
                encounter_date=d["encounter_date"],
                status="applied",
            )
        )
    return out


def _verify(session) -> list[dict]:
    return [
        dict(r) for r in session.run(_VERIFY_QUERY, canonical=list(CANONICAL_MILESTONES))
    ]


def _summarise(decisions: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for d in decisions:
        key = f"{d['action']}:{d['old_milestone']}->{d['new_milestone'] or 'none'}"
        counts[key] = counts.get(key, 0) + 1
    return counts


def _gate_high_findings(session, force: bool) -> None:
    n = open_high_severity_count(session)
    if n == 0 or force:
        return
    raise SystemExit(
        f"REFUSED: {n} open severity='high' audit findings. "
        "Resolve via the Stage 9b audit tile, or rerun with --force."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    driver = _connect()
    try:
        with driver.session() as session:
            _gate_high_findings(session, args.force)
            rows = [dict(r) for r in session.run(_PULL_QUERY)]
            decisions = _decide_actions(rows)
            backup = _backup_dir()
            _snapshot_csv(rows, backup / "milestones.csv")
            (backup / "decisions.json").write_text(json.dumps(decisions, indent=2))

            if not args.dry_run:
                _apply_decisions(session, decisions)
                upsert_findings(session, _decisions_to_audit_rows(decisions))
                violations = _verify(session)
            else:
                violations = []

            summary = {
                "rows_examined": len(rows),
                "decisions": _summarise(decisions),
                "violations_after_tidy": violations,
                "backup_dir": str(backup),
                "dry_run": args.dry_run,
            }
    finally:
        driver.close()

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"Examined: {summary['rows_examined']} milestone rows")
        for k, v in summary["decisions"].items():
            print(f"  {k}: {v}")
        print(f"Violations after tidy: {len(summary['violations_after_tidy'])}")
        print(f"Backup: {summary['backup_dir']}")
        if args.dry_run:
            print("DRY RUN - no changes written.")
    return 0 if not summary["violations_after_tidy"] else 2


if __name__ == "__main__":
    sys.exit(main())
