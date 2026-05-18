#!/usr/bin/env python3
"""Consolidate two unreviewed ncda_detector EpisodeOfCare nodes into one.

Use this when the silver labeller / linker has split a single clinical
episode into two detector episodes (e.g. CLL + SLL, or 'Colorectal' lung-met
dx + 'Other' nodal-met dx) and the curator wants the encounters merged onto
one primary record.

What it does (in order, in a single Neo4j session):
    1. Snapshot full properties + linked encounters of BOTH episodes to a
       JSON backup file (always, even in dry-run).
    2. Optionally remove specific phantom encounter -> episode IS_PART_OF
       links from the primary AND/OR secondary (e.g. the diabetic-review
       admin email mis-classified as `treatment_started`).
    3. Move every remaining encounter from the secondary episode onto the
       primary, preserving the original `milestone_type`. Encounters already
       linked to the primary are left alone (MERGE no-op + DELETE secondary
       relation).
    4. Optionally patch primary properties: `site`, `cancer_type`,
       `end_date`, `diagnosis_date`. Leaves anything you don't pass alone.
    5. Detach delete the secondary episode node.

Safety:
    - DRY-RUN by default. Use --apply to actually mutate the graph.
    - Refuses to operate on episodes that are reviewed (review_verdict /
      curator_signoff / reviewed_by) or non-detector source.
    - Backup is written under artifacts/ncda_episode_backup/ as
      <stamp>_consolidate_<dryrun|pre_apply_backup>.json with full node
      properties and the IS_PART_OF graph for both episodes.
    - Logs a JSON summary of what changed when --apply is set.

Usage example (the 4940120139 case: Colorectal + Other -> Colorectal):
    python scripts/ncda/consolidate_detector_episode.py \\
        --primary a15665920aae3823 \\
        --secondary 67ed45d5240733d5 \\
        --drop-link-from-primary 34f16956-34e4-4cc8-a38b-da0938af815e \\
        --drop-link-from-secondary 34f16956-34e4-4cc8-a38b-da0938af815e \\
        --set-site lower_gi \\
        --set-end-date 2025-10-24 \\
        --reason "Colorectal+Other are same caecal-cancer episode (4940120139)"

    Add --apply to actually write.
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

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)


_FETCH_EPISODE_Q = """
MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE|HAS_EPISODE]->(e:EpisodeOfCare {episode_id: $eid})
OPTIONAL MATCH (enc:Encounter)-[r:IS_PART_OF]->(e)
WITH p, e,
     collect({encounter_id: enc.id,
              date: toString(enc.date),
              milestone_type: r.milestone_type}) AS encounters
RETURN
    coalesce(toString(p.id), toString(p.patient_id)) AS patient_id,
    e.episode_id AS episode_id,
    coalesce(e.source, '<null>') AS source,
    coalesce(e.review_verdict, '<null>') AS review_verdict,
    coalesce(e.status_source, '<null>') AS status_source,
    coalesce(e.reviewed_by, '<null>') AS reviewed_by,
    properties(e) AS all_properties,
    encounters
"""

_DROP_LINK_Q = """
MATCH (enc:Encounter {id: $encounter_id})-[r:IS_PART_OF]->(e:EpisodeOfCare {episode_id: $episode_id})
WITH r, r.milestone_type AS milestone_type
DELETE r
RETURN count(r) AS dropped, milestone_type
"""

_MOVE_ENCOUNTERS_Q = """
MATCH (sec:EpisodeOfCare {episode_id: $secondary_id})
MATCH (primary:EpisodeOfCare {episode_id: $primary_id})
MATCH (enc:Encounter)-[r:IS_PART_OF]->(sec)
MERGE (enc)-[r2:IS_PART_OF]->(primary)
ON CREATE SET r2.milestone_type = r.milestone_type,
              r2.linked_by = 'manual_consolidate',
              r2.linked_at = datetime(),
              r2.agent_reasoning = $reason
DELETE r
RETURN enc.id AS encounter_id, r2.milestone_type AS milestone_type
"""

_PATCH_PRIMARY_WITH_SECONDARY_Q = """
MATCH (e:EpisodeOfCare {episode_id: $primary_id})
SET e += $updates,
    e.updated_at = datetime(),
    e.consolidation_reasoning = $reason,
    e.consolidated_from = coalesce(e.consolidated_from, []) + [$secondary_id],
    e.consolidated_at = datetime()
RETURN e.episode_id AS episode_id, e.site AS site, e.cancer_type AS cancer_type,
       toString(e.end_date) AS end_date, toString(e.diagnosis_date) AS diagnosis_date
"""

_PATCH_PRIMARY_NO_SECONDARY_Q = """
MATCH (e:EpisodeOfCare {episode_id: $primary_id})
SET e += $updates,
    e.updated_at = datetime(),
    e.patch_reasoning = $reason,
    e.patched_at = datetime()
RETURN e.episode_id AS episode_id, e.site AS site, e.cancer_type AS cancer_type,
       toString(e.end_date) AS end_date, toString(e.diagnosis_date) AS diagnosis_date
