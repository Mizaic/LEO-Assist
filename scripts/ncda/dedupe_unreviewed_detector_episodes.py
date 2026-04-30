#!/usr/bin/env python3
"""Delete unreviewed ncda_detector EpisodeOfCare nodes that shadow a curator-
reviewed episode for the same patient and cancer type.

Background:
    The curator workflow can mark an EpisodeOfCare as reviewed via several
    independent flags - source='reviewed', status_source='curator_signoff',
    review_verdict IS NOT NULL, or reviewed_by IS NOT NULL. Older review
    surfaces (haiku-engine-v1, episode-detector-v2, manual entries) leave
    source=null and only set the curator metadata.

    The NCDA detector run-back script's reviewed-guard only matches by exact
    episode_id and source='reviewed', so it cannot prevent a fresh detector
    candidate from co-existing with a curator-confirmed episode that came from
    a different engine. This script cleans up that historical drift.

Match key:
    (patient_id, lower(cancer_type)) - reviewed episodes do not store `site`
    so we fall back to cancer_type. A detector episode is deleted only when
    a reviewed episode exists for the same patient and same cancer type.

Safety:
    - Default mode is dry-run. Use --apply to actually DETACH DELETE.
    - Every detector episode that would be deleted is snapshotted (full node
      properties + linked encounter ids) to artifacts/ncda_episode_backup/
      <timestamp>_dedupe_pre_apply_backup.json before any write.
    - Reviewed episodes are NEVER touched - we only delete nodes whose
      review_verdict, status_source, reviewed_by, and source-as-reviewed are
      all null/false.
    - --patient <id> restricts the operation to a single patient.

Usage:
    python scripts/ncda/dedupe_unreviewed_detector_episodes.py
    python scripts/ncda/dedupe_unreviewed_detector_episodes.py --apply
    python scripts/ncda/dedupe_unreviewed_detector_episodes.py --patient 6282779235
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
from neo4j import GraphDatabase  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)


_REVIEWED_EPISODES_QUERY = """
MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE|HAS_EPISODE]->(e:EpisodeOfCare)
WHERE e.review_verdict IS NOT NULL
   OR e.status_source = 'curator_signoff'
   OR e.reviewed_by IS NOT NULL
   OR e.source = 'reviewed'
RETURN
    coalesce(toString(p.id), toString(p.patient_id)) AS patient_id,
    e.episode_id AS episode_id,
    coalesce(e.source, '<null>') AS source,
    e.cancer_type AS cancer_type,
    e.referral_date AS referral_date,
    e.diagnosis_date AS diagnosis_date,
    e.end_date AS end_date,
    e.review_verdict AS review_verdict,
    e.status_source AS status_source,
    e.reviewed_by AS reviewed_by,
    toString(e.reviewed_at) AS reviewed_at,
    e.engine_version AS engine_version
"""

_DETECTOR_EPISODES_QUERY = """
MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE|HAS_EPISODE]->(e:EpisodeOfCare)
WHERE e.source = 'ncda_detector'
  AND e.review_verdict IS NULL
  AND (e.status_source IS NULL OR e.status_source <> 'curator_signoff')
  AND e.reviewed_by IS NULL
  AND coalesce(toString(p.id), toString(p.patient_id)) IN $patient_ids
OPTIONAL MATCH (enc:Encounter)-[:IS_PART_OF]->(e)
WITH p, e, collect(DISTINCT enc.id) AS encounter_ids
RETURN
    coalesce(toString(p.id), toString(p.patient_id)) AS patient_id,
    e.episode_id AS episode_id,
    e.cancer_type AS cancer_type,
    e.site AS site,
    e.referral_date AS referral_date,
    e.diagnosis_date AS diagnosis_date,
    e.end_date AS end_date,
    e.engine_version AS engine_version,
    toString(e.created_at) AS created_at,
    toString(e.updated_at) AS updated_at,
    properties(e) AS all_properties,
    encounter_ids
