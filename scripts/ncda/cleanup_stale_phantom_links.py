#!/usr/bin/env python3
"""Drop stale IS_PART_OF links between encounters and ncda_detector episodes
that the current silver labeller / linker would no longer produce.

Two operating modes (can be combined in one run):

    --auto-treatment
        Scan every unreviewed ncda_detector EpisodeOfCare and re-label every
        encounter currently linked as ``treatment_started``.  When the
        current silver labeller does NOT return ``role='treatment'`` for that
        encounter (e.g. XaIg6 'Comment note' admin emails, XaXfG pharmacist
        drug-review templates, SPA Communication Templates), the IS_PART_OF
        relationship is proposed for deletion.  The encounter node itself is
        never touched.

    --drops ENCID:EPID[:milestone],...
        Explicit list of (encounter_id, episode_id [, optional milestone])
        triplets to drop.  Use for one-off curator overrides such as
        collapsing a pair of same-day duplicate FTR encounters that the
        new linker collapse rule will catch on next detector run, but that
        already exist as historical IS_PART_OF in the graph.

Safety:
    - DRY-RUN by default.  Use ``--apply`` to actually DELETE the
      relationships.
    - Refuses to mutate links on reviewed episodes (any of:
      review_verdict / status_source='curator_signoff' / reviewed_by /
      source='reviewed').
    - Backs up the full plan plus encounter texts to
      artifacts/ncda_episode_backup/<stamp>_phantom_links_<dryrun|pre_apply_backup>.json.

Usage:
    python scripts/ncda/cleanup_stale_phantom_links.py --auto-treatment
    python scripts/ncda/cleanup_stale_phantom_links.py --auto-treatment --apply
    python scripts/ncda/cleanup_stale_phantom_links.py \\
        --drops 74f306ca-4686-4e77-ad80-1a653e3b2915:a15665920aae3823:referral
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
from neo4j import GraphDatabase  # noqa: E402

from services.analysis_worker.app.ncda_detector.silver_labeller import (  # noqa: E402
    deterministic_label,
)

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)


_SCAN_TREATMENT_LINKS_QUERY = """
MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE|HAS_EPISODE]->(e:EpisodeOfCare)
WHERE e.source = 'ncda_detector'
  AND e.review_verdict IS NULL
  AND (e.status_source IS NULL OR e.status_source <> 'curator_signoff')
  AND e.reviewed_by IS NULL
MATCH (enc:Encounter)-[r:IS_PART_OF]->(e)
WHERE r.milestone_type = 'treatment_started'
RETURN
    coalesce(toString(p.id), toString(p.patient_id)) AS patient_id,
    e.episode_id AS episode_id,
    e.cancer_type AS cancer_type,
    e.site AS site,
    enc.id AS encounter_id,
    toString(enc.date) AS encounter_date,
    enc.text AS encounter_text,
    r.milestone_type AS milestone_type
"""

_FETCH_LINK_QUERY = """
MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE|HAS_EPISODE]->(e:EpisodeOfCare)
WHERE e.episode_id = $episode_id
  AND e.source = 'ncda_detector'
  AND e.review_verdict IS NULL
  AND (e.status_source IS NULL OR e.status_source <> 'curator_signoff')
  AND e.reviewed_by IS NULL
MATCH (enc:Encounter {id: $encounter_id})-[r:IS_PART_OF]->(e)
RETURN
    coalesce(toString(p.id), toString(p.patient_id)) AS patient_id,
    e.episode_id AS episode_id,
    e.cancer_type AS cancer_type,
    e.site AS site,
    enc.id AS encounter_id,
    toString(enc.date) AS encounter_date,
    enc.text AS encounter_text,
    r.milestone_type AS milestone_type
"""

_DROP_LINK_QUERY = """
MATCH (enc:Encounter {id: $encounter_id})-[r:IS_PART_OF]->(e:EpisodeOfCare {episode_id: $episode_id})
WHERE e.source = 'ncda_detector'
  AND e.review_verdict IS NULL
  AND (e.status_source IS NULL OR e.status_source <> 'curator_signoff')
  AND e.reviewed_by IS NULL
