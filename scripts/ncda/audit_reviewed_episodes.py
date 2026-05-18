#!/usr/bin/env python3
"""Stage 1 - Pre-flight audit of reviewed EpisodeOfCare records.

Walks every reviewed EpisodeOfCare via :IS_PART_OF, applies the deterministic
audit rules in services.analysis_worker.app.ncda_detector.audit_rules, and
optionally a curation-time LLM relabel pass. Findings persist to Neo4j as
:NCDALabelAudit nodes so the Stage 9b reviewer tile can act on them.

Stage 2 tidy migration BLOCKS on open severity='high' findings.

Usage:
    python scripts/ncda/audit_reviewed_episodes.py
    python scripts/ncda/audit_reviewed_episodes.py --json
    python scripts/ncda/audit_reviewed_episodes.py --limit-patients 5
    python scripts/ncda/audit_reviewed_episodes.py --enable-llm
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
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
    upsert_findings,
)
from services.analysis_worker.app.ncda_detector.audit_rules import (  # noqa: E402
    MilestonedEncounter,
    find_duplicate_roles,
    find_out_of_sequence,
    find_role_mismatches,
)

_PULL_QUERY = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(enc:Encounter)-[r:IS_PART_OF]->(e:EpisodeOfCare)
WHERE e.reviewed_at IS NOT NULL
  AND r.milestone_type IN [
      'referral','referral_sent','first_seen','diagnosis_confirmed',
      'treatment_started','benign_closure','outcome_letter'
  ]
RETURN
    coalesce(toString(p.id), toString(p.patient_id)) AS patient_id,
    e.id AS episode_id,
    e.cancer_type AS cancer_type,
    enc.id AS encounter_id,
    r.milestone_type AS milestone_type,
    toString(enc.date) AS encounter_date,
    enc.flags AS flags,
    enc.text AS text
ORDER BY patient_id, episode_id, encounter_date
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


def _pull_milestoned_encounters(session, limit_patients: int | None) -> list[dict]:
    rows = list(session.run(_PULL_QUERY))
    if limit_patients is None:
        return [dict(r) for r in rows]
    seen: dict[str, int] = {}
    out: list[dict] = []
    for r in rows:
        pid = r["patient_id"]
        seen[pid] = seen.get(pid, len(seen) + 1)
        if seen[pid] > limit_patients:
            continue
        out.append(dict(r))
    return out


def _group_by_episode(rows: list[dict]) -> dict[tuple[str, str | None], list[dict]]:
    bucket: dict[tuple[str, str | None], list[dict]] = defaultdict(list)
    for r in rows:
        bucket[(r["patient_id"], r["episode_id"])].append(r)
    return bucket


def _row_to_milestoned_encounter(r: dict) -> MilestonedEncounter:
    return MilestonedEncounter(
        patient_id=r["patient_id"],
        episode_id=r["episode_id"],
        encounter_id=r["encounter_id"],
        milestone_type=r["milestone_type"],
        encounter_date=r["encounter_date"],
        text=r["text"],
        flags=r["flags"],
    )


def run_deterministic_audit(rows: list[dict]) -> list[AuditFinding]:
    """Apply role-mismatch / out-of-sequence / duplicate-role checks."""
    findings: list[AuditFinding] = []
    encounters = [_row_to_milestoned_encounter(r) for r in rows]
    findings.extend(find_role_mismatches(encounters))
    for (_pid, _eid), episode_rows in _group_by_episode(rows).items():
        episode_encs = [_row_to_milestoned_encounter(r) for r in episode_rows]
        findings.extend(find_out_of_sequence(episode_encs))
        findings.extend(find_duplicate_roles(episode_encs))
    return findings


def run_llm_relabel(rows: list[dict]) -> list[AuditFinding]:
    """Optional LLM-at-curation pass.

    v0 ships a no-op stub. Replace with an Azure OpenAI / vLLM client call
    that takes (text, flags, current_milestone) and returns a structured
    relabel-suggestion. Findings of type 'llm_relabel_suggestion' write
    severity='low' so they never block tidy.
    """
    return []


def _emit_summary(findings: list[AuditFinding], as_json: bool) -> None:
    counts: dict[str, dict[str, int]] = {}
    for f in findings:
        counts.setdefault(f.finding_type, {})
        counts[f.finding_type][f.severity] = (
            counts[f.finding_type].get(f.severity, 0) + 1
        )
    if as_json:
        print(json.dumps({"counts": counts, "total": len(findings)}, indent=2))
        return
    print(f"Audit complete: {len(findings)} findings")
    for ftype, severities in counts.items():
        breakdown = ", ".join(f"{k}={v}" for k, v in sorted(severities.items()))
        print(f"  {ftype}: {breakdown}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit-patients", type=int, default=None)
    parser.add_argument("--enable-llm", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--dry-run", action="store_true", help="Compute but do not write findings."
    )
    args = parser.parse_args()

    driver = _connect()
    try:
        with driver.session() as session:
            rows = _pull_milestoned_encounters(session, args.limit_patients)
            findings = run_deterministic_audit(rows)
            if args.enable_llm:
                findings.extend(run_llm_relabel(rows))
            if not args.dry_run:
                upsert_findings(session, findings)
    finally:
        driver.close()

    _emit_summary(findings, args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