"""

_DELETE_SECONDARY_Q = """
MATCH (e:EpisodeOfCare {episode_id: $secondary_id})
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


def _fetch_episode(session: Any, eid: str) -> dict[str, Any] | None:
    rows = list(session.run(_FETCH_EPISODE_Q, eid=eid))
    if not rows:
        return None
    return dict(rows[0])


def _is_safe_to_mutate(ep: dict[str, Any]) -> tuple[bool, str | None]:
    if ep["source"] != "ncda_detector":
        return False, f"source is '{ep['source']}', not 'ncda_detector'"
    if ep["review_verdict"] != "<null>":
        return False, f"has review_verdict='{ep['review_verdict']}'"
    if ep["status_source"] == "curator_signoff":
        return False, "status_source='curator_signoff'"
    if ep["reviewed_by"] != "<null>":
        return False, f"reviewed_by='{ep['reviewed_by']}'"
    return True, None


def write_backup(
    backup_dir: Path,
    primary: dict[str, Any],
    secondary: dict[str, Any],
    plan: dict[str, Any],
    suffix: str,
) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = _iso_now()
    path = backup_dir / f"{stamp}_consolidate_{suffix}.json"
    payload = {
        "generated_at": stamp,
        "plan": plan,
        "primary_before": primary,
        "secondary_before": secondary,
    }
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary", required=True, help="Episode_id to keep / merge into.")
    parser.add_argument(
        "--secondary",
        required=False,
        default=None,
        help=(
            "Episode_id to merge from then delete.  Optional — when omitted "
            "the script runs in 'patch primary only' mode (drop phantom "
            "links + update properties, no merge or delete)."
        ),
    )
    parser.add_argument(
        "--drop-link-from-primary",
        action="append",
        default=[],
        help="Encounter_id to unlink from PRIMARY (e.g. phantom treatment milestone). May repeat.",
    )
    parser.add_argument(
        "--drop-link-from-secondary",
        action="append",
        default=[],
        help="Encounter_id to unlink from SECONDARY before the move. May repeat.",
    )
    parser.add_argument("--set-site", type=str, default=None, help="New value for primary.site.")
    parser.add_argument("--set-cancer-type", type=str, default=None, help="New value for primary.cancer_type.")
    parser.add_argument("--set-end-date", type=str, default=None, help="New value for primary.end_date (YYYY-MM-DD).")
    parser.add_argument("--set-diagnosis-date", type=str, default=None, help="New value for primary.diagnosis_date.")
    parser.add_argument("--reason", required=True, help="Consolidation reason recorded on primary node.")
    parser.add_argument(
        "--backup-dir",
        type=str,
        default="artifacts/ncda_episode_backup",
        help="Where to write the pre-apply / dry-run backup JSON.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually mutate the graph. Without this flag we dry-run only.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON summary on stdout in addition to the human summary.",
    )
    return parser.parse_args()


def _build_updates_dict(args: argparse.Namespace) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    if args.set_site is not None:
        updates["site"] = args.set_site
    if args.set_cancer_type is not None:
        updates["cancer_type"] = args.set_cancer_type
    if args.set_end_date is not None:
        updates["end_date"] = args.set_end_date
    if args.set_diagnosis_date is not None:
        updates["diagnosis_date"] = args.set_diagnosis_date
    return updates