"""

# Look up specific override eids regardless of whether the patient has any
# reviewed episode in the graph.  Used when --also-delete-eids includes a
# detector episode for a patient that has no curator-reviewed episodes yet.
_DETECTOR_EPISODES_BY_EID_QUERY = """
MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE|HAS_EPISODE]->(e:EpisodeOfCare)
WHERE e.episode_id IN $episode_ids
  AND e.source = 'ncda_detector'
  AND e.review_verdict IS NULL
  AND (e.status_source IS NULL OR e.status_source <> 'curator_signoff')
  AND e.reviewed_by IS NULL
OPTIONAL MATCH (enc:Encounter)-[:IS_PART_OF]->(e)
WITH p, e, collect(DISTINCT enc.id) AS encounter_ids
RETURN
    coalesce(toString(p.id), toString(p.patient_id)) AS patient_id,
    e.episode_id AS episode_id,
    e.cancer_type AS cancer_type,
    e.site AS site,
    e.referral_date AS referral_date,
    e.diagnosis_date AS diagnosis_date,
    e.end_date AS end_date,
    e.engine_version AS engine_version,
    toString(e.created_at) AS created_at,
    toString(e.updated_at) AS updated_at,
    properties(e) AS all_properties,
    encounter_ids
"""

_DELETE_EPISODE_Q = """
MATCH (e:EpisodeOfCare {episode_id: $episode_id})
WHERE e.source = 'ncda_detector'
  AND e.review_verdict IS NULL
  AND (e.status_source IS NULL OR e.status_source <> 'curator_signoff')
  AND e.reviewed_by IS NULL
DETACH DELETE e
RETURN count(e) AS deleted
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


def _norm_type(value: str | None) -> str:
    return (value or "").strip().lower()


def build_deletion_plan(
    session: Any,
    patient_filter: str | None = None,
    also_delete_eids: set[str] | None = None,
) -> dict[str, Any]:
    """Return a per-(patient, cancer_type) deletion plan.

    Args:
        session: Active Neo4j session.
        patient_filter: Optional single patient_id to scope the operation.
        also_delete_eids: Optional set of detector episode_ids that should be
            deleted even when no same-cancer-type reviewed episode matches.
            Used for one-off curator overrides (e.g. confirmed false positives
            for cancer types the curator has not yet formally reviewed).
    """
    also_delete_eids = also_delete_eids or set()

    reviewed_rows = [dict(r) for r in session.run(_REVIEWED_EPISODES_QUERY)]
    if patient_filter:
        reviewed_rows = [r for r in reviewed_rows if r["patient_id"] == patient_filter]

    reviewed_index: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    reviewed_patient_types: dict[str, set[str]] = defaultdict(set)
    for r in reviewed_rows:
        if not r["patient_id"]:
            continue
        key = (r["patient_id"], _norm_type(r["cancer_type"]))
        reviewed_index[key].append(r)
        reviewed_patient_types[r["patient_id"]].add(_norm_type(r["cancer_type"]))

    patient_ids = sorted(reviewed_patient_types.keys())

    detector_rows: list[dict[str, Any]] = []
    if patient_ids:
        detector_rows = [
            dict(r)
            for r in session.run(_DETECTOR_EPISODES_QUERY, patient_ids=patient_ids)
        ]

    # Pull any override-eid episodes that were not picked up via the
    # reviewed-patient scope (e.g. patient has no reviewed episode at all).
    seen_eids = {d["episode_id"] for d in detector_rows}
    missing_override_eids = sorted(also_delete_eids - seen_eids)
    if missing_override_eids:
        extra = [
            dict(r)
            for r in session.run(
                _DETECTOR_EPISODES_BY_EID_QUERY,
                episode_ids=missing_override_eids,
            )
        ]
        detector_rows.extend(extra)
        if patient_filter:
            detector_rows = [d for d in detector_rows if d["patient_id"] == patient_filter]

    if not detector_rows:
        return {
            "reviewed_episode_count": len(reviewed_rows),
            "candidate_patient_count": len(patient_ids),
            "to_delete": [],
            "to_keep_unmatched": [],
            "reviewed_index": {},
            "override_eids_requested": sorted(also_delete_eids),
            "override_eids_matched": [],
            "override_eids_unmatched": sorted(also_delete_eids),
        }

    to_delete: list[dict[str, Any]] = []
    to_keep: list[dict[str, Any]] = []
    override_matched: set[str] = set()
    for d in detector_rows:
        key = (d["patient_id"], _norm_type(d["cancer_type"]))
        matches = reviewed_index.get(key, [])
        is_override = d["episode_id"] in also_delete_eids
        if is_override:
            override_matched.add(d["episode_id"])
        if matches or is_override:
            to_delete.append(
                {
                    "patient_id": d["patient_id"],
                    "detector_episode_id": d["episode_id"],
                    "detector_cancer_type": d["cancer_type"],
                    "detector_site": d["site"],
                    "detector_referral_date": d["referral_date"],
                    "detector_diagnosis_date": d["diagnosis_date"],
                    "detector_end_date": d["end_date"],
                    "detector_created_at": d["created_at"],
                    "linked_encounter_count": len(d["encounter_ids"] or []),
                    "delete_reason": (
                        "curator_override"
                        if is_override and not matches
                        else (
                            "shadows_reviewed_and_curator_override"
                            if is_override and matches
                            else "shadows_reviewed_same_cancer_type"
                        )
                    ),
                    "matched_reviewed_episodes": [
                        {
                            "episode_id": m["episode_id"],
                            "engine_version": m["engine_version"],
                            "review_verdict": m["review_verdict"],
                            "reviewed_by": m["reviewed_by"],
                            "reviewed_at": m["reviewed_at"],
                            "referral_date": m["referral_date"],
                            "end_date": m["end_date"],
                        }
                        for m in matches
                    ],
                    "_full_properties": d["all_properties"],
                    "_encounter_ids": d["encounter_ids"],
                }
            )
        else:
            to_keep.append(
                {
                    "patient_id": d["patient_id"],
                    "detector_episode_id": d["episode_id"],
                    "detector_cancer_type": d["cancer_type"],
                    "detector_site": d["site"],
                    "reason": "no_reviewed_episode_for_this_cancer_type",
                    "patient_reviewed_cancer_types": sorted(
                        reviewed_patient_types[d["patient_id"]]
                    ),
                }
            )

    plan_extra = {
        "override_eids_requested": sorted(also_delete_eids),
        "override_eids_matched": sorted(override_matched),
        "override_eids_unmatched": sorted(also_delete_eids - override_matched),
    }

    return {
        "reviewed_episode_count": len(reviewed_rows),
        "candidate_patient_count": len(patient_ids),
        "to_delete": to_delete,
        "to_keep_unmatched": to_keep,
        "reviewed_index": {
            f"{pid}|{ctype}": len(eps)
            for (pid, ctype), eps in reviewed_index.items()
        },
        **plan_extra,
    }