WITH r, r.milestone_type AS milestone_type
DELETE r
RETURN count(r) AS dropped, milestone_type
"""


def _connect():
    uri = os.environ.get("NEO4J_PATIENT_URI", "").strip() or os.environ.get("NEO4J_URI", "").strip()
    user = os.environ.get("NEO4J_PATIENT_USER", "").strip() or os.environ.get("NEO4J_USER", "").strip()
    pw = os.environ.get("NEO4J_PATIENT_PASSWORD", "").strip() or os.environ.get("NEO4J_PASSWORD", "").strip()
    if not all([uri, user, pw]):
        raise SystemExit("ERROR: NEO4J credentials missing.")
    return GraphDatabase.driver(uri, auth=(user, pw))


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _relabel(row: dict[str, Any]) -> dict[str, Any]:
    """Re-run the current deterministic silver labeller on this encounter."""
    label = deterministic_label(
        patient_id=row.get("patient_id") or "",
        encounter_id=row["encounter_id"],
        encounter_date=row.get("encounter_date"),
        text=row.get("encounter_text") or "",
        flags=None,
    )
    return {
        "current_role": label.role,
        "current_outcome": label.outcome,
        "current_rationale": label.rationale,
        "site_hint": label.site_hint,
    }


def scan_phantom_treatments(session: Any, patient_filter: str | None = None) -> list[dict[str, Any]]:
    """Scan all detector episodes' treatment_started links and propose drops.

    Returns one row per (encounter, episode) IS_PART_OF link whose current
    silver label is no longer ``treatment``.  Each row includes the snippet
    of encounter text and the new label rationale so the curator can audit.
    """
    rows = [dict(r) for r in session.run(_SCAN_TREATMENT_LINKS_QUERY)]
    if patient_filter:
        rows = [r for r in rows if r["patient_id"] == patient_filter]
    proposals: list[dict[str, Any]] = []
    for row in rows:
        relabel = _relabel(row)
        if relabel["current_role"] != "treatment":
            text = (row.get("encounter_text") or "").strip()
            proposals.append(
                {
                    "patient_id": row["patient_id"],
                    "episode_id": row["episode_id"],
                    "cancer_type": row["cancer_type"],
                    "site": row["site"],
                    "encounter_id": row["encounter_id"],
                    "encounter_date": row["encounter_date"],
                    "milestone_type": row["milestone_type"],
                    "current_label_role": relabel["current_role"],
                    "current_label_outcome": relabel["current_outcome"],
                    "current_label_rationale": relabel["current_rationale"],
                    "encounter_text_snippet": text[:280],
                    "drop_reason": "current_labeller_returns_role_not_treatment",
                }
            )
    return proposals


def parse_drops(raw: str) -> list[dict[str, str]]:
    """Parse comma-separated ENCID:EPID[:milestone] triplets."""
    out: list[dict[str, str]] = []
    if not raw.strip():
        return out
    for piece in raw.split(","):
        piece = piece.strip()
        if not piece:
            continue
        parts = piece.split(":")
        if len(parts) < 2:
            raise SystemExit(
                f"ERROR: --drops entry must be ENCID:EPID[:milestone], got '{piece}'"
            )
        item = {
            "encounter_id": parts[0].strip(),
            "episode_id": parts[1].strip(),
        }
        if len(parts) >= 3 and parts[2].strip():
            item["expected_milestone_type"] = parts[2].strip()
        out.append(item)
    return out


def expand_manual_drops(session: Any, drops: list[dict[str, str]]) -> list[dict[str, Any]]:
    expanded: list[dict[str, Any]] = []
    for d in drops:
        rows = list(
            session.run(
                _FETCH_LINK_QUERY,
                encounter_id=d["encounter_id"],
                episode_id=d["episode_id"],
            )
        )
        if not rows:
            expanded.append(
                {
                    "patient_id": None,
                    "episode_id": d["episode_id"],
                    "encounter_id": d["encounter_id"],
                    "milestone_type": None,
                    "drop_reason": "manual_override_NOT_FOUND_OR_PROTECTED",
                    "current_label_role": None,
                }
            )
            continue
        row = dict(rows[0])
        relabel = _relabel(row)
        text = (row.get("encounter_text") or "").strip()
        item = {
            "patient_id": row["patient_id"],
            "episode_id": row["episode_id"],
            "cancer_type": row["cancer_type"],
            "site": row["site"],
            "encounter_id": row["encounter_id"],
            "encounter_date": row["encounter_date"],
            "milestone_type": row["milestone_type"],
            "current_label_role": relabel["current_role"],
            "current_label_outcome": relabel["current_outcome"],
            "current_label_rationale": relabel["current_rationale"],
            "encounter_text_snippet": text[:280],
            "drop_reason": "manual_override",
        }
        if (
            "expected_milestone_type" in d
            and d["expected_milestone_type"] != row["milestone_type"]
        ):
            item["drop_reason"] = (
                f"manual_override_milestone_mismatch_expected_"
                f"{d['expected_milestone_type']}_got_{row['milestone_type']}"
            )
        expanded.append(item)
    return expanded


def write_backup(plan: dict[str, Any], backup_dir: Path, suffix: str) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = _iso_now()
    path = backup_dir / f"{stamp}_phantom_links_{suffix}.json"
    payload = {
        "generated_at": stamp,
        "auto_treatment_proposals": plan.get("auto_treatment_proposals", []),
        "manual_drops": plan.get("manual_drops", []),
        "auto_count": len(plan.get("auto_treatment_proposals", [])),
        "manual_count": len(plan.get("manual_drops", [])),
    }
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def apply_drops(session: Any, items: list[dict[str, Any]]) -> dict[str, int]:
    dropped = 0
    skipped = 0
    for item in items:
        if not item.get("encounter_id") or not item.get("episode_id"):
            skipped += 1
            continue
        if item.get("drop_reason", "").startswith("manual_override_NOT_FOUND"):
            skipped += 1
            continue
        result = session.run(
            _DROP_LINK_QUERY,
            encounter_id=item["encounter_id"],
            episode_id=item["episode_id"],
        ).single()
        if result and result["dropped"] > 0:
            dropped += 1
        else:
            skipped += 1
    return {"dropped": dropped, "skipped": skipped}


def print_human_summary(plan: dict[str, Any], dry_run: bool) -> None:
    auto = plan.get("auto_treatment_proposals", [])
    manual = plan.get("manual_drops", [])
    mode = "DRY-RUN" if dry_run else "APPLY"
    print(f"=== Cleanup stale phantom IS_PART_OF links ({mode}) ===")
    print(f"Auto-treatment drops proposed : {len(auto)}")
    print(f"Manual drops requested        : {len(manual)}")
    print()
    if auto:
        print("--- Auto-treatment phantom drops ---")
        for item in auto:
            text = (item.get("encounter_text_snippet") or "").replace("\n", " ")
            print(
                f"  patient={item.get('patient_id'):<10} "
                f"episode={item.get('episode_id')} "
                f"enc={item.get('encounter_id')} "
                f"date={item.get('encounter_date')} "
                f"current_role={item.get('current_label_role')} "
                f"-> drop {item.get('milestone_type')}"
            )
            print(f"    text='{text[:160]}'")
        print()
    if manual:
        print("--- Manual override drops ---")
        for item in manual:
            text = (item.get("encounter_text_snippet") or "").replace("\n", " ")
            print(
                f"  patient={item.get('patient_id') or '?':<10} "
                f"episode={item.get('episode_id')} "
                f"enc={item.get('encounter_id')} "
                f"current_milestone={item.get('milestone_type')} "
                f"current_role={item.get('current_label_role')} "
                f"reason={item.get('drop_reason')}"
            )
            if text:
                print(f"    text='{text[:160]}'")
        print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--auto-treatment",
        action="store_true",
        help="Auto-discover phantom treatment_started links to drop.",
    )
    parser.add_argument(
        "--drops",
        type=str,
        default="",
        help="Comma-separated ENCID:EPID[:milestone] triplets for manual drops.",
    )
    parser.add_argument(
        "--patient",
        type=str,
        default=None,
        help="Limit auto-discovery to a single patient_id.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually DELETE the IS_PART_OF relationships (default: dry-run).",
    )
    parser.add_argument(
        "--backup-dir",
        type=str,
        default="artifacts/ncda_episode_backup",
        help="Where to write the pre-apply / dry-run backup JSON.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a JSON summary on stdout in addition to the human summary.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.auto_treatment and not args.drops:
        raise SystemExit(
            "ERROR: provide at least one of --auto-treatment or --drops."
        )

    backup_dir = Path(args.backup_dir)
    if not backup_dir.is_absolute():
        backup_dir = ROOT / backup_dir

    manual_specs = parse_drops(args.drops)

    driver = _connect()
    try:
        with driver.session() as session:
            auto_proposals: list[dict[str, Any]] = []
            if args.auto_treatment:
                auto_proposals = scan_phantom_treatments(
                    session, patient_filter=args.patient
                )
            manual_drops: list[dict[str, Any]] = []
            if manual_specs:
                manual_drops = expand_manual_drops(session, manual_specs)

            plan = {
                "auto_treatment_proposals": auto_proposals,
                "manual_drops": manual_drops,
            }

            backup_path = write_backup(
                plan,
                backup_dir,
                suffix="pre_apply_backup" if args.apply else "dry_run",
            )

            print_human_summary(plan, dry_run=not args.apply)
            print(f"Backup written: {backup_path}")

            apply_summary: dict[str, int] | None = None
            if args.apply:
                items = auto_proposals + manual_drops
                if items:
                    print()
                    print("Applying drops...")
                    apply_summary = apply_drops(session, items)
                    print(f"Dropped: {apply_summary['dropped']}")
                    print(f"Skipped: {apply_summary['skipped']}")

            if args.json:
                print()
                print(
                    json.dumps(
                        {
                            "mode": "apply" if args.apply else "dry_run",
                            "patient_filter": args.patient,
                            "backup_path": str(backup_path),
                            "auto_count": len(auto_proposals),
                            "manual_count": len(manual_drops),
                            "apply_summary": apply_summary,
                        },
                        indent=2,
                        default=str,
                    )
                )
    finally:
        driver.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