def main() -> int:
    args = parse_args()

    backup_dir = Path(args.backup_dir)
    if not backup_dir.is_absolute():
        backup_dir = ROOT / backup_dir

    driver = _connect()
    try:
        with driver.session() as session:
            primary = _fetch_episode(session, args.primary)
            secondary = _fetch_episode(session, args.secondary) if args.secondary else None
            if primary is None:
                raise SystemExit(f"ERROR: primary episode {args.primary} not found.")
            if args.secondary and secondary is None:
                raise SystemExit(f"ERROR: secondary episode {args.secondary} not found.")
            if secondary is not None and primary["patient_id"] != secondary["patient_id"]:
                raise SystemExit(
                    f"ERROR: primary belongs to patient {primary['patient_id']} but "
                    f"secondary belongs to {secondary['patient_id']}."
                )
            if secondary is None and args.drop_link_from_secondary:
                raise SystemExit(
                    "ERROR: --drop-link-from-secondary requires --secondary."
                )

            episodes_to_check = [("primary", primary)]
            if secondary is not None:
                episodes_to_check.append(("secondary", secondary))
            for label, ep in episodes_to_check:
                ok, why = _is_safe_to_mutate(ep)
                if not ok:
                    raise SystemExit(
                        f"ERROR: {label} episode {ep['episode_id']} is not safe to mutate: {why}"
                    )

            updates = _build_updates_dict(args)
            plan = {
                "primary_episode_id": args.primary,
                "secondary_episode_id": args.secondary,
                "patient_id": primary["patient_id"],
                "drop_links_from_primary": list(args.drop_link_from_primary),
                "drop_links_from_secondary": list(args.drop_link_from_secondary),
                "primary_property_updates": updates,
                "reason": args.reason,
                "secondary_encounter_count_before": (
                    len(secondary["encounters"]) if secondary is not None else 0
                ),
                "primary_encounter_count_before": len(primary["encounters"]),
                "mode": "merge_and_delete" if secondary is not None else "patch_only",
            }

            backup_path = write_backup(
                backup_dir,
                primary,
                secondary or {"episode_id": None, "encounters": [], "all_properties": {}},
                plan,
                suffix="pre_apply_backup" if args.apply else "dry_run",
            )

            mode = "APPLY" if args.apply else "DRY-RUN"
            mode_label = (
                "merge+delete" if secondary is not None else "patch-only (no secondary)"
            )
            print(f"=== Consolidate detector episodes ({mode}, {mode_label}) ===")
            print(f"Patient   : {primary['patient_id']}")
            print(f"Primary   : {args.primary}")
            print(f"Secondary : {args.secondary or '(none)'}")
            print(f"Reason    : {args.reason}")
            print()
            print("Primary encounters BEFORE:")
            for enc in primary["encounters"]:
                print(f"  - {enc['encounter_id']}  date={enc['date']}  milestone={enc['milestone_type']}")
            print()
            if secondary is not None:
                print("Secondary encounters BEFORE:")
                for enc in secondary["encounters"]:
                    print(f"  - {enc['encounter_id']}  date={enc['date']}  milestone={enc['milestone_type']}")
                print()
            print(f"Drop links from PRIMARY    : {plan['drop_links_from_primary']}")
            print(f"Drop links from SECONDARY  : {plan['drop_links_from_secondary']}")
            print(f"Primary property updates   : {updates}")
            print(f"Backup written: {backup_path}")

            mutation_log: dict[str, Any] = {}
            if args.apply:
                print()
                print("Applying mutations...")
                # 1. Drop phantom links first.
                drop_results: list[dict[str, Any]] = []
                for enc_id in args.drop_link_from_primary:
                    res = session.run(
                        _DROP_LINK_Q, encounter_id=enc_id, episode_id=args.primary
                    ).single()
                    drop_results.append(
                        {
                            "side": "primary",
                            "encounter_id": enc_id,
                            "episode_id": args.primary,
                            "dropped": res["dropped"] if res else 0,
                            "milestone_type": res["milestone_type"] if res else None,
                        }
                    )
                for enc_id in args.drop_link_from_secondary:
                    res = session.run(
                        _DROP_LINK_Q, encounter_id=enc_id, episode_id=args.secondary
                    ).single()
                    drop_results.append(
                        {
                            "side": "secondary",
                            "encounter_id": enc_id,
                            "episode_id": args.secondary,
                            "dropped": res["dropped"] if res else 0,
                            "milestone_type": res["milestone_type"] if res else None,
                        }
                    )
                mutation_log["dropped_links"] = drop_results

                # 2. Move remaining secondary encounters onto primary.
                if secondary is not None:
                    moved = [
                        dict(r)
                        for r in session.run(
                            _MOVE_ENCOUNTERS_Q,
                            primary_id=args.primary,
                            secondary_id=args.secondary,
                            reason=args.reason,
                        )
                    ]
                    mutation_log["moved_encounters"] = moved
                else:
                    mutation_log["moved_encounters"] = []

                # 3. Patch primary properties.
                if updates:
                    if secondary is not None:
                        patched = session.run(
                            _PATCH_PRIMARY_WITH_SECONDARY_Q,
                            primary_id=args.primary,
                            secondary_id=args.secondary,
                            updates=updates,
                            reason=args.reason,
                        ).single()
                    else:
                        patched = session.run(
                            _PATCH_PRIMARY_NO_SECONDARY_Q,
                            primary_id=args.primary,
                            updates=updates,
                            reason=args.reason,
                        ).single()
                    mutation_log["primary_after_patch"] = dict(patched) if patched else None
                else:
                    mutation_log["primary_after_patch"] = None

                # 4. Detach delete the secondary (only when secondary supplied).
                if secondary is not None:
                    deleted = session.run(
                        _DELETE_SECONDARY_Q, secondary_id=args.secondary
                    ).single()
                    mutation_log["secondary_deleted_count"] = (
                        deleted["deleted"] if deleted else 0
                    )
                else:
                    mutation_log["secondary_deleted_count"] = 0

                # 5. Verify.
                primary_after = _fetch_episode(session, args.primary)
                mutation_log["primary_after"] = primary_after
                print()
                print("Mutations done. Primary now has:")
                if primary_after:
                    print(
                        f"  site={primary_after['all_properties'].get('site')} "
                        f"cancer_type={primary_after['all_properties'].get('cancer_type')} "
                        f"end_date={primary_after['all_properties'].get('end_date')}"
                    )
                    print("  Encounters:")
                    for enc in primary_after["encounters"]:
                        print(
                            f"    - {enc['encounter_id']}  date={enc['date']}  "
                            f"milestone={enc['milestone_type']}"
                        )
                print()
                print(f"Secondary deleted: {mutation_log['secondary_deleted_count']}")

            if args.json:
                print()
                print(
                    json.dumps(
                        {
                            "mode": "apply" if args.apply else "dry_run",
                            "plan": plan,
                            "backup_path": str(backup_path),
                            "mutation_log": mutation_log,
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