def write_backup(plan: dict[str, Any], backup_dir: Path, suffix: str) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = _iso_now()
    path = backup_dir / f"{stamp}_dedupe_{suffix}.json"
    payload = {
        "generated_at": stamp,
        "reviewed_episode_count": plan["reviewed_episode_count"],
        "candidate_patient_count": plan["candidate_patient_count"],
        "delete_count": len(plan["to_delete"]),
        "keep_count": len(plan["to_keep_unmatched"]),
        "override_eids_requested": plan.get("override_eids_requested", []),
        "override_eids_matched": plan.get("override_eids_matched", []),
        "override_eids_unmatched": plan.get("override_eids_unmatched", []),
        "to_delete": plan["to_delete"],
        "to_keep_unmatched": plan["to_keep_unmatched"],
    }
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def apply_deletions(session: Any, to_delete: list[dict[str, Any]]) -> dict[str, int]:
    deleted = 0
    skipped = 0
    for item in to_delete:
        result = session.run(
            _DELETE_EPISODE_Q,
            episode_id=item["detector_episode_id"],
        ).single()
        if result and result["deleted"] > 0:
            deleted += 1
        else:
            skipped += 1
    return {"deleted": deleted, "skipped": skipped}


def print_human_summary(plan: dict[str, Any], dry_run: bool) -> None:
    mode = "DRY-RUN" if dry_run else "APPLY"
    delete_items = plan["to_delete"]
    keep_items = plan["to_keep_unmatched"]
    print(f"=== Detector / reviewed dedupe ({mode}) ===")
    print(f"Reviewed episodes scanned : {plan['reviewed_episode_count']}")
    print(f"Patients with reviewed eps: {plan['candidate_patient_count']}")
    print(f"Detector episodes to DELETE: {len(delete_items)}")
    print(f"Detector episodes to KEEP  : {len(keep_items)} (no reviewed match for this cancer type)")
    if plan.get("override_eids_requested"):
        print(f"Curator override eids requested: {plan['override_eids_requested']}")
        print(f"  matched : {plan.get('override_eids_matched', [])}")
        if plan.get("override_eids_unmatched"):
            print(f"  UNMATCHED (no detector episode found) : {plan['override_eids_unmatched']}")
    print()
    if delete_items:
        print("--- Deletion plan ---")
        for d in delete_items:
            matched = ", ".join(m["episode_id"] for m in d["matched_reviewed_episodes"])
            target = (
                f"shadows reviewed [{matched}]"
                if matched
                else "curator override (false-positive triage)"
            )
            print(
                f"  patient={d['patient_id']:<10} "
                f"cancer={(d['detector_cancer_type'] or '?'):<12} "
                f"site={(d['detector_site'] or '?'):<14} "
                f"detector_eid={d['detector_episode_id']} "
                f"linked_encounters={d['linked_encounter_count']} "
                f"reason={d.get('delete_reason', '?')} "
                f"-> {target}"
            )
        print()
    if keep_items:
        print("--- Kept (different cancer type, curator has not reviewed this site yet) ---")
        for k in keep_items:
            print(
                f"  patient={k['patient_id']:<10} "
                f"detector cancer={k['detector_cancer_type']:<12} "
                f"site={(k['detector_site'] or '?'):<14} "
                f"detector_eid={k['detector_episode_id']} "
                f"reviewed types for patient={k['patient_reviewed_cancer_types']}"
            )
        print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually DETACH DELETE the matching detector episodes (default: dry-run).",
    )
    parser.add_argument(
        "--patient",
        type=str,
        default=None,
        help="Limit the operation to a single patient_id.",
    )
    parser.add_argument(
        "--backup-dir",
        type=str,
        default="artifacts/ncda_episode_backup",
        help="Where to write the pre-apply / dry-run backup JSON.",
    )
    parser.add_argument(
        "--also-delete-eids",
        type=str,
        default="",
        help=(
            "Comma-separated detector episode_ids that should be deleted even "
            "when no same-cancer-type reviewed episode matches. Use this for "
            "curator-confirmed false positives (e.g. detector raised a phantom "
            "Lymphoma for a patient whose only reviewed episode is Breast)."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the plan as JSON to stdout in addition to the human summary.",
    )
    args = parser.parse_args()

    also_delete_eids = {
        eid.strip() for eid in args.also_delete_eids.split(",") if eid.strip()
    }

    backup_dir = Path(args.backup_dir)
    if not backup_dir.is_absolute():
        backup_dir = ROOT / backup_dir

    driver = _connect()
    try:
        with driver.session() as session:
            plan = build_deletion_plan(
                session,
                patient_filter=args.patient,
                also_delete_eids=also_delete_eids,
            )
            backup_path = write_backup(
                plan,
                backup_dir,
                suffix="dry_run" if not args.apply else "pre_apply_backup",
            )

            print_human_summary(plan, dry_run=not args.apply)
            print(f"Backup written: {backup_path}")

            apply_summary: dict[str, int] | None = None
            if args.apply and plan["to_delete"]:
                print()
                print("Applying deletions...")
                apply_summary = apply_deletions(session, plan["to_delete"])
                print(f"Deleted: {apply_summary['deleted']}")
                print(f"Skipped (already gone or reviewed): {apply_summary['skipped']}")

            if args.json:
                print()
                print(json.dumps(
                    {
                        "mode": "apply" if args.apply else "dry_run",
                        "patient_filter": args.patient,
                        "backup_path": str(backup_path),
                        "plan_summary": {
                            "reviewed_episode_count": plan["reviewed_episode_count"],
                            "candidate_patient_count": plan["candidate_patient_count"],
                            "delete_count": len(plan["to_delete"]),
                            "keep_count": len(plan["to_keep_unmatched"]),
                        },
                        "apply_summary": apply_summary,
                    },
                    indent=2,
                ))
    finally:
        driver.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
